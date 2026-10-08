"""S7 유통기한 경과 원료 투입 거부 — validate_pop_input (gates.yaml S7) + 유통기한 < 입고일 거부 (validate_mat_receipt R2)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from mescore.db import conn

from _helpers import PORK, client, free_plan_date, hook_rejected, new_work_order, ok, pass_incoming, receive, scan_input, start_batch


@pytest.mark.fn("F-POP-06")
def test_expired_lot():
    admin, worker = client("admin"), client("worker", "pop")
    today = date.today()
    # 유통기한 D-1 · 입고일 D-3 (유통기한 ≥ 입고일이어야 입고가 된다)
    old = ok(receive(admin, PORK, 5.0, today - timedelta(days=1), receipt_date=today - timedelta(days=3)), "입고")
    pass_incoming(worker, old["lot_no"])
    assert conn.q1("select expiry_date from x_foodservice_lot_ext where id = %s", (old["lot_id"],))["expiry_date"] == today - timedelta(days=1)
    wo = ok(new_work_order(admin, qty=10, plan_date=free_plan_date()), "조리 지시")
    s = start_batch(worker, wo["id"], backdate_min=0)
    r = scan_input(worker, s["id"], old["lot_no"], 1.0)
    assert hook_rejected(r) and "유통기한이 지난" in r.json()["message"], r.text
    assert conn.q1("select count(*) as n from pop_input where work_result_id = %s", (s["id"],))["n"] == 0
    # 유통기한 < 입고일 → 입고 자체가 422
    r = receive(admin, PORK, 5.0, today - timedelta(days=1), receipt_date=today)
    assert hook_rejected(r) and "입고일보다" in r.json()["message"], r.text
    # 유통기한 안의 LOT 는 투입된다 (추천 LOT 과 달라도 경고만 — 거부하지 않는다)
    fresh = ok(receive(admin, PORK, 5.0, today + timedelta(days=30)), "입고 2")
    pass_incoming(worker, fresh["lot_no"])
    assert ok(scan_input(worker, s["id"], fresh["lot_no"], 1.0), "투입")["lot_no"] == fresh["lot_no"]
