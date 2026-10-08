"""G-C06 계보 재현 · G-C07 추적 — `app/lineage.py` 함수만으로 (화면 없이). 개발2.

코어 시나리오(db-schema.md §3.3): 원재료 LOT 2 → 생산 LOT 2(같은 작업지시 · LOT①은 둘 다에 투입) → 합병 1(2:1) → 분할 3(1:3) → 출하 LOT 1(분할 ①② 출하 · ③ 재고)
= `lot_genealogy` **10행**(투입 3 + 합병 2 + 분할 3 + 출하 2). 역방향: 출하 LOT → 원재료 ①②. 정방향: 원재료 ① → 생산 ①② → 합병 → 분할 ①②③ → 출하(③ 재고).
임의 분기 5단 · 깊이 20 분기 100 에서 추적 2초 이내. 모든 행은 한 트랜잭션 안에서 만들고 끝에 되돌린다(DB 에 남기지 않는다).
같은 시나리오를 **API 로** 만드는 것은 `tests/test_pop_scenario.py` 다.
"""

from __future__ import annotations

import time
import pytest
from fastapi import HTTPException

from mescore.app import lineage
from mescore.db import conn

from _dev2_helpers import equipment_id, item_id, new_shipment, new_work_order, process_id, uniq

BY = "test"


class _Rollback(Exception):
    pass


@pytest.fixture()
def cur():
    try:
        with conn.tx() as c:
            yield c
            raise _Rollback
    except _Rollback:
        pass


def _result(cur, wo: dict) -> dict:
    cur.execute("""insert into pop_work_result (work_order_id, process_id, equipment_id, started_at, unit, created_by)
                   values (%s, %s, %s, now() - interval '1 hour', 'EA', 'test') returning *""", (wo["id"], wo["process_id"], wo["equipment_id"]))
    return dict(cur.fetchone())


def _end(cur, result_id: int, good: float) -> None:
    cur.execute("update pop_work_result set ended_at = now(), good_qty = %s where id = %s", (good, result_id))


def scenario(cur) -> dict:
    """코어 시나리오를 lineage 함수로. 돌려주는 dict: m[2] · p[2] · mg · s[3] · x · ship · wo."""
    raw1, raw2, prd = item_id("RAW-EX-01"), item_id("RAW-EX-02"), item_id("PRD-EX-01")
    m1 = lineage.make_material_lot(cur, item_id=raw1, qty=100, unit="kg", by=BY, insp_status="합격")
    m2 = lineage.make_material_lot(cur, item_id=raw2, qty=100, unit="kg", by=BY, insp_status="합격")
    wo = new_work_order(cur)
    r1, r2 = _result(cur, wo), _result(cur, wo)
    lineage.consume_material(cur, work_result_id=r1["id"], material_lot_id=m1["id"], qty=50, by=BY)
    lineage.consume_material(cur, work_result_id=r2["id"], material_lot_id=m1["id"], qty=50, by=BY)
    lineage.consume_material(cur, work_result_id=r2["id"], material_lot_id=m2["id"], qty=50, by=BY)
    _end(cur, r1["id"], 50)
    _end(cur, r2["id"], 50)
    p1 = lineage.make_product_lot(cur, work_result_id=r1["id"], by=BY)
    p2 = lineage.make_product_lot(cur, work_result_id=r2["id"], by=BY)
    mg = lineage.merge(cur, parent_ids=[p1["id"], p2["id"]], by=BY)
    s = lineage.split(cur, parent_id=mg["id"], count=3, by=BY, qtys=[30, 30, 30])
    ship = new_shipment(cur)
    lineage.ship(cur, shipment_id=ship["id"], lot_id=s[0]["id"], by=BY)
    lineage.ship(cur, shipment_id=ship["id"], lot_id=s[1]["id"], by=BY)
    x = lineage.shipment_lot(cur, ship["id"])
    return {"m": [m1, m2], "p": [p1, p2], "mg": mg, "s": s, "x": x, "ship": ship, "wo": wo, "r": [r1, r2]}


