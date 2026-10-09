"""자재 `mat` — 입고 · 입고검사 · 원재료 LOT · 재고 · 소요량 (F-MAT-01~11 · 개발2).

쓰기 경계(db-schema.md §2): mat_* 4 · lot(kind=MATERIAL 생성 — lineage.make_material_lot · insp_status) · qua_inspection · qua_insp_item(입고검사 기록).
번호는 numbering(LOT_MATERIAL · lineage 안) 뿐. 입고 번호 = 그 입고가 만든 원재료 LOT 번호(1 입고 = 1 LOT · D-201).
"""

from __future__ import annotations

import json
from datetime import date

import anyio
from fastapi import APIRouter, Form, Request

from ...db import conn
from .. import lineage, measure, nav, packs, printing, rbac, templating
from ..packs import t
from ..util import audit, http
from . import _dev2 as f

router = APIRouter()
JUDGEMENTS = ("합격", "불합격", "조건부")


def _form(request: Request):
    return anyio.from_thread.run(request.form)


def _items(kind: str | None = None) -> list[dict]:
    sql = "select id, item_code, item_name, item_type, unit from bas_item where use_yn = 'Y'"
    if kind:
        sql += " and item_type = %s"
        return conn.q(sql + " order by item_code", (kind,))
    return conn.q(sql + " order by item_code")


def _partners() -> list[dict]:
    return conn.q("select id, partner_code, partner_name, partner_type from bas_partner where use_yn = 'Y' order by partner_code")


def _receipt_rows(frm: date, to: date, item_id: int | None, partner_id: int | None) -> list[dict]:
    return conn.q("""select r.*, i.item_code, i.item_name, p.partner_name, l.lot_no, l.insp_status, s.state, k.remain_qty
                       from mat_receipt r
                       join bas_item i on i.id = r.item_id
                       left join bas_partner p on p.id = r.partner_id
                       left join lot l on l.id = r.lot_id
                       left join v_lot_state s on s.lot_id = l.id
                       left join v_lot_stock k on k.lot_id = l.id
                      where r.receipt_date between %s and %s and (%s::bigint is null or r.item_id = %s) and (%s::bigint is null or r.partner_id = %s)
                      order by r.receipt_date desc, r.id desc limit 500""", (frm, to, item_id, item_id, partner_id, partner_id))


# ── MAT-01 입고 ─────────────────────────────────────────────────────────
@router.get(nav.path_of("MAT-01"))                                                    # F-MAT-03 입고 조회 = 화면 GET
def receipts(request: Request, frm: str | None = None, to: str | None = None, item_id: str | None = None, partner_id: str | None = None,
             item_code: str | None = None, user: rbac.User = rbac.require_fn("F-MAT-03")):
    d1, d2 = f.period(frm, to)
    iid, pid = f.int_id(item_id, "item_id", "품목"), f.int_id(partner_id, "partner_id", "공급처")
    rows = _receipt_rows(d1, d2, iid, pid)
    items = _items("원재료") + _items("부자재")
    ctx = {"rows": rows, "frm": d1, "to": d2, "item_id": iid, "partner_id": pid,
           "item_options": f.options(items, "id", "item_code", "item_name"),
           "partner_options": f.options([p for p in _partners() if p["partner_type"] != "고객"], "id", "partner_code", "partner_name"),
           "today": date.today(), "attr_specs": packs.attrs_of("lot"), "scan_no": item_code or "", "scan_item": None, "item_id_default": None}
    if item_code is not None and item_code.strip() != "":                              # 스캔 진입 — 품목 바코드 → 등록 폼의 품목 칸
        hit = next((i for i in items if i["item_code"] == item_code.strip()), None)
        if hit is None:
            return f.scan_miss(request, "mat/receipts.html", ctx, screen_id="MAT-01", no=item_code, what="품목")
        ctx.update({"scan_item": hit, "item_id_default": hit["id"]})
    return templating.render(request, "mat/receipts.html", ctx, screen_id="MAT-01")


