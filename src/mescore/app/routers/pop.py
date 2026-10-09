"""생산실적 `pop` — 작업 목록(스캔) · 시작/종료 · 정지 · 폐기 · 투입 스캔 · LOT 라벨 (F-POP-01~08 · 개발2) + 분할/합병 API (D-12 · F-POP-03 의 계약 안).

쓰기 경계(db-schema.md §2): pop_* 5 · lot(kind=PRODUCT — lineage 경유) · lot_genealogy(lineage 경유만) · mat_stock* (투입 소비 — lineage.consume_material 경유).
`job_work_order.status` 는 바꾸지 않는다(진행 여부는 v_work_order_progress). 번호는 numbering(lineage 안) 뿐.
훅: F-POP-02 on_result_started · F-POP-03 on_result_closed(측정값 · 생산 LOT · collect 측정값 **후**). 모든 쓰기 전 validate_<table> · 후 after_save_<table>(D-504).
"""

from __future__ import annotations

from datetime import datetime

import anyio
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ...db import conn
from .. import collect, lineage, measure, nav, packs, printing, rbac, templating
from ..packs import t
from ..util import audit, http
from . import _dev2 as f

router = APIRouter()
POP01, POP02, POP03, POP04 = (nav.path_of(s) for s in ("POP-01", "POP-02", "POP-03", "POP-04"))
OPEN_STATUS = ("대기", "진행")


def _form(request: Request):
    return anyio.from_thread.run(request.form)


def _result_row(result_id: int, cur=None) -> dict | None:
    sql = """select r.*, w.work_order_no, w.item_id, w.plan_qty, w.status as wo_status, i.item_code, i.item_name, p.process_name,
                    e.equip_code, e.equip_name, k.worker_name, l.lot_no as product_lot_no,
                    (select count(*) from pop_input x where x.work_result_id = r.id and x.canceled_yn = 'N') as input_count,
                    (select count(*) from pop_stop s where s.work_result_id = r.id) as stop_count,
                    (select count(*) from pop_stop s where s.work_result_id = r.id and s.ended_at is null) as open_stop_count,
                    (select coalesce(sum(qty), 0) from pop_scrap s where s.work_result_id = r.id) as scrap_qty
               from pop_work_result r
               join job_work_order w on w.id = r.work_order_id
               join bas_item i on i.id = w.item_id
               join bas_process p on p.id = r.process_id
               left join bas_equipment e on e.id = r.equipment_id
               left join bas_worker k on k.id = r.worker_id
               left join lot l on l.id = r.product_lot_id
              where r.id = %s"""
    if cur is None:
        return conn.q1(sql, (int(result_id),))
    cur.execute(sql, (int(result_id),))
    r = cur.fetchone()
    return dict(r) if r else None


def _require_result(result_id: int, cur=None) -> dict:
    r = _result_row(result_id, cur)
    if r is None:
        raise http.not_found(t("없는 실적입니다"))
    return r


def _open_work_orders() -> list[dict]:
    return conn.q("""select w.*, i.item_code, i.item_name, p.process_name, e.equip_code, g.started, g.open_count, g.result_count, g.good_qty,
                            (w.plan_date = current_date) as is_today
                       from job_work_order w join bas_item i on i.id = w.item_id join bas_process p on p.id = w.process_id
                       left join bas_equipment e on e.id = w.equipment_id join v_work_order_progress g on g.work_order_id = w.id
                      where w.status in ('대기', '진행')
                      order by (w.plan_date = current_date) desc nulls last, w.plan_date desc nulls last, w.id desc limit 500""")


# ── POP-01 작업 목록 (스캔) ──────────────────────────────────────────────
@router.get(POP01)                                                                     # F-POP-01 작업 목록 조회 (스캔 ?no= → POP-02)
def work(request: Request, no: str | None = None, user: rbac.User = rbac.require_fn("F-POP-01")):
    ctx: dict = {"rows": _open_work_orders(), "scan_no": no or "", "today": datetime.now()}
    if no is not None and no.strip() != "":
        wo = conn.q1("select * from job_work_order where work_order_no = %s", (no.strip(),))
        if wo is None:
            return f.scan_miss(request, "pop/work.html", ctx, screen_id="POP-01", no=no, what="작업지시")
        if wo["status"] not in OPEN_STATUS:
            ctx["scan_error"] = f"{wo['work_order_no']} — {t('대기 · 진행 지시가 아닙니다')} ({wo['status']})"
            return templating.render(request, "pop/work.html", {**ctx, "code": "validation_error", "message": ctx["scan_error"],
                                                                 "fields": [f.field_error("no", "작업지시", wo["status"])]}, screen_id="POP-01", status_code=422)
        target = f"{POP02}?wo={wo['id']}"
        if http.wants_html(request):
            return RedirectResponse(target, status_code=303)
        ctx.update({"work_order": wo, "next": target})
    return templating.render(request, "pop/work.html", ctx, screen_id="POP-01")


