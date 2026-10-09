"""품질 `qua` — 검사 계획 · 검사 결과 · 판정 · 불량 집계 · 이상/시정 (F-QUA-01~11 · 개발2).

쓰기 경계(db-schema.md §2): qua_* 5 · lot.insp_status. 번호는 numbering(ISSUE — D-202) 뿐. 집계 SQL 은 stats(개발3) 뿐.
훅: F-QUA-05 on_inspection_judged. 모든 쓰기 전 validate_<table> · 후 after_save_<table>(D-504).
"""

from __future__ import annotations

from datetime import date, datetime

import anyio
from fastapi import APIRouter, Form, Request

from ...db import conn
from .. import lineage, measure, nav, packs, rbac, templating
from ..packs import t
from ..util import audit, http
from . import _dev2 as f

router = APIRouter()
QUA01, QUA02, QUA03, QUA04 = (nav.path_of(s) for s in ("QUA-01", "QUA-02", "QUA-03", "QUA-04"))
INSP_TYPES = ("입고", "공정", "최종")
JUDGEMENTS = ("합격", "불합격", "조건부")
ISSUE_STATUS = ("발생", "조치", "종결")


def _form(request: Request):
    return anyio.from_thread.run(request.form)


def _numbering():
    from .. import numbering  # noqa: PLC0415 — 개발1 모듈
    return numbering


def _items() -> list[dict]:
    return conn.q("select id, item_code, item_name from bas_item where use_yn = 'Y' order by item_code")


def _processes() -> list[dict]:
    return conn.q("select id, process_code, process_name from bas_process where use_yn = 'Y' order by seq, process_code")


def _plan_rows(insp_type: str | None, item_id: int | None, process_id: int | None) -> list[dict]:
    return conn.q("""select p.*, i.item_code, i.item_name, c.process_code, c.process_name,
                            (select count(*) from qua_insp_item x where x.plan_id = p.id) as recorded
                       from qua_insp_plan p left join bas_item i on i.id = p.item_id left join bas_process c on c.id = p.process_id
                      where (%s::text is null or p.insp_type = %s) and (%s::bigint is null or p.item_id = %s) and (%s::bigint is null or p.process_id = %s)
                      order by p.insp_type, p.item_id nulls first, p.process_id nulls first, p.seq, p.id""",
                  (insp_type, insp_type, item_id, item_id, process_id, process_id))


def plan_for_lot(insp_type: str, n: lineage.Node, process_id: int | None = None) -> list[dict]:
    """LOT 에 적용되는 계획 항목 — 유형 + (품목 일치 또는 품목 무관) + (공정 일치 또는 공정 무관). use_yn=Y."""
    return conn.q("""select * from qua_insp_plan where insp_type = %s and use_yn = 'Y'
                      and (item_id is null or item_id = %s) and (process_id is null or process_id = %s) order by seq, id""",
                  (insp_type, n.item_id, process_id))


def _insp_process(n: lineage.Node, process_id) -> int | None:
    """검사 공정 — 고른 공정(`process_id`) → 없으면 LOT 의 공정. 여러 공정을 거친 LOT 에 다른 공정의 검사를 할 때 고른다 (개발3 §3-18)."""
    pid = f.int_id(process_id, "process_id", "검사 공정")
    if pid is None:
        return conn.q1("select process_id from lot where id = %s", (n.id,))["process_id"]
    if conn.q1("select 1 as x from bas_process where id = %s and use_yn = 'Y'", (pid,)) is None:
        raise http.validation_error(t("없는 공정입니다"), fields=[f.field_error("process_id", "검사 공정", str(pid))])
    return pid


