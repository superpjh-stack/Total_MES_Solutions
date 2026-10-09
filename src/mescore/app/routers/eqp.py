"""설비 `eqp` — 가동 현황 · 가동 상태 기록 · 점검 · 고장 · 수집값 조회 (F-EQP-01~08 · 개발2).

쓰기 경계(db-schema.md §2): eqp_run_log · eqp_check · eqp_fault. `eqp_collect` 는 collect 만 쓴다(여기서는 읽기 — collect.latest/series).
**설비 제어 엔드포인트는 없다** — 가동 상태 기록(F-EQP-02)은 사람이 적는 기록이다. 모든 쓰기 전 validate_<table> · 후 after_save_<table>(D-504).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Form, Request

from ...db import conn
from .. import collect, nav, packs, rbac, templating
from ..packs import t
from ..util import audit, http
from . import _dev2 as f

router = APIRouter()
EQP01, EQP02, EQP03, EQP04 = (nav.path_of(s) for s in ("EQP-01", "EQP-02", "EQP-03", "EQP-04"))
STATES = ("가동", "정지", "점검", "고장")


def _equipment(cur=None) -> list[dict]:
    sql = "select e.id, e.equip_code, e.equip_name, e.collect_yn, e.process_id, p.process_name from bas_equipment e left join bas_process p on p.id = e.process_id where e.use_yn = 'Y' order by e.equip_code"
    if cur is None:
        return conn.q(sql)
    cur.execute(sql)
    return [dict(r) for r in cur.fetchall()]


def _require_equipment(equipment_id, cur=None) -> dict:
    eid = f.int_id(equipment_id, "equipment_id", "설비", required=True)
    sql = "select * from bas_equipment where id = %s and use_yn = 'Y'"
    if cur is None:
        row = conn.q1(sql, (eid,))
    else:
        cur.execute(sql, (eid,))
        row = cur.fetchone()
    if row is None:
        raise http.validation_error(t("없는 설비입니다"), fields=[f.field_error("equipment_id", "설비", str(eid))])
    return dict(row)


def _open_segment(cur, equipment_id: int) -> dict | None:
    cur.execute("select * from eqp_run_log where equipment_id = %s and ended_at is null order by started_at desc, id desc limit 1 for update", (equipment_id,))
    r = cur.fetchone()
    return dict(r) if r else None


def _start_segment(cur, *, equipment_id: int, state: str, at: datetime, source: str, note: str | None, user) -> dict:
    """이전 구간 닫기 + 새 구간 1행. 같은 상태가 열려 있으면 그대로 둔다(중복 구간 없음)."""
    cur_seg = _open_segment(cur, equipment_id)
    if cur_seg is not None and cur_seg["state"] == state and source == cur_seg["source"]:
        return cur_seg
    if cur_seg is not None:
        if cur_seg["started_at"] > at:
            raise http.validation_error(t("시각이 열린 구간의 시작보다 이릅니다"), fields=[f.field_error("at", "시각", f"{at} < {cur_seg['started_at']}")])
        cur.execute("update eqp_run_log set ended_at = %s, updated_at = now(), updated_by = %s where id = %s", (at, user.login_id, cur_seg["id"]))
    row = {"equipment_id": equipment_id, "state": state, "started_at": at, "source": source, "note": note}
    packs.hook("validate_eqp_run_log")(cur, row, user)
    cur.execute("insert into eqp_run_log (equipment_id, state, started_at, source, note, created_by) values (%s, %s, %s, %s, %s, %s) returning *",
                (equipment_id, state, at, source, note, user.login_id))
    saved = dict(cur.fetchone())
    packs.hook("after_save_eqp_run_log")(cur, saved, user)
    return saved


# ── EQP-01 가동 현황 ─────────────────────────────────────────────────────
@router.get(EQP01)                                                                     # F-EQP-01 가동 현황 조회 — 수집 설비는 collect.latest · 없으면 미수집
def status(request: Request, equip_code: str | None = None, user: rbac.User = rbac.require_fn("F-EQP-01")):
    rows = _equipment()
    segs = {r["equipment_id"]: r for r in conn.q("""select distinct on (equipment_id) * from eqp_run_log where ended_at is null order by equipment_id, started_at desc, id desc""")}
    for e in rows:
        seg = segs.get(e["id"])
        e["state"] = seg["state"] if seg else None
        e["state_since"] = seg["started_at"] if seg else None
        e["state_source"] = seg["source"] if seg else None
        e["latest"] = collect.latest(e["id"]) if e["collect_yn"] == "Y" else None
        e["last_received_at"] = e["latest"]["ts"] if e["latest"] else None
    ctx = {"rows": rows, "states": STATES, "state_options": [(s, t(s)) for s in STATES], "equipment_options": f.options(rows, "id", "equip_code", "equip_name"),
           "now": datetime.now().strftime("%Y-%m-%d %H:%M"), "scan_no": equip_code or "", "selected_id": None}     # now — 화면 표시용 문자열(pop/_layout 은 now[11:16])
    if equip_code is not None and equip_code.strip() != "":                            # 스캔 진입 — 설비 바코드 → 그 설비 카드
        hit = next((e for e in rows if e["equip_code"] == equip_code.strip()), None)
        if hit is None:
            return f.scan_miss(request, "eqp/status.html", ctx, screen_id="EQP-01", no=equip_code, what="설비")
        ctx.update({"selected_id": hit["id"], "rows": [hit] + [e for e in rows if e["id"] != hit["id"]]})
    return templating.render(request, "eqp/status.html", ctx, screen_id="EQP-01")


@router.post(EQP01)                                                                    # F-EQP-02 가동 상태 기록 (제어가 아니다)
def status_record(request: Request, equipment_id: str = Form(...), state: str = Form(...), at: str | None = Form(None), note: str | None = Form(None),
                  user: rbac.User = rbac.require_fn("F-EQP-02")):
    st = f.choice(state, "state", "상태", STATES)
    when = f.a_datetime(at, "at", "시각", default=datetime.now())
    with conn.tx() as cur:
        e = _require_equipment(equipment_id, cur)
        saved = _start_segment(cur, equipment_id=e["id"], state=st, at=when, source="manual", note=f.opt_text(note), user=user)
    audit.log_change(request, user, "F-EQP-02", f"eqp_run_log:{saved['id']}", {"equip_code": e["equip_code"], "state": st})
    return http.saved(request, f"{e['equip_code']} {t(st)}", data={"id": saved["id"], "equipment_id": e["id"], "state": st, "started_at": saved["started_at"].isoformat()})


# ── EQP-02 점검 ─────────────────────────────────────────────────────────
CHECK_SORT = {"at": "c.checked_at", "equip": "e.equip_code", "item": "c.item", "result": "c.result"}
FAULT_SORT = {"at": "x.occurred_at", "equip": "e.equip_code", "fixed": "x.fixed_at", "hours": "hours"}


@router.get(EQP02)                                                                     # F-EQP-04 점검 조회
def checks(request: Request, equipment_id: str | None = None, frm: str | None = None, to: str | None = None, sort: str | None = None,
           user: rbac.User = rbac.require_fn("F-EQP-04")):
    eid = f.int_id(equipment_id, "equipment_id", "설비")
    d1, d2 = f.period(frm, to)
    rows = conn.q("""select c.*, e.equip_code, e.equip_name from eqp_check c join bas_equipment e on e.id = c.equipment_id
                      where c.checked_at::date between %s and %s and (%s::bigint is null or c.equipment_id = %s) order by """ + http.sort_clause(sort, CHECK_SORT, "c.checked_at desc") + ", c.id desc limit 300", (d1, d2, eid, eid))
    return templating.render(request, "eqp/checks.html", {"rows": rows, "equipment_id": eid, "sort": sort or "", "frm": d1, "to": d2, "today": date.today(),
                                                          "equipment_options": f.options(_equipment(), "id", "equip_code", "equip_name")}, screen_id="EQP-02")


@router.post(EQP02)                                                                    # F-EQP-03 점검 등록
def check_create(request: Request, equipment_id: str = Form(...), item: str = Form(...), result: str | None = Form(None), checked_at: str | None = Form(None),
                 checker: str | None = Form(None), note: str | None = Form(None), user: rbac.User = rbac.require_fn("F-EQP-03")):
    e = _require_equipment(equipment_id)
    what = f.req_text(item, "item", "점검 항목")
    when = f.a_datetime(checked_at, "checked_at", "점검 일시", default=datetime.now())
    with conn.tx() as cur:
        row = {"equipment_id": e["id"], "checked_at": when, "item": what, "result": f.opt_text(result), "checker": f.opt_text(checker) or user.user_name, "note": f.opt_text(note)}
        packs.hook("validate_eqp_check")(cur, row, user)
        cur.execute("insert into eqp_check (equipment_id, checked_at, item, result, checker, note, created_by) values (%s, %s, %s, %s, %s, %s, %s) returning *",
                    (e["id"], when, what, row["result"], row["checker"], row["note"], user.login_id))
        saved = dict(cur.fetchone())
        packs.hook("after_save_eqp_check")(cur, saved, user)
    audit.log_change(request, user, "F-EQP-03", f"eqp_check:{saved['id']}", {"equip_code": e["equip_code"]})
    return http.saved(request, t("점검을 등록했습니다"), data={"id": saved["id"], "equipment_id": e["id"]})


# ── EQP-03 고장 ─────────────────────────────────────────────────────────
@router.get(EQP03)                                                                     # F-EQP-07 고장 조회 (MTTR 은 stats.equipment)
def faults(request: Request, equipment_id: str | None = None, frm: str | None = None, to: str | None = None, fixed: str | None = None,
           sort: str | None = None, user: rbac.User = rbac.require_fn("F-EQP-07")):
    eid = f.int_id(equipment_id, "equipment_id", "설비")
    d1, d2 = f.period(frm, to, days=90)
    fx = f.choice(fixed, "fixed", "복구 여부", ("Y", "N"), required=False)
    rows = conn.q("""select x.*, e.equip_code, e.equip_name, extract(epoch from (x.fixed_at - x.occurred_at)) / 3600 as hours
                       from eqp_fault x join bas_equipment e on e.id = x.equipment_id
                      where x.occurred_at::date between %s and %s and (%s::bigint is null or x.equipment_id = %s)
                        and (%s::text is null or (x.fixed_at is not null) = (%s = 'Y'))
                      order by """ + http.sort_clause(sort, FAULT_SORT, "x.occurred_at desc") + ", x.id desc limit 300", (d1, d2, eid, eid, fx, fx))
    return templating.render(request, "eqp/faults.html", {"rows": rows, "equipment_id": eid, "sort": sort or "", "frm": d1, "to": d2, "fixed": fx or "",
                                                          "equipment_options": f.options(_equipment(), "id", "equip_code", "equip_name")}, screen_id="EQP-03")


@router.post(EQP03)                                                                    # F-EQP-05 고장 등록 — 고장 행 + 가동 로그 `고장` 구간 시작
def fault_create(request: Request, equipment_id: str = Form(...), symptom: str = Form(...), occurred_at: str | None = Form(None),
                 user: rbac.User = rbac.require_fn("F-EQP-05")):
    what = f.req_text(symptom, "symptom", "증상")
    when = f.a_datetime(occurred_at, "occurred_at", "발생 시각", default=datetime.now())
    with conn.tx() as cur:
        e = _require_equipment(equipment_id, cur)
        seg = _start_segment(cur, equipment_id=e["id"], state="고장", at=when, source="manual", note=what, user=user)
        row = {"equipment_id": e["id"], "occurred_at": when, "symptom": what, "run_log_id": seg["id"]}
        packs.hook("validate_eqp_fault")(cur, row, user)
        cur.execute("insert into eqp_fault (equipment_id, occurred_at, symptom, run_log_id, created_by) values (%s, %s, %s, %s, %s) returning *",
                    (e["id"], when, what, seg["id"], user.login_id))
        saved = dict(cur.fetchone())
        packs.hook("after_save_eqp_fault")(cur, saved, user)
    audit.log_change(request, user, "F-EQP-05", f"eqp_fault:{saved['id']}", {"equip_code": e["equip_code"]})
    return http.saved(request, f"{e['equip_code']} {t('고장')} {t('등록')}", data={"id": saved["id"], "equipment_id": e["id"], "run_log_id": seg["id"]})


@router.post(EQP03 + "/{id}/fix")                                                      # F-EQP-06 고장 조치 — 고장 구간 닫기
def fault_fix(request: Request, id: int, fix_action: str = Form(...), fixed_at: str | None = Form(None), next_state: str | None = Form(None),
              user: rbac.User = rbac.require_fn("F-EQP-06")):
    act = f.req_text(fix_action, "fix_action", "조치 내용")
    after = f.choice(next_state, "next_state", "복구 후 상태", STATES, required=False) or "정지"
    if after == "고장":
        raise http.validation_error(t("복구 후 상태는 고장일 수 없습니다"), fields=[f.field_error("next_state", "복구 후 상태", after)])
    with conn.tx() as cur:
        cur.execute("select * from eqp_fault where id = %s for update", (id,))
        x = cur.fetchone()
        if x is None:
            raise http.not_found(t("없는 고장입니다"))
        if x["fixed_at"] is not None:
            raise http.validation_error(t("이미 조치한 고장입니다"), fields=[f.field_error("id", "고장", str(id))])
        when = f.a_datetime(fixed_at, "fixed_at", "복구 시각", default=datetime.now())
        if when < x["occurred_at"]:
            raise http.validation_error(t("복구 시각이 발생 시각보다 이릅니다"), fields=[f.field_error("fixed_at", "복구 시각", f"{when} < {x['occurred_at']}")])
        row = {**dict(x), "fixed_at": when, "fix_action": act, "fixed_by": user.login_id}
        packs.hook("validate_eqp_fault")(cur, row, user)
        cur.execute("update eqp_fault set fixed_at = %s, fix_action = %s, fixed_by = %s, updated_at = now(), updated_by = %s where id = %s returning *",
                    (when, act, user.login_id, user.login_id, id))
        saved = dict(cur.fetchone())
        seg = _open_segment(cur, x["equipment_id"])
        if seg is not None and seg["state"] == "고장":
            _start_segment(cur, equipment_id=x["equipment_id"], state=after, at=when, source="manual", note=t("고장 복구"), user=user)
        packs.hook("after_save_eqp_fault")(cur, saved, user)
    audit.log_change(request, user, "F-EQP-06", f"eqp_fault:{id}")
    return http.saved(request, t("고장 조치를 기록했습니다"), data={"id": id, "fixed_at": saved["fixed_at"].isoformat(), "next_state": after})


# ── EQP-04 수집값 조회 ───────────────────────────────────────────────────
@router.get(EQP04)                                                                     # F-EQP-08 수집값 조회 — collect.series · 0건 미수집
def collect_view(request: Request, equipment_id: str | None = None, tag: str | None = None, frm: str | None = None, to: str | None = None,
                 user: rbac.User = rbac.require_fn("F-EQP-08")):
    eid = f.int_id(equipment_id, "equipment_id", "설비")
    d1, d2 = f.period(frm, to, days=1)
    tg = f.opt_text(tag)
    tags = conn.q("select distinct tag from eqp_collect where (%s::bigint is null or equipment_id = %s) order by tag", (eid, eid))
    rows = []
    summary = None
    if eid is not None and tg:
        rows = collect.series(eid, tg, datetime.combine(d1, datetime.min.time()), datetime.combine(d2 + timedelta(days=1), datetime.min.time()))
        nums = [r["value"] for r in rows if isinstance(r["value"], (int, float))]
        summary = {"n": len(rows), "min": min(nums) if nums else None, "max": max(nums) if nums else None, "avg": sum(nums) / len(nums) if nums else None,
                   "last": rows[-1]["value"] if rows else None}
    return templating.render(request, "eqp/collect.html",
                             {"rows": rows, "summary": summary, "equipment_id": eid, "tag": tg or "", "frm": d1, "to": d2,
                              "tag_options": [(r["tag"], r["tag"]) for r in tags],
                              "equipment_options": f.options([e for e in _equipment()], "id", "equip_code", "equip_name")}, screen_id="EQP-04")