def _ids(e: dict) -> list[int]:
    return [e["m"][0]["id"], e["m"][1]["id"], e["p"][0]["id"], e["p"][1]["id"], e["mg"]["id"]] + [l["id"] for l in e["s"]] + [e["x"]["id"]]


@pytest.mark.fn("F-POP-03")
def test_core_scenario_is_exactly_10_rows(cur):
    e = scenario(cur)
    rows = lineage.genealogy_rows(_ids(e), cur)
    got: dict[str, int] = {}
    for r in rows:
        got[r["relation"]] = got.get(r["relation"], 0) + 1
    assert got == {"투입": 3, "합병": 2, "분할": 3, "출하": 2}, got
    assert len(rows) == 10
    assert all(r["relation_base"] == r["relation"] for r in rows)        # 코어 관계는 base = 이름
    assert e["mg"]["qty"] == 100 and e["x"]["kind"] == "SHIPMENT" and e["x"]["shipment_id"] == e["ship"]["id"]
    # 실적 ↔ 생산 LOT 연결
    cur.execute("select product_lot_id from pop_work_result where id = %s", (e["r"][0]["id"],))
    assert cur.fetchone()["product_lot_id"] == e["p"][0]["id"]
    # 번호는 numbering 규칙(core.yaml: 원재료 M · 생산 P · 출하 X) — 첫 글자로 종류를 판정하지는 않는다, 형식만 본다
    assert e["m"][0]["lot_no"][0] == "M" and e["p"][0]["lot_no"][0] == "P" and e["x"]["lot_no"][0] == "X"


def test_backward_trace_reaches_both_material_lots(cur):
    e = scenario(cur)
    tr = lineage.trace_backward(e["x"]["id"], cur)
    assert tr.direction == lineage.BACKWARD and tr.start.kind == "SHIPMENT"
    assert {n.id for n in tr.materials()} == {e["m"][0]["id"], e["m"][1]["id"]}
    assert len(tr.edges) == 9                                       # 재고 ③ 으로 가는 분할 한 줄만 빠진다
    assert e["s"][2]["id"] not in {n.id for n in tr.nodes()}
    assert [x.depth for x in tr.edges] == sorted(x.depth for x in tr.edges)
    assert len({x.genealogy_id for x in tr.edges}) == 9             # 중복 없음
    # 분할 LOT ① 하나만 거슬러도 원재료 ①② 둘 다
    assert {n.id for n in lineage.trace_backward(e["s"][0]["id"], cur).materials()} == {e["m"][0]["id"], e["m"][1]["id"]}
    # 생산 LOT ① 은 원재료 ① 만
    assert {n.id for n in lineage.trace_backward(e["p"][0]["id"], cur).materials()} == {e["m"][0]["id"]}


def test_forward_trace_and_states(cur):
    e = scenario(cur)
    tr = lineage.trace_forward(e["m"][0]["id"], cur)
    ids = {n.id for n in tr.nodes()} - {e["m"][0]["id"]}
    assert ids == {e["p"][0]["id"], e["p"][1]["id"], e["mg"]["id"], *[l["id"] for l in e["s"]], e["x"]["id"]}
    assert len(tr.edges) == 9                                       # 원재료 ② 의 투입 한 줄만 빠진다
    assert [n.id for n in tr.shipments()] == [e["x"]["id"]]
    assert [n.id for n in tr.stock()] == [e["s"][2]["id"]]          # 분할 ③ 은 재고
    st = {n.no: n.state for n in tr.nodes()}
    assert st[e["p"][0]["lot_no"]] == "소진" and st[e["mg"]["lot_no"]] == "소진"
    assert st[e["s"][0]["lot_no"]] == "출하" and st[e["s"][2]["lot_no"]] == "재고" and st[e["x"]["lot_no"]] == "출하"
    assert lineage.node(e["m"][0]["id"], cur).remain_qty == 0 and lineage.node(e["m"][0]["id"], cur).state == "소진"   # 50 + 50 투입
    assert lineage.node(e["m"][1]["id"], cur).remain_qty == 50
    assert [x.child.id for x in lineage.children_of(e["mg"]["id"], cur)] == [l["id"] for l in e["s"]]
    assert {x.parent.id for x in lineage.parents_of(e["mg"]["id"], cur)} == {e["p"][0]["id"], e["p"][1]["id"]}
    assert lineage.resolve(f" {e['mg']['lot_no']} ", cur).id == e["mg"]["id"]
    assert lineage.resolve("NO-SUCH-LOT", cur) is None