# ── QUA-01 검사 계획 ─────────────────────────────────────────────────────
@router.get(QUA01)                                                                     # F-QUA-03 검사 계획 조회
def plans(request: Request, insp_type: str | None = None, item_id: str | None = None, process_id: str | None = None,
          user: rbac.User = rbac.require_fn("F-QUA-03")):
    it = f.choice(insp_type, "insp_type", "검사 유형", INSP_TYPES, required=False)
    iid, pid = f.int_id(item_id, "item_id", "품목"), f.int_id(process_id, "process_id", "공정")
    return templating.render(request, "qua/plans.html",
                             {"rows": _plan_rows(it, iid, pid), "insp_type": it or "", "item_id": iid, "process_id": pid,
                              "type_options": [(x, t(x)) for x in INSP_TYPES], "item_options": f.options(_items(), "id", "item_code", "item_name"),
                              "process_options": f.options(_processes(), "id", "process_code", "process_name"),
                              "value_types": list(measure.VALUE_TYPES)}, screen_id="QUA-01")


def _plan_lines(form) -> list[dict]:
    keys, labels = f.list_form(form, "item_key"), f.list_form(form, "label")
    units, vtypes = f.list_form(form, "unit"), f.list_form(form, "value_type")
    stds, mins, maxs = f.list_form(form, "standard"), f.list_form(form, "min_value"), f.list_form(form, "max_value")
    lines = []
    for i, key in enumerate(keys):
        k = key.strip()
        if not k:
            continue
        vt = (vtypes[i] if i < len(vtypes) else "") or "number"
        if vt not in measure.VALUE_TYPES:
            raise http.validation_error(t("항목 형식이 올바르지 않습니다"), fields=[f.field_error("value_type", "형식", vt)])
        lines.append({"item_key": k, "label": (labels[i].strip() if i < len(labels) and labels[i].strip() else k), "unit": f.opt_text(units[i]) if i < len(units) else None,
                      "value_type": vt, "standard": f.opt_text(stds[i]) if i < len(stds) else None,
                      "min_value": f.num(mins[i] if i < len(mins) else None, "min_value", "하한"), "max_value": f.num(maxs[i] if i < len(maxs) else None, "min_value", "상한"),
                      "seq": i + 1})
    if not lines:
        raise http.validation_error(t("검사 항목이 한 줄도 없습니다"), fields=[f.field_error("item_key", "항목 키", t("필수"))])
    dup = {l["item_key"] for l in lines if sum(1 for x in lines if x["item_key"] == l["item_key"]) > 1}
    if dup:
        raise http.validation_error(t("항목 키가 겹칩니다"), fields=[f.field_error("item_key", "항목 키", str(sorted(dup)))])
    return lines


@router.post(QUA01)                                                                    # F-QUA-01 검사 계획 등록 (항목 N줄)
def plan_create(request: Request, insp_type: str = Form(...), item_id: str | None = Form(None), process_id: str | None = Form(None),
                user: rbac.User = rbac.require_fn("F-QUA-01")):
    it = f.choice(insp_type, "insp_type", "검사 유형", INSP_TYPES)
    iid, pid = f.int_id(item_id, "item_id", "품목"), f.int_id(process_id, "process_id", "공정")
    if iid is None and pid is None:
        raise http.validation_error(t("품목 또는 공정을 고릅니다"), fields=[f.field_error("item_id", "품목", t("필수")), f.field_error("process_id", "공정", t("필수"))])
    if iid is not None and conn.q1("select 1 from bas_item where id = %s", (iid,)) is None:
        raise http.validation_error(t("없는 품목입니다"), fields=[f.field_error("item_id", "품목", str(iid))])
    if pid is not None and conn.q1("select 1 from bas_process where id = %s", (pid,)) is None:
        raise http.validation_error(t("없는 공정입니다"), fields=[f.field_error("process_id", "공정", str(pid))])
    lines = _plan_lines(_form(request))
    ids = []
    with conn.tx() as cur:
        for ln in lines:
            cur.execute("select id from qua_insp_plan where insp_type = %s and coalesce(item_id, 0) = coalesce(%s, 0) and coalesce(process_id, 0) = coalesce(%s, 0) and item_key = %s",
                        (it, iid, pid, ln["item_key"]))
            if cur.fetchone():
                raise http.validation_error(t("이미 있는 검사 항목입니다"), fields=[f.field_error("item_key", "항목 키", ln["item_key"])])
            row = {**ln, "insp_type": it, "item_id": iid, "process_id": pid}
            packs.hook("validate_qua_insp_plan")(cur, row, user)
            cur.execute("""insert into qua_insp_plan (insp_type, item_id, process_id, item_key, label, unit, value_type, standard, min_value, max_value, seq, created_by)
                           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *""",
                        (it, iid, pid, ln["item_key"], ln["label"], ln["unit"], ln["value_type"], ln["standard"], ln["min_value"], ln["max_value"], ln["seq"], user.login_id))
            saved = dict(cur.fetchone())
            packs.hook("after_save_qua_insp_plan")(cur, saved, user)
            ids.append(saved["id"])
    audit.log_change(request, user, "F-QUA-01", f"qua_insp_plan:{it}:{iid or '-'}:{pid or '-'}", {"items": len(ids)})
    return http.saved(request, f"{t('검사 계획')} {len(ids)}", data={"ids": ids, "items": len(ids)})


