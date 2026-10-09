"""FastAPI 앱 — 팩 로드 · 세션 · 오류 핸들러 · 라우터 자동 include(코어 15 → 팩) · 공통 화면 · /health · after_commit 큐.

**개발자는 이 파일을 만지지 않는다.** 라우터는 `packs.router_modules()` 순서로 자동 include 한다 — `routers/<모듈>.py` 의 `router`.
라우터가 아직 등록하지 않은 화면 GET 경로는 `_placeholder.html` 로 **HTTP 200** + "미구현 — 담당 개발N" + 계약 문장을 낸다.
화면이 없다는 사실을 숨기지 않는다. 라우터가 그 경로를 등록하면 placeholder 는 저절로 빠진다. 공통 화면도 같다 —
`routers/home.py` 가 `/` 를 등록하면 여기의 메인은 빠진다 (D-21).
오류 계약은 `contracts/api-contract.md`: IntegrityError/DataError → 422 · HookError → 422 hook_rejected · DbUnavailable → 503.
"""

from __future__ import annotations

import importlib
import logging
import secrets
from pathlib import Path
from urllib.parse import quote

import psycopg
from fastapi import APIRouter, Depends, FastAPI, Form, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from ..db import conn
from . import auth, contracts, nav, packs, rbac, templating
from .packs import t
from .settings import get_settings
from .templating import STATIC_DIR, render
from .util import audit, http
from .util.http import HookError

log = logging.getLogger("mescore")
ROUTERS_DIR = Path(__file__).resolve().parent / "routers"


def _placeholder_routes() -> list:
    """화면 51(+팩) 의 GET 경로를 placeholder 로 만든다. RBAC 는 그대로 탄다 — 미로그인 401 · 권한 없음 403."""
    router = APIRouter()

    def make(screen_id: str):
        def view(request: Request, user=rbac.require_screen(screen_id)):
            return templating.placeholder(request, screen_id)

        view.__name__ = f"placeholder_{screen_id.replace('-', '_').lower()}"
        return view

    for s in nav.SCREENS:
        router.add_api_route(s.path, make(s.screen_id), methods=["GET"], include_in_schema=False)
    return list(router.routes)


def _module_file(module: str) -> Path | None:
    """라우터 모듈의 파일 경로 — 코어는 app/routers/<m>.py, 팩은 packs/<팩>/routers/<m>.py."""
    parts = module.split(".")
    if module.startswith("mescore.app.routers."):
        return ROUTERS_DIR / f"{parts[-1]}.py"
    pack = packs.current()
    if pack.dir is not None:
        return pack.dir / "routers" / f"{parts[-1]}.py"
    return None


