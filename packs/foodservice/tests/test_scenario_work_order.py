"""S4 활성 레시피 없는 메뉴의 조리 지시 거부 — validate_job_work_order (gates.yaml S4) + S8-a 원재료 지시 거부 + 취소 되돌림(D-505)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mescore.db import conn

from _helpers import MENU_NO_RECIPE, P, PORK, client, free_plan_date, hook_rejected, item_id, new_work_order, ok, process_id


def _hook_rows() -> int:
    return conn.q1("select count(*) as n from mat_requirement where source = 'hook'")["n"]


@pytest.mark.fn("F-JOB-01")
def test_no_active_recipe():
    admin = client("admin")
    before = _hook_rows()
    r = new_work_order(admin, qty=500, menu=MENU_NO_RECIPE, process="PRC-030")
    assert hook_rejected(r) and "활성 레시피가 없는" in r.json()["message"], r.text
    assert _hook_rows() == before                                                         # 소요량 행 0 · 지시 0 (같은 트랜잭션 되돌림)
    assert conn.q1("select count(*) as n from job_work_order where item_id = %s", (item_id(MENU_NO_RECIPE),))["n"] == 0
    # S8-a 원재료(돈육)에 조리 지시 → 422
    r = admin.post(P["JOB-01"], data={"item_id": item_id(PORK), "process_id": process_id("PRC-060"), "plan_qty": "10"})
    assert hook_rejected(r) and "원재료" in r.json()["message"], r.text
    # 단위가 인분이 아니면 422
    r = admin.post(P["JOB-01"], data={"item_id": item_id("MENU-0001"), "process_id": process_id("PRC-060"), "plan_qty": "10", "unit": "kg"})
    assert hook_rejected(r) and "인분" in r.json()["message"], r.text


@pytest.mark.fn("F-JOB-04")
def test_cancel_reverts_hook_requirement():
    """on_work_order_canceled (D-505) — 취소한 지시의 소요량을 같은 키 행에서 뺀다. 0 이 되면 행을 지운다."""
    admin = client("admin")
    day = free_plan_date()
    wo = ok(new_work_order(admin, qty=100, plan_date=day), "조리 지시")
    req = conn.q1("select required_qty from mat_requirement where period_from = %s and item_id = %s and source = 'hook'", (day, item_id(PORK)))
    assert req["required_qty"] == Decimal("12.000")                                       # 100 × 12.000/100
    wo2 = ok(new_work_order(admin, qty=200, plan_date=day), "조리 지시 2")
    assert conn.q1("select required_qty from mat_requirement where period_from = %s and item_id = %s and source = 'hook'", (day, item_id(PORK)))["required_qty"] == Decimal("36.000")   # 누적
    ok(admin.post(f"{P['JOB-01']}/{wo['id']}/cancel"), "취소")
    assert conn.q1("select required_qty from mat_requirement where period_from = %s and item_id = %s and source = 'hook'", (day, item_id(PORK)))["required_qty"] == Decimal("24.000")
    ok(admin.post(f"{P['JOB-01']}/{wo2['id']}/cancel"), "취소 2")
    assert conn.q1("select 1 as hit from mat_requirement where period_from = %s and item_id = %s and source = 'hook'", (day, item_id(PORK))) is None
