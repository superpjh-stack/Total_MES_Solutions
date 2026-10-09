"""trc — F-TRC-01~03 (정방향 · 역방향 · 번호 검색). 고정 데이터 = `migrate/examples` 의 코어 시나리오(계보 10행). 쓰기 0 — 조회 전후 행 수 diff 0 을 여기서도 센다. 개발3."""

from __future__ import annotations

import pytest

from mescore.db import conn

from _dev3_helpers import HTML, client, load_examples

BUSINESS_TABLES = ("lot", "lot_genealogy", "job_work_order", "pop_work_result", "pop_measure", "qua_inspection", "shp_shipment", "shp_document")


@pytest.fixture(scope="module", autouse=True)
def _examples():
    load_examples()


def _counts() -> dict[str, int]:
    return {t: conn.q1(f"select count(*)::int as n from {t}")["n"] for t in BUSINESS_TABLES}


@pytest.mark.fn("F-TRC-01")
def test_forward_material_to_shipment_and_stock():
    c = client("prod")
    before = _counts()
    r = c.get("/trc/forward", params={"no": "M-EX-0001"})
    assert r.status_code == 200
    body = r.json()
    nos = {n["no"] for st in body["stages"] for n in st["nodes"]}
    assert {"P-EX-0001", "P-EX-0002", "P-EX-0003", "P-EX-0004", "P-EX-0005", "P-EX-0006", "X-EX-0001"} <= nos
    assert body["depth"] == 4 and body["edge_count"] >= 9                                    # 투입 → 합병 → 분할 → 출하
    assert [x["no"] for x in body["shipments"]] == ["X-EX-0001"] and [x["no"] for x in body["stock"]] == ["P-EX-0006"]   # 분할 ③ 재고
    assert _counts() == before                                                               # 쓰기 0
    assert c.get("/trc/forward", params={"no": "NOPE"}).status_code == 422
    h = c.get("/trc/forward", params={"no": "NOPE"}, headers=HTML)
    assert h.status_code == 422 and "data-scan" in h.text                                    # 그 화면 422 재렌더
    assert c.get("/trc/forward").status_code == 200                                          # 빈 진입 — 스캔칸
    assert client("field").get("/trc/forward").status_code == 403                            # 현장: trc 없음


@pytest.mark.fn("F-TRC-02")
def test_backward_shipment_to_both_materials_with_links():
    c = client("qa")
    before = _counts()
    r = c.get("/trc/backward", params={"no": "X-EX-0001"})
    assert r.status_code == 200
    body = r.json()
    assert sorted(m["no"] for m in body["materials"]) == ["M-EX-0001", "M-EX-0002"]
    first = body["stages"][0]
    assert first["relations"] == ["출하"] and sorted(e["to"]["no"] for e in first["edges"]) == ["P-EX-0004", "P-EX-0005"]
    links = first["edges"][0]["links"]
    assert links["work_order"].startswith("/job/status?wo=W-EX-0001") and links["inspection"].startswith("/qua/inspections?no=")   # G-C08
    assert _counts() == before
    m = client("qa", device="mobile").get("/trc/backward", params={"no": "X-EX-0001"}, headers=HTML)
    assert m.status_code == 200 and "m-card" in m.text and "<details" in m.text
    assert c.get("/trc/backward", params={"no": " "}).status_code == 200


@pytest.mark.fn("F-TRC-03")
def test_search_by_partial_number_and_item():
    c = client("admin")
    r = c.get("/trc/search", params={"q": "P-EX-000"})
    assert r.status_code == 200
    nos = [x["node"]["no"] for x in r.json()["results"]]
    assert {"P-EX-0001", "P-EX-0006"} <= set(nos) and len(nos) >= 6
    assert all(x["links"]["forward"].endswith(x["node"]["no"]) for x in r.json()["results"])
    assert c.get("/trc/search", params={"q": "제품 1"}).json()["results"]
    assert c.get("/trc/search").json()["results"] is None
    assert c.get("/trc/search", params={"q": "ZZZ-NOPE"}).json()["results"] == []


@pytest.mark.fn("F-TRC-01")
def test_merge_node_shows_lot_qty_apart_from_edge_qty():
    """DEF-QA3-006 — 화살표 수량(qty · lot_genealogy.qty)과 노드 수량(lot_qty = lot.qty)은 따로 넘긴다. 합병 LOT P-EX-0003 = 화살표 50 + 50 · LOT 100."""
    body = client("prod").get("/trc/forward", params={"no": "M-EX-0001"}).json()
    merged = [e for st in body["stages"] for e in st["edges"] if e["to"]["no"] == "P-EX-0003"]
    assert [e["qty"] for e in merged] == [50.0, 50.0] and all(e["lot_qty"] == e["to"]["qty"] == 100.0 for e in merged)


@pytest.mark.fn("F-TRC-02")
def test_every_drilldown_link_opens_200():
    """DEF-QA2-002 · G-C08 — 노드 링크(지시 `?wo=<지시 번호>` · LOT · 검사 · 출하 · 정/역방향)가 전부 200. 지시 현황은 그 지시의 실적을 드릴다운한다(D-604)."""
    for role in ("prod", "qa"):
        c = client(role)
        body = c.get("/trc/backward", params={"no": "X-EX-0001"}).json()
        links = set(body["start_links"].values()) | {v for st in body["stages"] for e in st["edges"] for v in e["links"].values()}
        assert any(x.startswith("/job/status?wo=W-EX-0001") for x in links)
        bad = {x: c.get(x).status_code for x in links if c.get(x).status_code != 200}
        assert bad == {}, (role, bad)
    wo = client("qa").get("/job/status", params={"wo": "W-EX-0001"}).json()
    assert wo["detail"]["work_order_no"] == "W-EX-0001" and sorted(r["lot_no"] for r in wo["results"]) == ["P-EX-0001", "P-EX-0002"]
