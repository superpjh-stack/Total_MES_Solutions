"""권한 — 권한 표(모듈 × 역할 = 48칸)를 **DB 데이터**(`sys_permission` · `sys_role`)로 읽는다 (G-C17).

역할도 칸도 이 파일에 박혀 있지 않다. 팩이 역할을 늘려도(`pack.yaml: roles`) 코드를 고치지 않는다 —
SYS-03 이 행을 바꾸고 `invalidate()` 를 부르면 다음 요청부터 반영된다. 행이 없는 칸은 `없음` 이다(권한을 지어내지 않는다).

판정
  조회  그 모듈 칸의 level 이 `조회` 또는 `입력`
  쓰기  칸의 level 이 `입력` 이고, 기능의 범위(`function-list.md` 의 `범위` 열)가 칸의 `scopes` 에 들어 있다
        → `입력 (입고검사)` 는 입고검사 판정만, `입력 (승인)` 은 출하 승인만. 괄호 없는 `입력` 은 `일반` 기능만 (D-13)
  없음  메뉴에서 숨기고 403. 팩이 숨긴 메뉴(`menus.hide`)도 403

    require_login(request) -> User        미로그인 → 401
    require_screen("BAS-01")              화면 GET 의존성. 칸이 없음 · 숨긴 메뉴 · 채널 밖 → 403
    require_fn("F-BAS-01")                기능 의존성. 쓰기 기능이면 쓰기 판정(scope 포함), 읽기 기능이면 조회 판정
    current_user(request) -> User | None  **요청마다 DB** (sys_session ⋈ sys_user ⋈ sys_role, D-19)
    invalidate() · matrix() · roles() · cell(role_code, menu_code)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import Depends, Request

from . import contracts, nav
from .util import http

LEVEL_WRITE, LEVEL_READ, LEVEL_NONE = "입력", "조회", "없음"
LEVELS: tuple[str, ...] = (LEVEL_WRITE, LEVEL_READ, LEVEL_NONE)
SCOPE_GENERAL = contracts.SCOPE_GENERAL
STATUS_ACTIVE = "사용"
SESSION_ID_KEY = "sid"
DEVICE_SESSION_KEY = "device"
_STATE_ATTR = "mes_user"
_UNSET = object()


@dataclass(frozen=True)
class Role:
    id: int
    code: str
    name: str


@dataclass(frozen=True)
class Cell:
    level: str = LEVEL_NONE
    scopes: frozenset[str] = frozenset()

    @property
    def can_read(self) -> bool:
        return self.level in (LEVEL_WRITE, LEVEL_READ)

    def can_write(self, scope: str) -> bool:
        return self.level == LEVEL_WRITE and scope in self.scopes

    @property
    def label(self) -> str:
        """goal.md §6 표기 — `입력` · `입력 (입고검사)` · `조회` · `없음`."""
        if self.level != LEVEL_WRITE:
            return self.level
        extra = sorted(self.scopes - {SCOPE_GENERAL})
        if SCOPE_GENERAL in self.scopes:
            return LEVEL_WRITE + (f" (+{'·'.join(extra)})" if extra else "")
        return f"{LEVEL_WRITE} ({'·'.join(extra)})"


NO_CELL = Cell()

_CACHE: dict[str, object] = {"at": 0.0, "roles": None, "cells": None}
CACHE_SECONDS = 5.0


def invalidate() -> None:
    _CACHE["at"], _CACHE["roles"], _CACHE["cells"] = 0.0, None, None


def _load() -> tuple[list[Role], dict[tuple[str, str], Cell]]:
    now = time.monotonic()
    if _CACHE["roles"] is not None and now - float(_CACHE["at"]) < CACHE_SECONDS:  # type: ignore[arg-type]
        return _CACHE["roles"], _CACHE["cells"]  # type: ignore[return-value]
    from ..db import conn  # noqa — 순환 import 회피

    role_rows = conn.q("select id, role_code, role_name from sys_role where use_yn = 'Y' order by id")
    cell_rows = conn.q("""select r.role_code, p.menu_code, p.level, p.scopes
                            from sys_permission p join sys_role r on r.id = p.role_id""")
    roles = [Role(r["id"], r["role_code"], r["role_name"]) for r in role_rows]
    cells = {(r["role_code"], r["menu_code"]): Cell(r["level"], frozenset(r["scopes"] or ())) for r in cell_rows}
    _CACHE["at"], _CACHE["roles"], _CACHE["cells"] = now, roles, cells
    return roles, cells


def roles() -> list[Role]:
    return _load()[0]


def role(code: str) -> Role | None:
    return next((r for r in roles() if r.code == code), None)


def cell(role_code: str, menu_code: str) -> Cell:
    return _load()[1].get((role_code, menu_code), NO_CELL)


def can_read_menu(role_code: str, menu_code: str) -> bool:
    m = nav._MENU.get(menu_code)
    if m is not None and m.hidden:
        return False
    return cell(role_code, menu_code).can_read


def can_open(role_code: str, screen_id: str) -> bool:
    sc = nav.by_id(screen_id)
    if sc.common:
        return True
    return can_read_menu(role_code, sc.menu_code)


def can_do(role_code: str, function_id: str) -> bool:
    fn = contracts.function(function_id)
    if fn.is_batch or fn.is_token:
        return False
    if fn.menu_code and nav._MENU.get(fn.menu_code) is not None and nav._MENU[fn.menu_code].hidden:
        return False
    c = cell(role_code, fn.menu_code)
    return c.can_write(fn.scope) if fn.is_write else c.can_read


def matrix() -> list[dict]:
    rs = roles()
    return [{"menu": m, "cells": [cell(r.code, m.code) for r in rs]} for m in nav.ALL_MENUS]


def counts() -> dict[str, int]:
    """현재 DB 권한 표의 칸 수 — {'입력': n, '조회': n, '없음': n, '전체': n} (역할 × 메뉴 전부)."""
    out = {LEVEL_WRITE: 0, LEVEL_READ: 0, LEVEL_NONE: 0}
    for r in roles():
        for m in nav.ALL_MENUS:
            out[cell(r.code, m.code).level] += 1
    out["전체"] = sum(out.values())
    return out


# ── 사용자 ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class User:
    id: int
    login_id: str
    user_name: str
    role_code: str
    role_name: str
    device: str = "web"

    def can_open(self, screen_id: str) -> bool:
        return can_open(self.role_code, screen_id)

    def can(self, function_id: str) -> bool:
        return can_do(self.role_code, function_id)


def forget_user(request: Request) -> None:
    if hasattr(request, "state"):
        setattr(request.state, _STATE_ATTR, _UNSET)


def _verified_user(request: Request) -> User | None:
    session_id = request.session.get(SESSION_ID_KEY) if hasattr(request, "session") else None
    if not session_id:
        return None
    from ..db import conn  # noqa — 순환 import 회피

    row = conn.q1(
        """select u.id, u.login_id, u.user_name, u.status, r.role_code, r.role_name, r.use_yn as role_use_yn, s.device,
                  s.revoked_at, s.expires_at < now() as expired,
                  coalesce(extract(epoch from u.password_changed_at)::bigint, 0) <> s.password_version as password_changed
             from sys_session s
             join sys_user u on u.id = s.user_id
             join sys_role r on r.id = u.role_id
            where s.session_id = %s""",
        (str(session_id),))
    if (row is None or row["status"] != STATUS_ACTIVE or row["revoked_at"] is not None or row["expired"]
            or row["password_changed"] or row["role_use_yn"] != "Y"):
        request.session.clear()
        return None
    return User(id=row["id"], login_id=row["login_id"], user_name=row["user_name"], role_code=row["role_code"],
                role_name=row["role_name"], device=row["device"] or "web")


def current_user(request: Request) -> User | None:
    """이 요청의 사용자. **요청마다 DB 의 세션 · 계정을 다시 본다** — 중지 · 잠금 · 로그아웃 · 비밀번호 변경은 다음 요청부터 401.
    한 요청 안에서는 한 번만 조회한다. DB 연결 실패는 삼키지 않는다(503)."""
    if not hasattr(request, "state"):
        return _verified_user(request)
    cached = getattr(request.state, _STATE_ATTR, _UNSET)
    if cached is _UNSET:
        cached = _verified_user(request)
        setattr(request.state, _STATE_ATTR, cached)
    return cached


def require_login(request: Request) -> User:
    user = current_user(request)
    if user is None:
        raise http.unauthorized()
    return user


def _device(request: Request) -> str:
    q = request.query_params.get("device")
    if q in nav.DEVICE_CHANNEL:
        return q
    s = request.session.get(DEVICE_SESSION_KEY) if hasattr(request, "session") else None
    return s if s in nav.DEVICE_CHANNEL else "web"


def require_screen(screen_id: str):
    """화면 접근 의존성 — 칸 `없음` · 팩이 숨긴 메뉴 · 채널 허용 밖 → 403."""
    nav.by_id(screen_id)

    def _dep(request: Request) -> User:
        user = require_login(request)
        if not user.can_open(screen_id):
            raise http.forbidden(screen_id=screen_id)
        if not nav.channel_allowed(screen_id, _device(request)):
            raise http.forbidden(screen_id=screen_id, device=_device(request))
        return user

    return Depends(_dep)


def require_fn(function_id: str):
    """기능 수행 의존성 — **쓰기 엔드포인트는 반드시 이것을 쓴다.** 조회 권한만 있는 역할의 쓰기는 403."""
    fn = contracts.function(function_id)

    def _dep(request: Request) -> User:
        user = require_login(request)
        if not user.can(function_id):
            raise http.forbidden(function_id=function_id)
        if fn.screen_id and not nav.channel_allowed(fn.screen_id, _device(request)):
            raise http.forbidden(function_id=function_id, device=_device(request))
        return user

    return Depends(_dep)


def visible_menus(user: User | None) -> list[nav.Menu]:
    """좌측 메뉴 · 메인 카드 — `없음` 과 팩이 숨긴 메뉴는 뺀다(G-C17). 미로그인이면 빈 목록."""
    if user is None:
        return []
    return [m for m in nav.MENUS if can_read_menu(user.role_code, m.code)]
