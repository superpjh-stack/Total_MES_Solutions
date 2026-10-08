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


class HookError(Exception):
    """팩 훅이 올린다 → `main.py` 가 422 `hook_rejected` 로 바꾼다 (D-06). 같은 트랜잭션이 통째로 되돌림된다."""

    def __init__(self, message: str, *, fields: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.fields = fields or []


def flash(request, title: str, message: str, *, fields: list[dict] | None = None, kind: str = "info") -> None:
    if not hasattr(request, "session"):
        return
    request.session[FLASH_KEY] = {"title": title, "message": message, "kind": kind, "fields": fields or []}


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


def validation_error(message: str | None = None, *, fields: list[dict] | None = None) -> HTTPException:
    """422. `fields` 는 [{'name': 컬럼 식별자, 'label': 치환어, 'reason': …}]."""
    return _by_code("validation_error", message, fields=fields or [])


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
