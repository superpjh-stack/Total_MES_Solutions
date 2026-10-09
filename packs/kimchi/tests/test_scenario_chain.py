"""S1 — 입고 → 절임통 투입(염도) → 혼합(merge 혼합) → 금속검출 합격 → 포장 → 출하 → 역추적 (gates.yaml S1 · G-P04 · 개발3).

계보: 투입 M1→P1 (1) · 투입 P1→T1, P1→T2 (2) · 투입 M2, M3→X1 (2) · 혼합 T1, T2→X1 (2) · 투입 X1→K1 (1) · 출하 K1→S1 (1) = **9행** (gates.yaml).
혼합은 F-POP-03 종료의 합병 옵션 — `merge_lot_ids=T1,T2` · `merge_relation=혼합` → `lineage.make_product_lot(merge_parent_ids=)`(개발2 2bf68da) 가
별도 합병 LOT 없이 이 실적의 LOT(X1) 하나에 잇는다. P1 = 1000 (gates.yaml `P1 1000 … 500 + 350 투입 → 150 재고`) · in 1000 / out 850 은 손실률 측정값.
깊이 5(S1 ← K1 ← X1 ← T1 ← P1 ← M1) · 원재료 3 · TANK 2 · 절임통 배치 소진 · salinity_pct 측정값 2행 · P1 잔량 150 재고.
"""

from __future__ import annotations

import pytest

from _helpers import (ITEM_CABBAGE, ITEM_GARLIC, ITEM_PEPPER, approve, client, collect, end, equip_id, genealogy_rows, inspect, item_std, lot_by_no, lot_row,
                      new_shipment, receive_and_pass, run_result, scan_input, scan_ship, shipment_lot_no, start, ts, work_order)
from mescore.db import conn


def _tank_start(prod, p1_lot_no: str, tank_code: str, qty: float) -> dict:
    """P03 절임 실적 시작(절임통) → 투입 P1(부분 투입 — P1 은 잔량만큼 재고로 남는다)."""
    wo = work_order("P03", tank_code, qty=qty)
    s = start(prod, wo, tank_code)
    scan_input(prod, s["id"], p1_lot_no, qty)
    return s


def _tank_finish(prod, s: dict, tank_code: str, sensor_code: str, qty: float, salinity: float) -> dict:
    """X-TANK-01 등록(센서 연결) → 염도 수집 3점 → 완료 → 종료 → T(kind TANK)."""
    r = prod.post("/tank/operations", data={"work_result_id": s["id"], "input_weight_kg": qty, "sensor_equipment_id": equip_id(sensor_code)})
    assert r.status_code == 200, r.text
    reg = r.json()
    assert reg["target_salinity_pct"] == 9 and reg["target_hours"] == 48 and reg["plan_end_at"]
    for v in (salinity - 0.2, salinity + 0.1, salinity):
        assert collect(prod, sensor_code, {"salinity_pct": v}, at=ts()).status_code == 200
    done = prod.post(f"/tank/operations/{s['id']}/complete")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "완료" and done.json()["source"] == "collect" and done.json()["final_salinity_pct"] == salinity
    e = end(prod, s["id"], qty)
    lot = lot_by_no(e["lot_no"])
    assert lot["kind"] == "TANK" and lot["kind_base"] == "PRODUCT", lot
    m = conn.q1("select value_num, source from pop_measure where work_result_id = %s and param_key = 'salinity_pct'", (s["id"],))
    assert m and float(m["value_num"]) == salinity and m["source"] == "collect"
    ext = conn.q1("select tank_equipment_id from x_kimchi_lot_ext where id = %s", (lot["id"],))
    assert ext and ext["tank_equipment_id"] == equip_id(tank_code)
    return {**e, "result_id": s["id"], "lot_id": lot["id"]}


