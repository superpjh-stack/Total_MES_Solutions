"""pkg — X-PKG-01 테이핑기 실적 (F-X-PKG-01~02 · 개발3). 쓰는 테이블: x_kimchi_taping_log 만.

수집 원본은 코어 `eqp_collect`(AP-01 `pack_count` · `run_state`) → 훅 `on_collect` 가 같은 표에 `source=collect` 증분으로 쌓는다. 여기서는 수기 등록 + 조회(작업지시별 누계는 화면 집계).
가동 상태는 코어 `eqp_run_log` 를 읽는다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Form, Request

from mescore.app import nav, rbac, templating
from mescore.app.packs import t
from mescore.app.util import audit, http
from mescore.db import conn

from packs.kimchi import common
from packs.kimchi.adapters import collect_tags as tags
from packs.kimchi.common import f

router = APIRouter()
PATH = nav.path_of("X-PKG-01")
TABLE = "x_kimchi_taping_log"


def _machines() -> list[dict]:
    return common.equipment_of_type(None, tags.TAPING_MACHINE)


@router.get(PATH)                                                                      # F-X-PKG-02 조회
def taping(request: Request, equipment_id: str | None = None, work_order_id: str | None = None, frm: str | None = None, to: str | None = None,
           run_status: str | None = None, user: rbac.User = rbac.require_fn("F-X-PKG-02")):
    eid, woid = f.int_id(equipment_id, "equipment_id", "설비"), f.int_id(work_order_id, "work_order_id", "작업지시")
    d1, d2 = f.period(frm, to, days=7)
    rs = f.choice(run_status, "run_status", "가동상태", ("가동", "정지"), required=False)
    rows = conn.q(f"""select x.*, e.equip_code, e.equip_name, w.work_order_no from {TABLE} x join bas_equipment e on e.id = x.equipment_id
                      left join job_work_order w on w.id = x.work_order_id
                     where x.logged_at::date between %s and %s and (%s::bigint is null or x.equipment_id = %s) and (%s::bigint is null or x.work_order_id = %s)
                       and (%s::text is null or x.run_status = %s) order by x.logged_at desc, x.id desc limit 500""", (d1, d2, eid, eid, woid, woid, rs, rs))
    per_wo: dict[str, dict] = {}
    for r in rows:
        k = r["work_order_no"] or t("작업지시 없음")
        agg = per_wo.setdefault(k, {"work_order_no": k, "pack_qty": 0, "run_minutes": 0, "rows": 0})
        agg["pack_qty"] += float(r["pack_qty"] or 0)
        agg["run_minutes"] += float(r["run_minutes"] or 0)
        agg["rows"] += 1
    machines = _machines()
    states = {}
    for m in machines:
        last = conn.q1("select state, started_at from eqp_run_log where equipment_id = %s order by started_at desc, id desc limit 1", (m["id"],))
        states[m["id"]] = last["state"] if last else None
    ctx = {"rows": rows, "per_wo": sorted(per_wo.values(), key=lambda x: x["work_order_no"]), "equipment_id": eid, "work_order_id": woid, "frm": d1, "to": d2,
           "run_status": rs or "", "machines": [{**m, "state": states.get(m["id"]) or t("미수집")} for m in machines],
           "equipment_options": f.options(machines, "id", "equip_code", "equip_name"),
           "work_order_options": f.options(conn.q("select id, work_order_no from job_work_order where status in ('대기', '진행') order by id desc limit 200"), "id", "work_order_no"),
           "now": datetime.now().strftime("%Y-%m-%dT%H:%M"), "total_qty": sum(float(r["pack_qty"] or 0) for r in rows)}
    return templating.render(request, "pkg/taping.html", ctx, screen_id="X-PKG-01")


@router.post(PATH)                                                                     # F-X-PKG-01 수기 등록
def create(request: Request, equipment_id: str = Form(...), pack_qty: str = Form(...), work_order_id: str | None = Form(None), run_minutes: str | None = Form(None),
           run_status: str | None = Form(None), logged_at: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-PKG-01")):
    eid = f.int_id(equipment_id, "equipment_id", "설비", required=True)
    if eid not in {m["id"] for m in _machines()}:
        raise http.validation_error(t("자동포장기가 아닙니다"), fields=[f.field_error("equipment_id", "설비", str(eid))])
    woid = f.int_id(work_order_id, "work_order_id", "작업지시")
    if woid is not None and conn.q1("select 1 from job_work_order where id = %s", (woid,)) is None:
        raise http.validation_error(t("없는 작업지시입니다"), fields=[f.field_error("work_order_id", "작업지시", str(woid))])
    qty = f.num(pack_qty, "pack_qty", "포장 수량", required=True, nonneg=True)
    at = f.a_datetime(logged_at, "logged_at", "기록 시각", default=datetime.now())
    rs = f.choice(run_status, "run_status", "가동상태", ("가동", "정지"), required=False)
    if conn.q1(f"select 1 from {TABLE} where equipment_id = %s and logged_at = %s and source = 'manual'", (eid, at)):
        raise http.validation_error(t("같은 시각의 수기 기록이 이미 있습니다"), fields=[f.field_error("logged_at", "기록 시각", at.isoformat())])
    with conn.tx() as cur:
        cur.execute(f"""insert into {TABLE} (equipment_id, work_order_id, pack_qty, run_minutes, run_status, source, logged_at, created_by)
                        values (%s, %s, %s, %s, %s, 'manual', %s, %s) returning id""", (eid, woid, qty, f.num(run_minutes, "run_minutes", "가동 분", nonneg=True), rs, at, user.login_id))
        new_id = cur.fetchone()["id"]
    audit.log_change(request, user, "F-X-PKG-01", f"{TABLE}:{new_id}", {"pack_qty": str(qty)})
    return http.saved(request, t("테이핑 실적을 기록했습니다"), data={"id": new_id, "pack_qty": float(qty)})