@router.post(QUA01 + "/{id}")                                                          # F-QUA-02 검사 계획 수정 (항목 한 줄 — 기록된 키는 못 지운다)
def plan_update(request: Request, id: int, label: str | None = Form(None), unit: str | None = Form(None), standard: str | None = Form(None),
                min_value: str | None = Form(None), max_value: str | None = Form(None), seq: str | None = Form(None), use_yn: str | None = Form(None),
                user: rbac.User = rbac.require_fn("F-QUA-02")):
    p = conn.q1("select * from qua_insp_plan where id = %s", (id,))
    if p is None:
        raise http.not_found(t("없는 검사 항목입니다"))
    use = f.choice(use_yn, "use_yn", "사용 여부", ("Y", "N"), required=False) or p["use_yn"]
    if use == "N" and conn.q1("select 1 from qua_insp_item where plan_id = %s", (id,)):
        raise http.validation_error(t("기록된 검사 항목은 지울 수 없습니다"), fields=[f.field_error("use_yn", "항목 키", p["item_key"])])
    row = {**p, "label": f.opt_text(label) or p["label"], "unit": f.opt_text(unit) if unit is not None else p["unit"],
           "standard": f.opt_text(standard) if standard is not None else p["standard"],
           "min_value": f.num(min_value, "min_value", "하한") if min_value not in (None, "") else p["min_value"],
           "max_value": f.num(max_value, "max_value", "상한") if max_value not in (None, "") else p["max_value"],
           "seq": f.int_id(seq, "seq", "순서") if seq not in (None, "") else p["seq"], "use_yn": use}
    with conn.tx() as cur:
        packs.hook("validate_qua_insp_plan")(cur, row, user)
        cur.execute("""update qua_insp_plan set label = %s, unit = %s, standard = %s, min_value = %s, max_value = %s, seq = %s, use_yn = %s, updated_at = now(), updated_by = %s
                       where id = %s returning *""", (row["label"], row["unit"], row["standard"], row["min_value"], row["max_value"], row["seq"], use, user.login_id, id))
        saved = dict(cur.fetchone())
        packs.hook("after_save_qua_insp_plan")(cur, saved, user)
    audit.log_change(request, user, "F-QUA-02", f"qua_insp_plan:{id}")
    return http.saved(request, t("검사 계획을 수정했습니다"), data={"id": id, "use_yn": use})


# ── QUA-02 검사 결과 ─────────────────────────────────────────────────────
def _inspection_rows(frm: date, to: date, insp_type: str | None, judgement: str | None, lot_no: str | None) -> list[dict]:
    rows = conn.q("""select q.*, l.lot_no, l.kind, i.item_code, i.item_name,
                            (select count(*) from qua_insp_item x where x.inspection_id = q.id) as item_count,
                            (select count(*) from qua_insp_item x where x.inspection_id = q.id and x.deviated) as deviated_count
                       from qua_inspection q join lot l on l.id = q.lot_id left join bas_item i on i.id = l.item_id
                      where q.inspected_at::date between %s and %s and (%s::text is null or q.insp_type = %s)
                        and (%s::text is null or q.judgement = %s) and (%s::text is null or l.lot_no ilike %s)
                      order by q.inspected_at desc, q.id desc limit 300""",
                  (frm, to, insp_type, insp_type, judgement, judgement, lot_no, f"%{lot_no or ''}%"))
    if rows:
        items = conn.q("select * from qua_insp_item where inspection_id = any(%s) order by id", ([r["id"] for r in rows],))
        by: dict[int, list] = {}
        for it in items:
            by.setdefault(it["inspection_id"], []).append(it)
        for r in rows:
            r["items"] = by.get(r["id"], [])
    return rows