def test_guards_422(cur):
    e = scenario(cur)
    mg, s3, p1 = e["mg"]["id"], e["s"][2]["id"], e["p"][0]["id"]
    with pytest.raises(HTTPException) as ex:
        lineage.link(cur, mg, mg, lineage.PRODUCE, by=BY)
    assert ex.value.status_code == 422
    with pytest.raises(HTTPException) as ex:
        lineage.link(cur, s3, p1, lineage.PRODUCE, by=BY)               # 분할 ③ → 생산 ① 은 순환
    assert ex.value.status_code == 422 and "순환" in ex.value.detail["message"]
    with pytest.raises(HTTPException) as ex:
        lineage.link(cur, p1, s3, "없는관계", by=BY)
    assert ex.value.status_code == 422
    with pytest.raises(HTTPException) as ex:
        lineage.split(cur, parent_id=mg, count=2, by=BY)                 # 이미 소진된 LOT
    assert ex.value.status_code == 422
    with pytest.raises(HTTPException) as ex:
        lineage.ship(cur, shipment_id=e["ship"]["id"], lot_id=e["s"][0]["id"], by=BY)   # 이미 출하
    assert ex.value.status_code == 422 and "이미 출하" in ex.value.detail["message"]
    with pytest.raises(HTTPException) as ex:
        lineage.merge(cur, parent_ids=[s3], by=BY)                       # 코어 합병은 2 이상
    assert ex.value.status_code == 422
    with pytest.raises(HTTPException) as ex:
        lineage.split(cur, parent_id=s3, count=2, by=BY, qtys=[20, 20])  # 잔량 30 초과
    assert ex.value.status_code == 422
    # 출하 취소 → 다시 재고 → 다시 출하
    assert lineage.unship(cur, shipment_id=e["ship"]["id"], lot_id=e["s"][0]["id"], by=BY) == 1
    assert lineage.node(e["s"][0]["id"], cur).state == "재고"
    lineage.ship(cur, shipment_id=e["ship"]["id"], lot_id=e["s"][0]["id"], by=BY)
    assert lineage.node(e["s"][0]["id"], cur).state == "출하"
    # 미검사 · 불합격 원재료 LOT 투입 422
    bad = lineage.make_material_lot(cur, item_id=item_id("RAW-EX-01"), qty=10, unit="kg", by=BY)   # 미검사
    r = _result(cur, e["wo"])
    with pytest.raises(HTTPException) as ex:
        lineage.consume_material(cur, work_result_id=r["id"], material_lot_id=bad["id"], qty=1, by=BY)
    assert ex.value.status_code == 422
    cur.execute("update lot set insp_status = '불합격' where id = %s", (bad["id"],))
    with pytest.raises(HTTPException) as ex:
        lineage.consume_material(cur, work_result_id=r["id"], material_lot_id=bad["id"], qty=1, by=BY)
    assert ex.value.status_code == 422
    # 소진된 원재료 ① 투입 422
    with pytest.raises(HTTPException) as ex:
        lineage.consume_material(cur, work_result_id=r["id"], material_lot_id=e["m"][0]["id"], qty=1, by=BY)
    assert ex.value.status_code == 422


def test_retag_and_pack_relation_names(cur):
    e = scenario(cur)
    row = lineage.retag(cur, e["s"][2]["id"], "PRODUCT", by=BY)
    assert row["kind"] == "PRODUCT" and row["kind_base"] == "PRODUCT"
    with pytest.raises(HTTPException):
        lineage.retag(cur, e["s"][2]["id"], "없는종류", by=BY)
    assert lineage.relation("분할").base == "분할"
    with pytest.raises(HTTPException):
        lineage.relation_of_base("합병", "분할")


