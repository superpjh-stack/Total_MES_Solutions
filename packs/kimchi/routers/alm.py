"""alm — X-ALM-01 알람 이력 (F-X-ALM-01~03 · 개발3). 쓰는 테이블: x_kimchi_env_alarm 만 (alarm.ack · alarm.clear).

센서 이탈(온습도 · 염도 · 소독수)은 팩 테이블, 검사 · 측정값 이탈(손실률 · 금속 · CCP · 중량)은 코어 `qua_issue(source=hook)` — 한 목록에 **읽기 전용 행**으로 합친다(README §7 · D-501 1차).
현황판(?device=board)은 미해제 건수 + 최근 5건.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request

from mescore.app import nav, rbac, templating
from mescore.app.packs import t
from mescore.app.util import audit, http
from mescore.db import conn

from packs.kimchi import alarm, common
from packs.kimchi.common import f

router = APIRouter()
PATH = nav.path_of("X-ALM-01")
TABLE = "x_kimchi_env_alarm"
STATUSES = ("발생", "확인", "해제")


@router.get(PATH)                                                                      # F-X-ALM-03 조회 (+ qua_issue hook 행 읽기 전용)
def alarms(request: Request, kind: str | None = None, equipment_id: str | None = None, frm: str | None = None, to: str | None = None, status: str | None = None,
           user: rbac.User = rbac.require_fn("F-X-ALM-03")):
    eid = f.int_id(equipment_id, "equipment_id", "설비")
    d1, d2 = f.period(frm, to, days=7)
    st = f.choice(status, "status", "상태", STATUSES, required=False)
    k = f.opt_text(kind)
    env = conn.q(f"""select a.*, e.equip_code, e.equip_name, l.lot_no from {TABLE} a join bas_equipment e on e.id = a.equipment_id left join lot l on l.id = a.lot_id
                     where a.first_at::date between %s and %s and (%s::text is null or a.kind = %s) and (%s::bigint is null or a.equipment_id = %s) and (%s::text is null or a.status = %s)
                     order by (a.status <> '해제') desc, a.first_at desc, a.id desc limit 300""", (d1, d2, k, k, eid, eid, st, st))
    rows = [{"id": r["id"], "alarm_no": r["alarm_no"], "kind": r["kind"], "equip_code": r["equip_code"], "equip_name": r["equip_name"], "tag": r["tag"],
             "first_value": common.num(r["first_value"]), "last_value": common.num(r["last_value"]), "limit_text": r["limit_text"], "count": r["count"],
             "status": r["status"], "first_at": r["first_at"], "last_at": r["last_at"], "acked_by": r["acked_by"], "cleared_by": r["cleared_by"],
             "action_desc": r["action_desc"], "lot_no": r["lot_no"], "source": "env", "link": None} for r in env]
    if (st is None or st in ("발생", "확인")) and (k is None or k not in {x["kind"] for x in rows}):
        for q in conn.q("""select q.*, p.process_name, l.lot_no from qua_issue q left join bas_process p on p.id = q.process_id left join lot l on l.id = q.lot_id
                            where q.source = 'hook' and q.occurred_at::date between %s and %s and (%s::text is null or q.status <> '종결')
                            order by q.occurred_at desc, q.id desc limit 100""", (d1, d2, st)):
            rows.append({"id": None, "alarm_no": q["issue_no"], "kind": t("검사 · 측정값 이탈"), "equip_code": q["process_name"] or "-", "equip_name": "", "tag": "-",
                         "first_value": None, "last_value": None, "limit_text": q["content"], "count": 1, "status": q["status"], "first_at": q["occurred_at"],
                         "last_at": q["occurred_at"], "acked_by": None, "cleared_by": None, "action_desc": q["action"], "lot_no": q["lot_no"], "source": "qua_issue",
                         "link": f"{nav.path_of('QUA-04')}?status={q['status']}"})
    rows.sort(key=lambda r: (r["status"] in ("해제", "종결"), -r["first_at"].timestamp()))
    open_count = conn.q1(f"select count(*) as n from {TABLE} where status <> '해제'")["n"]
    ctx = {"rows": rows, "kind": k or "", "equipment_id": eid, "frm": d1, "to": d2, "status": st or "", "open_count": open_count, "recent": rows[:5],
           "kind_options": [(c["code"], c["code_name"]) for c in conn.q("select code, code_name from bas_code where group_code = 'ALARM_KIND' and use_yn = 'Y' order by seq")],
           "status_options": [(x, t(x)) for x in STATUSES],
           "equipment_options": f.options(conn.q(f"select distinct e.id, e.equip_code, e.equip_name from bas_equipment e join {TABLE} a on a.equipment_id = e.id order by e.equip_code"), "id", "equip_code", "equip_name")}
    return templating.render(request, "alm/alarms.html", ctx, screen_id="X-ALM-01")


@router.post(PATH + "/{id}/ack")                                                       # F-X-ALM-01 확인
def ack(request: Request, id: int, user: rbac.User = rbac.require_fn("F-X-ALM-01")):
    with conn.tx() as cur:
        row = alarm.ack(cur, id, user.login_id)
    audit.log_change(request, user, "F-X-ALM-01", f"{TABLE}:{row['alarm_no']}")
    return http.saved(request, f"{row['alarm_no']} {t('확인')}", back=PATH, data={"id": id, "status": row["status"]})


@router.post(PATH + "/{id}/clear")                                                     # F-X-ALM-02 해제 (조치 내용 필수)
def clear(request: Request, id: int, action_desc: str | None = Form(None), user: rbac.User = rbac.require_fn("F-X-ALM-02")):
    why = f.req_text(action_desc, "action_desc", "조치 내용")
    with conn.tx() as cur:
        row = alarm.clear(cur, id, user.login_id, why)
    audit.log_change(request, user, "F-X-ALM-02", f"{TABLE}:{row['alarm_no']}", {"action": why})
    return http.saved(request, f"{row['alarm_no']} {t('해제')}", back=PATH, data={"id": id, "status": row["status"]})
