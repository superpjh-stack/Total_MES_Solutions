"""S2 검식 미합격 배치 출고 금지 — validate_shipment (gates.yaml S2 · scenarios.md S2)."""

from __future__ import annotations

import pytest

from mescore.db import conn

from _helpers import P, approve, client, end_batch, final_inspection, free_plan_date, hook_rejected, new_shipment, new_work_order, ok, scan_ship, start_batch


def _batch(admin, worker) -> dict:
    wo = ok(new_work_order(admin, qty=100, plan_date=free_plan_date()), "조리 지시")
    s = start_batch(worker, wo["id"], backdate_min=0)
    return {**end_batch(worker, s["id"], 100, 0), "wo": wo}


@pytest.mark.fn("F-SHP-07")
def test_block_uninspected():
    admin, worker, nutri, shipping = client("admin"), client("worker", "pop"), client("nutritionist"), client("shipping")
    # (a) 검식 없음 — 코어 F-SHP-05 가 미검사 LOT 스캔에서 먼저 422 (scenarios.md S2 "둘 중 하나")
    b = _batch(admin, worker)
    sh = new_shipment(shipping)
    r = scan_ship(shipping, sh["shipment_no"], b["lot_no"])
    assert r.status_code == 422 and r.json()["code"] == "validation_error", r.text
    # (b) 공정 검사만 합격(insp_status=합격) → 스캔은 통과 · 승인 직전 훅이 "최종 검식 없음" 으로 422 hook_rejected
    insp = ok(nutri.post(P["QUA-02"], data={"insp_type": "공정", "lot_no": b["lot_no"], "i_measure_temp": 80}), "공정 검사")
    ok(nutri.post(f"{P['QUA-02']}/{insp['id']}/judge", data={"judgement": "합격"}), "공정 판정")
    ok(scan_ship(shipping, sh["shipment_no"], b["lot_no"]), "스캔")
    r = approve(admin, sh["id"])
    assert hook_rejected(r) and "검식 합격 전" in r.json()["message"], r.text
    assert conn.q1("select status from shp_shipment where id = %s", (sh["id"],))["status"] == "등록"
    # (c) 최종 검식 불합격 → 같은 지시의 배치는 전부 거부 (R1' 샘플링 완화의 반대쪽)
    b2 = _batch(admin, worker)
    final_inspection(nutri, b2["lot_no"], "불합격", foreign="Y", sensory=74)
    r = scan_ship(shipping, sh["shipment_no"], b2["lot_no"])
    assert r.status_code == 422, r.text                                              # 코어 — 불합격 LOT 은 lineage.ship 이 422
    # (d) 최종 합격 → 승인 200
    b3 = _batch(admin, worker)
    final_inspection(nutri, b3["lot_no"], "합격")
    sh2 = new_shipment(shipping)
    ok(scan_ship(shipping, sh2["shipment_no"], b3["lot_no"]), "스캔")
    assert ok(approve(admin, sh2["id"]), "승인")["status"] == "승인"


@pytest.mark.fn("F-SHP-07")
def test_order_item_mismatch_rejected():
    """R3 — 수주에 없는 메뉴의 배치를 그 수주 출고에 담으면 거부."""
    from _helpers import MENU_NO_RECIPE, new_order
    admin, worker, nutri, shipping = client("admin"), client("worker", "pop"), client("nutritionist"), client("shipping")
    b = _batch(admin, worker)
    final_inspection(nutri, b["lot_no"], "합격")
    order = new_order(admin, 10, menu=MENU_NO_RECIPE)                               # 수주 상세 = 시금치무침뿐
    sh = new_shipment(shipping, order["order_no"])
    ok(scan_ship(shipping, sh["shipment_no"], b["lot_no"]), "스캔")
    r = approve(admin, sh["id"])
    assert hook_rejected(r) and "수주에 없는" in r.json()["message"], r.text