def _raw_lot(cur, item: int, no: str) -> int:
    cur.execute("""insert into lot (lot_no, kind, kind_base, item_id, qty, unit, insp_status, created_by)
                   values (%s, 'PRODUCT', 'PRODUCT', %s, 1, 'EA', '합격', 'test') returning id""", (no, item))
    return cur.fetchone()["id"]


def test_random_branching_five_levels(cur):
    """임의 분기 5단 — 각 단에서 분할 2 · 합병 2 · 생산 1:1 을 섞는다. 깊이를 가정하지 않는 재귀 조회가 전부 닿아야 한다."""
    prd = item_id("PRD-EX-01")
    root = lineage.make_material_lot(cur, item_id=item_id("RAW-EX-01"), qty=1000, unit="kg", by=BY, insp_status="합격")
    wo = new_work_order(cur)
    r = _result(cur, wo)
    lineage.consume_material(cur, work_result_id=r["id"], material_lot_id=root["id"], qty=100, by=BY)
    _end(cur, r["id"], 100)
    level = [lineage.make_product_lot(cur, work_result_id=r["id"], by=BY)["id"]]
    for depth in range(5):
        nxt: list[int] = []
        for i, lid in enumerate(level):
            if i % 3 == 0:
                nxt += [c["id"] for c in lineage.split(cur, parent_id=lid, count=2, by=BY)]
            elif i % 3 == 1:
                child = _raw_lot(cur, prd, uniq("T-G"))
                lineage.link(cur, lid, child, lineage.PRODUCE, by=BY)
                nxt.append(child)
            else:
                nxt.append(lid)                                     # 다음 단에서 합병의 재료로
        if len(nxt) >= 2 and depth % 2 == 1:
            a, b = nxt[-2], nxt[-1]
            if lineage.node(a, cur).state == "재고" and lineage.node(b, cur).state == "재고":
                nxt = nxt[:-2] + [lineage.merge(cur, parent_ids=[a, b], by=BY)["id"]]
        level = nxt
    fw = lineage.trace_forward(root["id"], cur)
    leaves = {n.id for n in fw.stock()}
    assert leaves and leaves <= {n.id for n in fw.nodes()}
    assert max(e.depth for e in fw.edges) >= 5
    for leaf in list(leaves)[:3]:
        bw = lineage.trace_backward(leaf, cur)
        assert [n.id for n in bw.materials()] == [root["id"]]


def test_depth_20_branch_100_under_2_seconds(cur):
    """깊이 20 · 분기 100 (LOT 2,001 · 화살표 2,000). 추적 조회만 잰다 — 경로 저장 0."""
    prd = item_id("PRD-EX-01")
    root = _raw_lot(cur, prd, uniq("T-R"))
    cur.execute("update lot set qty = 100000 where id = %s", (root,))
    heads = [c["id"] for c in lineage.split(cur, parent_id=root, count=100, by=BY)]
    for h in heads:
        prev = h
        for _ in range(19):
            child = _raw_lot(cur, prd, uniq("T-D"))
            lineage.link(cur, prev, child, lineage.PRODUCE, by=BY)
            prev = child
    t0 = time.perf_counter()
    fw = lineage.trace_forward(root, cur)
    t_fw = time.perf_counter() - t0
    assert len(fw.edges) == 2000 and max(e.depth for e in fw.edges) == 20
    leaf = fw.edges[-1].child.id
    t0 = time.perf_counter()
    bw = lineage.trace_backward(leaf, cur)
    t_bw = time.perf_counter() - t0
    assert len(bw.edges) == 20 and bw.edges[-1].parent.id == root
    assert t_fw < 2.0 and t_bw < 2.0, f"정방향 {t_fw:.2f}s · 역방향 {t_bw:.2f}s"
    print(f"\n[G-C07] 깊이 20 · 분기 100 — 정방향 {t_fw:.3f}s (edges 2000) · 역방향 {t_bw:.3f}s")