@router.get(QUA02)                                                                     # F-QUA-06 검사 결과 조회 (스캔 ?no=)
def inspections(request: Request, no: str | None = None, insp_type: str | None = None, frm: str | None = None, to: str | None = None,
                judgement: str | None = None, lot: str | None = None, process_id: str | None = None, user: rbac.User = rbac.require_fn("F-QUA-06")):
    it = f.choice(insp_type, "insp_type", "검사 유형", INSP_TYPES, required=False)
    jd = f.choice(judgement, "judgement", "판정", JUDGEMENTS, required=False)
    d1, d2 = f.period(frm, to)
    ctx: dict = {"rows": _inspection_rows(d1, d2, it, jd, f.opt_text(lot)), "frm": d1, "to": d2, "insp_type": it or "공정", "judgement": jd or "", "lot_filter": lot or "",
                 "lot": None, "fields": [], "pending": [], "scan_no": no or "", "type_options": [(x, t(x)) for x in INSP_TYPES],
                 "insp_process_id": None, "process_options": f.options(_processes(), "id", "process_code", "process_name"),
                 "judgement_options": [(x, t(x)) for x in JUDGEMENTS], "defect_options": f.options(conn.q("select id, defect_code, defect_name from bas_defect_code where use_yn = 'Y' order by defect_code"), "id", "defect_code", "defect_name")}
    if no is not None and no.strip() != "":
        n = lineage.resolve(no)
        if n is None:
            return f.scan_miss(request, "qua/inspections.html", ctx, screen_id="QUA-02", no=no, what="LOT")
        kind_type = it or ("입고" if n.kind_base == lineage.MATERIAL else "공정")
        proc = _insp_process(n, process_id)
        ctx.update({"lot": n, "insp_type": kind_type, "insp_process_id": proc, "fields": measure.plan_fields(plan_for_lot(kind_type, n, proc)),
                    "pending": conn.q("select * from qua_inspection where lot_id = %s and judgement is null order by id desc", (n.id,)),
                    "history": conn.q("select * from qua_inspection where lot_id = %s order by inspected_at desc, id desc limit 20", (n.id,))})
    return templating.render(request, "qua/inspections.html", ctx, screen_id="QUA-02")


