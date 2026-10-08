"""렌더링 — `contracts/interfaces.md` §2.

    render(request, template, ctx, *, screen_id=..., status_code=200)

`screen_id` 를 주면 헤더 · 좌측 메뉴(권한 `없음` · 팩 숨김은 빠진다) · 우측 계약 패널(그 화면의 기능 줄) · 채널 레이아웃을 자동으로
채우고 접근 로그(`sys_access_log` kind=view)를 남긴다 (G-C18). 템플릿 전역에 `t()`(용어 치환) 가 있다.

**백엔드 우선 (D-18)**: 요청 `Accept` 에 `text/html` 이 없으면 템플릿을 그리지 않고 **`ctx` 를 JSON** 으로 준다 —
테스트 · API 검증이 같은 데이터를 본다. `request` · 설정 · 함수 객체는 빠지고 dataclass · datetime · Decimal 은 그대로 풀린다.
템플릿 검색 경로는 `packs.template_dirs()` — 팩 `templates/` 가 코어보다 먼저(같은 이름은 덮어쓴다).
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import auth, contracts, nav, packs, rbac
from .packs import t
from .settings import get_settings
from .util import audit, http, screen

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
NO_VIEW_LOG = {"CMN-01", "CMN-03"}
_SKIP_KEYS = {"request", "settings", "nav", "t", "flash", "asset_v"}

env = Environment(
    loader=FileSystemLoader([str(d) for d in packs.template_dirs()]),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.globals.update(NOT_COLLECTED=screen.NOT_COLLECTED, EXAMPLE=screen.EXAMPLE, t=t)
env.filters.update(txt=screen.txt, num=screen.num, dt=screen.dt, t=t)


def _fmt_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def asset_version() -> str:
    try:
        return str(int(max((STATIC_DIR / n).stat().st_mtime for n in ("style.css", "app.js"))))
    except OSError:
        return "0"


def jsonable(v: Any, depth: int = 0) -> Any:
    """ctx → JSON 으로 풀 수 있는 값. dataclass · datetime · Decimal · set 을 풀고, 나머지 객체는 str()."""
    if depth > 8:
        return str(v)
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {f.name: jsonable(getattr(v, f.name), depth + 1) for f in dataclasses.fields(v) if not f.name.startswith("_")}
    if isinstance(v, dict):
        return {str(k): jsonable(x, depth + 1) for k, x in v.items() if not callable(x) and str(k) not in _SKIP_KEYS}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [jsonable(x, depth + 1) for x in v]
    if isinstance(v, Path):
        return str(v)
    if callable(v):
        return None
    return str(v)


def screen_context(request: Request, screen_id: str | None) -> dict[str, Any]:
    s = get_settings()
    user = rbac.current_user(request)
    device = auth.device_of(request)
    pack = packs.current()
    ctx: dict[str, Any] = {
        "request": request,
        "asset_v": asset_version(),
        "flash": http.pop_flash(request),
        "system_name": nav.SYSTEM_NAME,
        "pack_name": pack.name or "",
        "core_version": pack.core_version,
        "now": _fmt_now(),
        "user": user,
        "menus": rbac.visible_menus(user),
        "device": device,
        "channel": nav.DEVICE_CHANNEL[device],
        "settings": s,
        "nav": nav,
        "screen_id": screen_id,
        "screen": None,
        "screen_name": "",
        "menu_name": "",
        "active_menu": "",
        "functions": [],
        "grid_page_size": s.grid_page_size,
        "board_refresh_seconds": s.board_refresh_seconds,
    }
    if screen_id:
        sc = nav.by_id(screen_id)
        ctx["screen"] = sc
        ctx["screen_name"] = t(sc.name)
        if not sc.common:
            m = nav.menu(sc.menu_code)
            ctx["menu_name"] = t(m.name)
            ctx["active_menu"] = m.code
            ctx["functions"] = [{"fn": f, "allowed": bool(user and user.can(f.id))} for f in contracts.functions_of(screen_id)]
    return ctx


def render(request: Request, template: str, ctx: dict | None = None, *, screen_id: str | None = None,
           status_code: int = 200):
    base = screen_context(request, screen_id)
    if ctx:
        base.update(ctx)
    user = base.get("user")
    if screen_id and screen_id not in NO_VIEW_LOG and user is not None:
        audit.log_view(request, user, screen_id)
    if not http.wants_html(request):
        body = {k: jsonable(v) for k, v in base.items() if k not in _SKIP_KEYS and not callable(v)}
        body["template"] = template
        return JSONResponse(body, status_code=status_code)
    html = env.get_template(template).render(**base)
    return HTMLResponse(html, status_code=status_code)


def placeholder(request: Request, screen_id: str):
    """미구현 화면 — HTTP **200** 으로 "미구현 — 담당 개발N" 과 계약 문장을 보여 준다. JSON 은 `placeholder: true`."""
    sc = nav.by_id(screen_id)
    return render(request, "_placeholder.html",
                  {"item": sc, "placeholder": True, "owner": sc.owner, "note": f"미구현 — 담당 {sc.owner}"}, screen_id=screen_id)
