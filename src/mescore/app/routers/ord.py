"""ord 라우터 — 수주 · 이력 · 납기 달력 · 생산계획 (기능 10 · F-ORD-01~10) · 담당 개발3.

쓰는 테이블: `ord_order` `ord_order_dtl` `ord_order_hist` `ord_plan` 뿐 (db-schema.md §2). 작업지시 · 출하에는 쓰지 않는다 — 상세별 지시 · 출하 수량은 읽어서 계산한다.
번호는 `numbering.next("ORDER" | "PLAN", cur=cur)` (개발1). 저장 순서: 검증 → `validate_<table>` 훅 → tx → `after_save_<table>`(D-504) → `audit.log_change` → `http.saved`.
훅 자리: F-ORD-01 `on_order_created` · F-ORD-02/03 `on_order_status_changed`(D-505 — 상태가 바뀔 때만).
집계(납기 달력)는 `stats.delivery` 만 부른다 — 이 파일에 집계 SQL 은 없다.

  ORD-01 수주       GET/POST /ord/orders · POST /ord/orders/{id} · /cancel
  ORD-02 수주 이력   GET /ord/order-history
  ORD-03 납기 달력   GET /ord/delivery-calendar (모바일 390px — 주 단위 접힘)
  ORD-04 생산계획    GET/POST /ord/plans · POST /ord/plans/{id} · /confirm
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ...db import conn
from .. import nav, packs, rbac, stats, templating
from ..packs import t
from ..util import audit, http

router = APIRouter()

REGISTERED, IN_PROGRESS, DONE, CANCELED = "등록", "진행", "완료", "취소"
ORDER_STATUSES: tuple[str, ...] = (REGISTERED, IN_PROGRESS, DONE, CANCELED)
PLANNED, CONFIRMED, PLAN_CANCELED = "계획", "확정", "취소"
PLAN_STATUSES: tuple[str, ...] = (PLANNED, CONFIRMED, PLAN_CANCELED)
LIST_LIMIT = 300
WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def _numbering():
    from .. import numbering  # noqa: PLC0415 — 개발1 모듈 (없으면 ModuleNotFoundError → 500, 번호를 지어내지 않는다)
    return numbering


# ── 공통 ───────────────────────────────────────────────────────────────
def _date(text: str | None, label: str, *, required: bool = False) -> date | None:
    try:
        d = stats.parse_date(text)
    except ValueError:
        raise http.validation_error(t("날짜 형식(YYYY-MM-DD)이 아닙니다"), fields=[{"name": label, "label": t(label), "reason": text}]) from None
    if d is None and required:
        raise http.validation_error(t("필수값을 입력해 주세요"), fields=[{"name": label, "label": t(label), "reason": t("비어 있음")}])
    return d


def _qty(text: str | None, label: str = "qty") -> Decimal:
    try:
        q = Decimal(str(text or "").strip().replace(",", ""))
    except InvalidOperation:
        raise http.validation_error(t("수량은 숫자여야 합니다"), fields=[{"name": label, "label": t("수량"), "reason": text}]) from None
    if q <= 0:
        raise http.validation_error(t("수량은 0 보다 커야 합니다"), fields=[{"name": label, "label": t("수량"), "reason": str(q)}])
    return q


def _partner(code: str) -> dict:
    row = conn.q1("select id, partner_code, partner_name from bas_partner where partner_code = %s and use_yn = 'Y'", (code.strip(),))
    if row is None:
        raise http.validation_error(t("없는 거래처입니다"), fields=[{"name": "partner_code", "label": t("거래처"), "reason": code}])
    return row


def _item(code: str) -> dict:
    row = conn.q1("select id, item_code, item_name, unit from bas_item where item_code = %s and use_yn = 'Y'", (code.strip(),))
    if row is None:
        raise http.validation_error(t("없는 품목입니다"), fields=[{"name": "item_code", "label": t("품목"), "reason": code}])
    return row


def _order(order_id: int) -> dict:
    row = conn.q1("""select o.*, p.partner_code, p.partner_name from ord_order o join bas_partner p on p.id = o.partner_id where o.id = %s""", (order_id,))
    if row is None:
        raise http.not_found()
    return row


def _lines(order_id: int) -> list[dict]:
    """상세 + 지시 수량 · 출하 수량 (읽기 — job · shp 테이블을 읽어 계산한다)."""
    return _lines_of([order_id]).get(order_id, [])


def _lines_of(order_ids: list[int]) -> dict[int, list[dict]]:
    """수주 여러 건의 상세를 한 번에 — {order_id: [상세…]} (ORD-01 목록의 모든 수주 · 상세 N줄 펼침)."""
    if not order_ids:
        return {}
    rows = conn.q("""
        select d.order_id, d.id, d.line_no, d.item_id, i.item_code, i.item_name, d.qty, d.unit, d.status,
               (select count(*)::int from job_work_order w where w.order_dtl_id = d.id and w.status <> '취소') as wo_count,
               (select sum(w.plan_qty) from job_work_order w where w.order_dtl_id = d.id and w.status <> '취소') as wo_qty,
               (select sum(g.qty) from lot_genealogy g join lot x on x.id = g.child_lot_id join lot p on p.id = g.parent_lot_id
                  join shp_shipment s on s.id = x.shipment_id
                 where g.relation_base = '출하' and s.order_id = d.order_id and s.status <> '취소' and p.item_id = d.item_id) as shipped_qty
          from ord_order_dtl d join bas_item i on i.id = d.item_id
         where d.order_id = any(%s) order by d.order_id, d.line_no""", (list(order_ids),))
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["order_id"], []).append(r)
    return out


def _hist(cur, order_id: int, field: str, before, after, by: str) -> None:
    cur.execute("""insert into ord_order_hist (order_id, changed_by, field, before_value, after_value, created_by) values (%s, %s, %s, %s, %s, %s)""",
                (order_id, by, field, None if before is None else str(before), None if after is None else str(after), by))


def _read_lines(request: Request, item_codes: list[str], qtys: list[str], units: list[str]) -> list[dict]:
    if not item_codes or len(item_codes) != len(qtys):
        raise http.validation_error(t("상세를 한 줄 이상 입력해 주세요"), fields=[{"name": "item_code", "label": t("품목"), "reason": t("비어 있음")}])
    lines = []
    for i, (code, qty) in enumerate(zip(item_codes, qtys), start=1):
        if not (code or "").strip() and not (qty or "").strip():
            continue
        item = _item(code or "")
        unit = (units[i - 1] if i - 1 < len(units) else "") or item["unit"]
        lines.append({"line_no": len(lines) + 1, "item_id": item["id"], "item_code": item["item_code"], "qty": _qty(qty, f"qty[{i}]"), "unit": unit or None})
    if not lines:
        raise http.validation_error(t("상세를 한 줄 이상 입력해 주세요"), fields=[{"name": "item_code", "label": t("품목"), "reason": t("비어 있음")}])
    return lines


# ── ORD-01 수주 ───────────────────────────────────────────────────────
@router.get(nav.path_of("ORD-01"), response_class=HTMLResponse)                     # F-ORD-04 수주 조회 = 화면 GET
def orders(request: Request, frm: str = "", to: str = "", partner: str = "", status: str = "", id: str = "",
           user: rbac.User = rbac.require_fn("F-ORD-04")):
    if status and status not in ORDER_STATUSES:
        raise http.validation_error(t("상태가 올바르지 않습니다"), fields=[{"name": "status", "label": t("상태"), "reason": status}])
    d1, d2 = _date(frm, "frm"), _date(to, "to")
    rows = conn.q(f"""
        select o.id, o.order_no, o.order_date, o.due_date, o.status, o.note, p.partner_code, p.partner_name,
               (select count(*)::int from ord_order_dtl d where d.order_id = o.id) as line_count,
               (select sum(d.qty) from ord_order_dtl d where d.order_id = o.id) as qty,
               (select count(*)::int from job_work_order w where w.order_dtl_id in (select id from ord_order_dtl where order_id = o.id) and w.status <> '취소') as wo_count,
               (select count(*)::int from shp_shipment s where s.order_id = o.id and s.status = '승인') as shipped_count,
               count(*) over ()::int as total_count
          from ord_order o join bas_partner p on p.id = o.partner_id
         where (%(d1)s::date is null or o.order_date >= %(d1)s::date) and (%(d2)s::date is null or o.order_date <= %(d2)s::date)
           and (%(partner)s::text is null or p.partner_code ilike '%%' || %(partner)s::text || '%%' or p.partner_name ilike '%%' || %(partner)s::text || '%%')
           and (%(status)s::text is null or o.status = %(status)s::text)
         order by o.order_date desc, o.id desc limit {LIST_LIMIT}""",
                  {"d1": d1, "d2": d2, "partner": partner.strip() or None, "status": status or None})
    total = rows[0]["total_count"] if rows else 0                                   # 조건에 맞는 전체 건수 (상한 LIST_LIMIT 밖 포함)
    by_order = _lines_of([r["id"] for r in rows])
    for r in rows:
        r.pop("total_count", None)
        r["lines"] = by_order.get(r["id"], [])                                       # 모든 수주의 상세 N줄 (디자이너1 원형 tr.dtl)
    opened, lines = None, []
    if id.strip():
        if not id.strip().isdigit():
            raise http.not_found()
        opened = _order(int(id))
        lines = _lines(opened["id"])
    partners = conn.q("select partner_code, partner_name from bas_partner where use_yn = 'Y' order by partner_code")
    items = conn.q("select item_code, item_name, unit from bas_item where use_yn = 'Y' order by item_code")
    return templating.render(request, "ord/orders.html", {
        "rows": rows, "total": total, "limit": LIST_LIMIT, "opened": opened, "lines": lines, "partners": partners, "items": items, "statuses": ORDER_STATUSES,
        "today": date.today(), "attr_specs": packs.attrs_of("ord_order"),
        "q": {"frm": frm, "to": to, "partner": partner, "status": status},
    }, screen_id="ORD-01")


@router.post(nav.path_of("ORD-01"))                                                  # F-ORD-01 수주 등록
def create_order(request: Request, partner_code: str = Form(""), order_date: str = Form(""), due_date: str = Form(""), note: str = Form(""),
                 item_code: list[str] = Form([]), qty: list[str] = Form([]), unit: list[str] = Form([]),
                 user: rbac.User = rbac.require_fn("F-ORD-01")):
    if not partner_code.strip():
        raise http.validation_error(t("필수값을 입력해 주세요"), fields=[{"name": "partner_code", "label": t("거래처"), "reason": t("비어 있음")}])
    partner = _partner(partner_code)
    d_order = _date(order_date, "order_date") or date.today()
    d_due = _date(due_date, "due_date")
    lines = _read_lines(request, item_code, qty, unit)
    try:
        attrs = packs.read_attrs(request, "ord_order")
    except ValueError as exc:
        raise http.validation_error(str(exc)) from None
    with conn.tx() as cur:
        order_no = _numbering().next("ORDER", cur=cur)
        row = {"order_no": order_no, "partner_id": partner["id"], "order_date": d_order, "due_date": d_due, "status": REGISTERED,
               "note": note.strip() or None, "attrs": attrs, "lines": lines}
        packs.hook("validate_ord_order")(cur, row, user)
        cur.execute("""insert into ord_order (order_no, partner_id, order_date, due_date, status, note, attrs, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s) returning id""",
                    (order_no, partner["id"], d_order, d_due, REGISTERED, row["note"], json.dumps(attrs, ensure_ascii=False), user.login_id))
        row["id"] = cur.fetchone()["id"]
        for ln in lines:
            dtl = {"order_id": row["id"], **ln}
            packs.hook("validate_ord_order_dtl")(cur, dtl, user)
            cur.execute("""insert into ord_order_dtl (order_id, line_no, item_id, qty, unit, created_by) values (%s, %s, %s, %s, %s, %s) returning id""",
                        (row["id"], ln["line_no"], ln["item_id"], ln["qty"], ln["unit"], user.login_id))
            dtl["id"] = cur.fetchone()["id"]
            packs.hook("after_save_ord_order_dtl")(cur, dtl, user)
        packs.hook("after_save_ord_order")(cur, row, user)                               # D-504
        _hist(cur, row["id"], "등록", None, order_no, user.login_id)
        packs.hook("on_order_created")(cur, row, user)                                   # interfaces.md §9
    audit.log_change(request, user, "F-ORD-01", f"ord_order:{order_no}", {"lines": len(lines)})
    return http.saved(request, t("수주를 등록했습니다") + f" — {order_no}", back=f"{nav.path_of('ORD-01')}?id={row['id']}",
                      data={"id": row["id"], "order_no": order_no, "lines": len(lines)})


@router.post(nav.path_of("ORD-01") + "/{order_id}")                                   # F-ORD-02 수주 수정
def update_order(request: Request, order_id: int, due_date: str = Form(None), note: str = Form(None), status: str = Form(None),
                 dtl_id: list[str] = Form([]), item_code: list[str] = Form([]), qty: list[str] = Form([]), unit: list[str] = Form([]),
                 user: rbac.User = rbac.require_fn("F-ORD-02")):
    order = _order(order_id)
    if order["status"] == CANCELED:
        raise http.validation_error(t("취소된 수주는 수정할 수 없습니다"), fields=[{"name": "status", "label": t("상태"), "reason": order["status"]}])
    if status is not None and status and status not in (REGISTERED, IN_PROGRESS, DONE):
        raise http.validation_error(t("상태가 올바르지 않습니다"), fields=[{"name": "status", "label": t("상태"), "reason": status}])
    new_due = _date(due_date, "due_date") if due_date is not None else order["due_date"]
    lines = {ln["id"]: ln for ln in _lines(order_id)}
    edits = []
    for i, did in enumerate(dtl_id):
        if not str(did).strip().isdigit() or int(did) not in lines:
            raise http.validation_error(t("없는 수주 상세입니다"), fields=[{"name": "dtl_id", "label": t("수주"), "reason": str(did)}])
        cur_line = lines[int(did)]
        code = (item_code[i] if i < len(item_code) else "") or cur_line["item_code"]
        item = _item(code)
        new_qty = _qty(qty[i], f"qty[{i + 1}]") if i < len(qty) and (qty[i] or "").strip() else cur_line["qty"]
        new_unit = (unit[i] if i < len(unit) else "") or cur_line["unit"]
        if item["id"] != cur_line["item_id"] and cur_line["wo_count"]:
            raise http.validation_error(t("작업지시가 붙은 상세의 품목은 바꿀 수 없습니다"),
                                        fields=[{"name": "item_code", "label": t("품목"), "reason": f"{cur_line['item_code']} → {code}"}])
        edits.append((cur_line, item, new_qty, new_unit))
    with conn.tx() as cur:
        row = {**order, "due_date": new_due, "note": note.strip() if note is not None else order["note"], "status": status or order["status"]}
        packs.hook("validate_ord_order")(cur, row, user)
        cur.execute("update ord_order set due_date = %s, note = %s, status = %s, updated_at = now(), updated_by = %s where id = %s",
                    (row["due_date"], row["note"], row["status"], user.login_id, order_id))
        if row["due_date"] != order["due_date"]:
            _hist(cur, order_id, "due_date", order["due_date"], row["due_date"], user.login_id)
        for cur_line, item, new_qty, new_unit in edits:
            dtl = {**cur_line, "item_id": item["id"], "qty": new_qty, "unit": new_unit}
            packs.hook("validate_ord_order_dtl")(cur, dtl, user)
            cur.execute("update ord_order_dtl set item_id = %s, qty = %s, unit = %s, updated_at = now(), updated_by = %s where id = %s",
                        (item["id"], new_qty, new_unit, user.login_id, cur_line["id"]))
            if Decimal(str(new_qty)) != Decimal(str(cur_line["qty"])):
                _hist(cur, order_id, f"qty[{cur_line['line_no']}]", cur_line["qty"], new_qty, user.login_id)
            if item["id"] != cur_line["item_id"]:
                _hist(cur, order_id, f"item[{cur_line['line_no']}]", cur_line["item_code"], item["item_code"], user.login_id)
            packs.hook("after_save_ord_order_dtl")(cur, dtl, user)
        packs.hook("after_save_ord_order")(cur, row, user)
        if row["status"] != order["status"]:
            _hist(cur, order_id, "status", order["status"], row["status"], user.login_id)
            packs.hook("on_order_status_changed")(cur, {**row, "before_status": order["status"]}, user)   # D-505
    audit.log_change(request, user, "F-ORD-02", f"ord_order:{order['order_no']}")
    return http.saved(request, t("수주를 수정했습니다"), back=f"{nav.path_of('ORD-01')}?id={order_id}", data={"id": order_id, "order_no": order["order_no"]})


@router.post(nav.path_of("ORD-01") + "/{order_id}/cancel")                            # F-ORD-03 수주 취소
def cancel_order(request: Request, order_id: int, user: rbac.User = rbac.require_fn("F-ORD-03")):
    order = _order(order_id)
    if order["status"] == CANCELED:
        raise http.validation_error(t("이미 취소된 수주입니다"), fields=[{"name": "status", "label": t("상태"), "reason": order["status"]}])
    running = conn.q("""select w.work_order_no, w.status from job_work_order w join ord_order_dtl d on d.id = w.order_dtl_id
                         where d.order_id = %s and w.status in ('대기', '진행') order by w.work_order_no""", (order_id,))
    if running:
        raise http.validation_error(t("진행 중인 작업지시가 있어 취소할 수 없습니다"),
                                    fields=[{"name": "work_order_no", "label": t("작업지시"), "reason": f"{w['work_order_no']} {w['status']}"} for w in running])
    with conn.tx() as cur:
        row = {**order, "status": CANCELED}
        packs.hook("validate_ord_order")(cur, row, user)
        cur.execute("update ord_order set status = %s, updated_at = now(), updated_by = %s where id = %s and status <> %s",
                    (CANCELED, user.login_id, order_id, CANCELED))
        if cur.rowcount != 1:
            raise http.validation_error(t("수주 상태가 바뀌어 취소하지 못했습니다"), fields=[{"name": "status", "label": t("상태"), "reason": t("다시 조회")}])
        packs.hook("after_save_ord_order")(cur, row, user)
        _hist(cur, order_id, "status", order["status"], CANCELED, user.login_id)
        packs.hook("on_order_status_changed")(cur, {**row, "before_status": order["status"]}, user)       # D-505
    audit.log_change(request, user, "F-ORD-03", f"ord_order:{order['order_no']}")
    return http.saved(request, t("수주를 취소했습니다"), back=nav.path_of("ORD-01"), data={"id": order_id, "order_no": order["order_no"], "status": CANCELED})


# ── ORD-02 수주 이력 ───────────────────────────────────────────────────
@router.get(nav.path_of("ORD-02"), response_class=HTMLResponse)                     # F-ORD-05 수주 이력 조회
def order_history(request: Request, order_no: str = "", frm: str = "", to: str = "", user: rbac.User = rbac.require_fn("F-ORD-05")):
    d1, d2 = _date(frm, "frm"), _date(to, "to")
    rows = conn.q(f"""
        select h.id, h.order_id, o.order_no, p.partner_name, h.changed_at, h.changed_by, h.field, h.before_value, h.after_value
          from ord_order_hist h join ord_order o on o.id = h.order_id join bas_partner p on p.id = o.partner_id
         where (%(no)s::text is null or o.order_no ilike '%%' || %(no)s::text || '%%')
           and (%(d1)s::date is null or h.changed_at::date >= %(d1)s::date) and (%(d2)s::date is null or h.changed_at::date <= %(d2)s::date)
         order by h.changed_at desc, h.id desc limit {LIST_LIMIT}""", {"no": order_no.strip() or None, "d1": d1, "d2": d2})
    return templating.render(request, "ord/order_history.html", {"rows": rows, "limit": LIST_LIMIT, "q": {"order_no": order_no, "frm": frm, "to": to}},
                             screen_id="ORD-02")


# ── ORD-03 납기 달력 ───────────────────────────────────────────────────
def _month(ym: str) -> tuple[date, date]:
    text = (ym or "").strip()
    try:
        first = date.fromisoformat(text + "-01") if text else date.today().replace(day=1)
    except ValueError:
        raise http.validation_error(t("월 형식(YYYY-MM)이 아닙니다"), fields=[{"name": "ym", "label": t("월"), "reason": text}]) from None
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, nxt - timedelta(days=1)


@router.get(nav.path_of("ORD-03"), response_class=HTMLResponse)                     # F-ORD-06 납기 달력 조회
def delivery_calendar(request: Request, ym: str = "", user: rbac.User = rbac.require_fn("F-ORD-06")):
    first, last = _month(ym)
    today = date.today()
    by_day = {r["day"]: r for r in stats.delivery(first, last, by="day", today=today)}      # 집계는 stats 만
    orders_of_day: dict[date, list[dict]] = {}
    for o in conn.q("""select o.id, o.order_no, o.due_date, o.status, p.partner_name,
                              exists (select 1 from shp_shipment s where s.order_id = o.id and s.status = '승인') as shipped
                         from ord_order o join bas_partner p on p.id = o.partner_id
                        where o.status <> '취소' and o.due_date between %s and %s order by o.due_date, o.order_no""", (first, last)):
        orders_of_day.setdefault(o["due_date"], []).append(o)
    days, weeks, week = [], [], []
    d = first - timedelta(days=first.weekday())
    while d <= last or len(week) % 7:
        agg = by_day.get(d) or {}
        entry = {"date": d, "in_month": first <= d <= last, "weekday": WEEKDAYS[d.weekday()], "today": d == today,
                 "due_count": agg.get("due_count", 0), "shipped_count": agg.get("shipped_count", 0), "late_count": agg.get("late", 0),
                 "pending_count": agg.get("pending", 0), "orders": orders_of_day.get(d, [])}
        if entry["in_month"]:
            days.append(entry)
        week.append(entry)
        if len(week) == 7:
            weeks.append({"start": week[0]["date"], "end": week[-1]["date"], "days": week, "open": any(x["today"] for x in week),
                          "due_count": sum(x["due_count"] for x in week), "shipped_count": sum(x["shipped_count"] for x in week),
                          "late_count": sum(x["late_count"] for x in week)})
            week = []
        d += timedelta(days=1)
    if not any(w["open"] for w in weeks) and weeks:
        weeks[0]["open"] = True
    prev_m, next_m = (first - timedelta(days=1)).strftime("%Y-%m"), (last + timedelta(days=1)).strftime("%Y-%m")
    return templating.render(request, "ord/delivery_calendar.html", {
        "ym": first.strftime("%Y-%m"), "first": first, "last": last, "prev_ym": prev_m, "next_ym": next_m, "days": days, "weeks": weeks,
        "total": {"due_count": sum(x["due_count"] for x in days), "shipped_count": sum(x["shipped_count"] for x in days),
                  "late_count": sum(x["late_count"] for x in days)}, "weekdays": WEEKDAYS,
    }, screen_id="ORD-03")


# ── ORD-04 생산계획 ────────────────────────────────────────────────────
def _plan(plan_id: int) -> dict:
    row = conn.q1("""select pl.*, i.item_code, i.item_name, o.order_no, d.line_no
                       from ord_plan pl join bas_item i on i.id = pl.item_id
                       left join ord_order_dtl d on d.id = pl.order_dtl_id left join ord_order o on o.id = d.order_id
                      where pl.id = %s""", (plan_id,))
    if row is None:
        raise http.not_found()
    return row


def _order_dtl(order_no: str, line_no: str) -> dict | None:
    if not (order_no or "").strip():
        return None
    ln = (line_no or "1").strip()
    row = conn.q1("""select d.id, d.item_id, d.qty, d.unit, o.order_no, d.line_no from ord_order_dtl d join ord_order o on o.id = d.order_id
                      where o.order_no = %s and d.line_no = %s and o.status <> '취소'""", (order_no.strip(), int(ln) if ln.isdigit() else -1))
    if row is None:
        raise http.validation_error(t("없는 수주 상세입니다"), fields=[{"name": "order_no", "label": t("수주"), "reason": f"{order_no} / {ln}"}])
    return row


@router.get(nav.path_of("ORD-04"), response_class=HTMLResponse)                     # F-ORD-10 생산계획 조회
def plans(request: Request, frm: str = "", to: str = "", item: str = "", status: str = "", id: str = "",
          user: rbac.User = rbac.require_fn("F-ORD-10")):
    if status and status not in PLAN_STATUSES:
        raise http.validation_error(t("상태가 올바르지 않습니다"), fields=[{"name": "status", "label": t("상태"), "reason": status}])
    d1, d2 = _date(frm, "frm"), _date(to, "to")
    rows = conn.q(f"""
        select pl.id, pl.plan_no, pl.plan_date, pl.plan_qty, pl.unit, pl.status, i.item_code, i.item_name, o.order_no, d.line_no,
               (select count(*)::int from job_work_order w where w.plan_id = pl.id and w.status <> '취소') as wo_count,
               (select sum(w.plan_qty) from job_work_order w where w.plan_id = pl.id and w.status <> '취소') as wo_qty,
               (select sum(r.good_qty) from pop_work_result r join job_work_order w on w.id = r.work_order_id
                 where w.plan_id = pl.id and r.ended_at is not null) as actual_qty
          from ord_plan pl join bas_item i on i.id = pl.item_id
          left join ord_order_dtl d on d.id = pl.order_dtl_id left join ord_order o on o.id = d.order_id
         where (%(d1)s::date is null or pl.plan_date >= %(d1)s::date) and (%(d2)s::date is null or pl.plan_date <= %(d2)s::date)
           and (%(item)s::text is null or i.item_code ilike '%%' || %(item)s::text || '%%' or i.item_name ilike '%%' || %(item)s::text || '%%')
           and (%(status)s::text is null or pl.status = %(status)s::text)
         order by pl.plan_date desc, pl.id desc limit {LIST_LIMIT}""", {"d1": d1, "d2": d2, "item": item.strip() or None, "status": status or None})
    opened = None
    if id.strip():
        if not id.strip().isdigit():
            raise http.not_found()
        opened = _plan(int(id))
    items = conn.q("select item_code, item_name, unit from bas_item where use_yn = 'Y' order by item_code")
    waiting = conn.q("""select o.order_no, d.line_no, i.item_code, i.item_name, d.qty, d.unit from ord_order_dtl d
                         join ord_order o on o.id = d.order_id join bas_item i on i.id = d.item_id
                        where o.status in ('등록', '진행') order by o.due_date nulls last, o.order_no, d.line_no limit 100""")
    return templating.render(request, "ord/plans.html", {
        "rows": rows, "limit": LIST_LIMIT, "opened": opened, "items": items, "waiting": waiting, "statuses": PLAN_STATUSES, "today": date.today(),
        "attr_specs": packs.attrs_of("ord_plan"), "q": {"frm": frm, "to": to, "item": item, "status": status},
    }, screen_id="ORD-04")


@router.post(nav.path_of("ORD-04"))                                                  # F-ORD-07 생산계획 등록
def create_plan(request: Request, item_code: str = Form(""), plan_date: str = Form(""), plan_qty: str = Form(""), unit: str = Form(""),
                order_no: str = Form(""), line_no: str = Form(""), user: rbac.User = rbac.require_fn("F-ORD-07")):
    dtl = _order_dtl(order_no, line_no)
    code = item_code.strip()
    if not code and dtl is None:
        raise http.validation_error(t("필수값을 입력해 주세요"), fields=[{"name": "item_code", "label": t("품목"), "reason": t("비어 있음")}])
    item = _item(code) if code else conn.q1("select id, item_code, item_name, unit from bas_item where id = %s", (dtl["item_id"],))
    day = _date(plan_date, "plan_date", required=True)
    qty = _qty(plan_qty, "plan_qty")
    try:
        attrs = packs.read_attrs(request, "ord_plan")
    except ValueError as exc:
        raise http.validation_error(str(exc)) from None
    with conn.tx() as cur:
        plan_no = _numbering().next("PLAN", cur=cur)
        row = {"plan_no": plan_no, "order_dtl_id": dtl["id"] if dtl else None, "item_id": item["id"], "plan_date": day, "plan_qty": qty,
               "unit": (unit.strip() or item["unit"] or None), "status": PLANNED, "attrs": attrs}
        packs.hook("validate_ord_plan")(cur, row, user)
        cur.execute("""insert into ord_plan (plan_no, order_dtl_id, item_id, plan_date, plan_qty, unit, status, attrs, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s) returning id""",
                    (plan_no, row["order_dtl_id"], item["id"], day, qty, row["unit"], PLANNED, json.dumps(attrs, ensure_ascii=False), user.login_id))
        row["id"] = cur.fetchone()["id"]
        packs.hook("after_save_ord_plan")(cur, row, user)
    audit.log_change(request, user, "F-ORD-07", f"ord_plan:{plan_no}")
    return http.saved(request, t("생산계획을 등록했습니다") + f" — {plan_no}", back=f"{nav.path_of('ORD-04')}?id={row['id']}",
                      data={"id": row["id"], "plan_no": plan_no})


@router.post(nav.path_of("ORD-04") + "/{plan_id}")                                    # F-ORD-08 생산계획 수정
def update_plan(request: Request, plan_id: int, item_code: str = Form(None), plan_date: str = Form(None), plan_qty: str = Form(None),
                unit: str = Form(None), user: rbac.User = rbac.require_fn("F-ORD-08")):
    plan = _plan(plan_id)
    if plan["status"] == PLAN_CANCELED:
        raise http.validation_error(t("취소된 생산계획은 수정할 수 없습니다"), fields=[{"name": "status", "label": t("상태"), "reason": plan["status"]}])
    new_item = _item(item_code) if item_code is not None and item_code.strip() else None
    new_date = _date(plan_date, "plan_date") if plan_date is not None and plan_date.strip() else None
    new_qty = _qty(plan_qty, "plan_qty") if plan_qty is not None and plan_qty.strip() else None
    if plan["status"] == CONFIRMED:
        changed = [{"name": "item_code", "label": t("품목"), "reason": item_code} for _ in [0] if new_item and new_item["id"] != plan["item_id"]]
        changed += [{"name": "plan_date", "label": t("계획일"), "reason": plan_date} for _ in [0] if new_date and new_date != plan["plan_date"]]
        if changed:
            raise http.validation_error(t("확정된 생산계획은 수량만 바꿀 수 있습니다"), fields=changed)
    row = {**plan, "item_id": new_item["id"] if new_item else plan["item_id"], "plan_date": new_date or plan["plan_date"],
           "plan_qty": new_qty if new_qty is not None else plan["plan_qty"], "unit": (unit.strip() if unit else None) or plan["unit"]}
    with conn.tx() as cur:
        packs.hook("validate_ord_plan")(cur, row, user)
        cur.execute("update ord_plan set item_id = %s, plan_date = %s, plan_qty = %s, unit = %s, updated_at = now(), updated_by = %s where id = %s",
                    (row["item_id"], row["plan_date"], row["plan_qty"], row["unit"], user.login_id, plan_id))
        packs.hook("after_save_ord_plan")(cur, row, user)
    audit.log_change(request, user, "F-ORD-08", f"ord_plan:{plan['plan_no']}")
    return http.saved(request, t("생산계획을 수정했습니다"), back=f"{nav.path_of('ORD-04')}?id={plan_id}", data={"id": plan_id, "plan_no": plan["plan_no"]})


@router.post(nav.path_of("ORD-04") + "/{plan_id}/confirm")                            # F-ORD-09 생산계획 확정
def confirm_plan(request: Request, plan_id: int, user: rbac.User = rbac.require_fn("F-ORD-09")):
    plan = _plan(plan_id)
    if plan["status"] != PLANNED:
        reason = t("이미 확정된 생산계획입니다") if plan["status"] == CONFIRMED else t("취소된 생산계획은 확정할 수 없습니다")
        raise http.validation_error(reason, fields=[{"name": "status", "label": t("상태"), "reason": plan["status"]}])
    with conn.tx() as cur:
        row = {**plan, "status": CONFIRMED}
        packs.hook("validate_ord_plan")(cur, row, user)
        cur.execute("update ord_plan set status = %s, updated_at = now(), updated_by = %s where id = %s and status = %s",
                    (CONFIRMED, user.login_id, plan_id, PLANNED))
        if cur.rowcount != 1:
            raise http.validation_error(t("생산계획 상태가 바뀌어 확정하지 못했습니다"), fields=[{"name": "status", "label": t("상태"), "reason": t("다시 조회")}])
        packs.hook("after_save_ord_plan")(cur, row, user)
    audit.log_change(request, user, "F-ORD-09", f"ord_plan:{plan['plan_no']}")
    return http.saved(request, t("생산계획을 확정했습니다"), back=f"{nav.path_of('ORD-04')}?id={plan_id}",
                      data={"id": plan_id, "plan_no": plan["plan_no"], "status": CONFIRMED})
