"""tank — X-TANK-01 절임통 운영 · X-TANK-02 염도 추이 (F-X-TANK-01~05 · 개발3). 쓰는 테이블: x_kimchi_tank 만.

절임통 배치 = 코어 실적(`pop_work_result` 공정 P03 · 설비 절임통) + 1:1 ext(`x_kimchi_tank`) — 실적 시작 · 종료는 코어 POP-02 가 하고 여기서는 ext 만 쓴다(D-501).
종료 훅 `on_result_closed` 가 LOT 을 `TANK` 로 바꾼다. 염도 시계열은 `eqp_collect`(센서 SS-nn) — 센서 ↔ 절임통 매핑은 배치 등록 때 고르거나 미확정(D-206).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Form, Request

from mescore.app import collect, nav, rbac, templating
from mescore.app.packs import t
from mescore.app.util import audit, http
from mescore.db import conn

from packs.kimchi import common
from packs.kimchi.adapters import collect_tags as tags
from packs.kimchi.common import f

router = APIRouter()
OPS, SAL = nav.path_of("X-TANK-01"), nav.path_of("X-TANK-02")
TABLE = "x_kimchi_tank"
SALINITY, HOURS = "salinity_pct", "salting_hours"


def _sensors() -> list[dict]:
    return common.equipment_of_type(None, tags.SALINITY_SENSOR, collect="Y")


def _latest_salinity(sensor_id: int | None) -> dict | None:
    if sensor_id is None:
        return None
    lv = collect.latest(sensor_id)
    return lv["tags"].get(tags.SALINITY_TAG) if lv else None


def _open_results() -> list[dict]:
    """절임통에서 진행 중(ended_at NULL)이고 아직 배치 등록이 안 된 P03 실적."""
    rows = conn.q("""select r.id, r.started_at, r.equipment_id, e.equip_code, w.work_order_no, i.item_code, i.item_name from pop_work_result r
                       join bas_process p on p.id = r.process_id and p.process_code = %s join bas_equipment e on e.id = r.equipment_id
                       join job_work_order w on w.id = r.work_order_id join bas_item i on i.id = w.item_id
                      where r.ended_at is null and not exists (select 1 from x_kimchi_tank k where k.id = r.id) order by r.started_at desc""", (common.SALTING_PROCESS,))
    return [r for r in rows if tags.is_type(r["equip_code"], tags.TANK, (common.equipment(None, r["equipment_id"]) or {}).get("attrs") or {})]


@router.get(OPS)                                                                       # F-X-TANK-04 조회 — 절임통 × 현재 배치 (현황판 ?device=board 는 JSON 폴링)
def operations(request: Request, user: rbac.User = rbac.require_fn("F-X-TANK-04")):
    now = f.now()
    tiles = []
    for r in conn.q("select * from x_kimchi_v_tank_board order by equip_code"):
        tile = dict(r)
        tile["elapsed_hours"] = round((now - r["started_at"]).total_seconds() / 3600, 1) if r["started_at"] else None
        tile["overdue"] = bool(r["plan_end_at"] and r["plan_end_at"] < now and r["tank_status"] != "완료")
        latest = _latest_salinity(r["sensor_equipment_id"]) if r["work_result_id"] else None
        tile["salinity"] = latest["value"] if latest else None
        tile["salinity_at"] = latest["ts"] if latest else None
        tile["salinity_note"] = "" if r["sensor_equipment_id"] or not r["work_result_id"] else common.UNDECIDED_SENSOR
        tiles.append(tile)
    recent = conn.q(f"""select k.*, e.equip_code, r.started_at, r.ended_at, l.lot_no, w.work_order_no, i.item_name from {TABLE} k join bas_equipment e on e.id = k.equipment_id
                         join pop_work_result r on r.id = k.id left join lot l on l.id = r.product_lot_id join job_work_order w on w.id = r.work_order_id
                         join bas_item i on i.id = w.item_id order by k.created_at desc limit 50""")
    stds = conn.q("""select s.id, s.item_id, s.size_type, s.std_value, s.tolerance, i.item_code from x_kimchi_item_std s join bas_item i on i.id = s.item_id
                     join bas_process p on p.id = s.process_id where p.process_code = %s and s.param_key = %s and s.use_yn = 'Y' order by i.item_code, s.size_type nulls first, s.valid_from desc""",
                  (common.SALTING_PROCESS, SALINITY))
    open_results = _open_results()
    ctx = {"tiles": tiles, "rows": recent, "open_results": open_results,
           "result_options": [(r["id"], f"{r['work_order_no']} {r['equip_code']} {r['item_name']}") for r in open_results],
           "std_options": [(s["id"], f"{s['item_code']} {s['size_type'] or t('전체')} {common.num(s['std_value']) if s['std_value'] is not None else t('미확정')} %") for s in stds],
           "sensor_options": f.options(_sensors(), "id", "equip_code", "equip_name"),
           "size_options": [(c["code"], c["code_name"]) for c in conn.q("select code, code_name from bas_code where group_code = 'SIZE_TYPE' and use_yn = 'Y' order by seq")],
           "open_count": sum(1 for x in tiles if x["work_result_id"]), "tank_count": len(tiles), "salinity_path": SAL, "pop_path": nav.path_of("POP-02")}
    return templating.render(request, "tank/operations.html", ctx, screen_id="X-TANK-01")


@router.post(OPS)                                                                      # F-X-TANK-01 투입 등록 (실적은 코어 POP-02 가 만든다)
def register(request: Request, work_result_id: str = Form(...), std_id: str | None = Form(None), size_type: str | None = Form(None),
             input_weight_kg: str | None = Form(None), sensor_equipment_id: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-TANK-01")):
    rid = f.int_id(work_result_id, "work_result_id", "실적", required=True)
    r = conn.q1("""select r.*, p.process_code, e.equip_code, e.attrs as equip_attrs, w.item_id from pop_work_result r join bas_process p on p.id = r.process_id
                   left join bas_equipment e on e.id = r.equipment_id join job_work_order w on w.id = r.work_order_id where r.id = %s""", (rid,))
    if r is None:
        raise http.validation_error(t("없는 실적입니다"), fields=[f.field_error("work_result_id", "실적", str(rid))])
    if r["process_code"] != common.SALTING_PROCESS or r["ended_at"] is not None:
        raise http.validation_error(t("진행 중인 절임 실적이 아닙니다"), fields=[f.field_error("work_result_id", "실적", f"{rid} {r['process_code']}")])
    if r["equipment_id"] is None or not tags.is_type(r["equip_code"], tags.TANK, r["equip_attrs"] or {}):
        raise http.validation_error(t("실적의 설비가 절임통이 아닙니다"), fields=[f.field_error("work_result_id", "설비", r["equip_code"] or "-")])
    if conn.q1(f"select 1 from {TABLE} where id = %s", (rid,)):
        raise http.validation_error(t("이미 등록한 배치입니다"), fields=[f.field_error("work_result_id", "실적", str(rid))])
    if conn.q1(f"select 1 from {TABLE} where equipment_id = %s and status <> '완료'", (r["equipment_id"],)):
        raise http.validation_error(t("같은 절임통에 미완료 배치가 있습니다"), fields=[f.field_error("work_result_id", "설비", r["equip_code"])])
    size = f.opt_text(size_type)
    sid = f.int_id(std_id, "std_id", "절임 조건")
    if sid is not None:
        std = conn.q1("select s.* from x_kimchi_item_std s join bas_process p on p.id = s.process_id where s.id = %s and p.process_code = %s and s.param_key = %s",
                      (sid, common.SALTING_PROCESS, SALINITY))
        if std is None or std["item_id"] != r["item_id"]:
            raise http.validation_error(t("이 품목의 절임 염도 기준이 아닙니다"), fields=[f.field_error("std_id", "절임 조건", str(sid))])
        size = size or std["size_type"]
    else:
        std = common.std_for(None, r["item_id"], SALINITY, size_type=size)
    hours_std = common.std_for(None, r["item_id"], HOURS, size_type=size)
    hours = hours_std["std_value"] if hours_std else None
    sensor = f.int_id(sensor_equipment_id, "sensor_equipment_id", "염도센서")
    if sensor is not None and sensor not in {s["id"] for s in _sensors()}:
        raise http.validation_error(t("염도센서가 아닙니다"), fields=[f.field_error("sensor_equipment_id", "염도센서", str(sensor))])
    plan_end = (r["started_at"] + timedelta(hours=float(hours))) if hours is not None else None
    with conn.tx() as cur:
        cur.execute(f"""insert into {TABLE} (id, equipment_id, std_id, target_salinity_pct, target_hours, input_weight_kg, plan_end_at, status, sensor_equipment_id, created_by)
                        values (%s, %s, %s, %s, %s, %s, %s, '진행', %s, %s)""",
                    (rid, r["equipment_id"], std["id"] if std else None, std["std_value"] if std else None, hours,
                     f.num(input_weight_kg, "input_weight_kg", "투입 중량", positive=True), plan_end, sensor, user.login_id))
    audit.log_change(request, user, "F-X-TANK-01", f"{TABLE}:{rid}", {"equip": r["equip_code"], "std_id": std["id"] if std else None})
    undecided = [k for k, v in (("salinity_pct", std and std["std_value"]), ("salting_hours", hours)) if v is None]
    return http.saved(request, f"{r['equip_code']} {t('절임통 투입 등록')}" + (f" — {t('미확정')} {undecided}" if undecided else ""),
                      data={"id": rid, "equipment_id": r["equipment_id"], "std_id": std["id"] if std else None, "target_salinity_pct": common.num(std["std_value"]) if std else None,
                            "target_hours": common.num(hours), "plan_end_at": plan_end.isoformat() if plan_end else None, "sensor_equipment_id": sensor, "undecided": undecided})


@router.post(OPS + "/{id}/cancel")                                                     # F-X-TANK-02 취소 — 실적 종료 전만 · ext 행 삭제
def cancel(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-TANK-02")):
    k = common.tank_row(None, id)
    if k is None:
        raise http.not_found(t("없는 절임통 배치입니다"))
    if k["ended_at"] is not None:
        raise http.validation_error(t("종료된 실적의 배치는 취소할 수 없습니다"), fields=[f.field_error("id", "실적", str(id))])
    with conn.tx() as cur:
        cur.execute(f"delete from {TABLE} where id = %s", (id,))
    audit.log_change(request, user, "F-X-TANK-02", f"{TABLE}:{id}")
    return http.saved(request, t("절임통 투입을 취소했습니다"), data={"id": id})


@router.post(OPS + "/{id}/complete")                                                   # F-X-TANK-03 절임 완료 처리 (실적 종료는 POP-02 · 순서 자유)
def complete(request: Request, id: int, final_salinity_pct: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-TANK-03")):
    k = common.tank_row(None, id)
    if k is None:
        raise http.not_found(t("없는 절임통 배치입니다"))
    if k["status"] == "완료":
        raise http.validation_error(t("이미 완료한 배치입니다"), fields=[f.field_error("id", "배치", str(id))])
    final = f.num(final_salinity_pct, "final_salinity_pct", "완료 염도", nonneg=True)
    source = "manual"
    if final is None and k["sensor_equipment_id"] is not None:
        v = collect.aggregate(k["sensor_equipment_id"], tags.SALINITY_TAG, k["started_at"], f.now(), "last")
        final, source = (common.dec(v), "collect") if v is not None else (None, "none")
    with conn.tx() as cur:
        cur.execute(f"update {TABLE} set status = '완료', completed_at = now(), final_salinity_pct = %s, updated_at = now(), updated_by = %s where id = %s", (final, user.login_id, id))
    audit.log_change(request, user, "F-X-TANK-03", f"{TABLE}:{id}", {"final_salinity_pct": str(final), "source": source})
    return http.saved(request, t("절임 완료 처리했습니다") + (f" — {t('염도')} {float(final):g} %" if final is not None else f" — {t('염도')} {t('미수집')}"),
                      data={"id": id, "status": "완료", "final_salinity_pct": common.num(final), "source": source})


@router.get(SAL)                                                                       # F-X-TANK-05 염도 추이 (쓰기 0)
def salinity(request: Request, equipment_id: str | None = None, frm: str | None = None, to: str | None = None, user: rbac.User = rbac.require_fn("F-X-TANK-05")):
    eid = f.int_id(equipment_id, "equipment_id", "설비")
    d1, d2 = f.period(frm, to, days=3)
    sensors = _sensors()
    tanks = common.equipment_of_type(None, tags.TANK)
    rows, target, tolerance, sensor, note = [], None, None, None, ""
    if eid is not None:
        if eid in {s["id"] for s in sensors}:
            sensor = eid
            k = common.one(None, f"select * from {TABLE} where sensor_equipment_id = %s and status <> '완료' order by created_at desc limit 1", (eid,))
        else:
            k = common.one(None, f"select * from {TABLE} where equipment_id = %s order by (status <> '완료') desc, created_at desc limit 1", (eid,))
            sensor = k["sensor_equipment_id"] if k else None
            if sensor is None:
                e = common.equipment(None, eid)
                mapped = next((s for s in sensors if tags.tank_code_for(s["equip_code"]) == (e or {}).get("equip_code")), None)
                sensor = mapped["id"] if mapped else None
                note = "" if sensor else common.UNDECIDED_SENSOR
        if k:
            target, tolerance = common.num(k["target_salinity_pct"]), common.num(common.tank_tolerance(None, k))
        if sensor is not None:
            rows = collect.series(sensor, tags.SALINITY_TAG, datetime.combine(d1, time.min).astimezone(), datetime.combine(d2, time.max).astimezone())
    vals = [r["value"] for r in rows if isinstance(r["value"], (int, float))]
    ctx = {"rows": rows, "equipment_id": eid, "frm": d1, "to": d2, "target": target, "tolerance": tolerance, "sensor_equipment_id": sensor, "note": note,
           "summary": {"n": len(vals), "min": min(vals) if vals else None, "max": max(vals) if vals else None, "last": vals[-1] if vals else None},
           "equipment_options": f.options(tanks, "id", "equip_code", "equip_name") + f.options(sensors, "id", "equip_code", "equip_name")}
    return templating.render(request, "tank/salinity.html", ctx, screen_id="X-TANK-02")