def create_app() -> FastAPI:
    s = get_settings()
    pack = packs.current()                 # 병합 규칙 위반이면 여기서 PackError — 조용히 기동하지 않는다
    contracts.functions()                  # 계약 표가 깨졌으면 여기서 실패한다
    contracts.pack_functions()
    app = FastAPI(title=nav.SYSTEM_NAME, description="MES 표준플랫폼 — 코어 + 업종 팩", version=pack.core_version,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def request_middleware(request: Request, call_next):
        response = await call_next(request)
        for k, v in http.SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        # after_commit 큐 — 응답이 성공(2xx · 3xx)으로 끝난 뒤, 트랜잭션 밖에서 (D-06 · D-20)
        queue = getattr(request.state, http.AFTER_COMMIT_ATTR, None)
        if queue and response.status_code < 400:
            for event, payload in queue:
                _run_after_commit(event, payload)
        return response

    app.add_middleware(SessionMiddleware, secret_key=s.session_secret or secrets.token_urlsafe(32),
                       session_cookie=s.session_cookie, same_site="lax", https_only=False, max_age=auth.SESSION_MAX_AGE_SECONDS)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ── 라우터 include (코어 15 = 모듈 12 + home · dashboard · popup → 팩) ──
    registered: set[tuple[str, str]] = set()
    include_errors: list[str] = []          # 원문 — 서버 쪽만
    include_error_names: list[str] = []     # /health — 모듈과 예외 종류뿐
    missing: list[str] = []                 # 파일이 아직 없는 모듈 (오류가 아니다 — D-26)
    for module in packs.router_modules():
        f = _module_file(module)
        if f is not None and not f.exists():
            missing.append(module.rsplit(".", 1)[-1])
            continue
        try:
            mod = importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 — 임포트 실패를 숨기지 않는다
            log.exception("라우터 임포트 실패: %s", module)
            include_errors.append(f"{module}: {type(exc).__name__}: {exc}")
            include_error_names.append(f"{module.rsplit('.', 1)[-1]}: {type(exc).__name__}")
            continue
        r = getattr(mod, "router", None)
        if r is None:
            include_errors.append(f"{module}: router 없음")
            include_error_names.append(f"{module.rsplit('.', 1)[-1]}: router 없음")
            continue
        app.include_router(r)
        for route in r.routes:
            for m in getattr(route, "methods", None) or ():
                registered.add((m, getattr(route, "path", "")))
    app.state.include_errors = include_errors
    app.state.routers_missing = missing

    # ── 인증 · 공통 화면 (아키텍트) — 라우터에 없는 경로만 ──
    def _safe_next(nxt: str | None) -> str | None:
        if nxt and nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
            return nxt
        return None

    def _login_page(request: Request, *, message: str = "", login_id: str = "", next: str | None = None,
                    device: str | None = None, status_code: int = 200):
        """로그인 화면 — `GET /login` 은 개발1 `routers/home.login_form`(D-21), `POST /login` 실패 401 재렌더는 여기.
        두 화면이 같은 ctx 를 갖도록 `home.role_summary()`(권한 표 요약 · 비밀 없음) · `n_menus` 를 같이 싣는다(회전 4)."""
        from .routers import home as home_router  # noqa — 순환 import 회피 (home 이 templating 을 쓴다)
        return render(request, "login.html",
                      {"message": message, "login_id": login_id, "next": _safe_next(next) or "",
                       "login_device": device if device in nav.DEVICE_CHANNEL else "web",
                       "role_summary": home_router.role_summary(), "n_menus": len(nav.MENUS)},
                      screen_id="CMN-01", status_code=status_code)

    common = APIRouter()

    @common.get("/login", include_in_schema=False)
    def login_form(request: Request, next: str | None = None, device: str | None = None):
        return _login_page(request, message="로그인이 필요합니다" if next else "", next=next, device=device)

    @common.post("/login")
    def login_submit(request: Request, login_id: str = Form(...), password: str = Form(...),
                     next: str | None = Form(None), device: str | None = Form(None)):
        result = auth.authenticate(request, login_id, password, device)
        if not result.ok or result.session is None:
            if not http.wants_html(request):
                return JSONResponse({"code": "unauthorized", "message": result.reason}, status_code=401)
            return _login_page(request, message=result.reason, login_id=login_id, next=next, device=device, status_code=401)
        auth.open_session(request, result.session)
        target = _safe_next(next) or auth.home_path_for(result.session.user, result.session.device)
        if not http.wants_html(request):
            resp = JSONResponse({"ok": True, "login_id": result.session.user.login_id, "role_code": result.session.user.role_code,
                                 "device": result.session.device, "next": target}, status_code=200)
            return resp
        return RedirectResponse(target, status_code=303)

    @common.post("/logout")
    @common.get("/logout", include_in_schema=False)
    def logout(request: Request):
        auth.close_session(request)
        return RedirectResponse("/login", status_code=303)

    @common.get("/error", include_in_schema=False)
    def error_screen(request: Request, status: int | None = None):
        st = status if (status is not None and 400 <= status <= 599) else None
        shown = st or 422
        return render(request, "_error.html",
                      {"status": shown, "code": http.code_for_status(shown), "message": http.status_message(shown),
                       "fields": [], "detail_note": "", "guide": st is None}, screen_id="CMN-03", status_code=st or 200)

    @common.get("/", include_in_schema=False)
    def main_page(request: Request, user: rbac.User = Depends(rbac.require_login)):
        """메인 (IA) — 모듈 카드를 일하는 순서로 (Phase 0 아키텍트판, D-21). 권한 `없음` 은 카드도 링크도 없다."""
        menus = rbac.visible_menus(user)
        cards = [{"menu": m, "level": rbac.cell(user.role_code, m.code).label,
                  "screens": [{"screen": sc, "functions": [f.name for f in contracts.functions_of(sc.screen_id)]} for sc in m.screens],
                  "fn_count": len(contracts.functions_of_module(m.code))} for m in menus]
        return render(request, "home/main.html",
                      {"cards": cards, "n_menus": len(nav.MENUS), "n_screens": len(nav.SCREENS),
                       "n_functions": sum(1 for f in contracts.all_functions() if not f.is_batch),
                       "n_batch": len(contracts.batch_functions()), "lineage": packs.current().lineage,
                       "numbering": packs.current().numbering, "pack": packs.current()}, screen_id="CMN-02")

    @common.get("/dashboard", include_in_schema=False)
    def dashboard(request: Request, user: rbac.User = Depends(rbac.require_login)):
        return templating.placeholder(request, "CMN-04")

    @common.get("/popup/{kind}", include_in_schema=False)
    def popup(request: Request, kind: str, user: rbac.User = Depends(rbac.require_login)):
        kinds = next((c.get("kinds") or [] for c in packs.current().common if c["id"] == "CMN-05"), [])
        if kind not in kinds:
            raise http.not_found(f"팝업 종류 {kind!r} 는 없다 — {kinds}")
        return templating.placeholder(request, "CMN-05")

    @common.get("/openapi.json", include_in_schema=False)
    def openapi_spec(user: rbac.User = Depends(rbac.require_login)):
        if not rbac.can_read_menu(user.role_code, "sys"):
            raise http.forbidden()
        return JSONResponse(app.openapi())

    @common.get("/health")
    def health() -> JSONResponse:
        """인증 없이 열린다 — 상태값과 건수만. 접속 문자열 · 호스트 · DB 이름은 싣지 않는다."""
        try:
            conn.ping()
            db_ok = True
        except conn.DbUnavailable as exc:
            log.error("/health — DB 연결 실패: %s", exc)
            db_ok = False
        body = {
            "status": "ok" if db_ok and not include_errors else "degraded",
            "system": nav.SYSTEM_NAME,
            "pack": pack.name or "",
            "core_version": pack.core_version,
            "db": {"ok": db_ok},
            "menus": len(nav.MENUS),
            "screens": len(nav.CORE_SCREENS),
            "functions": sum(1 for f in contracts.functions() if not f.is_batch),
            "placeholders": len(app.state.placeholder_paths),
            "pack_screens": len(nav.PACK_SCREENS),
            "router_include_errors": include_error_names,
        }
        return JSONResponse(body, status_code=200 if db_ok else 503)

    picked = APIRouter()
    for r in common.routes:
        if all((m, getattr(r, "path", "")) not in registered for m in (getattr(r, "methods", None) or ["GET"])):
            picked.routes.append(r)
    app.include_router(picked)
    for route in picked.routes:
        for m in getattr(route, "methods", None) or ():
            registered.add((m, getattr(route, "path", "")))

    # ── 오류 핸들러 (contracts/api-contract.md) ──
    def _error_page(request: Request, status: int, code: str, message: str, *, fields=None, note: str = ""):
        """DB 가 끊긴 상태에서도 그려져야 하므로 메뉴 · 접근 로그를 타지 않는다."""
        html = templating.env.get_template("_error.html").render(
            request=request, system_name=nav.SYSTEM_NAME, asset_v=templating.asset_version(), status=status, code=code,
            message=message, fields=fields or [], detail_note=note, guide=False, device=auth.device_of(request),
            board_refresh_seconds=s.board_refresh_seconds)
        return HTMLResponse(html, status_code=status, headers=http.SECURITY_HEADERS)

    def _screen_to_return(request: Request) -> str:
        path = request.url.path
        hits = [sc.path for sc in nav.ALL if sc.path != "/" and "{" not in sc.path and (path == sc.path or path.startswith(sc.path + "/"))]
        return max(hits, key=len) if hits else "/"

    def _back_with_flash(request: Request, message: str, fields: list[dict]):
        http.flash(request, t("입력값을 확인해 주세요"), message, fields=fields, kind="warn")
        return RedirectResponse(request.headers.get("referer") or _screen_to_return(request), status_code=303)

    def _invalid_input(request: Request, message: str, fields: list[dict], code: str = "validation_error"):
        if http.wants_html(request) and request.method == "POST":
            return _back_with_flash(request, message, fields)
        if http.wants_html(request):
            return _error_page(request, 422, code, message, fields=fields)
        return JSONResponse({"code": code, "message": message, "fields": fields}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    @app.exception_handler(HTTPException)
    async def on_http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = detail.get("code") or http.code_for_status(exc.status_code)
        message = detail.get("message") or http.status_message(exc.status_code)
        html = http.wants_html(request)
        if exc.status_code == 401 and html and request.method in ("GET", "HEAD") and request.url.path != "/login":
            nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(f"/login?next={quote(nxt, safe='')}", status_code=303)
        if exc.status_code == 422 and html and request.method == "POST":
            return _back_with_flash(request, message, detail.get("fields") or [])
        if html:
            return _error_page(request, exc.status_code, code, message, fields=detail.get("fields"), note=detail.get("decision", ""))
        return JSONResponse({"code": code, "message": message, **{k: v for k, v in detail.items() if k not in {"code", "message"}}},
                            status_code=exc.status_code)

    _REASONS = {"missing": "필수 항목입니다", "int_parsing": "정수여야 합니다", "float_parsing": "숫자여야 합니다",
                "decimal_parsing": "숫자여야 합니다", "date_parsing": "날짜 형식(YYYY-MM-DD)이 아닙니다",
                "date_from_datetime_parsing": "날짜 형식(YYYY-MM-DD)이 아닙니다", "datetime_parsing": "일시 형식이 아닙니다",
                "datetime_from_date_parsing": "일시 형식이 아닙니다", "bool_parsing": "예/아니오 값이어야 합니다"}

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        fields = [{"name": ".".join(str(x) for x in e.get("loc", [])[1:]) or "입력",
                   "reason": _REASONS.get(e.get("type", ""), e.get("msg", ""))} for e in exc.errors()]
        return _invalid_input(request, http.status_message(422), fields)

    @app.exception_handler(HookError)
    async def on_hook_error(request: Request, exc: HookError):
        """팩 훅의 거부 → 422 `hook_rejected`. 트랜잭션은 `conn.tx()` 가 이미 되돌림했다 (D-06)."""
        return _invalid_input(request, exc.message, exc.fields, code="hook_rejected")

    @app.exception_handler(psycopg.errors.IntegrityError)
    async def on_integrity_error(request: Request, exc: psycopg.errors.IntegrityError):
        diag = getattr(exc, "diag", None)
        reason = (getattr(diag, "message_primary", None) or str(exc)).strip()
        return _invalid_input(request, http.status_message(422), [{"name": getattr(diag, "constraint_name", None) or "제약", "reason": reason}])

    @app.exception_handler(psycopg.DataError)
    async def on_data_error(request: Request, exc: psycopg.DataError):
        if isinstance(exc, psycopg.errors.NumericValueOutOfRange):
            reason = "숫자가 저장할 수 있는 범위를 넘었습니다"
        elif isinstance(exc, psycopg.errors.StringDataRightTruncation):
            reason = "글자 수가 저장할 수 있는 길이를 넘었습니다"
        elif isinstance(exc, (psycopg.errors.InvalidDatetimeFormat, psycopg.errors.DatetimeFieldOverflow)):
            reason = "날짜 · 일시 형식이 올바르지 않습니다"
        elif isinstance(exc, psycopg.errors.InvalidTextRepresentation):
            reason = "값의 형식이 올바르지 않습니다"
        elif "NUL" in str(exc):
            reason = "쓸 수 없는 글자(NUL)가 들어 있습니다"
        else:
            reason = "저장할 수 없는 값입니다"
        return _invalid_input(request, http.status_message(422), [{"name": "입력", "reason": reason}])

    @app.exception_handler(conn.DbUnavailable)
    async def on_db_unavailable(request: Request, exc: conn.DbUnavailable):
        log.error("DB 연결 실패 %s %s — %s", request.method, request.url.path, exc)
        if http.wants_html(request):
            return _error_page(request, 503, "db_unavailable", "서비스 일시 중단")
        return JSONResponse({"code": "db_unavailable", "message": "서비스 일시 중단"}, status_code=503, headers=http.SECURITY_HEADERS)

    @app.exception_handler(Exception)
    async def on_unhandled_exception(request: Request, exc: Exception):
        log.exception("미처리 예외 %s %s", request.method, request.url.path)
        try:
            sc = nav.by_path(request.url.path)
            audit.write_log(kind=audit.ERROR, login_id=None, screen_id=sc.screen_id if sc else None,
                            detail={"path": request.url.path, "error": f"{type(exc).__name__}: {exc}"[:500]}, ip=audit.client_ip(request))
        except Exception:  # noqa: BLE001 — 로그 적재 실패가 원래의 500 응답을 가리지 않게 한다
            log.exception("접근 로그(오류) 기록 실패")
        reason = f"{type(exc).__name__}: {exc}" if get_settings().env == "dev" else ""
        if http.wants_html(request):
            return _error_page(request, 500, "internal_error", "예상하지 못한 오류", note=reason)
        body = {"code": "internal_error", "message": "예상하지 못한 오류"}
        if reason:
            body["reason"] = reason
        return JSONResponse(body, status_code=500, headers=http.SECURITY_HEADERS)

    # ── 미구현 화면 placeholder (라우터가 GET 을 등록하지 않은 화면 경로만) ──
    ph = APIRouter()
    for r in _placeholder_routes():
        if ("GET", getattr(r, "path", "")) not in registered:
            ph.routes.append(r)
    app.include_router(ph)
    app.state.placeholder_paths = [getattr(r, "path", "") for r in ph.routes]
    return app


def _run_after_commit(event: str, payload: dict) -> None:
    """`after_commit_<event>` 훅 — 실패해도 응답은 이미 성공. 서버 로그 + `ifc_outbox` 실패 행 (D-20)."""
    import json

    fn = packs.hook(f"after_commit_{event}")
    if fn is packs.NOOP_HOOK:
        return
    try:
        fn(payload)
    except Exception as exc:  # noqa: BLE001 — 트랜잭션 밖 · 응답 뒤. 남기고 넘어간다
        log.exception("after_commit_%s 실패", event)
        try:
            conn.x("""insert into ifc_outbox (event, payload, status, attempts, last_error, created_by)
                      values (%s, %s::jsonb, '실패', 1, %s, 'after_commit')""",
                   (event, json.dumps(payload, ensure_ascii=False, default=str), f"{type(exc).__name__}: {exc}"[:500]))
        except Exception:  # noqa: BLE001
            log.exception("ifc_outbox 기록 실패")


app = create_app()