@router.post(QUA02)                                                                    # F-QUA-04 검사 결과 등록 (판정 전 judgement NULL)
def inspection_create(request: Request, insp_type: str = Form(...), lot_no: str | None = Form(None), lot_id: str | None = Form(None),
                      note: str | None = Form(None), process_id: str | None = Form(None), user: rbac.User = rbac.require_fn("F-QUA-04")):
    it = f.choice(insp_type, "insp_type", "검사 유형", INSP_TYPES)
    n = lineage.resolve(lot_no) if f.opt_text(lot_no) else lineage.node(f.int_id(lot_id, "lot_id", "LOT", required=True))
    if n is None:
        raise http.validation_error(t("없는 LOT 번호입니다"), fields=[f.field_error("lot_no", "LOT", lot_no or lot_id or "")])
    if n.kind_base == lineage.SHIPMENT or n.state == lineage.SHIPPED:
        raise http.validation_error(t("출하된 LOT 은 검사할 수 없습니다"), fields=[f.field_error("lot_no", "LOT", n.no)])
    proc = _insp_process(n, process_id)
    fields = measure.plan_fields(plan_for_lot(it, n, proc))
    values, errs = measure.parse_form(fields, _form(request))
    if errs:
        raise http.validation_error(t("검사 항목 값을 확인해 주세요"), fields=errs)
    items = []
    for p in fields:
        v = values.get(p["param_key"])
        if v is None:
            continue
        dev = measure.deviated(p, v["value_num"])
        items.append({"plan_id": p["id"], "item_key": p["param_key"], "value_num": v["value_num"], "value_text": v["value_text"], "unit": p.get("unit"), "deviated": dev,
                      "item_judgement": "불합격" if dev else ("합격" if v["value_num"] is not None and (p["min_value"] is not None or p["max_value"] is not None) else None)})
    with conn.tx() as cur:
        row = {"lot_id": n.id, "insp_type": it, "inspector": user.login_id, "judgement": None, "note": f.opt_text(note), "items": items}
        packs.hook("validate_qua_inspection")(cur, row, user)
        cur.execute("insert into qua_inspection (lot_id, insp_type, inspected_at, inspector, note, created_by) values (%s, %s, now(), %s, %s, %s) returning *",
                    (n.id, it, user.login_id, row["note"], user.login_id))
        insp = dict(cur.fetchone())
        for x in items:
            cur.execute("""insert into qua_insp_item (inspection_id, plan_id, item_key, value_num, value_text, unit, item_judgement, deviated, created_by)
                           values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (insp["id"], x["plan_id"], x["item_key"], x["value_num"], x["value_text"], x["unit"], x["item_judgement"], x["deviated"], user.login_id))
        insp["items"] = items
        packs.hook("after_save_qua_inspection")(cur, insp, user)
    audit.log_change(request, user, "F-QUA-04", f"qua_inspection:{insp['id']}", {"lot_no": n.no, "insp_type": it, "process_id": proc, "items": len(items)})
    return http.saved(request, f"{n.no} {t('검사')} {t('등록')} — {t('판정')} {t('대기')}", back=f"{QUA02}?no={n.no}" + (f"&process_id={proc}" if proc else ""),
                      data={"id": insp["id"], "lot_id": n.id, "lot_no": n.no, "process_id": proc, "items": len(items), "deviated": [x["item_key"] for x in items if x["deviated"]]})


@router.post(QUA02 + "/{id}/judge")                                                    # F-QUA-05 검사 판정 (불합격이면 불량코드 · 수량 N줄)
def inspection_judge(request: Request, id: int, judgement: str = Form(...), note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-QUA-05")):
    insp = conn.q1("select * from qua_inspection where id = %s", (id,))
    if insp is None:
        raise http.not_found(t("없는 검사입니다"))
    if insp["judgement"] is not None:
        raise http.validation_error(t("이미 판정한 검사입니다 — 수정은 새 검사로"), fields=[f.field_error("id", "검사", f"{id} {insp['judgement']}")])
    j = f.choice(judgement, "judgement", "판정", JUDGEMENTS)
    form = _form(request)
    codes, qtys = f.list_form(form, "defect_code_id"), f.list_form(form, "defect_qty")
    defects = []
    for i, code in enumerate(codes):
        if not code.strip():
            continue
        did = f.int_id(code, "defect_code_id", "불량코드", required=True)
        if conn.q1("select 1 from bas_defect_code where id = %s", (did,)) is None:
            raise http.validation_error(t("없는 불량코드입니다"), fields=[f.field_error("defect_code_id", "불량코드", code)])
        defects.append({"defect_code_id": did, "qty": f.num(qtys[i] if i < len(qtys) else None, "defect_qty", "불량 수량", nonneg=True)})
    if j == "불합격" and not defects:
        raise http.validation_error(t("불합격이면 불량코드를 한 줄 이상 넣습니다"), fields=[f.field_error("defect_code_id", "불량코드", t("필수"))])
    with conn.tx() as cur:
        row = {**insp, "judgement": j, "judged_by": user.login_id, "note": f.opt_text(note) or insp["note"], "defects": defects}
        packs.hook("validate_qua_inspection")(cur, row, user)
        cur.execute("update qua_inspection set judgement = %s, judged_at = now(), judged_by = %s, note = %s, updated_at = now(), updated_by = %s where id = %s returning *",
                    (j, user.login_id, row["note"], user.login_id, id))
        saved = dict(cur.fetchone())
        for d in defects:
            cur.execute("insert into qua_defect (inspection_id, defect_code_id, qty, created_by) values (%s, %s, %s, %s)", (id, d["defect_code_id"], d["qty"], user.login_id))
        cur.execute("update lot set insp_status = %s, updated_at = now(), updated_by = %s where id = %s", (j, user.login_id, insp["lot_id"]))
        saved["defects"] = defects
        packs.hook("after_save_qua_inspection")(cur, saved, user)
        packs.hook("on_inspection_judged")(cur, saved, user)
    lot_no = conn.q1("select lot_no from lot where id = %s", (insp["lot_id"],))["lot_no"]
    audit.log_change(request, user, "F-QUA-05", f"qua_inspection:{id}", {"lot_no": lot_no, "judgement": j, "defects": len(defects)})
    return http.saved(request, f"{lot_no} {t('판정')} {j}", back=f"{QUA02}?no={lot_no}", data={"id": id, "lot_id": insp["lot_id"], "lot_no": lot_no, "judgement": j, "defects": len(defects)})


# ── QUA-03 불량 집계 ─────────────────────────────────────────────────────
@router.get(QUA03)                                                                     # F-QUA-07 불량 집계 조회 — stats.quality(by=defect)
def defect_stats(request: Request, frm: str | None = None, to: str | None = None, user: rbac.User = rbac.require_fn("F-QUA-07")):
    d1, d2 = f.period(frm, to)
    from .. import stats  # noqa: PLC0415 — 개발3 모듈. 없으면 ModuleNotFoundError(500) — 조용히 빈 표를 그리지 않는다
    rows = stats.quality(d1, d2, by="defect")       # {defect_code_id, code, name, defect_count, defect_qty, inspection_count}
    total = {"defect_count": sum(r["defect_count"] or 0 for r in rows), "defect_qty": sum(r["defect_qty"] or 0 for r in rows),
             "inspection_count": sum(r["inspection_count"] or 0 for r in rows)} if rows else None
    return templating.render(request, "qua/defect_stats.html", {"rows": rows, "frm": d1, "to": d2, "total": total}, screen_id="QUA-03")


# ── QUA-04 이상 · 시정 ───────────────────────────────────────────────────
@router.get(QUA04)                                                                     # F-QUA-11 이상 조회
def issues(request: Request, status: str | None = None, frm: str | None = None, to: str | None = None, process_id: str | None = None,
           user: rbac.User = rbac.require_fn("F-QUA-11")):
    st = f.choice(status, "status", "상태", ISSUE_STATUS, required=False)
    d1, d2 = f.period(frm, to, days=90)
    pid = f.int_id(process_id, "process_id", "공정")
    rows = conn.q("""select q.*, p.process_name, l.lot_no from qua_issue q left join bas_process p on p.id = q.process_id left join lot l on l.id = q.lot_id
                      where q.occurred_at::date between %s and %s and (%s::text is null or q.status = %s) and (%s::bigint is null or q.process_id = %s)
                      order by q.occurred_at desc, q.id desc limit 300""", (d1, d2, st, st, pid, pid))
    return templating.render(request, "qua/issues.html", {"rows": rows, "status": st or "", "frm": d1, "to": d2, "process_id": pid,
                                                          "status_options": [(x, t(x)) for x in ISSUE_STATUS],
                                                          "process_options": f.options(_processes(), "id", "process_code", "process_name")}, screen_id="QUA-04")


@router.post(QUA04)                                                                    # F-QUA-08 이상 등록
def issue_create(request: Request, content: str = Form(...), occurred_at: str | None = Form(None), process_id: str | None = Form(None),
                 lot_no: str | None = Form(None), cause: str | None = Form(None), user: rbac.User = rbac.require_fn("F-QUA-08")):
    body = f.req_text(content, "content", "내용")
    pid = f.int_id(process_id, "process_id", "공정")
    if pid is not None and conn.q1("select 1 from bas_process where id = %s", (pid,)) is None:
        raise http.validation_error(t("없는 공정입니다"), fields=[f.field_error("process_id", "공정", str(pid))])
    lot = None
    if f.opt_text(lot_no):
        lot = lineage.resolve(lot_no)
        if lot is None:
            raise http.validation_error(t("없는 LOT 번호입니다"), fields=[f.field_error("lot_no", "LOT", lot_no)])
    at = f.a_datetime(occurred_at, "occurred_at", "발생 시각", default=datetime.now())
    with conn.tx() as cur:
        no = _numbering().next("ISSUE", cur=cur)
        row = {"issue_no": no, "occurred_at": at, "process_id": pid, "lot_id": lot.id if lot else None, "content": body, "cause": f.opt_text(cause), "status": "발생", "source": "manual"}
        packs.hook("validate_qua_issue")(cur, row, user)
        cur.execute("""insert into qua_issue (issue_no, occurred_at, process_id, lot_id, content, cause, status, source, created_by)
                       values (%s, %s, %s, %s, %s, %s, '발생', 'manual', %s) returning *""", (no, at, pid, row["lot_id"], body, row["cause"], user.login_id))
        saved = dict(cur.fetchone())
        packs.hook("after_save_qua_issue")(cur, saved, user)
    audit.log_change(request, user, "F-QUA-08", f"qua_issue:{no}")
    return http.saved(request, f"{t('이상')} {no}", data={"id": saved["id"], "issue_no": no, "status": "발생"})


@router.post(QUA04 + "/{id}/action")                                                   # F-QUA-09 시정 조치 등록
def issue_action(request: Request, id: int, action: str = Form(...), action_by: str | None = Form(None), action_at: str | None = Form(None),
                 user: rbac.User = rbac.require_fn("F-QUA-09")):
    q = conn.q1("select * from qua_issue where id = %s", (id,))
    if q is None:
        raise http.not_found(t("없는 이상입니다"))
    if q["status"] == "종결":
        raise http.validation_error(t("종결된 이상에는 조치를 더할 수 없습니다"), fields=[f.field_error("id", "이상", q["issue_no"])])
    act = f.req_text(action, "action", "조치 내용")
    at = f.a_datetime(action_at, "action_at", "조치 일시", default=datetime.now())
    with conn.tx() as cur:
        row = {**q, "action": act, "action_by": f.opt_text(action_by) or user.login_id, "action_at": at, "status": "조치"}
        packs.hook("validate_qua_issue")(cur, row, user)
        cur.execute("update qua_issue set action = %s, action_by = %s, action_at = %s, status = '조치', updated_at = now(), updated_by = %s where id = %s returning *",
                    (act, row["action_by"], at, user.login_id, id))
        saved = dict(cur.fetchone())
        packs.hook("after_save_qua_issue")(cur, saved, user)
    audit.log_change(request, user, "F-QUA-09", f"qua_issue:{q['issue_no']}")
    return http.saved(request, t("조치를 기록했습니다"), data={"id": id, "status": "조치"})


@router.post(QUA04 + "/{id}/close")                                                    # F-QUA-10 이상 종결 (조치가 없으면 422)
def issue_close(request: Request, id: int, user: rbac.User = rbac.require_fn("F-QUA-10")):
    q = conn.q1("select * from qua_issue where id = %s", (id,))
    if q is None:
        raise http.not_found(t("없는 이상입니다"))
    if not q["action"]:
        raise http.validation_error(t("조치가 없는 이상은 종결할 수 없습니다"), fields=[f.field_error("action", "조치 내용", t("필수"))])
    if q["status"] == "종결":
        raise http.validation_error(t("이미 종결한 이상입니다"), fields=[f.field_error("id", "이상", q["issue_no"])])
    with conn.tx() as cur:
        row = {**q, "status": "종결"}
        packs.hook("validate_qua_issue")(cur, row, user)
        cur.execute("update qua_issue set status = '종결', updated_at = now(), updated_by = %s where id = %s returning *", (user.login_id, id))
        saved = dict(cur.fetchone())
        packs.hook("after_save_qua_issue")(cur, saved, user)
    audit.log_change(request, user, "F-QUA-10", f"qua_issue:{q['issue_no']}")
    return http.saved(request, t("이상을 종결했습니다"), data={"id": id, "status": "종결"})