@pytest.mark.fn("F-X-TANK-01")
@pytest.mark.fn("F-X-TANK-03")
def test_s1_chain():
    prod, qa = client("prod"), client("qa")
    item_std(prod, "salinity_pct", std_value=9)
    item_std(prod, "salting_hours", std_value=48)
    # 1. 입고 3 (배추 1000 · 고춧가루 200 · 마늘 40) → 입고검사 합격
    m1, m2, m3 = receive_and_pass(ITEM_CABBAGE, 1000, prod=prod, qa=qa), receive_and_pass(ITEM_PEPPER, 200, prod=prod, qa=qa), receive_and_pass(ITEM_GARLIC, 40, prod=prod, qa=qa)
    # 2. P02 전처리 — in 1000 · out 850 → 손실률 15 (이탈 없음) → P1 (양품 1000 — gates.yaml p1_remain_qty 150 의 전제)
    r1 = run_result(prod, work_order("P02", qty=1000), [(m1["lot_no"], 1000)], 1000, input_weight_kg=1000, output_weight_kg=850)
    loss = conn.q1("select value_num, deviated from pop_measure where work_result_id = %s and param_key = 'loss_rate_pct'", (r1["result_id"],))
    assert loss and float(loss["value_num"]) == 15 and loss["deviated"] is False
    # 3·4. 절임통 2 (TK-01 500 · TK-02 350) — 염도 센서 SS-01 · SS-02
    s2, s3 = _tank_start(prod, r1["lot_no"], "TK-01", 500), _tank_start(prod, r1["lot_no"], "TK-02", 350)   # 한 LOT 을 두 통에
    t1 = _tank_finish(prod, s2, "TK-01", "SS-01", 500, 8.9)
    t2 = _tank_finish(prod, s3, "TK-02", "SS-02", 350, 9.1)
    p1 = lot_row(r1["lot_id"])
    assert p1["state"] == "재고" and float(p1["remain_qty"]) == 150        # gates.yaml p1_remain_qty 150 · 재고 (1000 − 500 − 350)
    # 5. P06 혼합 실적 R4 — 투입 M2 · M3 → 종료(합병 옵션 parents [T1, T2] relation 혼합) → X1 한 LOT
    s4 = start(prod, work_order("P06", "FL-01", qty=1090), "FL-01")
    scan_input(prod, s4["id"], m2["lot_no"], 200)
    scan_input(prod, s4["id"], m3["lot_no"], 40)
    e4 = prod.post(f"/pop/result/{s4['id']}/end", data={"good_qty": 1090, "merge_lot_ids": f"{t1['lot_no']},{t2['lot_no']}", "merge_relation": "혼합"})
    assert e4.status_code == 200, e4.text
    x1 = lot_by_no(e4.json()["lot_no"])
    assert x1["kind"] == "PRODUCT" and float(x1["qty"]) == 1090 and x1["process_id"] == conn.q1("select process_id from pop_work_result where id = %s", (s4["id"],))["process_id"]
    assert lot_row(t1["lot_id"])["state"] == "소진" and lot_row(t2["lot_id"])["state"] == "소진"
    # 6. 금속검출 검사 on X1 — OK · 합격 → qua_issue +0
    before = conn.q1("select count(*) as n from qua_issue where source = 'hook'")["n"]
    inspect(qa, x1["lot_no"], "공정", "합격", metal_detect="OK", inspect_qty=85, ng_qty=0)
    assert conn.q1("select count(*) as n from qua_issue where source = 'hook'")["n"] == before
    # 7. P08 포장 — 투입 X1 1000 → K1 · 최종 검사 합격 (중량 범위 미확정 → 이탈 판정 없음)
    r5 = run_result(prod, work_order("P08", "AP-01", qty=1000), [(x1["lot_no"], 1000)], 1000, equip_code="AP-01")
    inspect(qa, r5["lot_no"], "최종", "합격", pack_weight_kg=10.0)
    assert conn.q1("select deviated from qua_insp_item i join qua_inspection q on q.id = i.inspection_id where q.lot_id = %s and i.item_key = 'pack_weight_kg'", (r5["lot_id"],))["deviated"] is False
    # 8. 출하 — 등록 → 스캔 K1 → 승인 (validate_shipment 통과)
    s = new_shipment(prod)
    assert scan_ship(prod, s["shipment_no"], r5["lot_no"]).status_code == 200
    ap = approve(prod, s["id"])
    assert ap.status_code == 200, ap.text
    assert conn.q1("select status from shp_shipment where id = %s", (s["id"],))["status"] == "승인"
    s1_no = shipment_lot_no(s["id"])
    # 9. 계보 · 역추적
    ids = [m1["lot_id"], m2["lot_id"], m3["lot_id"], r1["lot_id"], t1["lot_id"], t2["lot_id"], x1["id"], r5["lot_id"], lot_by_no(s1_no)["id"]]
    rows = genealogy_rows(ids)
    got: dict[str, int] = {}
    for r in rows:
        got[r["relation"]] = got.get(r["relation"], 0) + 1
    assert len(rows) == 9 and got == {"투입": 6, "혼합": 2, "출하": 1}, got                 # gates.yaml genealogy_rows 9
    assert all(r["relation_base"] == "합병" for r in rows if r["relation"] == "혼합")
    bw = prod.get("/trc/backward", params={"no": s1_no}).json()
    assert sorted(n["no"] for n in bw["materials"]) == sorted([m1["lot_no"], m2["lot_no"], m3["lot_no"]])
    assert bw["depth"] == 5 and bw["edge_count"] == 9
    tank_nodes = [n for st in bw["stages"] for n in st["nodes"] if n["kind"] == "TANK"]
    assert len(tank_nodes) == 2 and all(n["kind_label"] == "절임통 배치" and n["state"] == "소진" for n in tank_nodes)
    assert conn.q1("select count(*) as n from pop_measure where param_key = 'salinity_pct' and work_result_id = any(%s)", ([t1["result_id"], t2["result_id"]],))["n"] == 2
    # 화면(HTML) — 절임통 운영 · 역추적에 업종어
    html = prod.get("/tank/operations", headers={"accept": "text/html"}).text
    assert "절임통" in html and "TK-01" in html
    assert client("admin").get("/trc/backward", params={"no": s1_no}, headers={"accept": "text/html"}).status_code == 200
