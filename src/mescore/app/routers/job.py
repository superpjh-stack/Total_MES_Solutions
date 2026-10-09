"""job 라우터 — 작업지시 (기능 7 · 화면 3) · 담당 개발1.

쓰는 테이블: `job_work_order` `job_lot` · `ord_order_dtl.status`(지시 연결 상태만) — db-schema.md §2.
`ord_plan.status` 는 **바꾸지 않는다**(D-101 · 개발3 안): F-JOB-01 은 `확정` 계획만 받고(`계획` · `취소` 는 422) 상태 전이는 F-ORD-09 만 한다.
LOT 을 미리 만들지 않고 실적에 쓰지 않는다. 진행 여부는 저장하지 않고 실적 유무로 계산한다(`v_work_order_progress`).
번호는 `numbering.next("WORK_ORDER", cur=cur)` 만 만든다(G-C08).

행 잠금 (interfaces.md §1): 지시를 고치는 쪽(수정 · 마감 · 취소)은 `lock_work_order` = `for update`. 그 지시에 무엇을 붙이는 쪽
(개발2 `pop.assert_open` · `lineage._assert_open`)은 `for share`. 한 트랜잭션은 지시 행을 하나만 잠그고 순서는 실적/LOT 행 → 지시 행 → 채번 카운터.

훅 (interfaces.md §9 · D-504 · D-505): `validate_job_work_order` 저장 직전 · `after_save_job_work_order` 저장 직후(같은 tx) ·
`on_work_order_created`(F-JOB-01) · `on_work_order_closed`(F-JOB-03) · `on_work_order_canceled`(F-JOB-04).

담당 화면과 기능 (contracts/function-list.md)
  JOB-01 작업지시 /job/work-orders — F-JOB-01 등록 · F-JOB-02 수정 · F-JOB-03 마감 · F-JOB-04 취소 · F-JOB-05 조회
  JOB-02 지시 현황 /job/status — F-JOB-06 (오늘 · 이번 주 · 계획 대비 실적 · `?wo=` 실적 드릴다운 D-604 · 모바일 390px)
  JOB-03 작업지시서 출력 /job/print?id= — F-JOB-07 (`printing.render_print("work_order")` · 개발2 모듈이 아직 없으면 번호 텍스트 + 바코드 자리 `미확정`)
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from starlette.datastructures import FormData

from ...db import conn
from .. import measure, nav, numbering, packs, rbac, templating
from ..packs import t
from ..util import audit, http
from .bas import bad, contains, decimal_of, form_data, id_of_path, ref_of, text_of

router = APIRouter()

WORK_ORDERS, STATUS, PRINT = nav.path_of("JOB-01"), nav.path_of("JOB-02"), nav.path_of("JOB-03")
ST_WAIT, ST_RUN, ST_CLOSED, ST_CANCEL = "대기", "진행", "마감", "취소"
STATUSES = (ST_WAIT, ST_RUN, ST_CLOSED, ST_CANCEL)
DTL_WAIT, DTL_ORDERED = "대기", "지시"
PLAN_CONFIRMED = "확정"                           # D-101 — 이 상태의 계획만 지시로 이어진다 (F-ORD-09 가 올린다)
LIST_LIMIT = 500                                 # 목록 · 현황판은 `w.id desc`(최신 등록 우선) 로 이 안에서 — 잔존 데이터가 많아도 방금 만든 지시가 보인다
PRINTING_AVAILABLE = importlib.util.find_spec("mescore.app.printing") is not None     # 개발2 R2 — 있으면 그것으로 출력한다

WO_SELECT = """
select w.id, w.work_order_no, w.item_id, w.process_id, w.equipment_id, w.plan_id, w.order_dtl_id, w.bom_id, w.plan_qty, w.unit, w.plan_date,
       w.status, w.closed_at, w.closed_by, w.note, w.attrs, w.created_at, w.created_by, w.updated_at, w.updated_by,
       i.item_code, i.item_name, i.spec as item_spec, p.process_code, p.process_name, e.equip_code, e.equip_name,
       b.version as bom_version, pl.plan_no, od.line_no as order_line_no, oo.order_no, oo.due_date, pt.partner_name,
       v.started, v.result_count, v.open_count, v.good_qty, v.defect_qty,
       (select count(*) from job_lot jl where jl.work_order_id = w.id) as lot_line_count
  from job_work_order w
  join bas_item i on i.id = w.item_id
  join bas_process p on p.id = w.process_id
  left join bas_equipment e on e.id = w.equipment_id
  left join bas_bom b on b.id = w.bom_id
  left join ord_plan pl on pl.id = w.plan_id
  left join ord_order_dtl od on od.id = w.order_dtl_id
  left join ord_order oo on oo.id = od.order_id
  left join bas_partner pt on pt.id = oo.partner_id
  join v_work_order_progress v on v.work_order_id = w.id