@router.post(nav.path_of("MAT-01"))                                                   # F-MAT-01 입고 등록
def receipt_create(request: Request, item_id: str = Form(...), qty: str = Form(...), receipt_date: str | None = Form(None),
                   partner_id: str | None = Form(None), unit: str | None = Form(None), note: str | None = Form(None),
                   user: rbac.User = rbac.require_fn("F-MAT-01")):
    iid = f.int_id(item_id, "item_id", "품목", required=True)
    item = conn.q1("select * from bas_item where id = %s and use_yn = 'Y'", (iid,))
    if item is None:
        raise http.validation_error(t("없는 품목입니다"), fields=[f.field_error("item_id", "품목", str(iid))])
    pid = f.int_id(partner_id, "partner_id", "공급처")
    if pid is not None and conn.q1("select 1 from bas_partner where id = %s", (pid,)) is None:
        raise http.validation_error(t("없는 거래처입니다"), fields=[f.field_error("partner_id", "공급처", str(pid))])
    q = f.num(qty, "qty", "수량", required=True, positive=True)
    rdate = f.a_date(receipt_date, "receipt_date", "입고일", default=date.today())
    u = f.opt_text(unit) or item["unit"]
    try:
        attrs = packs.read_attrs(_form(request), "lot")
    except ValueError as exc:
        raise http.validation_error(str(exc), fields=[f.field_error("attrs", "속성", str(exc))]) from None
    with conn.tx() as cur:
        lot = lineage.make_material_lot(cur, item_id=iid, qty=q, unit=u, by=user.login_id, partner_id=pid, made_at=rdate, attrs=attrs,
                                        note=f.opt_text(note), user=user)
        row = {"receipt_no": lot["lot_no"], "item_id": iid, "partner_id": pid, "receipt_date": rdate, "qty": q, "unit": u, "lot_id": lot["id"],
               "note": f.opt_text(note), "attrs": attrs}
        packs.hook("validate_mat_receipt")(cur, row, user)
        cur.execute("""insert into mat_receipt (receipt_no, item_id, partner_id, receipt_date, qty, unit, lot_id, note, attrs, created_by)
                       values (%(receipt_no)s, %(item_id)s, %(partner_id)s, %(receipt_date)s, %(qty)s, %(unit)s, %(lot_id)s, %(note)s, %(attrs)s::jsonb, %(by)s)
                       returning *""", {**row, "attrs": json.dumps(attrs, ensure_ascii=False), "by": user.login_id})
        saved = dict(cur.fetchone())
        cur.execute("""insert into mat_stock_trx (item_id, lot_id, trx_type, qty, unit, ref_table, ref_id, created_by) values (%s, %s, '입고', %s, %s, 'mat_receipt', %s, %s)""",
                    (iid, lot["id"], q, u, saved["id"], user.login_id))
        cur.execute("""insert into mat_stock (item_id, qty, unit, created_by) values (%s, %s, %s, %s)
                       on conflict (item_id) do update set qty = mat_stock.qty + excluded.qty, unit = coalesce(mat_stock.unit, excluded.unit), updated_at = now(), updated_by = excluded.created_by""",
                    (iid, q, u, user.login_id))
        packs.hook("after_save_mat_receipt")(cur, saved, user)
    audit.log_change(request, user, "F-MAT-01", f"mat_receipt:{saved['receipt_no']}", {"lot_no": lot["lot_no"], "qty": str(q)})
    return http.saved(request, t("입고를 등록했습니다") + f" — {t('원재료 LOT')} {lot['lot_no']}",
                      data={"id": saved["id"], "receipt_no": saved["receipt_no"], "lot_id": lot["id"], "lot_no": lot["lot_no"],
                            "label_url": f"{nav.path_of('MAT-03')}/{lot['id']}/label"})