# ── POP-02 작업 시작 · 종료 ──────────────────────────────────────────────
def _login_worker_id(user: rbac.User) -> int | None:
    """작업 시작의 작업자 기본값 — 로그인 사용자의 `sys_user.worker_id` (비우고 시작해도 서버가 같은 값을 쓴다)."""
    row = conn.q1("select worker_id from sys_user where id = %s", (user.id,))
    return row["worker_id"] if row else None


def _equipment_options(process_id: int | None, equipment_id: int | None = None) -> list:
    """작업 시작의 설비 선택지 — 지시 공정의 설비(`bas_equipment.process_id`)만 + 지시에 지정된 설비."""
    return f.options(conn.q("""select id, equip_code, equip_name from bas_equipment
                                where use_yn = 'Y' and (process_id = %s or id = %s) order by equip_code""", (process_id, equipment_id)),
                     "id", "equip_code", "equip_name")


@router.get(POP02)                                                                     # 화면 — ?wo= 지시 · ?id= 실적
def result(request: Request, wo: str | None = None, id: str | None = None, user: rbac.User = rbac.require_screen("POP-02")):
    ctx: dict = {"work_order": None, "result": None, "results": [], "params": [], "values": {}, "latest": {}, "inputs": [], "stops": [], "scraps": [],
                 "equipment_options": [],
                 "worker_options": f.options(conn.q("select id, worker_code, worker_name from bas_worker where use_yn = 'Y' order by worker_code"), "id", "worker_code", "worker_name"),
                 "stop_reasons": [(c["code"], c["code_name"]) for c in conn.q("select code, code_name from bas_code where group_code = 'STOP_REASON' and use_yn = 'Y' order by seq")],
                 "defect_options": f.options(conn.q("select id, defect_code, defect_name from bas_defect_code where use_yn = 'Y' order by defect_code"), "id", "defect_code", "defect_name"),
                 "scan_no": "", "worker_id_default": _login_worker_id(user)}
    rid = f.int_id(id, "id", "실적")
    if rid is not None:
        r = _require_result(rid)
        ctx["result"] = r
        ctx["work_order"] = conn.q1("select * from job_work_order where id = %s", (r["work_order_id"],))
        ctx["equipment_options"] = _equipment_options(r["process_id"], r["equipment_id"])
        ctx["params"] = measure.params_for(r["process_id"])
        ctx["values"] = measure.values_of(r["id"])
        if r["equipment_id"] is not None:
            lv = collect.latest(r["equipment_id"])
            if lv:
                ctx["latest"] = {p["param_key"]: lv["tags"][p["tag"]] for p in ctx["params"] if p["is_collect"] and p["tag"] in lv["tags"]}
        ctx["inputs"] = conn.q("""select x.*, l.lot_no, i.item_name from pop_input x join lot l on l.id = x.material_lot_id left join bas_item i on i.id = l.item_id
                                   where x.work_result_id = %s order by x.id""", (r["id"],))
        ctx["stops"] = conn.q("select * from pop_stop where work_result_id = %s order by id", (r["id"],))
        ctx["scraps"] = conn.q("select s.*, d.defect_code from pop_scrap s left join bas_defect_code d on d.id = s.defect_code_id where s.work_result_id = %s order by s.id", (r["id"],))
        ctx["product_lot"] = lineage.node(r["product_lot_id"]) if r["product_lot_id"] else None
        ctx["stock_lots"] = [n for n in (lineage.node(x["id"]) for x in conn.q("select id from lot where work_order_id = %s and kind_base = 'PRODUCT' order by id", (r["work_order_id"],))) if n and n.state == lineage.IN_STOCK]
        ctx["stock_lot_options"] = [(n.id, f"{n.no} {n.qty if n.qty is not None else ''}") for n in ctx["stock_lots"]]
        ctx["attr_specs"] = packs.attrs_of("lot")
    else:
        woid = f.int_id(wo, "wo", "작업지시")
        if woid is not None:
            w = conn.q1("""select w.*, i.item_code, i.item_name, p.process_name from job_work_order w join bas_item i on i.id = w.item_id
                           join bas_process p on p.id = w.process_id where w.id = %s""", (woid,))
            if w is None:
                raise http.not_found(t("없는 작업지시입니다"))
            ctx["work_order"] = w
            ctx["equipment_options"] = _equipment_options(w["process_id"], w["equipment_id"])
            ctx["params"] = measure.params_for(w["process_id"])
            ctx["results"] = conn.q("""select r.*, l.lot_no as product_lot_no from pop_work_result r left join lot l on l.id = r.product_lot_id
                                        where r.work_order_id = %s order by r.started_at desc, r.id desc""", (woid,))
            open_r = next((x for x in ctx["results"] if x["ended_at"] is None), None)
            if open_r is not None and http.wants_html(request):
                return RedirectResponse(f"{POP02}?id={open_r['id']}", status_code=303)
    return templating.render(request, "pop/result.html", ctx, screen_id="POP-02")