"""
WO_SORT = {"work_order_no": "w.work_order_no", "plan_date": "w.plan_date", "item_code": "i.item_code", "process_code": "p.process_code",
           "plan_qty": "w.plan_qty", "status": "w.status", "created_at": "w.created_at"}
JOB_LOT_SELECT = """
select jl.id, jl.work_order_id, jl.item_id, jl.required_qty, jl.unit, jl.lot_id, i.item_code, i.item_name, l.lot_no
  from job_lot jl join bas_item i on i.id = jl.item_id left join lot l on l.id = jl.lot_id
 where jl.work_order_id = any(%s) order by jl.work_order_id, jl.id
"""


# ── 읽기 도우미 ─────────────────────────────────────────────────────────
def wo_of_key(raw: str) -> dict:
    """쿼리의 지시 키(`?wo=` · `?id=`) → 지시 행. 숫자면 id, 아니면 지시 번호(`W…` · 팩 접두) — D-604 추적 링크는 번호를 넘긴다. 없으면 404.
    경로의 `{id}` 는 계속 숫자만(`wo_of_path`)."""
    key = (raw or "").strip()
    if key.isascii() and key.isdigit():
        return wo_of_path(key)
    row = conn.q1(WO_SELECT + " where w.work_order_no = %s", (key[:60],)) if key else None
    if row is None:
        raise http.not_found()
    return row


def measures_of_result(work_result_id: int, process_id: int | None) -> list[dict]:
    """실적 한 건의 측정값 — 개발2 `measure.params_with_recorded` · `values_of` 그대로(라우터 SQL 0). 값이 없으면 `미수집`."""
    values = measure.values_of(work_result_id)
    out = []
    for prm in measure.params_with_recorded(process_id, values):
        v = values.get(prm["param_key"])
        out.append({"param_key": prm["param_key"], "label": t(prm.get("label") or prm["param_key"]), "unit": (v or {}).get("unit") or prm.get("unit"),
                    "value": measure.display_value(v), "value_num": (v or {}).get("value_num"), "value_text": (v or {}).get("value_text"),
                    "source": (v or {}).get("source") or prm.get("source"), "deviated": bool((v or {}).get("deviated")),
                    "measured_at": (v or {}).get("measured_at"), "recorded": v is not None, "recorded_only": bool(prm.get("recorded_only"))})
    return out


def wo_of_path(raw_id: str) -> dict:
    row = conn.q1(WO_SELECT + " where w.id = %s", (id_of_path(raw_id),))
    if row is None:
        raise http.not_found()
    return row


def lock_work_order(cur, work_order_id: int) -> dict:
    """지시 행을 `for update` 로 잠그고 **지금의 상태**를 돌려준다 — 수정 · 마감 · 취소가 판정하고 바꾸는 동안 실적 · LOT 이 새로 붙지 못한다.
    트랜잭션 밖에서 읽은 상태 · 건수는 낡았을 수 있다 — 판정은 이 잠금 뒤에 다시 읽은 값으로 한다."""
    cur.execute("select id, work_order_no, status, order_dtl_id, plan_id from job_work_order where id = %s for update", (work_order_id,))
    row = cur.fetchone()
    if row is None:
        raise http.not_found()
    return row


def result_counts(cur, work_order_id: int) -> tuple[int, int]:
    """(실적 수, 종료 안 된 실적 수) — 잠근 뒤에 센다."""
    cur.execute("select count(*) as n, count(*) filter (where ended_at is null) as open from pop_work_result where work_order_id = %s", (work_order_id,))
    r = cur.fetchone()
    return int(r["n"]), int(r["open"])


def _date_of(form: FormData, key: str, label: str, *, required: bool = False) -> date | None:
    value = text_of(form, key, label, max_len=10, required=required)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise bad("입력값을 확인해 주세요", key, f"날짜 형식(YYYY-MM-DD)이 아닙니다: {value}", label) from None


def active_bom_id(item_id: int) -> int | None:
    """그 품목의 사용 중인 BOM — 버전이 여럿이면 가장 최근 등록 것."""
    row = conn.q1("select id from bas_bom where item_id = %s and use_yn = 'Y' order by created_at desc, id desc limit 1", (item_id,))
    return row["id"] if row else None


def bom_lines(bom_id: int) -> list[dict]:
    return conn.q("select component_item_id, qty, unit, loss_rate from bas_bom_dtl where bom_id = %s order by seq, id", (bom_id,))


def options() -> dict[str, list[tuple[str, str]]]:
    return {
        "item_id": [(str(r["id"]), f"{r['item_code']} {r['item_name']}") for r in conn.q(
            "select id, item_code, item_name from bas_item where use_yn = 'Y' and item_type in ('제품', '반제품') order by item_code limit 1000")],
        "process_id": [(str(r["id"]), f"{r['process_code']} {r['process_name']}") for r in conn.q(
            "select id, process_code, process_name from bas_process where use_yn = 'Y' order by seq, process_code")],
        "equipment_id": [(str(r["id"]), f"{r['equip_code']} {r['equip_name']}") for r in conn.q(
            "select id, equip_code, equip_name from bas_equipment where use_yn = 'Y' order by equip_code")],
        "plan_id": [(str(r["id"]), f"{r['plan_no']} ({r['plan_date']} · {r['plan_qty']})") for r in conn.q(
            "select id, plan_no, plan_date, plan_qty from ord_plan where status = %s order by plan_date desc, id desc limit 500", (PLAN_CONFIRMED,))],   # D-101 확정만
        "order_dtl_id": [(str(r["id"]), f"{r['order_no']} #{r['line_no']} ({r['item_code']} {r['qty']})") for r in conn.q(
            """select d.id, o.order_no, d.line_no, i.item_code, d.qty from ord_order_dtl d join ord_order o on o.id = d.order_id join bas_item i on i.id = d.item_id
                where o.status <> '취소' order by o.order_date desc, d.line_no limit 500""")],
        "status": [(s, s) for s in STATUSES],
    }


# ── JOB-01 작업지시 ───────────────────────────────────────────────────────
@router.get(WORK_ORDERS, response_class=HTMLResponse)                                              # F-JOB-05 작업지시 조회 = 화면 GET
def work_orders(request: Request, date_from: str = "", date_to: str = "", item_id: str = "", process_id: str = "", status: str = "",
                no: str = "", edit: str = "", sort: str = "", user: rbac.User = rbac.require_fn("F-JOB-05")) -> HTMLResponse:
    where, params = ["true"], []
    for key, val in (("date_from", date_from), ("date_to", date_to)):
        if val.strip():
            try:
                d = date.fromisoformat(val.strip())
            except ValueError:
                raise bad("입력값을 확인해 주세요", key, f"날짜 형식(YYYY-MM-DD)이 아닙니다: {val}", "기간") from None
            where.append("w.plan_date >= %s" if key == "date_from" else "w.plan_date <= %s")
            params.append(d)
    for key, val in (("item_id", item_id), ("process_id", process_id)):
        if val.strip():
            if not val.strip().isdigit():
                raise bad("입력값을 확인해 주세요", key, f"없는 값입니다: {val}")
            where.append(f"w.{key} = %s")
            params.append(int(val))
    if status.strip():
        if status not in STATUSES:
            raise bad("입력값을 확인해 주세요", "status", f"{' · '.join(STATUSES)} 중 하나: {status}", "상태")
        if status == ST_RUN:
            where.append("w.status = '대기' and v.started")        # 진행 = 대기 상태인데 실적이 있는 것 (저장하지 않는다)
        elif status == ST_WAIT:
            where.append("w.status = '대기' and not v.started")
        else:
            where.append("w.status = %s")
            params.append(status)
    if no.strip():
        where.append(contains("w.work_order_no"))
        params.append(no.strip())
    order = http.sort_clause(sort, WO_SORT, "w.id desc")                                                          # D-37 — 기본은 최신 등록 우선
    rows = conn.q(WO_SELECT + f" where {' and '.join(where)} order by {order}, w.id desc limit {LIST_LIMIT}", params)
    for r in rows:
        r["progress"] = ST_RUN if (r["status"] == ST_WAIT and r["started"]) else r["status"]
    editing = wo_of_path(edit) if edit else None
    if editing:
        editing["lots"] = conn.q(JOB_LOT_SELECT, ([editing["id"]],))
    return templating.render(request, "job/work_orders.html", {
        "rows": rows, "editing": editing, "options": options(), "path": WORK_ORDERS, "print_path": PRINT, "statuses": STATUSES,
        "f": {"date_from": date_from, "date_to": date_to, "item_id": item_id, "process_id": process_id, "status": status, "no": no, "edit": edit},
        "next_no": numbering.peek("WORK_ORDER") if numbering.rule("WORK_ORDER") else None,
        "attrs_specs": packs.attrs_of("job_work_order"),
        "can": {"create": user.can("F-JOB-01"), "update": user.can("F-JOB-02"), "close": user.can("F-JOB-03"), "cancel": user.can("F-JOB-04")},
    }, screen_id="JOB-01")


@router.post(WORK_ORDERS)                                                                            # F-JOB-01 작업지시 등록
def create_work_order(request: Request, user: rbac.User = rbac.require_fn("F-JOB-01"), form: FormData = Depends(form_data)):
    item_id = ref_of(form, "item_id", "품목", "bas_item", required=True)
    process_id = ref_of(form, "process_id", "공정", "bas_process", required=True)
    equipment_id = ref_of(form, "equipment_id", "설비", "bas_equipment")
    plan_id = ref_of(form, "plan_id", "생산계획", "ord_plan")
    plan = None
    if plan_id is not None:                                                                          # D-101 — 확정된 계획만 지시로 이어진다
        plan = conn.q1("select plan_no, status, order_dtl_id, plan_date from ord_plan where id = %s", (plan_id,))
        if plan["status"] != PLAN_CONFIRMED:
            raise bad("확정된 계획만 지시로 이어진다", "plan_id", f"{plan['plan_no']} 상태 {plan['status']}", "생산계획")
    order_dtl_id = ref_of(form, "order_dtl_id", "수주 상세", "ord_order_dtl")
    if plan is not None and plan["order_dtl_id"] is not None:                                         # DEF-QA3-002 — 계획의 수주 상세를 잇는다
        if order_dtl_id is None:
            order_dtl_id = plan["order_dtl_id"]
        elif order_dtl_id != plan["order_dtl_id"]:
            raise bad("입력값을 확인해 주세요", "order_dtl_id", f"생산계획 {plan['plan_no']} 의 수주 상세와 다릅니다", "수주 상세")
    bom_id = ref_of(form, "bom_id", "BOM", "bas_bom") if text_of(form, "bom_id", "BOM", max_len=20) else active_bom_id(item_id)
    if bom_id is not None and conn.q1("select 1 as hit from bas_bom where id = %s and item_id = %s", (bom_id, item_id)) is None:
        raise bad("입력값을 확인해 주세요", "bom_id", "그 품목의 BOM 이 아닙니다", "BOM")
    plan_qty = decimal_of(form, "plan_qty", "계획 수량", required=True, positive=True)
    row: dict[str, Any] = {
        "item_id": item_id, "process_id": process_id, "equipment_id": equipment_id, "plan_id": plan_id, "order_dtl_id": order_dtl_id,
        "bom_id": bom_id, "plan_qty": plan_qty, "unit": text_of(form, "unit", "단위", max_len=20),
        "plan_date": _date_of(form, "plan_date", "계획일") or (plan["plan_date"] if plan else None), "note": text_of(form, "note", "비고", max_len=1000), "status": ST_WAIT,
    }
    if row["unit"] is None:
        row["unit"] = (conn.q1("select unit from bas_item where id = %s", (item_id,)) or {}).get("unit")
    try:
        row["attrs"] = packs.read_attrs(form, "job_work_order")
    except ValueError as exc:
        raise http.validation_error(str(exc), fields=[{"name": "attrs", "label": t("업종 속성"), "reason": str(exc)}]) from None
    lines = bom_lines(bom_id) if bom_id else []
    with conn.tx() as cur:
        packs.hook("validate_job_work_order")(cur, row, user)
        row["work_order_no"] = numbering.next("WORK_ORDER", cur=cur)                             # 채번 카운터는 마지막에 (교착 순서)
        cur.execute("""insert into job_work_order (work_order_no, item_id, process_id, equipment_id, plan_id, order_dtl_id, bom_id, plan_qty, unit,
                                                   plan_date, status, note, attrs, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s) returning id""",
                    (row["work_order_no"], item_id, process_id, equipment_id, plan_id, order_dtl_id, bom_id, plan_qty, row["unit"], row["plan_date"],
                     ST_WAIT, row["note"], json.dumps(row["attrs"], ensure_ascii=False), user.login_id))
        row["id"] = cur.fetchone()["id"]
        row["lots"] = []
        for ln in lines:                                                                             # BOM 이 있으면 소요 원재료 줄 (LOT 은 비움)
            req = (Decimal(ln["qty"]) * plan_qty * (Decimal(1) + Decimal(ln["loss_rate"] or 0) / Decimal(100))).quantize(Decimal("0.001"))
            cur.execute("insert into job_lot (work_order_id, item_id, required_qty, unit, created_by) values (%s, %s, %s, %s, %s) returning id",
                        (row["id"], ln["component_item_id"], req, ln["unit"], user.login_id))
            row["lots"].append({"id": cur.fetchone()["id"], "item_id": ln["component_item_id"], "required_qty": req, "unit": ln["unit"]})
        if order_dtl_id is not None:
            cur.execute("update ord_order_dtl set status = %s, updated_at = now(), updated_by = %s where id = %s and status = %s",
                        (DTL_ORDERED, user.login_id, order_dtl_id, DTL_WAIT))
        packs.hook("after_save_job_work_order")(cur, row, user)
        packs.hook("on_work_order_created")(cur, row, user)
    audit.log_change(request, user, "F-JOB-01", f"job_work_order:{row['work_order_no']}", {"id": row["id"], "item_id": item_id, "plan_qty": str(plan_qty), "lots": len(row["lots"])})
    return http.saved(request, t("작업지시를 등록했습니다") + f" — {row['work_order_no']}", back=WORK_ORDERS,
                      data={"id": row["id"], "work_order_no": row["work_order_no"], "status": ST_WAIT, "job_lot_rows": len(row["lots"])})


@router.post(WORK_ORDERS + "/{id}")                                                                  # F-JOB-02 작업지시 수정
def update_work_order(request: Request, id: str, user: rbac.User = rbac.require_fn("F-JOB-02"), form: FormData = Depends(form_data)):
    existing = wo_of_path(id)
    row: dict[str, Any] = {}
    if "plan_qty" in form:
        row["plan_qty"] = decimal_of(form, "plan_qty", "계획 수량", required=True, positive=True)
    if "equipment_id" in form:
        row["equipment_id"] = ref_of(form, "equipment_id", "설비", "bas_equipment")
    for key, label in (("item_id", "품목"), ("process_id", "공정")):
        if key in form:
            row[key] = ref_of(form, key, label, "bas_item" if key == "item_id" else "bas_process", required=True)
    if "plan_date" in form:
        row["plan_date"] = _date_of(form, "plan_date", "계획일")
    if "unit" in form:
        row["unit"] = text_of(form, "unit", "단위", max_len=20)
    if "note" in form:
        row["note"] = text_of(form, "note", "비고", max_len=1000)
    if "status" in form:
        raise bad("상태는 마감 · 취소 버튼으로만 바꾼다", "status", str(form.get("status")), "상태")
    if any(k.startswith("attr_") for k in form.keys()):
        try:
            row["attrs"] = {**(existing.get("attrs") or {}), **packs.read_attrs(form, "job_work_order")}
        except ValueError as exc:
            raise http.validation_error(str(exc), fields=[{"name": "attrs", "label": t("업종 속성"), "reason": str(exc)}]) from None
    if not row:
        raise http.validation_error(t("바꿀 값이 없습니다"))
    with conn.tx() as cur:
        locked = lock_work_order(cur, existing["id"])
        if locked["status"] in (ST_CLOSED, ST_CANCEL):
            raise bad(f"{locked['status']} 상태의 작업지시는 수정할 수 없습니다", "status", locked["status"], "상태")
        n_results, _open = result_counts(cur, existing["id"])
        if n_results:
            beyond = sorted(set(row) - {"plan_qty", "equipment_id", "note", "attrs"})
            if beyond:
                raise bad("진행 중인 작업지시는 수량 · 설비만 바꿀 수 있습니다", beyond[0], f"실적 {n_results}건", "변경 항목")
        merged = {**existing, **row}
        packs.hook("validate_job_work_order")(cur, merged, user)
        sets = ", ".join(f"{k} = %s::jsonb" if k == "attrs" else f"{k} = %s" for k in row)
        vals = [json.dumps(v, ensure_ascii=False) if k == "attrs" else v for k, v in row.items()]
        cur.execute(f"update job_work_order set {sets}, updated_at = now(), updated_by = %s where id = %s", [*vals, user.login_id, existing["id"]])
        packs.hook("after_save_job_work_order")(cur, merged, user)
    audit.log_change(request, user, "F-JOB-02", f"job_work_order:{existing['work_order_no']}", {"id": existing["id"], "changed": list(row)})
    return http.saved(request, t("작업지시를 수정했습니다") + f" — {existing['work_order_no']}", back=WORK_ORDERS,
                      data={"id": existing["id"], "work_order_no": existing["work_order_no"], "changed": list(row)})


@router.post(WORK_ORDERS + "/{id}/close")                                                            # F-JOB-03 작업지시 마감
def close_work_order(request: Request, id: str, user: rbac.User = rbac.require_fn("F-JOB-03")):
    existing = wo_of_path(id)
    with conn.tx() as cur:
        locked = lock_work_order(cur, existing["id"])
        if locked["status"] in (ST_CLOSED, ST_CANCEL):
            raise bad(f"이미 {locked['status']} 상태입니다", "status", locked["status"], "상태")
        _n, n_open = result_counts(cur, existing["id"])
        if n_open:
            raise bad("종료되지 않은 실적이 있어 마감할 수 없습니다", "open_count", f"진행 중 실적 {n_open}건", "실적")
        cur.execute("update job_work_order set status = %s, closed_at = now(), closed_by = %s, updated_at = now(), updated_by = %s where id = %s",
                    (ST_CLOSED, user.login_id, user.login_id, existing["id"]))
        cur.execute(WO_SELECT + " where w.id = %s", (existing["id"],))
        wo = cur.fetchone()
        packs.hook("on_work_order_closed")(cur, wo, user)
    audit.log_change(request, user, "F-JOB-03", f"job_work_order:{existing['work_order_no']}", {"id": existing["id"]})
    return http.saved(request, t("작업지시를 마감했습니다") + f" — {existing['work_order_no']}", back=WORK_ORDERS,
                      data={"id": existing["id"], "work_order_no": existing["work_order_no"], "status": ST_CLOSED})


@router.post(WORK_ORDERS + "/{id}/cancel")                                                           # F-JOB-04 작업지시 취소
def cancel_work_order(request: Request, id: str, user: rbac.User = rbac.require_fn("F-JOB-04")):
    existing = wo_of_path(id)
    with conn.tx() as cur:
        locked = lock_work_order(cur, existing["id"])
        if locked["status"] in (ST_CLOSED, ST_CANCEL):
            raise bad(f"이미 {locked['status']} 상태입니다", "status", locked["status"], "상태")
        n_results, _open = result_counts(cur, existing["id"])
        if n_results:
            raise bad("실적이 있는 작업지시는 취소할 수 없습니다", "result_count", f"실적 {n_results}건", "실적")
        cur.execute("update job_work_order set status = %s, updated_at = now(), updated_by = %s where id = %s", (ST_CANCEL, user.login_id, existing["id"]))
        if locked["order_dtl_id"] is not None:                                                      # 다른 살아 있는 지시가 없으면 수주 상세를 대기로
            cur.execute("""update ord_order_dtl set status = %s, updated_at = now(), updated_by = %s where id = %s and status = %s
                             and not exists (select 1 from job_work_order x where x.order_dtl_id = %s and x.id <> %s and x.status <> %s)""",
                        (DTL_WAIT, user.login_id, locked["order_dtl_id"], DTL_ORDERED, locked["order_dtl_id"], existing["id"], ST_CANCEL))
        cur.execute(WO_SELECT + " where w.id = %s", (existing["id"],))
        wo = cur.fetchone()
        packs.hook("on_work_order_canceled")(cur, wo, user)                                          # D-505
    audit.log_change(request, user, "F-JOB-04", f"job_work_order:{existing['work_order_no']}", {"id": existing["id"]})
    return http.saved(request, t("작업지시를 취소했습니다") + f" — {existing['work_order_no']}", back=WORK_ORDERS,
                      data={"id": existing["id"], "work_order_no": existing["work_order_no"], "status": ST_CANCEL})


# ── JOB-02 지시 현황 ─────────────────────────────────────────────────────
@router.get(STATUS, response_class=HTMLResponse)                                                     # F-JOB-06 지시 현황 조회
def status_board(request: Request, range: str = "today", wo: str = "", user: rbac.User = rbac.require_fn("F-JOB-06")) -> HTMLResponse:
    today = date.today()
    if range not in ("today", "week"):
        raise bad("입력값을 확인해 주세요", "range", f"today 또는 week: {range}", "기간")
    frm = today if range == "today" else today - timedelta(days=today.weekday())
    to = today if range == "today" else frm + timedelta(days=6)
    rows = conn.q(WO_SELECT + " where (w.plan_date between %s and %s) or (w.plan_date is null and w.created_at::date between %s and %s) "
                  f"order by w.id desc limit {LIST_LIMIT}", (frm, to, frm, to))                 # 최신 등록 우선 — 상한 안에 방금 만든 지시가 든다
    for r in rows:
        r["progress"] = ST_RUN if (r["status"] == ST_WAIT and r["started"]) else r["status"]
        r["achieve_pct"] = float((Decimal(r["good_qty"]) / Decimal(r["plan_qty"]) * 100).quantize(Decimal("0.1"))) if r["plan_qty"] else None
    summary = {s: sum(1 for r in rows if r["progress"] == s) for s in STATUSES}
    summary["전체"] = len(rows)
    detail, results = None, []
    if wo.strip():
        detail = wo_of_key(wo)                                                                          # id 또는 지시 번호 (D-604)
        results = conn.q("""select r.id, r.process_id, r.started_at, r.ended_at, r.good_qty, r.defect_qty, r.unit, e.equip_code, e.equip_name, k.worker_name, l.lot_no
                              from pop_work_result r left join bas_equipment e on e.id = r.equipment_id left join bas_worker k on k.id = r.worker_id
                              left join lot l on l.id = r.product_lot_id where r.work_order_id = %s order by r.started_at desc""", (detail["id"],))
        for r in results:                                                                            # D-604 — 실적별 측정값 (선언 + 기록만 남은 키 · 빈 값 미수집)
            r["measures"] = measures_of_result(r["id"], r["process_id"] or detail["process_id"])
    return templating.render(request, "job/status.html", {
        "rows": rows, "summary": summary, "range": range, "frm": frm, "to": to, "detail": detail, "results": results, "path": STATUS, "print_path": PRINT,
    }, screen_id="JOB-02")


# ── JOB-03 작업지시서 출력 ───────────────────────────────────────────────
@router.get(PRINT, response_class=HTMLResponse)                                                      # F-JOB-07 작업지시서 출력
def print_work_order(request: Request, id: str = "", user: rbac.User = rbac.require_fn("F-JOB-07")) -> HTMLResponse:
    if not id.strip():
        return templating.render(request, "job/print_pick.html", {
            "rows": conn.q(WO_SELECT + f" where w.status <> '취소' order by w.id desc limit {LIST_LIMIT}"), "path": PRINT}, screen_id="JOB-03")
    wo = wo_of_key(id)                                                                                # id 또는 지시 번호 · 없으면 404
    wo["lots"] = conn.q(JOB_LOT_SELECT, ([wo["id"]],))
    wo.update({"equipment_code": wo["equip_code"], "equipment_name": wo["equip_name"], "spec": wo["item_spec"]})   # 개발2 양식의 열 이름
    params = conn.q("select param_key, label, unit, value_type, min_value, max_value, required_yn, source, collect_tag, seq from bas_process_param "
                    "where process_id = %s and use_yn = 'Y' order by seq, param_key", (wo["process_id"],))
    bom_rows = [{**l, "seq": i} for i, l in enumerate(wo["lots"], start=1)]
    data = {"work_order": wo, "wo": wo, "lots": wo["lots"], "bom_rows": bom_rows, "params": params,            # 양식 계약: wo · bom_rows · params
            "printed_at": datetime.now(), "printed_by": user.login_id}
    if PRINTING_AVAILABLE:
        from .. import printing  # noqa — 개발2 모듈. 있을 때만
        if _has_template("print/work_order.html"):                                              # 개발2 양식이 있으면 그것으로
            return printing.render_print(request, "work_order", data, screen_id="JOB-03")
        return templating.render(request, "job/print.html", {**data, "barcode_svg": printing.barcode_svg(wo["work_order_no"]),
                                                             "barcode_note": "print/work_order.html(개발2) 대기 — 바코드만 printing 것"}, screen_id="JOB-03")
    return templating.render(request, "job/print.html", {**data, "barcode_svg": None, "barcode_note": "printing 모듈(개발2) 대기"}, screen_id="JOB-03")


def _has_template(name: str) -> bool:
    """개발2 의 인쇄 양식이 검색 경로(팩 → 코어)에 있는가 — 있으면 그것을 쓰고, 없으면 job/print.html 로 그린다(조용한 폴백이 아니라 화면에 사유를 적는다)."""
    from jinja2 import TemplateNotFound
    try:
        templating.env.loader.get_source(templating.env, name)
    except TemplateNotFound:
        return False
    return True
