"""로그인 · 로그아웃 · 세션(`sys_session`) · 비밀번호 해시 · 잠금 (`interfaces.md` §2 · D-14 · D-19).

- 비밀번호는 PBKDF2-HMAC-SHA256 해시만 저장한다. 평문 · 기본 비밀번호는 코드 어디에도 없다 (G-C19).
- 로그인 성공 · 실패는 `sys_access_log`(login_ok · login_fail)에 남는다 (G-C18).
- 실패 횟수는 `sys_user.fail_count`. `MES_LOGIN_LOCK_COUNT` 가 있을 때만 그 횟수에서 `잠금` (D-14). 상태 `사용` 인 계정만 로그인한다.
- 세션은 DB 행이다. 쿠키(서명)에는 세션 ID 만 들고, 유효 판정은 요청마다 `rbac.current_user` 가 DB 로 한다 (D-19).

    auth.login(cur, login_id, password, device) -> Session | None
    auth.logout(cur, session_id)
    auth.hash_password(raw) · auth.verify(raw, hashed)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from ..db import conn
from . import nav, rbac
from .rbac import User
from .settings import get_settings
from .util import audit, http

PBKDF2_ITERATIONS = 260_000
PBKDF2_ALGO = "pbkdf2_sha256"
STATUS_ACTIVE, STATUS_STOPPED, STATUS_LOCKED = "사용", "중지", "잠금"
SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60     # 쿠키 · sys_session.expires_at — 자동 로그아웃 수치는 정본에 없다 (D-19)
BAD_CREDENTIALS = "아이디 또는 비밀번호가 올바르지 않습니다"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "$".join([PBKDF2_ALGO, str(PBKDF2_ITERATIONS), base64.b64encode(salt).decode(), base64.b64encode(dk).decode()])


def verify(password: str, stored: str) -> bool:
    parts = (stored or "").split("$")
    if len(parts) != 4 or parts[0] != PBKDF2_ALGO:
        return False
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2])
        expected = base64.b64decode(parts[3])
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


verify_password = verify


@dataclass(frozen=True)
class Session:
    session_id: str
    user: User
    device: str


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    session: Session | None = None
    reason: str = ""


def _log(kind: str, login_id: str | None, user_id: int | None, ip: str | None, detail: str, device: str | None) -> None:
    audit.write_log(kind=kind, login_id=login_id, user_id=user_id, screen_id="CMN-01", detail=detail, ip=ip, device=device)


def login(cur, login_id: str, password: str, device: str | None = None, *, client_ip: str | None = None) -> LoginResult:
    """ID/비밀번호 인증 → `sys_session` 한 행. 결과를 접근 로그에 남기고 실패 횟수를 갱신한다. 비밀번호 값은 어디에도 쓰지 않는다."""
    login_id = (login_id or "").strip()
    device = device if device in nav.DEVICE_CHANNEL else "web"
    cur.execute(
        """select u.id, u.login_id, u.user_name, u.password_hash, u.status, u.fail_count, r.role_code, r.role_name,
                  coalesce(extract(epoch from u.password_changed_at)::bigint, 0) as password_version
             from sys_user u join sys_role r on r.id = u.role_id
            where u.login_id = %s""", (login_id,))
    u = cur.fetchone()
    if u is None:
        _log(audit.LOGIN_FAIL, login_id[:50] or None, None, client_ip, "미등록 ID", device)
        return LoginResult(False, reason=BAD_CREDENTIALS)
    if u["status"] != STATUS_ACTIVE:
        _log(audit.LOGIN_FAIL, u["login_id"], u["id"], client_ip, f"{u['status']} 계정", device)
        return LoginResult(False, reason=f"{u['status']} 상태 계정은 로그인할 수 없습니다")
    if not verify(password or "", u["password_hash"]):
        fails = int(u["fail_count"] or 0) + 1
        lock = get_settings().login_lock_count
        locked = lock is not None and fails >= lock
        cur.execute("update sys_user set fail_count = %s, status = case when %s then %s else status end where id = %s",
                    (fails, locked, STATUS_LOCKED, u["id"]))
        _log(audit.LOGIN_FAIL, u["login_id"], u["id"], client_ip, f"비밀번호 불일치 ({fails}회)" + (" · 잠금" if locked else ""), device)
        return LoginResult(False, reason=BAD_CREDENTIALS)
    session_id = secrets.token_urlsafe(24)
    cur.execute("update sys_user set fail_count = 0, last_login_at = now() where id = %s", (u["id"],))
    cur.execute(
        """insert into sys_session (session_id, user_id, device, issued_at, expires_at, password_version, created_by)
           values (%s, %s, %s, now(), now() + make_interval(secs => %s), %s, %s)""",
        (session_id, u["id"], device, SESSION_MAX_AGE_SECONDS, u["password_version"], u["login_id"]))
    _log(audit.LOGIN_OK, u["login_id"], u["id"], client_ip, "로그인 성공", device)
    user = User(id=u["id"], login_id=u["login_id"], user_name=u["user_name"], role_code=u["role_code"], role_name=u["role_name"],
                device=device)
    return LoginResult(True, session=Session(session_id=session_id, user=user, device=device))


def logout(cur, session_id: str) -> int:
    """그 세션을 서버에서 무효로 만든다 — 로그아웃 전의 쿠키를 다시 써도 통하지 않는다."""
    cur.execute("update sys_session set revoked_at = now() where session_id = %s and revoked_at is null", (session_id,))
    return cur.rowcount


def revoke_user_sessions(cur, user_id: int) -> int:
    """F-SYS-03 중지 · 비밀번호 재설정 때 — 그 사용자의 세션 전부."""
    cur.execute("update sys_session set revoked_at = now() where user_id = %s and revoked_at is null", (user_id,))
    return cur.rowcount


# ── 요청 쪽 ────────────────────────────────────────────────────────────
def device_of(request) -> str:
    q = request.query_params.get("device")
    if q in nav.DEVICE_CHANNEL:
        return q
    s = request.session.get(rbac.DEVICE_SESSION_KEY) if hasattr(request, "session") else None
    return s if s in nav.DEVICE_CHANNEL else "web"


def home_path_for(user: User, device: str) -> str:
    """로그인 직후 갈 곳 — POP · 현황판 · 모바일로 연 세션은 그 채널의 첫 화면(조회 가능한 것), 아니면 메인."""
    if device in nav.DEVICE_CHANNEL and device != "web":
        from . import packs
        for sid in packs.current().channels.get(device, []):
            if sid in nav._BY_ID and user.can_open(sid):
                return nav.path_of(sid)
    return "/"


def authenticate(request, login_id: str, password: str, device: str | None) -> LoginResult:
    with conn.tx() as cur:
        result = login(cur, login_id, password, device, client_ip=audit.client_ip(request))
    return result


def open_session(request, session: Session) -> None:
    request.session.clear()
    request.session[rbac.SESSION_ID_KEY] = session.session_id
    request.session[rbac.DEVICE_SESSION_KEY] = session.device
    rbac.forget_user(request)


def close_session(request) -> None:
    user = rbac.current_user(request)
    session_id = request.session.get(rbac.SESSION_ID_KEY)
    if session_id:
        with conn.tx() as cur:
            logout(cur, str(session_id))
    if user is not None:
        audit.write_log(kind=audit.LOGIN_OK, login_id=user.login_id, user_id=user.id, screen_id="CMN-01", detail="로그아웃",
                        ip=audit.client_ip(request), device=device_of(request))
    request.session.clear()
    rbac.forget_user(request)


def require_collect_token(request) -> None:
    """`POST /ifc/collect` 의 인증 — `X-Collect-Token` = `MES_COLLECT_TOKEN`. 토큰이 설정돼 있지 않으면 전부 401."""
    token = get_settings().collect_token
    given = request.headers.get("x-collect-token") or ""
    if not token or not hmac.compare_digest(given, token):
        raise http.unauthorized("수집 토큰이 올바르지 않습니다")
