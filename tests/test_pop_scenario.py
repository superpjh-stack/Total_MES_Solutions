"""G-C06 코어 시나리오를 **API(화면이 부르는 것과 같은)** 로 한 바퀴 (개발2).

입고 2 → 입고검사 합격 → 작업지시(같은 지시) 실적 ① 시작 → 투입 스캔(원재료 ①) → 종료(생산 LOT ① + 투입 계보) → 실적 ② 시작 → 투입(원재료 ①②) → 종료
→ 합병(2:1) → 분할(1:3) → 출하 LOT(분할 ①② — `lineage.ship`, 출하 라우터는 개발3) → `lot_genealogy` 10행 · 역추적 원재료 ①② · 정방향 ③ 재고 · 라벨 4종 렌더 · 바코드 스캔 왕복.
"""

from __future__ import annotations

import pytest

from mescore.app import lineage, nav, printing
from mescore.db import conn

from _dev2_helpers import HTML, client, item_id, new_shipment, new_work_order, partner_id

POP02, POP03, POP04, MAT01, MAT02, MAT03 = (nav.path_of(s) for s in ("POP-02", "POP-03", "POP-04", "MAT-01", "MAT-02", "MAT-03"))


def _receive_and_pass(item_code: str, qty: float) -> dict:
    body = client("prod").post(MAT01, data={"item_id": item_id(item_code), "qty": qty, "partner_id": partner_id("SUP-EX-01")}).json()
    assert client("qa").post(MAT02, data={"lot_no": body["lot_no"], "judgement": "합격"}).status_code == 200
    return body


def _run(c, wo: dict, inputs: list[tuple[str, float]], good: float) -> dict:
    s = c.post(f"{POP02}/start", data={"work_order_id": wo["id"]}).json()
    assert s["ok"]
    for lot_no, qty in inputs:
        r = c.post(POP03, data={"work_result_id": s["id"], "barcode": lot_no, "qty": qty})
        assert r.status_code == 200, r.text
    e = c.post(f"{POP02}/{s['id']}/end", data={"good_qty": good})
    assert e.status_code == 200, e.text
    return {**e.json(), "result_id": s["id"]}


@pytest.mark.fn("F-POP-03")
def test_core_scenario_through_api_is_10_rows():
    c = client("prod")
    m1, m2 = _receive_and_pass("RAW-EX-01", 100), _receive_and_pass("RAW-EX-02", 100)
    wo = new_work_order(process_code="PRC-EX-02")
    p1 = _run(c, wo, [(m1["lot_no"], 50)], 50)
    p2 = _run(c, wo, [(m1["lot_no"], 50), (m2["lot_no"], 50)], 50)
    mg = c.post(f"{POP02}/{p2['result_id']}/merge", data={"lot_ids": f"{p1['lot_no']},{p2['lot_no']}"}).json()
    assert mg["ok"] and mg["qty"] == 100
    sp = c.post(f"{POP02}/{p2['result_id']}/split", data={"lot_id": mg["id"], "count": 3, "qtys": "30,30,40"}).json()
    assert sp["ok"] and len(sp["lots"]) == 3
    s1, s2, s3 = sp["lots"]
    ship = new_shipment()
    with conn.tx() as cur:
        lineage.ship(cur, shipment_id=ship["id"], lot_id=s1["id"], by="prod")
        lineage.ship(cur, shipment_id=ship["id"], lot_id=s2["id"], by="prod")
    x = conn.q1("select * from lot where shipment_id = %s and kind_base = 'SHIPMENT'", (ship["id"],))
    ids = [m1["lot_id"], m2["lot_id"], p1["lot_id"], p2["lot_id"], mg["id"], s1["id"], s2["id"], s3["id"], x["id"]]
    rows = conn.q("select relation, relation_base from lot_genealogy where parent_lot_id = any(%(i)s) or child_lot_id = any(%(i)s)", {"i": ids})
    got: dict[str, int] = {}
    for r in rows:
        got[r["relation"]] = got.get(r["relation"], 0) + 1
    assert got == {"투입": 3, "합병": 2, "분할": 3, "출하": 2} and len(rows) == 10, got
    # G-C07 — 역방향 · 정방향
    bw = lineage.trace_backward(x["id"])
    assert {n.no for n in bw.materials()} == {m1["lot_no"], m2["lot_no"]}
    fw = lineage.trace_forward(m1["lot_id"])
    assert [n.no for n in fw.shipments()] == [x["lot_no"]] and [n.id for n in fw.stock()] == [s3["id"]]
    assert lineage.state(s3["id"]) == "재고" and lineage.state(s1["id"]) == "출하" and lineage.state(mg["id"]) == "소진"
    # G-C08 — LOT 번호 하나로 지시 · 실적 · 측정값 · 검사 · 출하
    n = lineage.resolve(s1["lot_no"])
    assert n.work_order_no == wo["work_order_no"]
    assert conn.q1("select product_lot_id from pop_work_result where id = %s", (p2["result_id"],))["product_lot_id"] == p2["lot_id"]
    # G-C14 — 라벨 4종 렌더 + 바코드 스캔 왕복
    for lot in (m1["lot_id"], p1["lot_id"], mg["id"], s3["id"]):
        html = c.get(POP04, params={"lot": lot}, headers=HTML).text
        no = conn.q1("select lot_no from lot where id = %s", (lot,))["lot_no"]
        assert f'aria-label="{no}"' in html and lineage.resolve(no).id == lot
        assert c.get(POP04, params={"no": no}).json()["lot_no"] == no
    assert c.get(f"{MAT03}/{m1['lot_id']}/label", headers=HTML).status_code == 200
    ship_label = printing.shipment_label_for(ship["id"])
    assert ship_label["lot_count"] == 2 and ship_label["total_qty"] == 60 and ship_label["shipment_lot_no"] == x["lot_no"]
    assert f'aria-label="{ship["shipment_no"]}"' in printing.barcode_svg(ship["shipment_no"])
    wo_svg = printing.barcode_svg(wo["work_order_no"])
    assert f'aria-label="{wo["work_order_no"]}"' in wo_svg
    assert "<rect" in printing.barcode_svg("C261009-001")
