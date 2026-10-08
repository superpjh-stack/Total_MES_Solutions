"""home 라우터 — 메인 IA (CMN-02 `/`) + 개발용 역할 로그인 (D-605) · 담당 개발1.

메인: 모듈 12 카드를 **일하는 순서**(`core.yaml: order` · 팩 `menus.order` = `nav.MENUS`)로. 현재 역할의 칸(`rbac.cell`)이 `없음` 이면
카드는 흐리게 + 링크 없음(G-C17 — `check_routes` 가 `href` 로 센다). 팩이 숨긴 모듈은 `nav.MENUS` 에 없다. 어떤 테이블에도 쓰지 않는다.
"오늘 건수" 는 개발3 `stats` 의 공개 함수가 생기면 붙인다 — 지금은 지어내지 않고 자리만 둔다(`미수집`).

개발용 로그인(D-605): `MES_ENV=dev` 일 때만 `POST /login/as`(role) 가 시드 계정(`seed_core.USERS`)으로 로그인한다. 운영(`MES_ENV` ≠ dev)은 404.
비밀번호는 환경변수 `MES_SEED_PASSWORD` 만 — 코드 · 화면에 값이 없다(G-C19). `main.py` 는 라우터에 없는 공통 경로만 자기 것으로 둔다(D-21).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import auth, contracts, nav, packs, rbac, templating
from ..settings import get_settings
from ..util import http

router = APIRouter()


def cards_for(user: rbac.User) -> list[dict]:
    pack = packs.current()
    names = {r["code"]: r["name"] for r in pack.roles}
    out = []
    for i, m in enumerate(nav.MENUS, start=1):
        cell = rbac.cell(user.role_code, m.code)
        write_roles = [names.get(r["code"], r["code"]) for r in pack.roles if pack.permission(m.code, r["code"])["level"] == rbac.LEVEL_WRITE]
        out.append({
            "menu": m, "seq": i, "level": cell.label, "allowed": cell.can_read,
            "screens": [{"screen": sc, "functions": [f.name for f in contracts.functions_of(sc.screen_id)]} for sc in m.screens],
            "fn_count": len(contracts.functions_of_module(m.code)), "write_roles": write_roles, "today": None,
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


@router.post("/login/as", include_in_schema=False)
def login_as(request: Request, role: str = Form(...), device: str | None = Form(None), nxt: str | None = Form(None, alias="next")):
    """D-605 — 개발 환경(`MES_ENV=dev`)에서만 역할 버튼으로 시드 계정 로그인. 운영에서는 이 경로가 없다(404)."""
    s = get_settings()
    if s.env != "dev":
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
