"""wsh — X-WSH-01 소독수 농도 로그 (F-X-WSH-01~03 · 개발3). 쓰는 테이블: x_kimchi_sanitizer_log · x_kimchi_env_alarm(alarm.raise_env) 만.

센서 시계열 본체는 코어 `eqp_collect`(SW-01 `sanitizer_ppm` · `collect.series`) — 여기 복사하지 않는다. 수기 기록(센서 미연동 구간 · 접촉시간 · 투입비율)만 팩 로그.
10 ppm 미달 기준은 `bas_process_param(P03, sanitizer_ppm).min_value` — 비어 있으면 판정하지 않는다.
"""

from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Form, Request

from mescore.app import collect, nav, rbac, templating
from mescore.app.packs import t
from mescore.app.util import audit, http
from mescore.db import conn

from packs.kimchi import alarm, common
from packs.kimchi.adapters import collect_tags as tags
from packs.kimchi.common import f

router = APIRouter()
PATH = nav.path_of("X-WSH-01")
SCREEN = "X-WSH-01"
TABLE = "x_kimchi_sanitizer_log"
TAG = "sanitizer_ppm"


def _devices() -> list[dict]:
    return common.equipment_of_type(None, tags.SANITIZER)


def _threshold() -> dict | None:
    return common.param_by_code(None, common.SALTING_PROCESS, TAG)


@router.get(PATH)                                                                      # F-X-WSH-03 조회 — 수기 + 센서 한 목록
def sanitizer(request: Request, equipment_id: str | None = None, work_order_id: str | None = None, frm: str | None = None, to: str | None = None,
              deviated: str | None = None, user: rbac.User = rbac.require_fn("F-X-WSH-03")):
    eid, woid = f.int_id(equipment_id, "equipment_id", "설비"), f.int_id(work_order_id, "work_order_id", "작업지시")
    d1, d2 = f.period(frm, to, days=7)
    dev = f.choice(deviated, "deviated", "이탈", ("Y", "N"), required=False)
    devices = _devices()
    p = _threshold()
    lo = common.num(p["min_value"]) if p else None
    manual = conn.q(f"""select s.*, e.equip_code, e.equip_name, w.work_order_no, a.alarm_no, a.status as alarm_status from {TABLE} s
                          join bas_equipment e on e.id = s.equipment_id left join job_work_order w on w.id = s.work_order_id left join x_kimchi_env_alarm a on a.id = s.alarm_id
                         where s.measured_at::date between %s and %s and (%s::bigint is null or s.equipment_id = %s) and (%s::bigint is null or s.work_order_id = %s)
                           and (%s::text is null or s.deviated = %s) and s.canceled_yn = 'N' order by s.measured_at desc, s.id desc limit 300""",
                    (d1, d2, eid, eid, woid, woid, dev, dev))
    rows = [{"id": r["id"], "measured_at": r["measured_at"], "equip_code": r["equip_code"], "equip_name": r["equip_name"], "work_order_no": r["work_order_no"],
             "ppm_value": common.num(r["ppm_value"]), "contact_min": common.num(r["contact_min"]), "dosing_rate": common.num(r["dosing_rate"]),
             "source": r["source"], "deviated": r["deviated"] == "Y", "alarm_no": r["alarm_no"], "alarm_status": r["alarm_status"], "cancelable": r["source"] == "manual"} for r in manual]
    for d in devices:
        if eid is not None and d["id"] != eid:
            continue
        for s in collect.series(d["id"], TAG, datetime.combine(d1, time.min).astimezone(), datetime.combine(d2, time.max).astimezone()):
            is_dev = lo is not None and isinstance(s["value"], (int, float)) and s["value"] < lo
            if dev is not None and is_dev != (dev == "Y"):
                continue
            rows.append({"id": None, "measured_at": s["ts"], "equip_code": d["equip_code"], "equip_name": d["equip_name"], "work_order_no": None,
                         "ppm_value": s["value"], "contact_min": None, "dosing_rate": None, "source": "collect", "deviated": is_dev, "alarm_no": None,
                         "alarm_status": None, "cancelable": False})
    rows.sort(key=lambda r: r["measured_at"], reverse=True)
    ctx = {"rows": rows, "equipment_id": eid, "work_order_id": woid, "frm": d1, "to": d2, "deviated": dev or "", "threshold": lo, "threshold_text": common.limit_text(lo, None, "ppm") if lo is not None else t("미확정"),
           "equipment_options": f.options(devices, "id", "equip_code", "equip_name"),
           "work_order_options": f.options(conn.q("select id, work_order_no from job_work_order where status in ('대기', '진행') order by id desc limit 200"), "id", "work_order_no"),
           "alarm_path": nav.path_of("X-ALM-01"), "now": datetime.now().strftime("%Y-%m-%dT%H:%M")}
    return templating.render(request, "wsh/sanitizer.html", ctx, screen_id=SCREEN)


