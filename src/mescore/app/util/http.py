"""오류 규약 — `contracts/api-contract.md` · `goal.md` §2.5. (`interfaces.md` §8)

| 상황 | status | code | 메시지 |
|---|---|---|---|
| 필수값 누락 · 코드 중복 · 없는 LOT 스캔 · 재출하 · 자기 자신 계보 · 측정값 필수 누락 | 422 | validation_error | 항목별 사유 |
| 팩 훅 거부 (`HookError`) | 422 | hook_rejected | 훅이 준 문장 |
| 인증 실패 | 401 | unauthorized | 로그인이 필요합니다 (브라우저 GET 은 /login 303) |
| 권한 없음 · 숨긴 메뉴 · 채널 밖 | 403 | forbidden | 접근 권한이 없습니다 |
| 대상 없음 (경로의 키) | 404 | not_found | 대상을 찾을 수 없습니다 |
| DB 연결 실패 | 503 | db_unavailable | 서비스 일시 중단 |
| ERP · 미확정 연계 | 501 | undecided | … 미확정 (D-nn) |
| 처리되지 않은 예외 | 500 | internal_error | 예상하지 못한 오류 |

**조용한 실패 금지.** 오류를 잡아 기본값으로 대체하지 않는다. 여기 정의된 예외로 올린다.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl

from fastapi import HTTPException

ERRORS: dict[str, tuple[int, str]] = {
    "validation_error": (422, "입력값을 확인해 주세요"),
    "hook_rejected": (422, "업종 규칙이 거부했습니다"),
    "unauthorized": (401, "로그인이 필요합니다"),
    "forbidden": (403, "접근 권한이 없습니다"),
    "not_found": (404, "대상을 찾을 수 없습니다"),
    "db_unavailable": (503, "서비스 일시 중단"),
    "undecided": (501, "미확정"),
    "internal_error": (500, "예상하지 못한 오류"),
}

FLASH_KEY = "flash"
AFTER_COMMIT_ATTR = "after_commit_events"
FORM_ECHO_KEY = "mes.form_body"          # scope 키 — FormEcho 가 urlencoded POST 본문을 복사해 둔다(422 뒤 입력값 유지)
FORM_ECHO_MAX = 64 * 1024                # 이보다 큰 본문은 복사하지 않는다
#: 422 뒤 되돌려 주지 않는 칸 — 비밀번호 · 토큰 (G-C19)
SECRET_FIELD_HINTS = ("password", "passwd", "secret", "token", "csrf")
VALUE_MAX = 2000                         # 칸 하나의 길이 상한(세션 쿠키 크기)


class HookError(Exception):
    """팩 훅이 올린다 → `main.py` 가 422 `hook_rejected` 로 바꾼다 (D-06). 같은 트랜잭션이 통째로 되돌림된다."""

    def __init__(self, message: str, *, fields: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.fields = fields or []


def clean_values(values: dict | None) -> dict[str, Any]:
    """폼 값 → 알림에 실어 되돌릴 값. 비밀 칸 제외 · 문자열 길이 상한 · 같은 이름 여러 값은 목록."""
    out: dict[str, Any] = {}
    for k, v in (values or {}).items():
        k = str(k)
        if any(h in k.lower() for h in SECRET_FIELD_HINTS):
            continue
        if isinstance(v, (list, tuple)):
            out[k] = [str(x)[:VALUE_MAX] for x in v]
        elif v is not None:
            out[k] = str(v)[:VALUE_MAX]
    return out


def posted_values(request) -> dict[str, Any]:
    """이 요청의 urlencoded POST 본문(FormEcho 가 복사) → {이름: 값 | [값…]}. 없으면 {} (multipart · 큰 본문 · 다른 메서드)."""
    scope = getattr(request, "scope", None) or {}
    body = scope.get(FORM_ECHO_KEY)
    if not body:
        return {}
    out: dict[str, Any] = {}
    for k, v in parse_qsl(body.decode("utf-8", errors="replace"), keep_blank_values=True):
        if k in out:
            out[k] = (out[k] if isinstance(out[k], list) else [out[k]]) + [v]
        else:
            out[k] = v
    return clean_values(out)


class FormEcho:
    """순수 ASGI 미들웨어 — `application/x-www-form-urlencoded` POST 본문을 흘려보내며 `scope["mes.form_body"]` 에 복사한다.
    본문을 소비하지 않는다(라우터는 그대로 읽는다). 422 핸들러가 `posted_values` 로 입력값을 알림에 싣는다(api-contract.md §2)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        ctype = dict(scope.get("headers") or []).get(b"content-type", b"")
        if not ctype.startswith(b"application/x-www-form-urlencoded"):
            return await self.app(scope, receive, send)
        chunks: list[bytes] = []
        size = 0

        async def recv():
            nonlocal size
            msg = await receive()
            if msg.get("type") == "http.request":
                body = msg.get("body", b"")
                size += len(body)
                if size <= FORM_ECHO_MAX:
                    chunks.append(body)
                    if not msg.get("more_body", False):
                        scope[FORM_ECHO_KEY] = b"".join(chunks)
                else:
                    scope.pop(FORM_ECHO_KEY, None)
            return msg

        return await self.app(scope, recv, send)


