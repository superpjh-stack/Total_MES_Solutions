"""접근 로그 — `sys_access_log` 에 쓰는 한 곳 (G-C18). (`interfaces.md` §2)

    write_log(...)                                   로그인 성공 · 실패 · 조회 · 변경 · 오류 — 아키텍트 코드가 부른다
    log_view(request, user, screen_id)               templating.render 가 부른다
    log_change(request, user, fn_id, target, detail) 데이터 변경 — **개발자는 쓰기 성공 직후 이것을 부른다**

종류 `kind`: login_ok · login_fail · view · change · error. 로그 적재 실패를 삼키지 않는다.
비밀번호 · 세션 ID 는 어떤 칸에도 적지 않는다.
"""

from __future__ import annotations

import json

from ...db import conn

LOGIN_OK, LOGIN_FAIL, VIEW, CHANGE, ERROR = "login_ok", "login_fail", "view", "change", "error"


def client_ip(request) -> str | None:
    return request.client.host if getattr(request, "client", None) else None


def device_of(request) -> str | None:
    try:
        from .. import auth
        return auth.device_of(request)
    except Exception:  # noqa: BLE001 — 세션이 없는 요청(테스트 · 오류 처리 중)
        return None


def write_log(*, kind: str, login_id: str | None, user_id: int | None = None, screen_id: str | None = None,
              fn_id: str | None = None, target: str | None = None, detail: dict | str | None = None,
              ip: str | None = None, device: str | None = None) -> None:
    if isinstance(detail, str):
        detail = {"text": detail[:1000]}
    conn.x(
        """insert into sys_access_log (logged_at, user_id, login_id, kind, screen_id, fn_id, target, detail, ip, device)
           values (now(), %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)""",
        (user_id, login_id, kind, screen_id, fn_id, target, json.dumps(detail or {}, ensure_ascii=False), ip, device),
    )


def log_view(request, user, screen_id: str) -> None:
    write_log(kind=VIEW, login_id=user.login_id, user_id=user.id, screen_id=screen_id,
              detail={"path": request.url.path, "method": request.method}, ip=client_ip(request), device=device_of(request))


def log_change(request, user, fn_id: str, target: str, detail: dict | None = None) -> None:
    """데이터 변경 로그 — 누가 · 언제 · 무엇을. `target` 은 `테이블:업무 번호`.

        audit.log_change(request, user, "F-BAS-01", f"bas_item:{item_code}")
    """
    from .. import contracts  # noqa — 순환 import 회피

    fn = contracts.function(fn_id)
    write_log(kind=CHANGE, login_id=user.login_id, user_id=user.id, screen_id=fn.screen_id or None, fn_id=fn_id, target=target,
              detail={"name": fn.name, "path": request.url.path, **(detail or {})}, ip=client_ip(request), device=device_of(request))
