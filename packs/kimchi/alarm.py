"""환경 알람 — `x_kimchi_env_alarm` 에 쓰는 유일한 자리 (hooks.md §0 · README §7 · D-512) (개발3 · 2026-10-09).

    raise_env(cur, *, kind, equipment_id, tag, value, limit_text, at, lot_id=None, work_result_id=None, param_id=None, by="hook") -> (alarm_id, created)

같은 (설비 · 태그) 에 `status <> 해제` 행이 있으면 새 행 대신 `last_value · last_at · count+1` 갱신(폭주 방지 · D-512). 없으면 `numbering.next("ALARM")` 로 1행.
검사 · 측정값 이탈(손실률 · 금속 · CCP · 중량)은 여기 오지 않는다 — 코어 `qua_issue(source=hook)`.
"""

from __future__ import annotations

from mescore.app import numbering
from mescore.app.packs import t

from packs.kimchi import common


def raise_env(cur, *, kind: str, equipment_id: int, tag: str, value, limit_text: str, at, lot_id: int | None = None,
              work_result_id: int | None = None, param_id: int | None = None, by: str = "hook") -> tuple[int, bool]:
    cur.execute("""select id, count from x_kimchi_env_alarm where equipment_id = %s and tag = %s and status <> '해제'
                   order by first_at desc, id desc limit 1 for update""", (int(equipment_id), tag))
    open_row = cur.fetchone()
    if open_row is not None:
        cur.execute("""update x_kimchi_env_alarm set last_value = %s, last_at = %s, count = count + 1, lot_id = coalesce(lot_id, %s),
                              work_result_id = coalesce(work_result_id, %s), updated_at = now(), updated_by = %s where id = %s""",
                    (value, at, lot_id, work_result_id, by, open_row["id"]))
        return int(open_row["id"]), False
    no = numbering.next("ALARM", cur=cur)
    cur.execute("""insert into x_kimchi_env_alarm (alarm_no, kind, equipment_id, tag, first_value, last_value, limit_text, count, lot_id, work_result_id, param_id,
                                                  status, first_at, last_at, created_by)
                   values (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, '발생', %s, %s, %s) returning id""",
                (no, kind, int(equipment_id), tag, value, value, limit_text, lot_id, work_result_id, param_id, at, at, by))
    return int(cur.fetchone()["id"]), True


def ack(cur, alarm_id: int, by: str) -> dict:
    r = common.one(cur, "select * from x_kimchi_env_alarm where id = %s for update", (int(alarm_id),))
    if r is None:
        from mescore.app.util import http
        raise http.not_found(t("없는 알람입니다"))
    if r["status"] == "해제":
        from mescore.app.util import http
        raise http.validation_error(t("이미 해제한 알람입니다"), fields=[{"name": "id", "label": t("알람"), "reason": r["alarm_no"]}])
    cur.execute("update x_kimchi_env_alarm set status = '확인', acked_at = now(), acked_by = %s, updated_at = now(), updated_by = %s where id = %s returning *",
                (by, by, r["id"]))
    return dict(cur.fetchone())


def clear(cur, alarm_id: int, by: str, action_desc: str) -> dict:
    from mescore.app.util import http

    r = common.one(cur, "select * from x_kimchi_env_alarm where id = %s for update", (int(alarm_id),))
    if r is None:
        raise http.not_found(t("없는 알람입니다"))
    if r["status"] == "해제":
        raise http.validation_error(t("이미 해제한 알람입니다"), fields=[{"name": "id", "label": t("알람"), "reason": r["alarm_no"]}])
    cur.execute("""update x_kimchi_env_alarm set status = '해제', cleared_at = now(), cleared_by = %s, action_desc = %s,
                          acked_at = coalesce(acked_at, now()), acked_by = coalesce(acked_by, %s), updated_at = now(), updated_by = %s where id = %s returning *""",
                (by, action_desc, by, by, r["id"]))
    return dict(cur.fetchone())