def flash(request, title: str, message: str, *, fields: list[dict] | None = None, kind: str = "info",
          values: dict | None = None) -> None:
    """알림 한 번. `values` = 422 뒤 폼에 다시 채울 입력값 `{이름: 값 | [값…]}`(비밀 칸 제외) — 템플릿은 `flash.values` 로 읽는다."""
    if not hasattr(request, "session"):
        return
    request.session[FLASH_KEY] = {"title": title, "message": message, "kind": kind, "fields": fields or [],
                                  "values": clean_values(values)}


def pop_flash(request) -> dict | None:
    if not hasattr(request, "session"):
        return None
    return request.session.pop(FLASH_KEY, None)


def wants_html(request) -> bool:
    return "text/html" in (request.headers.get("accept") or "")


def saved(request, message: str = "저장했습니다", *, back: str | None = None, data: dict | None = None):
    """쓰기 성공 규약. 브라우저(HTML)는 알림을 남기고 원래 화면으로 303, 그 밖(JSON · 테스트)은 200 JSON.

        return http.saved(request, t("품목을 등록했습니다"), data={"id": new_id})
    """
    from fastapi.responses import JSONResponse, RedirectResponse  # noqa

    if not wants_html(request):
        return JSONResponse({"ok": True, "message": message, **(data or {})})
    flash(request, "알림", message, kind="ok")
    return RedirectResponse(back or request.headers.get("referer") or "/", status_code=303)


def after_commit(request, event: str, payload: dict) -> None:
    """커밋 뒤 `after_commit_<event>(payload)` 훅을 부르도록 큐에 넣는다 — `main.py` 미들웨어가 응답 뒤에 비운다 (D-20)."""
    if not hasattr(request, "state"):
        return
    queue = getattr(request.state, AFTER_COMMIT_ATTR, None)
    if queue is None:
        queue = []
        setattr(request.state, AFTER_COMMIT_ATTR, queue)
    queue.append((event, payload))


def err(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    detail.update({k: v for k, v in extra.items() if v is not None})
    return HTTPException(status_code=status, detail=detail)


def _by_code(code: str, message: str | None = None, **extra: Any) -> HTTPException:
    status, default = ERRORS[code]
    return err(status, code, message or default, **extra)


def validation_error(message: str | None = None, *, fields: list[dict] | None = None, values: dict | None = None) -> HTTPException:
    """422. `fields` 는 [{'name': 컬럼 식별자, 'label': 치환어, 'reason': …}].
    `values` = 브라우저 폼 POST 가 303 으로 돌아갈 때 다시 채울 입력값(주지 않으면 요청 본문에서 — `posted_values`). JSON 응답에는 싣지 않는다."""
    return _by_code("validation_error", message, fields=fields or [], values=clean_values(values) if values else None)


def sort_clause(sort: str | None, allowed: dict[str, str] | list[str] | tuple[str, ...], default: str) -> str:
    """목록 화면 `?sort=` 의 공용 해석 — **허용한 열만** SQL `order by` 본문으로(D-37). `sort` = `열` · `-열`(내림) · 쉼표로 여럿.
    `allowed` = {공개 이름: SQL 식} 또는 이름 목록(이름 = 식). 비면 `default`(라우터가 쓴 SQL 그대로). 모르는 열 → 422(조용히 무시하지 않는다).

        order = http.sort_clause(sort, {"no": "w.work_order_no", "date": "w.plan_date"}, "w.id desc")
        conn.q(f"select … order by {order} limit %s", …)
    """
    if not sort or not sort.strip():
        return default
    table = dict(allowed) if isinstance(allowed, dict) else {a: a for a in allowed}
    parts, bad = [], []
    for raw in sort.split(","):
        name = raw.strip()
        if not name:
            continue
        desc = name.startswith("-")
        name = name.lstrip("+-").strip()
        if name not in table:
            bad.append(name)
            continue
        parts.append(f"{table[name]} {'desc' if desc else 'asc'}")
    if bad:
        raise validation_error("정렬할 수 없는 열입니다", fields=[{"name": "sort", "label": "정렬", "reason": f"{bad} — 허용 {sorted(table)}"}])
    return ", ".join(parts) or default


def hook_rejected(exc: HookError) -> HTTPException:
    return _by_code("hook_rejected", exc.message, fields=exc.fields)


def unauthorized(message: str | None = None) -> HTTPException:
    return _by_code("unauthorized", message)


def forbidden(message: str | None = None, **extra: Any) -> HTTPException:
    return _by_code("forbidden", message, **extra)


def not_found(message: str | None = None) -> HTTPException:
    return _by_code("not_found", message)


def db_unavailable(message: str | None = None) -> HTTPException:
    return _by_code("db_unavailable", message)


def undecided(decision: str, what: str = "") -> HTTPException:
    """501 — 사람이 아직 정하지 않은 것. `undecided("D-02", "ERP 연계")` → `ERP 연계 미확정 (D-02)`."""
    label = f"{what} 미확정 ({decision})" if what else f"미확정 ({decision})"
    return _by_code("undecided", label, decision=decision)


def status_message(status: int) -> str:
    for _code, (st, msg) in ERRORS.items():
        if st == status:
            return msg
    return "오류가 발생했습니다"


def code_for_status(status: int) -> str:
    for code, (st, _msg) in ERRORS.items():
        if st == status:
            return code
    return "error"


SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
}