@router.post(PATH)                                                                     # F-X-WSH-01 수기 기록 (+ 10ppm 미달 알람)
def create(request: Request, equipment_id: str = Form(...), ppm_value: str = Form(...), work_order_id: str | None = Form(None), contact_min: str | None = Form(None),
           dosing_rate: str | None = Form(None), measured_at: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-WSH-01")):
    eid = f.int_id(equipment_id, "equipment_id", "설비", required=True)
    e = common.equipment(None, eid)
    if e is None or not tags.is_type(e["equip_code"], tags.SANITIZER, e.get("attrs") or {}):
        raise http.validation_error(t("소독수 공급장치가 아닙니다"), fields=[f.field_error("equipment_id", "설비", str(eid))])
    woid = f.int_id(work_order_id, "work_order_id", "작업지시")
    if woid is not None and conn.q1("select 1 from job_work_order where id = %s", (woid,)) is None:
        raise http.validation_error(t("없는 작업지시입니다"), fields=[f.field_error("work_order_id", "작업지시", str(woid))])
    ppm = f.num(ppm_value, "ppm_value", "농도", required=True, nonneg=True)
    at = f.a_datetime(measured_at, "measured_at", "측정 시각", default=datetime.now())
    p = _threshold()
    lo = p["min_value"] if p else None
    deviated = lo is not None and ppm < lo
    with conn.tx() as cur:
        alarm_id = None
        if deviated:
            alarm_id, _created = alarm.raise_env(cur, kind=tags.alarm_kind(TAG, p["label"]), equipment_id=eid, tag=TAG, value=ppm,
                                                limit_text=common.limit_text(lo, p["max_value"], p["unit"]), at=at, param_id=p["id"], by=user.login_id)
        cur.execute(f"""insert into {TABLE} (equipment_id, work_order_id, ppm_value, contact_min, dosing_rate, source, deviated, alarm_id, measured_at, created_by)
                        values (%s, %s, %s, %s, %s, 'manual', %s, %s, %s, %s) returning id""",
                    (eid, woid, ppm, f.num(contact_min, "contact_min", "접촉시간", nonneg=True), f.num(dosing_rate, "dosing_rate", "투입비율", nonneg=True),
                     "Y" if deviated else "N", alarm_id, at, user.login_id))
        new_id = cur.fetchone()["id"]
    audit.log_change(request, user, "F-X-WSH-01", f"{TABLE}:{new_id}", {"ppm": str(ppm), "deviated": deviated})
    msg = t("소독수 농도를 기록했습니다") + (f" — {t('이탈')} ({common.limit_text(lo, None, 'ppm')})" if deviated else "")
    return http.saved(request, msg, data={"id": new_id, "deviated": deviated, "alarm_id": alarm_id, "undecided": lo is None})


@router.post(PATH + "/{id}/cancel")                                                    # F-X-WSH-02 취소 (manual 만 · 행 삭제 안 함)
def cancel(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-WSH-02")):
    r = conn.q1(f"select * from {TABLE} where id = %s", (id,))
    if r is None:
        raise http.not_found(t("없는 기록입니다"))
    if r["source"] != "manual":
        raise http.validation_error(t("수집 기록은 취소할 수 없습니다"), fields=[f.field_error("id", "기록", r["source"])])
    if r["canceled_yn"] == "Y":
        raise http.validation_error(t("이미 취소한 기록입니다"), fields=[f.field_error("id", "기록", str(id))])
    with conn.tx() as cur:
        cur.execute(f"update {TABLE} set canceled_yn = 'Y', updated_at = now(), updated_by = %s where id = %s", (user.login_id, id))
    audit.log_change(request, user, "F-X-WSH-02", f"{TABLE}:{id}")
    return http.saved(request, t("기록을 취소했습니다"), data={"id": id, "canceled_yn": "Y"})
