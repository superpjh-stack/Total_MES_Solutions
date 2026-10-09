"""home 라우터 — 메인 IA (CMN-02 `/`) + 개발용 역할 로그인 (D-605) · 담당 개발1.

메인: 모듈 12 카드를 **일하는 순서**(`core.yaml: order` · 팩 `menus.order` = `nav.MENUS`)로. 현재 역할의 칸(`rbac.cell`)이 `없음` 이면
카드는 흐리게 + 링크 없음(G-C17 — `check_routes` 가 `href` 로 센다). 팩이 숨긴 모듈은 `nav.MENUS` 에 없다. 어떤 테이블에도 쓰지 않는다.
"오늘 건수" 는 개발3 `stats.today_counts()`(코어 모듈 12 → int · 출처 `stats.TODAY_COUNT_SOURCES`)에서만 온다 — 집계 SQL 은 `stats` 에만.
카드 ctx `today`(int · 0 도 숫자) · `today_label`(짧은 라벨) · `today_source`(출처 문장). 팩 모듈은 `None` → 화면 `미수집`.

로그인(CMN-01 `GET /login`): 화면은 `main._login_page` 와 같은 ctx + `role_summary`(역할 × 채널 × 입력 메뉴 — DB 권한 표 요약 · 비밀 없음).
`main.py` 는 라우터가 등록한 공통 경로를 자기 것으로 두지 않는다(D-21) — `POST /login` 실패 재렌더는 여전히 `main._login_page`.

개발용 로그인(D-605): `dev_login_allowed` — `MES_ENV=dev` 명시 + 루프백 요청일 때만 `POST /login/as`(role) 가 시드 계정(`seed_core.USERS`)으로 로그인한다. 운영(`MES_ENV` ≠ dev)은 404.
비밀번호는 환경변수 `MES_SEED_PASSWORD` 만 — 코드 · 화면에 값이 없다(G-C19). `main.py` 는 라우터에 없는 공통 경로만 자기 것으로 둔다(D-21).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import auth, contracts, guide, nav, packs, rbac, stats, templating
from ..settings import get_settings
from ..util import http

router = APIRouter()


# 카드에 붙이는 짧은 라벨 (뜻 = stats.TODAY_COUNT_SOURCES · 디자이너3 home.html 머리 주석). 값은 stats.today_counts() 에서만
TODAY_LABELS: dict[str, str] = {
    "bas": "오늘 변경", "ord": "오늘 납기", "job": "오늘 지시", "mat": "오늘 입고", "pop": "오늘 실적", "qua": "검사 대기",
    "eqp": "고장 중", "shp": "출하 대기", "trc": "오늘 연결", "kpi": "측정값 이탈", "sys": "오늘 로그인", "ifc": "오늘 수신 거부",
}


def today_counts() -> dict[str, dict]:
    """모듈 코드 → {"value": int, "label": str, "source": str}. 값은 개발3 `stats.today_counts()` 그대로 — 여기서 SQL 을 쓰지 않는다.
    팩 모듈(코어 12 밖)은 키가 없다 → 카드 `today` None → 화면 `미수집`."""
    fn = getattr(stats, "today_counts", None)    # 개발3 회전 4 공표 — 없는 버전이면 전부 미수집
    if not callable(fn):
        return {}
    sources = getattr(stats, "TODAY_COUNT_SOURCES", {})
    return {code: {"value": v, "label": TODAY_LABELS.get(code, "오늘"), "source": sources.get(code, "")}
            for code, v in fn().items()}


def cards_for(user: rbac.User) -> list[dict]:
    pack = packs.current()
    counts = today_counts()
    names = {r["code"]: r["name"] for r in pack.roles}
    out = []
    for i, m in enumerate(nav.MENUS, start=1):
        cell = rbac.cell(user.role_code, m.code)
        write_roles = [names.get(r["code"], r["code"]) for r in pack.roles if pack.permission(m.code, r["code"])["level"] == rbac.LEVEL_WRITE]
        out.append({
            "menu": m, "seq": i, "level": packs.t(cell.label), "allowed": cell.can_read,   # 권한 범위(입고검사 …)도 팩 용어로
            "screens": [{"screen": sc, "functions": [f.name for f in contracts.functions_of(sc.screen_id)]} for sc in m.screens],
            "fn_count": len(contracts.functions_of_module(m.code)), "write_roles": write_roles,
            "today": (counts.get(m.code) or {}).get("value"), "today_label": (counts.get(m.code) or {}).get("label") or "오늘", "today_source": (counts.get(m.code) or {}).get("source") or "",
        })
    return out


@router.get("/", include_in_schema=False)
def main_page(request: Request, user: rbac.User = Depends(rbac.require_login)) -> HTMLResponse:
    """메인 (IA) — CMN-02. 권한 `없음` 카드는 흐림 + 링크 없음."""
    cards = cards_for(user)
    return templating.render(request, "home/main.html", {
        "cards": cards, "n_allowed": sum(1 for c in cards if c["allowed"]), "n_menus": len(nav.MENUS), "n_screens": len(nav.SCREENS),
        "n_functions": sum(1 for f in contracts.all_functions() if not f.is_batch), "n_batch": len(contracts.batch_functions()),
        "lineage": packs.current().lineage, "numbering": packs.current().numbering, "pack": packs.current(),
    }, screen_id="CMN-02")


# ── 메인(IA) 하위 메뉴 — 기능표 · 업무 프로세스 (읽기 전용 안내 · 어떤 테이블에도 쓰지 않는다) ──
MAIN_TABS = (("/", "모듈 지도"), ("/main/functions", "기능표"), ("/main/processes", "업무 프로세스"))


def _screen_link(screen_id: str, user: rbac.User) -> dict:
    """화면 ID → 이름 · 경로 · 열 수 있는지(권한 칸 + 채널). 팩이 숨긴 화면은 open=False."""
    try:
        s = nav.by_id(screen_id)
    except KeyError:
        return {"screen_id": screen_id, "name": screen_id, "path": None, "open": False, "menu": None}
    m = nav.menu_of_screen(screen_id)
    visible = m is not None and any(x.code == m.code for x in nav.MENUS)
    return {"screen_id": screen_id, "name": s.name, "path": s.path, "menu": m.name if m else None,
            "open": bool(visible and rbac.can_read_menu(user.role_code, m.code))}


@router.get("/main/functions", include_in_schema=False)
def main_functions(request: Request, module: str = "", q: str = "", user: rbac.User = Depends(rbac.require_login)) -> HTMLResponse:
    """메인 › 기능표 — contracts/function-list.md 의 기능을 모듈 · 화면별로. 현재 역할이 할 수 있는지(`user.can`)를 함께 보인다."""
    menus = [m for m in nav.MENUS]
    order = {m.module: i for i, m in enumerate(menus)}
    rows = []
    for f in contracts.all_functions():
        if f.is_batch:
            continue
        if f.module not in order:                       # 팩이 숨긴 모듈의 기능은 보이지 않는다
            continue
        if module and f.module != module:
            continue
        if q and q not in f.id and q not in f.name and q not in f.text:
            continue
        link = _screen_link(f.screen_id, user)
        rows.append({"id": f.id, "module": f.module, "screen_id": f.screen_id, "screen": link["name"], "path": link["path"] if link["open"] else None,
                     "name": f.name, "kind": f.kind, "write": f.is_write, "api": f.api, "channels": list(f.channels),
                     "roles": list(f.roles), "scope": f.scope, "text": f.text, "can": user.can(f.id)})
    rows.sort(key=lambda r: (order.get(r["module"], 99), r["id"]))
    by_module = []
    for m in menus:
        fs = [r for r in rows if r["module"] == m.module]
        if fs:
            by_module.append({"module": m.module, "name": m.name, "rows": fs,
                              "n_write": sum(1 for r in fs if r["write"]), "n_can": sum(1 for r in fs if r["can"])})
    batch = [{"id": f.id, "name": f.name, "api": f.api, "text": f.text} for f in contracts.batch_functions()]
    return templating.render(request, "home/functions.html", {
        "tabs": MAIN_TABS, "tab": "/main/functions", "groups": by_module, "batch": batch, "module": module, "q": q,
        "module_options": [(m.module, m.name) for m in menus], "n_rows": len(rows), "n_can": sum(1 for r in rows if r["can"]),
    }, screen_id="CMN-02")


@router.get("/main/processes", include_in_schema=False)
def main_processes(request: Request, code: str = "", user: rbac.User = Depends(rbac.require_login)) -> HTMLResponse:
    """메인 › 업무 프로세스 — 화면들을 엮어 쓰는 업무 흐름 유형(app/guide.py). 단계마다 화면 링크 · 담당 역할 · 남는 데이터."""
    roles = {r.code: r.name for r in rbac.roles()}
    items = []
    for p in guide.processes():
        steps = []
        for i, st in enumerate(p.steps, 1):
            link = _screen_link(st.screen_id, user)
            steps.append({"no": i, **link, "role": st.role, "role_name": roles.get(st.role, st.role), "mine": st.role == user.role_code,
                          "action": st.action, "output": st.output})
        items.append({"code": p.code, "name": p.name, "kind": p.kind, "when": p.when, "goal": p.goal, "steps": steps,
                      "checks": list(p.checks), "measures": list(p.measures),
                      "screens": len({s["screen_id"] for s in steps}), "n_open": sum(1 for s in steps if s["open"])})
    kinds = []
    for p in items:
        if p["kind"] not in kinds:
            kinds.append(p["kind"])
    current = next((p for p in items if p["code"] == code), None)
    return templating.render(request, "home/processes.html", {
        "tabs": MAIN_TABS, "tab": "/main/processes", "processes": items, "kinds": kinds, "current": current, "code": code,
    }, screen_id="CMN-02")


def role_summary() -> list[dict]:
    """로그인 화면용 권한 표 요약 — 역할마다 {code name channels[{device label}] write_menus[{code name label}] read_count}.
    채널 = 그 역할이 열 수 있는(조회 이상) 메뉴의 채널 합. 숨긴 모듈 제외(`nav.MENUS`). DB 권한 표(`rbac`) 그대로 · 비밀 없음."""
    out = []
    for r in rbac.roles():
        chans: set[str] = set()
        writes, n_read = [], 0
        for m in nav.MENUS:
            c = rbac.cell(r.code, m.code)
            if not c.can_read:
                continue
            n_read += 1
            chans.update(m.channels)
            if c.level == rbac.LEVEL_WRITE:
                writes.append({"code": m.code, "name": m.name, "label": packs.t(c.label)})
        out.append({"code": r.code, "name": r.name,
                    "channels": [{"device": dev, "label": ch} for dev, ch in nav.DEVICE_CHANNEL.items() if ch in chans],
                    "write_menus": writes, "read_count": n_read})
    return out


def _safe_next(nxt: str | None) -> str | None:
    if nxt and nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
        return nxt
    return None


@router.get("/login", include_in_schema=False)
def login_form(request: Request, next: str | None = None, device: str | None = None):  # noqa: A002 — 쿼리 이름 그대로
    """CMN-01 로그인 화면 — `main._login_page` 와 같은 ctx + `role_summary`."""
    return templating.render(request, "login.html", {
        "message": "로그인이 필요합니다" if next else "", "login_id": "", "next": _safe_next(next) or "",
        "login_device": device if device in nav.DEVICE_CHANNEL else "web",
        "role_summary": role_summary(), "n_menus": len(nav.MENUS),
        "dev_login": dev_login_allowed(request),   # 개발용 역할 버튼을 그려도 되는가(D-605) — 디자이너1 login.html
    }, screen_id="CMN-01")


def dev_login_allowed(request: Request) -> bool:
    """D-605 · DEF-QA1-001 · DEF-QA3-001 — 개발용 무비밀번호 로그인을 열어도 되는가.

    아키텍트 `settings.dev_login_allowed(request)`(`MES_ENV=dev` + 루프백 주소) 가 있으면 그것을 쓰고, 없으면 같은 조건을 여기서 본다.
    여기서 한 가지를 더 막는다 — 프록시 전달 헤더(`X-Forwarded-For` · `Forwarded`)가 있으면 바깥 요청이므로 거짓.
    """
    if request.headers.get("x-forwarded-for") or request.headers.get("forwarded"):
        return False
    from .. import settings as _settings

    judge = getattr(_settings, "dev_login_allowed", None)
    if callable(judge):
        return bool(judge(request))
    import ipaddress
    import os

    if (os.environ.get("MES_ENV") or "").strip().lower() != "dev" or get_settings().env != "dev":
        return False
    try:
        return ipaddress.ip_address(request.client.host if request.client else "").is_loopback
    except ValueError:
        return False


@router.post("/login/as", include_in_schema=False)
def login_as(request: Request, role: str = Form(...), device: str | None = Form(None), nxt: str | None = Form(None, alias="next")):
    """D-605 — 개발 환경(`MES_ENV=dev` 명시 + 루프백)에서만 역할 버튼으로 시드 계정 로그인. 그 밖에서는 이 경로가 없다(404)."""
    s = get_settings()
    if not dev_login_allowed(request):
        raise http.not_found()
    from ...db.seed_core import USERS  # noqa — 시드 계정 ID 는 한 곳(seed_core)에서

    login_id = next((lid for lid, _name, code in USERS if code == role), None)
    if login_id is None:
        raise http.validation_error("없는 역할입니다", fields=[{"name": "role", "label": "역할", "reason": role}])
    if not s.seed_password:
        raise http.validation_error("MES_SEED_PASSWORD 미설정 — 개발용 로그인을 쓸 수 없다", fields=[{"name": "role", "label": "역할", "reason": "MES_SEED_PASSWORD"}])
    result = auth.authenticate(request, login_id, s.seed_password, device)
    if not result.ok or result.session is None:
        if not http.wants_html(request):
            return JSONResponse({"code": "unauthorized", "message": result.reason}, status_code=401)
        return RedirectResponse(f"/login?device={device or 'web'}", status_code=303)
    auth.open_session(request, result.session)
    target = nxt if (nxt and nxt.startswith("/") and not nxt.startswith("//")) else auth.home_path_for(result.session.user, result.session.device)
    if not http.wants_html(request):
        return JSONResponse({"ok": True, "login_id": login_id, "role_code": result.session.user.role_code, "device": result.session.device, "next": target})
    return RedirectResponse(target, status_code=303)