@router.post(nav.path_of("MAT-01") + "/{id}")                                         # F-MAT-02 입고 수정
def receipt_update(request: Request, id: int, qty: str | None = Form(None), receipt_date: str | None = Form(None),
                   partner_id: str | None = Form(None), note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-MAT-02")):
    r = conn.q1("select * from mat_receipt where id = %s", (id,))
    if r is None:
        raise http.not_found(t("없는 입고입니다"))
    if conn.q1("select 1 from pop_input where material_lot_id = %s and canceled_yn = 'N'", (r["lot_id"],)):
        raise http.validation_error(t("이미 투입된 LOT 의 입고는 고칠 수 없습니다"), fields=[f.field_error("id", "입고", r["receipt_no"])])
    new_qty = f.num(qty, "qty", "수량", positive=True)
    rdate = f.a_date(receipt_date, "receipt_date", "입고일", default=r["receipt_date"])
    pid = f.int_id(partner_id, "partner_id", "공급처") if partner_id not in (None, "") else r["partner_id"]
    diff = (new_qty - r["qty"]) if new_qty is not None else None
    with conn.tx() as cur:
        row = {**r, "qty": new_qty if new_qty is not None else r["qty"], "receipt_date": rdate, "partner_id": pid, "note": f.opt_text(note) if note is not None else r["note"]}
        packs.hook("validate_mat_receipt")(cur, row, user)
        cur.execute("update mat_receipt set qty = %s, receipt_date = %s, partner_id = %s, note = %s, updated_at = now(), updated_by = %s where id = %s",
                    (row["qty"], rdate, pid, row["note"], user.login_id, id))
        if r["lot_id"] is not None:
            cur.execute("update lot set qty = %s, partner_id = %s, made_at = %s, updated_at = now(), updated_by = %s where id = %s",
                        (row["qty"], pid, rdate, user.login_id, r["lot_id"]))
        if diff is not None and diff != 0:
            cur.execute("""insert into mat_stock_trx (item_id, lot_id, trx_type, qty, unit, ref_table, ref_id, reason, created_by)
                           values (%s, %s, '입고', %s, %s, 'mat_receipt', %s, %s, %s)""", (r["item_id"], r["lot_id"], diff, r["unit"], id, t("입고 수정 보정"), user.login_id))
            cur.execute("update mat_stock set qty = qty + %s, updated_at = now(), updated_by = %s where item_id = %s", (diff, user.login_id, r["item_id"]))
        packs.hook("after_save_mat_receipt")(cur, row, user)
    audit.log_change(request, user, "F-MAT-02", f"mat_receipt:{r['receipt_no']}", {"qty_diff": str(diff) if diff is not None else None})
    return http.saved(request, t("입고를 수정했습니다"), data={"id": id, "qty_diff": float(diff) if diff is not None else 0})


# ── MAT-02 입고검사 ──────────────────────────────────────────────────────
def _incoming_plan(item_id: int | None) -> list[dict]:
    return conn.q("""select * from qua_insp_plan where insp_type = '입고' and use_yn = 'Y' and (item_id is null or item_id = %s) order by seq, id""", (item_id,))


def _uninspected(limit: int = 200) -> list[dict]:
    return conn.q("""select l.id, l.lot_no, l.insp_status, l.qty, l.unit, l.made_at, i.item_code, i.item_name, p.partner_name
                       from lot l join bas_item i on i.id = l.item_id left join bas_partner p on p.id = l.partner_id
                      where l.kind_base = 'MATERIAL'
                      order by (l.insp_status = '미검사') desc, l.made_at desc, l.id desc limit %s""", (limit,))


@router.get(nav.path_of("MAT-02"))                                                    # F-MAT-05 입고검사 조회 (스캔 ?no=)
def inspections(request: Request, no: str | None = None, user: rbac.User = rbac.require_fn("F-MAT-05")):
    ctx: dict = {"rows": _uninspected(), "lot": None, "plan": [], "fields": [], "judgements": JUDGEMENTS,
                 "judgement_options": [(j, t(j)) for j in JUDGEMENTS], "scan_no": no or ""}
    if no is not None and no.strip() != "":
        n = lineage.resolve(no)
        if n is None or n.kind_base != lineage.MATERIAL:
            return f.scan_miss(request, "mat/inspections.html", ctx, screen_id="MAT-02", no=no, what="원재료 LOT")
        plan = _incoming_plan(n.item_id)
        ctx.update({"lot": n, "plan": plan, "fields": measure.plan_fields(plan),
                    "last": conn.q1("select * from qua_inspection where lot_id = %s order by inspected_at desc, id desc limit 1", (n.id,))})
    return templating.render(request, "mat/inspections.html", ctx, screen_id="MAT-02")


def _insp_values(fields: list[dict], form) -> list[dict]:
    """검사 항목 값 — 비운 칸은 행을 만들지 않는다. 형식 오류 422. 기준 이탈은 저장 + deviated."""
    values, errs = measure.parse_form(fields, form)
    if errs:
        raise http.validation_error(t("검사 항목 값을 확인해 주세요"), fields=errs)
    out = []
    for p in fields:
        v = values.get(p["param_key"])
        if v is None:
            continue
        dev = measure.deviated(p, v["value_num"])
        out.append({"plan_id": p["id"], "item_key": p["param_key"], "value_num": v["value_num"], "value_text": v["value_text"], "unit": p.get("unit"),
                    "deviated": dev, "item_judgement": "불합격" if dev else ("합격" if v["value_num"] is not None and (p["min_value"] is not None or p["max_value"] is not None) else None)})
    return out


def _insert_inspection(cur, *, lot_id: int, insp_type: str, items: list[dict], judgement: str | None, note: str | None, user) -> dict:
    row = {"lot_id": lot_id, "insp_type": insp_type, "inspector": user.login_id, "judgement": judgement, "note": note, "items": items}
    packs.hook("validate_qua_inspection")(cur, row, user)
    cur.execute("""insert into qua_inspection (lot_id, insp_type, inspected_at, inspector, judgement, judged_at, judged_by, note, created_by)
                   values (%s, %s, now(), %s, %s, case when %s::text is null then null else now() end, %s, %s, %s) returning *""",
                (lot_id, insp_type, user.login_id, judgement, judgement, user.login_id if judgement else None, note, user.login_id))
    insp = dict(cur.fetchone())
    for it in items:
        cur.execute("""insert into qua_insp_item (inspection_id, plan_id, item_key, value_num, value_text, unit, item_judgement, deviated, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (insp["id"], it["plan_id"], it["item_key"], it["value_num"], it["value_text"], it["unit"], it["item_judgement"], it["deviated"], user.login_id))
    insp["items"] = items
    packs.hook("after_save_qua_inspection")(cur, insp, user)
    return insp


@router.post(nav.path_of("MAT-02"))                                                   # F-MAT-04 입고검사 판정
def inspection_judge(request: Request, judgement: str = Form(...), lot_no: str | None = Form(None), lot_id: str | None = Form(None),
                     note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-MAT-04")):
    j = f.choice(judgement, "judgement", "판정", JUDGEMENTS)
    n = lineage.resolve(lot_no) if f.opt_text(lot_no) else (lineage.node(f.int_id(lot_id, "lot_id", "원재료 LOT", required=True)))
    if n is None:
        raise http.validation_error(t("없는 LOT 입니다"), fields=[f.field_error("lot_no", "원재료 LOT", lot_no or lot_id or "")])
    if n.kind_base != lineage.MATERIAL:
        raise http.validation_error(t("원재료 LOT 이 아닙니다"), fields=[f.field_error("lot_no", "원재료 LOT", f"{n.no} {n.kind}")])
    if conn.q1("select 1 from pop_input where material_lot_id = %s and canceled_yn = 'N'", (n.id,)):
        raise http.validation_error(t("이미 투입된 LOT 은 다시 판정할 수 없습니다"), fields=[f.field_error("lot_no", "원재료 LOT", n.no)])
    fields = measure.plan_fields(_incoming_plan(n.item_id))         # 항목 0건도 허용 (D-513)
    items = _insp_values(fields, _form(request))
    with conn.tx() as cur:
        insp = _insert_inspection(cur, lot_id=n.id, insp_type="입고", items=items, judgement=j, note=f.opt_text(note), user=user)
        cur.execute("update lot set insp_status = %s, updated_at = now(), updated_by = %s where id = %s", (j, user.login_id, n.id))
        packs.hook("on_inspection_judged")(cur, insp, user)
    audit.log_change(request, user, "F-MAT-04", f"qua_inspection:{insp['id']}", {"lot_no": n.no, "judgement": j, "items": len(items)})
    return http.saved(request, f"{n.no} {t('입고검사')} {j}", data={"id": insp["id"], "lot_id": n.id, "lot_no": n.no, "judgement": j, "items": len(items)})


# ── MAT-03 원재료 LOT ────────────────────────────────────────────────────
@router.get(nav.path_of("MAT-03"))                                                    # F-MAT-06 원재료 LOT 조회
def lots(request: Request, no: str | None = None, item_id: str | None = None, state: str | None = None, insp: str | None = None,
         user: rbac.User = rbac.require_fn("F-MAT-06")):
    iid = f.int_id(item_id, "item_id", "품목")
    rows = conn.q("""select l.id, l.lot_no, l.kind, l.qty, l.unit, l.insp_status, l.made_at, i.item_code, i.item_name, p.partner_name, s.state,
                            k.consumed_qty, k.remain_qty,
                            (select string_agg(distinct w.work_order_no, ', ') from pop_input pi join pop_work_result r on r.id = pi.work_result_id
                              join job_work_order w on w.id = r.work_order_id where pi.material_lot_id = l.id and pi.canceled_yn = 'N') as used_in
                       from lot l join v_lot_state s on s.lot_id = l.id join v_lot_stock k on k.lot_id = l.id
                       join bas_item i on i.id = l.item_id left join bas_partner p on p.id = l.partner_id
                      where l.kind_base = 'MATERIAL' and (%s::bigint is null or l.item_id = %s) and (%s::text is null or s.state = %s)
                        and (%s::text is null or l.insp_status = %s) and (%s::text is null or l.lot_no ilike %s)
                      order by l.made_at desc, l.id desc limit 500""",
                  (iid, iid, f.opt_text(state), f.opt_text(state), f.opt_text(insp), f.opt_text(insp), f.opt_text(no), f"%{(no or '').strip()}%"))
    return templating.render(request, "mat/lots.html", {"rows": rows, "item_options": f.options(_items("원재료") + _items("부자재"), "id", "item_code", "item_name"),
                                                        "item_id": iid, "state": state or "", "insp": insp or "", "no": no or ""}, screen_id="MAT-03")


@router.get(nav.path_of("MAT-03") + "/{id}/label")                                    # F-MAT-07 원재료 LOT 라벨 출력
def lot_label(request: Request, id: int, size: str = "100x50", user: rbac.User = rbac.require_fn("F-MAT-07")):
    label = printing.label_for(id, size=size)
    return printing.render_print(request, "label_lot", {"labels": [label], "size": size, **label}, screen_id="MAT-03")


# ── MAT-04 재고 ─────────────────────────────────────────────────────────
@router.get(nav.path_of("MAT-04"))                                                    # F-MAT-08 재고 조회 (모바일 390px)
def stock(request: Request, item_id: str | None = None, user: rbac.User = rbac.require_fn("F-MAT-08")):
    iid = f.int_id(item_id, "item_id", "품목")
    rows = conn.q("""select s.*, i.item_code, i.item_name, i.item_type,
                            (select coalesce(sum(qty), 0) from mat_stock_trx x where x.item_id = s.item_id) as trx_sum
                       from mat_stock s join bas_item i on i.id = s.item_id
                      where (%s::bigint is null or s.item_id = %s) order by i.item_code""", (iid, iid))
    lots_by_item: dict[int, list[dict]] = {}
    for l in conn.q("""select l.id, l.item_id, l.lot_no, l.qty, l.unit, l.insp_status, l.made_at, k.remain_qty, st.state
                         from lot l join v_lot_stock k on k.lot_id = l.id join v_lot_state st on st.lot_id = l.id
                        where l.kind_base = 'MATERIAL' and (%s::bigint is null or l.item_id = %s) order by l.made_at desc, l.id desc limit 1000""", (iid, iid)):
        lots_by_item.setdefault(l["item_id"], []).append(l)
    for r in rows:
        r["lots"] = lots_by_item.get(r["item_id"], [])
    return templating.render(request, "mat/stock.html", {"rows": rows, "item_options": f.options(_items(), "id", "item_code", "item_name"), "item_id": iid},
                             screen_id="MAT-04")


@router.post(nav.path_of("MAT-04") + "/adjust")                                       # F-MAT-09 재고 조정
def stock_adjust(request: Request, item_id: str = Form(...), qty: str = Form(...), reason: str | None = Form(None),
                 user: rbac.User = rbac.require_fn("F-MAT-09")):
    iid = f.int_id(item_id, "item_id", "품목", required=True)
    item = conn.q1("select * from bas_item where id = %s", (iid,))
    if item is None:
        raise http.validation_error(t("없는 품목입니다"), fields=[f.field_error("item_id", "품목", str(iid))])
    q = f.num(qty, "qty", "조정 수량", required=True)
    if q == 0:
        raise http.validation_error(t("조정 수량이 0 입니다"), fields=[f.field_error("qty", "조정 수량", "0")])
    why = f.req_text(reason, "reason", "사유")
    with conn.tx() as cur:
        row = {"item_id": iid, "trx_type": "조정", "qty": q, "unit": item["unit"], "reason": why}
        packs.hook("validate_mat_stock_trx")(cur, row, user)
        cur.execute("""insert into mat_stock_trx (item_id, trx_type, qty, unit, reason, created_by) values (%s, '조정', %s, %s, %s, %s) returning *""",
                    (iid, q, item["unit"], why, user.login_id))
        trx = dict(cur.fetchone())
        cur.execute("""insert into mat_stock (item_id, qty, unit, created_by) values (%s, %s, %s, %s)
                       on conflict (item_id) do update set qty = mat_stock.qty + excluded.qty, updated_at = now(), updated_by = excluded.created_by returning qty""",
                    (iid, q, item["unit"], user.login_id))
        new_qty = cur.fetchone()["qty"]
        packs.hook("after_save_mat_stock_trx")(cur, trx, user)
    audit.log_change(request, user, "F-MAT-09", f"mat_stock:{item['item_code']}", {"qty": str(q), "reason": why})
    return http.saved(request, t("재고를 조정했습니다"), data={"id": trx["id"], "item_id": iid, "stock_qty": float(new_qty)})


# ── MAT-05 소요량 ────────────────────────────────────────────────────────
@router.get(nav.path_of("MAT-05"))                                                    # F-MAT-11 소요량 조회
def requirements(request: Request, frm: str | None = None, to: str | None = None, user: rbac.User = rbac.require_fn("F-MAT-11")):
    d1, d2 = f.period(frm, to, days=7)
    rows = conn.q("""select q.*, i.item_code, i.item_name from mat_requirement q join bas_item i on i.id = q.item_id
                      where q.period_from <= %s and q.period_to >= %s order by q.shortage_qty desc, i.item_code""", (d2, d1))
    return templating.render(request, "mat/requirements.html", {"rows": rows, "frm": d1, "to": d2}, screen_id="MAT-05")


@router.post(nav.path_of("MAT-05") + "/calc")                                         # F-MAT-10 소요량 계산
def requirements_calc(request: Request, frm: str | None = Form(None), to: str | None = Form(None), user: rbac.User = rbac.require_fn("F-MAT-10")):
    d1, d2 = f.period(frm, to, days=7)
    demand = conn.q("""select d.component_item_id as item_id, sum(d.qty * (1 + d.loss_rate / 100) * src.qty) as required_qty, min(d.unit) as unit
                         from (select p.item_id, p.plan_qty as qty from ord_plan p where p.status = '확정' and p.plan_date between %(f)s and %(t)s
                               union all
                               select w.item_id, w.plan_qty from job_work_order w where w.status = '대기' and w.plan_id is null
                                  and coalesce(w.plan_date, %(f)s) between %(f)s and %(t)s) src
                         join bas_bom b on b.item_id = src.item_id and b.use_yn = 'Y'
                         join bas_bom_dtl d on d.bom_id = b.id
                        group by d.component_item_id""", {"f": d1, "t": d2})
    stocks = {r["item_id"]: r["qty"] for r in conn.q("select item_id, qty from mat_stock")}
    with conn.tx() as cur:
        cur.execute("delete from mat_requirement where period_from = %s and period_to = %s and source = 'calc'", (d1, d2))
        n = 0
        for r in demand:
            stock_qty = stocks.get(r["item_id"], 0)
            shortage = max(r["required_qty"] - stock_qty, 0)
            row = {"period_from": d1, "period_to": d2, "item_id": r["item_id"], "required_qty": r["required_qty"], "stock_qty": stock_qty,
                   "shortage_qty": shortage, "unit": r["unit"], "source": "calc"}
            packs.hook("validate_mat_requirement")(cur, row, user)
            cur.execute("""insert into mat_requirement (period_from, period_to, item_id, required_qty, stock_qty, shortage_qty, unit, source, calc_at, created_by)
                           values (%s, %s, %s, %s, %s, %s, %s, 'calc', now(), %s)""",
                        (d1, d2, r["item_id"], r["required_qty"], stock_qty, shortage, r["unit"], user.login_id))
            n += 1
    audit.log_change(request, user, "F-MAT-10", f"mat_requirement:{d1}~{d2}", {"rows": n})
    return http.saved(request, t("소요량을 계산했습니다") + f" — {n}", data={"rows": n, "frm": str(d1), "to": str(d2)})
