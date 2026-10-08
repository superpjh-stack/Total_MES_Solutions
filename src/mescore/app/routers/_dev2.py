"""개발2 라우터 공용 — 폼 값 해석 · 스캔 진입 422 재렌더 · 조회 기간 기본값. (`_` 로 시작하므로 main.py 가 include 하지 않는다)"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from .. import templating
from ..packs import t
from ..util import http


def field_error(name: str, label: str, reason: str) -> dict:
    return {"name": name, "label": t(label), "reason": reason}


def req_text(value: str | None, name: str, label: str) -> str:
    v = (value or "").strip()
    if not v:
        raise http.validation_error(t("필수 항목이 비었습니다"), fields=[field_error(name, label, t("필수"))])
    return v


def opt_text(value: str | None) -> str | None:
    v = (value or "").strip()
    return v or None


def num(value, name: str, label: str, *, required: bool = False, positive: bool = False, nonneg: bool = False) -> Decimal | None:
    if value is None or str(value).strip() == "":
        if required:
            raise http.validation_error(t("필수 항목이 비었습니다"), fields=[field_error(name, label, t("필수"))])
        return None
    try:
        d = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        raise http.validation_error(t("숫자여야 합니다"), fields=[field_error(name, label, str(value))]) from None
    if positive and d <= 0:
        raise http.validation_error(t("0 보다 커야 합니다"), fields=[field_error(name, label, str(d))])
    if nonneg and d < 0:
        raise http.validation_error(t("0 이상이어야 합니다"), fields=[field_error(name, label, str(d))])
    return d


def int_id(value, name: str, label: str, *, required: bool = False) -> int | None:
    if value is None or str(value).strip() == "":
        if required:
            raise http.validation_error(t("필수 항목이 비었습니다"), fields=[field_error(name, label, t("필수"))])
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        raise http.validation_error(t("선택 값이 올바르지 않습니다"), fields=[field_error(name, label, str(value))]) from None


def a_date(value, name: str, label: str, *, default: date | None = None, required: bool = False) -> date | None:
    if value is None or str(value).strip() == "":
        if required and default is None:
            raise http.validation_error(t("필수 항목이 비었습니다"), fields=[field_error(name, label, t("필수"))])
        return default
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise http.validation_error(t("날짜 형식(YYYY-MM-DD)이 아닙니다"), fields=[field_error(name, label, str(value))]) from None


def now() -> datetime:
    """시간대가 붙은 지금 — DB timestamptz 와 비교할 수 있게."""
    return datetime.now().astimezone()


def aware(v: datetime | None) -> datetime | None:
    return v if v is None or v.tzinfo is not None else v.astimezone()


def a_datetime(value, name: str, label: str, *, default: datetime | None = None) -> datetime | None:
    if value is None or str(value).strip() == "":
        return aware(default)
    try:
        return aware(datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")))
    except ValueError:
        raise http.validation_error(t("일시 형식이 아닙니다"), fields=[field_error(name, label, str(value))]) from None


def period(frm: str | None, to: str | None, days: int = 30) -> tuple[date, date]:
    """조회 기간 — 비면 오늘까지 최근 `days` 일."""
    t2 = a_date(to, "to", "기간 끝", default=date.today())
    f = a_date(frm, "frm", "기간 시작", default=t2 - timedelta(days=days))
    if f > t2:
        raise http.validation_error(t("기간 시작이 끝보다 늦습니다"), fields=[field_error("frm", "기간 시작", f"{f} > {t2}")])
    return f, t2


def choice(value: str | None, name: str, label: str, allowed: tuple[str, ...], *, required: bool = True) -> str | None:
    v = (value or "").strip()
    if not v:
        if required:
            raise http.validation_error(t("필수 항목이 비었습니다"), fields=[field_error(name, label, t("필수"))])
        return None
    if v not in allowed:
        raise http.validation_error(t("허용되지 않는 값입니다"), fields=[field_error(name, label, f"{v} ∉ {list(allowed)}")])
    return v


def scan_miss(request, template: str, ctx: dict[str, Any], *, screen_id: str, no: str, what: str = "LOT"):
    """스캔 진입 GET `?no=` 의 없는 번호 — **그 화면을 422 로 다시 그린다**(api-contract.md §2 · S-11). JSON 은 ctx + code/message/fields."""
    message = t("없는 번호입니다")
    ctx = dict(ctx, scan_no=no, scan_error=message, code="validation_error", message=message,
               fields=[field_error("no", what, no)])
    return templating.render(request, template, ctx, screen_id=screen_id, status_code=422)


def list_form(form, name: str) -> list[str]:
    """같은 이름의 폼 칸 여러 개(항목 N줄) — 없으면 []."""
    return [str(v) for v in form.getlist(name)] if hasattr(form, "getlist") else list(form.get(name) or [])


def options(rows, id_key: str, *label_keys: str) -> list[tuple]:
    """select 매크로용 [(값, 표시), …]."""
    return [(r[id_key], " ".join(str(r[k]) for k in label_keys if r.get(k) is not None)) for r in rows]
