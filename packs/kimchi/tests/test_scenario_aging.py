"""S4 — 숙성 투입(split 숙성 · AGING) → 예정일 전 출하 거부 → 완료 후 출하 → 역추적 (gates.yaml S4 · 개발3).

K1(1000) → X-AGE-01 숙성 600 → `lineage.split(count=1, qtys=[600], relation=숙성, kind=AGING)` — 남는 400 은 K1 자신의 잔량(부분 분할 · D-43 회전 8).
계보 +1(숙성 1) · 출하 +1.
회전 8 기대값(D-515 「잔량 유지」 · gates.yaml S4): aging_qty 600 · k1_leftover_qty 400 · k1_leftover_state 재고 · k1_state 재고 · k1_leftover_lot K1 ·
genealogy_delta 1 · backward_materials 2 (이 테스트의 K1 은 양념 M2 · M3 로만 만든다).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from _helpers import (ITEM_GARLIC, ITEM_PEPPER, approve, client, equip_id, genealogy_rows, inspect, lot_by_no, lot_row, new_shipment, receive_and_pass, run_result,
                      scan_ship, shipment_lot_no, work_order)
from mescore.db import conn


def _packed_lot(prod, qa, qty: float = 1000) -> dict:
    m2, m3 = receive_and_pass(ITEM_PEPPER, 200, prod=prod, qa=qa), receive_and_pass(ITEM_GARLIC, 40, prod=prod, qa=qa)
    x = run_result(prod, work_order("P06", "FL-01", qty=qty), [(m2["lot_no"], 200), (m3["lot_no"], 40)], qty, equip_code="FL-01")
    inspect(qa, x["lot_no"], "공정", "합격", metal_detect="OK", inspect_qty=100, ng_qty=0)
    k = run_result(prod, work_order("P08", "AP-01", qty=qty), [(x["lot_no"], qty)], qty, equip_code="AP-01")
    inspect(qa, k["lot_no"], "최종", "합격", pack_weight_kg=10)
    return {**k, "materials": [m2["lot_no"], m3["lot_no"]]}


@pytest.mark.fn("F-X-AGE-01")
@pytest.mark.fn("F-X-AGE-02")
@pytest.mark.fn("F-X-AGE-03")
def test_s4_aging():
    prod, qa, field = client("prod"), client("qa"), client("field", device="mobile")
    k1 = _packed_lot(prod, qa, 1000)
    g_before = conn.q1("select count(*) as n from lot_genealogy")["n"]
    # 숙성 투입 600 → A1 AGING · 예정 +21 (품목 기준 없음 · D-511) · 잔량 400 은 K1 자신에 재고로 (D-515 · D-43)
    r = field.post("/age/stock", data={"barcode": k1["lot_no"], "qty": 600, "equipment_id": equip_id("CR-02")})
    assert r.status_code == 200, r.text
    a1 = r.json()
    assert a1["kind"] == "AGING" and a1["aging_days"] == 21 and a1["aging_days_source"] == "D-511" and a1["mode"] == "split"
    assert a1["aging_due_date"] == (date.today() + timedelta(days=21)).isoformat()
    a1_row = lot_by_no(a1["lot_no"])
    assert a1_row["kind"] == "AGING" and a1_row["kind_base"] == "PRODUCT" and float(a1_row["qty"]) == 600 and a1_row["state"] == "재고" and a1_row["insp_status"] == "합격"
    rest = lot_by_no(a1["rest"]["lot_no"])
    assert rest["lot_no"] == k1["lot_no"]                                                                         # k1_leftover_lot K1
    assert rest["kind"] == "PRODUCT" and float(rest["remain_qty"]) == 400 and rest["state"] == "재고"             # k1_leftover_qty · state
    assert lot_row(k1["lot_id"])["state"] == "재고"                                                               # k1_state 재고
    assert conn.q1("select count(*) as n from lot_genealogy")["n"] == g_before + 1                                # genealogy_delta 1
    rel = conn.q("select relation, relation_base, qty from lot_genealogy where parent_lot_id = %s order by id", (k1["lot_id"],))
    assert [x["relation"] for x in rel] == ["숙성"] and {x["relation_base"] for x in rel} == {"분할"} and float(rel[0]["qty"]) == 600
    ext = conn.q1("select * from x_kimchi_lot_ext where id = %s", (a1["id"],))
    assert ext["shippable_yn"] == "N" and ext["location_equipment_id"] == equip_id("CR-02") and ext["aging_start_date"] == date.today()
    stock = field.get("/age/stock").json()
    assert any(x["lot_no"] == a1["lot_no"] for x in stock["rows"])
    # 이미 숙성 배치 → 422 · 잔량 초과 → 422
    assert field.post("/age/stock", data={"barcode": a1["lot_no"], "qty": 1, "equipment_id": equip_id("CR-02")}).status_code == 422
    assert field.post("/age/stock", data={"barcode": rest["lot_no"], "qty": 500, "equipment_id": equip_id("CR-02")}).status_code == 422
    # 예정일 전 출하 승인 → 422 hook_rejected (숙성 미완료)
    s = new_shipment(prod)
    assert scan_ship(prod, s["shipment_no"], a1["lot_no"]).status_code == 200
    first = approve(prod, s["id"])
    assert first.status_code == 422 and first.json()["code"] == "hook_rejected" and "숙성 완료 전" in first.json()["message"], first.text
    # 완료 처리 — 예정일 전은 사유 필수
    assert prod.post(f"/age/stock/{a1['id']}/complete").status_code == 422
    done = prod.post(f"/age/stock/{a1['id']}/complete", data={"reason": "조기 출고 (예시)"})
    assert done.status_code == 200 and done.json()["early"] is True
    assert conn.q1("select kind from sys_access_log where fn_id = 'F-X-AGE-02' order by id desc limit 1")["kind"] == "change"
    assert prod.post(f"/age/stock/{a1['id']}/complete", data={"reason": "x"}).status_code == 422                # 두 번 완료 불가
    ok = approve(prod, s["id"])
    assert ok.status_code == 200, ok.text
    assert conn.q1("select count(*) as n from lot_genealogy")["n"] == g_before + 2
    # 역추적 S(A1) — 원재료 2 (양념) + 배추 없음(이 테스트는 절임통 생략) · AGING 노드
    bw = prod.get("/trc/backward", params={"no": shipment_lot_no(s["id"])}).json()
    assert sorted(n["no"] for n in bw["materials"]) == sorted(k1["materials"]) and len(bw["materials"]) == 2     # backward_materials 2
    aging_nodes = [n for st in bw["stages"] for n in st["nodes"] if n["kind"] == "AGING"]
    assert len(aging_nodes) == 1 and aging_nodes[0]["kind_label"] == "숙성 배치"
    # 전량 숙성 — LOT 자체가 숙성 배치 (retag · 계보 0행)
    g2 = conn.q1("select count(*) as n from lot_genealogy")["n"]
    full = field.post("/age/stock", data={"barcode": rest["lot_no"], "equipment_id": equip_id("CR-02")})
    assert full.status_code == 200 and full.json()["mode"] == "retag" and full.json()["lot_no"] == rest["lot_no"] and full.json()["qty"] == 400
    assert lot_by_no(rest["lot_no"])["kind"] == "AGING" and conn.q1("select count(*) as n from lot_genealogy")["n"] == g2
    # 모바일 390px 화면 200
    assert field.get("/age/stock", params={"device": "mobile"}, headers={"accept": "text/html"}).status_code == 200


@pytest.mark.fn("F-X-AGE-05")
@pytest.mark.fn("F-X-AGE-06")
@pytest.mark.fn("F-X-AGE-07")
def test_cold_moves_in_out_balance():
    prod, qa, field = client("prod"), client("qa"), client("field")
    k = _packed_lot(prod, qa, 100)
    cr = equip_id("CR-01")
    r = field.post("/age/cold-moves/in", data={"barcode": k["lot_no"], "equipment_id": cr, "qty": 100})
    assert r.status_code == 200 and r.json()["location_equipment_id"] == cr, r.text
    assert conn.q1("select location_equipment_id from x_kimchi_lot_ext where id = %s", (k["lot_id"],))["location_equipment_id"] == cr
    assert field.post("/age/cold-moves/out", data={"barcode": k["lot_no"], "equipment_id": cr, "qty": 150}).status_code == 422      # 잔량 초과
    out = field.post("/age/cold-moves/out", data={"barcode": k["lot_no"], "equipment_id": cr, "qty": 40})
    assert out.status_code == 200 and out.json()["balance"] == 60
    out2 = field.post("/age/cold-moves/out", data={"barcode": k["lot_no"], "equipment_id": cr})                                    # 나머지 전량
    assert out2.status_code == 200 and out2.json()["balance"] == 0
    assert conn.q1("select location_equipment_id from x_kimchi_lot_ext where id = %s", (k["lot_id"],))["location_equipment_id"] is None
    page = field.get("/age/cold-moves", params={"no": k["lot_no"]}).json()
    assert [x["trx_type"] for x in page["rows"]] == ["출고", "출고", "입고"]
    assert any(s["equip_code"] == "CR-01" for s in page["summary"])
    assert field.post("/age/cold-moves/in", data={"barcode": "NOPE-000", "equipment_id": cr}).status_code == 422
    assert field.post("/age/cold-moves/in", data={"barcode": k["lot_no"], "equipment_id": equip_id("TK-01")}).status_code == 422      # 냉장고 아님
