"""S3 검식 불합격 → 품질 이슈 자동 생성 — on_inspection_judged (gates.yaml S3)."""

from __future__ import annotations

import pytest

from mescore.db import conn

from _helpers import COOK_PROCESS, P, client, end_batch, final_inspection, free_plan_date, new_shipment, new_work_order, ok, scan_ship, start_batch


@pytest.mark.fn("F-QUA-05")
def test_issue_auto():
    admin, worker, nutri, shipping = client("admin"), client("worker", "pop"), client("nutritionist"), client("shipping")
    wo = ok(new_work_order(admin, qty=100, plan_date=free_plan_date()), "조리 지시")
    s = start_batch(worker, wo["id"], backdate_min=0)
    b = end_batch(worker, s["id"], 100, 0)
    before = conn.q1("select count(*) as n from qua_issue where source = 'hook'")["n"]
    insp = final_inspection(nutri, b["lot_no"], "불합격", foreign="Y", sensory=74)
    issues = conn.q("""select q.*, p.process_code from qua_issue q left join bas_process p on p.id = q.process_id where q.inspection_id = %s""", (insp["id"],))
    assert len(issues) == 1 and conn.q1("select count(*) as n from qua_issue where source = 'hook'")["n"] == before + 1
    q = issues[0]
    assert q["source"] == "hook" and q["status"] == "발생" and q["process_code"] == COOK_PROCESS and q["attrs"]["issue_type"] == "이물" and q["lot_id"] == b["lot_id"]
    assert "검식 불합격" in q["content"] and q["issue_no"]
    assert conn.q1("select insp_status from lot where id = %s", (b["lot_id"],))["insp_status"] == "불합격"
    # QUA-04 화면에 보인다
    screen = ok(admin.get(P["QUA-04"], params={"status": "발생"}), "품질 이슈")
    assert any(r["id"] == q["id"] for r in screen["rows"])
    # 이후 출고 스캔 422 (코어 — 불합격 LOT)
    sh = new_shipment(shipping)
    assert scan_ship(shipping, sh["shipment_no"], b["lot_no"]).status_code == 422
    # 이물 없이 불합격 → 품질이상 · 입고검사 불합격은 이슈를 만들지 않는다 (hooks.md §5 조건)
    wo2 = ok(new_work_order(admin, qty=50, plan_date=free_plan_date()), "조리 지시 2")
    s2 = start_batch(worker, wo2["id"], backdate_min=0)
    b2 = end_batch(worker, s2["id"], 50, 0)
    insp2 = final_inspection(nutri, b2["lot_no"], "불합격", foreign="N", sensory=60)
    assert conn.q1("select attrs from qua_issue where inspection_id = %s", (insp2["id"],))["attrs"]["issue_type"] == "품질이상"