@router.post(POP02 + "/start")                                                         # F-POP-02 작업 시작
def result_start(request: Request, work_order_id: str | None = Form(None), work_order_no: str | None = Form(None), equipment_id: str | None = Form(None),
                 worker_id: str | None = Form(None), note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-POP-02")):
    with conn.tx() as cur:
        if f.opt_text(work_order_no):
            cur.execute("select * from job_work_order where work_order_no = %s for share", (work_order_no.strip(),))
        else:
            cur.execute("select * from job_work_order where id = %s for share", (f.int_id(work_order_id, "work_order_id", "작업지시", required=True),))
        wo = cur.fetchone()
        if wo is None:
            raise http.validation_error(t("없는 작업지시입니다"), fields=[f.field_error("work_order_id", "작업지시", work_order_no or work_order_id or "")])
        if wo["status"] not in OPEN_STATUS:
            raise http.validation_error(t("대기 · 진행 지시만 시작할 수 있습니다"), fields=[f.field_error("work_order_id", "작업지시", f"{wo['work_order_no']} {wo['status']}")])
        cur.execute("select id from pop_work_result where work_order_id = %s and ended_at is null", (wo["id"],))
        if cur.fetchone():
            raise http.validation_error(t("같은 지시의 종료되지 않은 실적이 있습니다"), fields=[f.field_error("work_order_id", "작업지시", wo["work_order_no"])])
        eid = f.int_id(equipment_id, "equipment_id", "설비") or wo["equipment_id"]
        if eid is not None:
            cur.execute("select 1 from bas_equipment where id = %s", (eid,))
            if cur.fetchone() is None:
                raise http.validation_error(t("없는 설비입니다"), fields=[f.field_error("equipment_id", "설비", str(eid))])
        kid = f.int_id(worker_id, "worker_id", "작업자")
        if kid is None:
            cur.execute("select worker_id from sys_user where id = %s", (user.id,))
            kid = (cur.fetchone() or {}).get("worker_id")
        row = {"work_order_id": wo["id"], "process_id": wo["process_id"], "equipment_id": eid, "worker_id": kid, "unit": wo["unit"], "note": f.opt_text(note)}
        packs.hook("validate_pop_work_result")(cur, row, user)
        cur.execute("""insert into pop_work_result (work_order_id, process_id, equipment_id, worker_id, started_at, unit, note, created_by)
                       values (%s, %s, %s, %s, now(), %s, %s, %s) returning *""", (wo["id"], wo["process_id"], eid, kid, wo["unit"], row["note"], user.login_id))
        saved = dict(cur.fetchone())
        packs.hook("after_save_pop_work_result")(cur, saved, user)
        packs.hook("on_result_started")(cur, saved, user)
    audit.log_change(request, user, "F-POP-02", f"pop_work_result:{saved['id']}", {"work_order_no": wo["work_order_no"]})
    return http.saved(request, f"{wo['work_order_no']} {t('작업 시작')}", back=f"{POP02}?id={saved['id']}",
                      data={"id": saved["id"], "work_order_id": wo["id"], "work_order_no": wo["work_order_no"], "started_at": saved["started_at"].isoformat()})


@router.post(POP02 + "/{id}/end")                                                      # F-POP-03 작업 종료
def result_end(request: Request, id: int, good_qty: str | None = Form(None), defect_qty: str | None = Form(None), unit: str | None = Form(None),
               note: str | None = Form(None), merge_lot_ids: str | None = Form(None), merge_relation: str | None = Form(None),
               user: rbac.User = rbac.require_fn("F-POP-03")):
    r = _require_result(id)
    if r["ended_at"] is not None:
        raise http.validation_error(t("이미 종료된 실적입니다"), fields=[f.field_error("id", "실적", str(id))])
    good = f.num(good_qty, "good_qty", "양품", required=True, nonneg=True)
    bad = f.num(defect_qty, "defect_qty", "불량", nonneg=True) or 0
    params = measure.params_for(r["process_id"])
    values, errs = measure.parse_form(params, _form(request))
    if errs:
        raise http.validation_error(t("필수 측정값이 비었습니다") if all(e["reason"] == t("필수") for e in errs) else t("측정값을 확인해 주세요"), fields=errs)
    try:
        attrs = packs.read_attrs(_form(request), "lot")
    except ValueError as exc:
        raise http.validation_error(str(exc), fields=[f.field_error("attrs", "속성", str(exc))]) from None
    merge_ids = _csv_ids(merge_lot_ids, "merge_lot_ids", "합병 LOT") or None    # 선택 — 재고 생산 LOT 을 이 실적의 LOT 에 합병 (별도 합병 LOT 없이)
    with conn.tx() as cur:
        cur.execute("select * from pop_work_result where id = %s for update", (id,))
        row = dict(cur.fetchone())
        row.update({"ended_at": datetime.now(), "good_qty": good, "defect_qty": bad, "unit": f.opt_text(unit) or row["unit"], "note": f.opt_text(note) or row["note"],
                    "measures": values})
        packs.hook("validate_pop_work_result")(cur, row, user)
        cur.execute("update pop_work_result set ended_at = now(), good_qty = %s, defect_qty = %s, unit = %s, note = %s, updated_at = now(), updated_by = %s where id = %s returning *",
                    (good, bad, row["unit"], row["note"], user.login_id, id))
        saved = dict(cur.fetchone())
        cur.execute("update pop_stop set ended_at = now(), updated_at = now(), updated_by = %s where work_result_id = %s and ended_at is null", (user.login_id, id))
        recorded = measure.record(cur, id, params, values, by=user.login_id)
        lot = lineage.make_product_lot(cur, work_result_id=id, by=user.login_id, qty=good, unit=saved["unit"], attrs=attrs,
                                       merge_parent_ids=merge_ids, merge_relation=f.opt_text(merge_relation) or lineage.MERGE, user=user)
        collected = measure.fill_collect(cur, saved, params, by=user.login_id)
        saved.update({"product_lot": lot, "product_lot_id": lot["id"], "measures": recorded + collected})
        packs.hook("after_save_pop_work_result")(cur, saved, user)
        packs.hook("on_result_closed")(cur, saved, user)
    audit.log_change(request, user, "F-POP-03", f"pop_work_result:{id}", {"lot_no": lot["lot_no"], "good_qty": str(good), "measures": len(recorded) + len(collected),
                                                                        **({"merge": merge_ids} if merge_ids else {})})
    deviated = [m["param_key"] for m in recorded + collected if m["deviated"]]
    return http.saved(request, f"{t('작업을 종료했습니다')} — {t('생산 LOT')} {lot['lot_no']}" + (f" · {t('이탈')} {len(deviated)}" if deviated else ""),
                      back=f"{POP02}?id={id}",
                      data={"id": id, "lot_id": lot["id"], "lot_no": lot["lot_no"], "label_url": f"{POP04}?lot={lot['id']}", "merged": merge_ids or [],
                            "measures": {m["param_key"]: {"value_num": templating.jsonable(m["value_num"]), "value_text": m["value_text"], "source": m["source"],
                                                          "deviated": m["deviated"]} for m in recorded + collected}, "deviated": deviated})


@router.post(POP02 + "/{id}/stop")                                                     # F-POP-04 정지 기록
def result_stop(request: Request, id: int, reason_code: str | None = Form(None), started_at: str | None = Form(None), ended_at: str | None = Form(None),
                note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-POP-04")):
    r = _require_result(id)
    with conn.tx() as cur:
        cur.execute("select * from pop_stop where work_result_id = %s and ended_at is null order by id desc limit 1 for update", (id,))
        open_stop = cur.fetchone()
        if open_stop is not None:
            end = f.a_datetime(ended_at, "ended_at", "정지 끝", default=datetime.now())
            cur.execute("update pop_stop set ended_at = %s, note = coalesce(%s, note), updated_at = now(), updated_by = %s where id = %s returning *",
                        (end, f.opt_text(note), user.login_id, open_stop["id"]))
            saved = dict(cur.fetchone())
            packs.hook("after_save_pop_stop")(cur, saved, user)
            action = "closed"
        else:
            if r["ended_at"] is not None:
                raise http.validation_error(t("종료된 실적에는 정지를 기록할 수 없습니다"), fields=[f.field_error("id", "실적", str(id))])
            code = f.req_text(reason_code, "reason_code", "정지 사유")
            cur.execute("select 1 from bas_code where group_code = 'STOP_REASON' and code = %s and use_yn = 'Y'", (code,))
            if cur.fetchone() is None:
                raise http.validation_error(t("정지 사유 코드가 아닙니다"), fields=[f.field_error("reason_code", "정지 사유", code)])
            start = f.a_datetime(started_at, "started_at", "정지 시작", default=datetime.now())
            end = f.a_datetime(ended_at, "ended_at", "정지 끝")
            row = {"work_result_id": id, "reason_code": code, "started_at": start, "ended_at": end, "note": f.opt_text(note)}
            packs.hook("validate_pop_stop")(cur, row, user)
            cur.execute("insert into pop_stop (work_result_id, reason_code, started_at, ended_at, note, created_by) values (%s, %s, %s, %s, %s, %s) returning *",
                        (id, code, start, end, row["note"], user.login_id))
            saved = dict(cur.fetchone())
            packs.hook("after_save_pop_stop")(cur, saved, user)
            action = "opened" if end is None else "recorded"
    audit.log_change(request, user, "F-POP-04", f"pop_stop:{saved['id']}", {"action": action})
    return http.saved(request, t("정지를 닫았습니다") if action == "closed" else t("정지를 기록했습니다"), back=f"{POP02}?id={id}",
                      data={"id": saved["id"], "action": action, "ended_at": saved["ended_at"].isoformat() if saved["ended_at"] else None})


@router.post(POP02 + "/{id}/scrap")                                                    # F-POP-05 폐기 기록 (종료 후에도 가능)
def result_scrap(request: Request, id: int, qty: str = Form(...), defect_code_id: str | None = Form(None), unit: str | None = Form(None),
                 user: rbac.User = rbac.require_fn("F-POP-05")):
    r = _require_result(id)
    q = f.num(qty, "qty", "폐기 수량", required=True, positive=True)
    did = f.int_id(defect_code_id, "defect_code_id", "불량코드")
    if did is not None and conn.q1("select 1 from bas_defect_code where id = %s", (did,)) is None:
        raise http.validation_error(t("없는 불량코드입니다"), fields=[f.field_error("defect_code_id", "불량코드", str(did))])
    with conn.tx() as cur:
        row = {"work_result_id": id, "defect_code_id": did, "qty": q, "unit": f.opt_text(unit) or r["unit"]}
        packs.hook("validate_pop_scrap")(cur, row, user)
        cur.execute("insert into pop_scrap (work_result_id, defect_code_id, qty, unit, created_by) values (%s, %s, %s, %s, %s) returning *",
                    (id, did, q, row["unit"], user.login_id))
        saved = dict(cur.fetchone())
        packs.hook("after_save_pop_scrap")(cur, saved, user)
    audit.log_change(request, user, "F-POP-05", f"pop_scrap:{saved['id']}", {"qty": str(q)})
    return http.saved(request, t("폐기를 기록했습니다"), back=f"{POP02}?id={id}", data={"id": saved["id"], "qty": float(q)})


# ── 분할 · 합병 (D-12 — 코어 화면 없음 · POP-02 버튼 · F-POP-03 의 계약 안) ──
def _csv_ids(text: str | None, name: str, label: str) -> list[int]:
    out = []
    for part in (text or "").replace("\n", ",").split(","):
        p = part.strip()
        if not p:
            continue
        n = lineage.resolve(p) if not p.isdigit() else None
        if n is not None:
            out.append(n.id)
        else:
            out.append(f.int_id(p, name, label, required=True))
    return out


@router.post(POP02 + "/{id}/split")
def result_split(request: Request, id: int, count: str = Form(...), qtys: str | None = Form(None), lot_id: str | None = Form(None),
                 relation: str | None = Form(None), user: rbac.User = rbac.require_fn("F-POP-03")):
    r = _require_result(id)
    parent = f.int_id(lot_id, "lot_id", "LOT") or r["product_lot_id"]
    if parent is None:
        raise http.validation_error(t("분할할 생산 LOT 이 없습니다"), fields=[f.field_error("lot_id", "생산 LOT", str(id))])
    qty_list = [x.strip() for x in (qtys or "").split(",") if x.strip()] or None
    with conn.tx() as cur:
        children = lineage.split(cur, parent_id=parent, count=f.int_id(count, "count", "분할 수", required=True), by=user.login_id, qtys=qty_list,
                                 relation=f.opt_text(relation) or lineage.SPLIT, user=user)
    audit.log_change(request, user, "F-POP-03", f"lot:{parent}", {"split": [c["lot_no"] for c in children]})
    return http.saved(request, f"{t('분할')} {len(children)}", back=f"{POP02}?id={id}",
                      data={"parent_id": parent, "lots": [{"id": c["id"], "lot_no": c["lot_no"], "qty": templating.jsonable(c["qty"])} for c in children]})


@router.post(POP02 + "/{id}/merge")
def result_merge(request: Request, id: int, lot_ids: str = Form(...), qty: str | None = Form(None), relation: str | None = Form(None),
                 user: rbac.User = rbac.require_fn("F-POP-03")):
    _require_result(id)
    ids = _csv_ids(lot_ids, "lot_ids", "LOT")
    with conn.tx() as cur:
        child = lineage.merge(cur, parent_ids=ids, by=user.login_id, qty=f.num(qty, "qty", "수량", positive=True), relation=f.opt_text(relation) or lineage.MERGE, user=user)
    audit.log_change(request, user, "F-POP-03", f"lot:{child['id']}", {"merge": ids})
    return http.saved(request, f"{t('합병')} — {child['lot_no']}", back=f"{POP02}?id={id}", data={"id": child["id"], "lot_no": child["lot_no"], "qty": templating.jsonable(child["qty"]), "parents": ids})


# ── POP-03 투입 스캔 ────────────────────────────────────────────────────
@router.get(POP03)                                                                     # 화면 — ?result= 실적 · ?no= LOT 스캔(미리 보기)
def inputs(request: Request, result: str | None = None, no: str | None = None, user: rbac.User = rbac.require_screen("POP-03")):
    rid = f.int_id(result, "result", "실적")
    ctx: dict = {"result": _require_result(rid) if rid else None, "rows": [], "lot": None, "scan_no": no or "", "open_results": [], "last_qty": None, "last_unit": None}
    if rid:
        ctx["rows"] = conn.q("""select x.*, l.lot_no, l.insp_status, i.item_code, i.item_name from pop_input x join lot l on l.id = x.material_lot_id
                                 left join bas_item i on i.id = l.item_id where x.work_result_id = %s order by x.id desc""", (rid,))
        last = next((x for x in ctx["rows"] if x["canceled_yn"] == "N"), None)      # 「투입량 직전 값 유지」 — 취소되지 않은 마지막 투입
        if last is not None:
            ctx["last_qty"], ctx["last_unit"] = last["qty"], last["unit"]
    else:
        ctx["open_results"] = conn.q("""select r.id, r.started_at, w.work_order_no, i.item_name from pop_work_result r join job_work_order w on w.id = r.work_order_id
                                         join bas_item i on i.id = w.item_id where r.ended_at is null order by r.started_at desc limit 50""")
    if no is not None and no.strip() != "":
        n = lineage.resolve(no)
        if n is None:
            return f.scan_miss(request, "pop/inputs.html", ctx, screen_id="POP-03", no=no, what="원재료 LOT")
        ctx["lot"] = n
    return templating.render(request, "pop/inputs.html", ctx, screen_id="POP-03")


@router.post(POP03)                                                                    # F-POP-06 투입 스캔 — 한 번 스캔 = 한 건
def input_scan(request: Request, work_result_id: str = Form(...), barcode: str = Form(...), qty: str | None = Form(None), unit: str | None = Form(None),
               user: rbac.User = rbac.require_fn("F-POP-06")):
    rid = f.int_id(work_result_id, "work_result_id", "실적", required=True)
    r = _require_result(rid)
    n = lineage.resolve(barcode)
    if n is None:
        raise http.validation_error(t("없는 LOT 번호입니다"), fields=[f.field_error("barcode", "원재료 LOT", barcode)])
    with conn.tx() as cur:
        row = {"work_result_id": rid, "material_lot_id": n.id, "qty": f.num(qty, "qty", "투입량", positive=True), "unit": f.opt_text(unit)}
        packs.hook("validate_pop_input")(cur, row, user)
        input_id = lineage.consume_material(cur, work_result_id=rid, material_lot_id=n.id, qty=row["qty"], by=user.login_id, unit=row["unit"])
        cur.execute("select * from pop_input where id = %s", (input_id,))
        packs.hook("after_save_pop_input")(cur, dict(cur.fetchone()), user)
    audit.log_change(request, user, "F-POP-06", f"pop_input:{input_id}", {"lot_no": n.no, "qty": str(row["qty"])})
    return http.saved(request, f"{t('투입')} {n.no}", back=f"{POP03}?result={rid}",
                      data={"id": input_id, "lot_id": n.id, "lot_no": n.no, "work_result_id": rid, "work_order_no": r["work_order_no"]})


@router.post(POP03 + "/{id}/cancel")                                                   # F-POP-07 투입 취소 (종료 전만)
def input_cancel(request: Request, id: int, user: rbac.User = rbac.require_fn("F-POP-07")):
    with conn.tx() as cur:
        input_id = lineage.cancel_consume(cur, input_id=id, by=user.login_id)
        cur.execute("select * from pop_input where id = %s", (input_id,))
        row = dict(cur.fetchone())
        packs.hook("after_save_pop_input")(cur, row, user)
    audit.log_change(request, user, "F-POP-07", f"pop_input:{id}")
    return http.saved(request, t("투입을 취소했습니다"), back=f"{POP03}?result={row['work_result_id']}", data={"id": id, "work_result_id": row["work_result_id"]})


# ── POP-04 LOT 라벨 ─────────────────────────────────────────────────────
@router.get(POP04)                                                                     # F-POP-08 생산 LOT 라벨 출력 (?lot= · ?no= 스캔)
def labels(request: Request, lot: str | None = None, no: str | None = None, size: str = "100x50", user: rbac.User = rbac.require_fn("F-POP-08")):
    lid = f.int_id(lot, "lot", "LOT")
    ctx: dict = {"rows": [], "scan_no": no or "", "size": size}
    if lid is None and no is not None and no.strip() != "":
        n = lineage.resolve(no)
        if n is None:
            ctx["rows"] = _recent_product_lots()
            return f.scan_miss(request, "pop/labels.html", ctx, screen_id="POP-04", no=no, what="생산 LOT")
        lid = n.id
    if lid is not None:
        label = printing.label_for(lid, size=size)
        return printing.render_print(request, "label_lot", {"labels": [label], "size": size, **label}, screen_id="POP-04")
    ctx["rows"] = _recent_product_lots()
    return templating.render(request, "pop/labels.html", ctx, screen_id="POP-04")


def _recent_product_lots() -> list[dict]:
    return conn.q("""select l.id, l.lot_no, l.kind, l.qty, l.unit, l.made_at, i.item_code, i.item_name, w.work_order_no, s.state
                       from lot l join v_lot_state s on s.lot_id = l.id left join bas_item i on i.id = l.item_id left join job_work_order w on w.id = l.work_order_id
                      where l.kind_base = 'PRODUCT' order by l.made_at desc, l.id desc limit 100""")
