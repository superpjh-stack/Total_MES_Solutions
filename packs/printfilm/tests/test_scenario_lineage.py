"""G-P04 S1 — 엘컴화인 설계도 §3 계보 10행을 **API 로** 한 바퀴 (gates.yaml: scenarios[S1] · 개발2).

원재료 LOT 2 → 입고검사 합격 → 수주 → Job(인쇄 · 판사양 · 아니록스 · 잉크) → POP 시작 · 투입 M① · 종료 = Roll① / 시작 · 투입 M①② · 종료 = Roll②
→ splice(2:1) = F → 슬리팅(1:3) = S①②③ → 검사 합격 S①② → 출하 등록 · 스캔 S①② → 승인 → lot_genealogy 10행
= 투입 3 + splice 2 + 슬리팅 3 + 출하 2 · relation_base 투입 3 · 합병 2 · 분할 3 · 출하 2 · 역추적 M①② · 정방향 S③ 재고.
"""

from __future__ import annotations

import pytest

from mescore.app import lineage
from mescore.db import conn

from _helpers import HTML, P, approve, client, genealogy_by_relation, inspect, new_shipment, s1_upto_slitting, scan


@pytest.mark.fn("F-X-RLL-02")
@pytest.mark.fn("F-X-RLL-04")
def test_ten_rows():
    x = s1_upto_slitting()
    m1, m2, job, r1, r2, fz, s1, s2, s3 = (x[k] for k in ("m1", "m2", "job", "r1", "r2", "f", "s1", "s2", "s3"))
    # 번호 형식 (pack.yaml: numbering — M+YYMMDD-+3 · J+YYMMDD-+3 · R+YYMMDD-+4)
    assert m1["lot_no"].startswith("M") and len(m1["lot_no"]) == 11 and job["work_order_no"].startswith("J") and r1["lot_no"].startswith("R") and len(r1["lot_no"]) == 12
    # 인쇄 롤 — 훅 on_result_closed: kind ROLL · base PRODUCT · ext 인쇄 · 투입 계보 = pop_input 수
    for r, n_in in ((r1, 1), (r2, 2)):
        lot = conn.q1("select l.kind, l.kind_base, l.attrs, x.process_type, x.equipment_id from lot l join x_printfilm_lot_ext x on x.id = l.id where l.id = %s", (r["lot_id"],))
        assert lot["kind"] == "ROLL" and lot["kind_base"] == "PRODUCT" and lot["process_type"] == "인쇄" and lot["equipment_id"] is not None
        assert lot["attrs"]["length_m"] == 1000 and lot["attrs"]["width_mm"] == 1000
        assert conn.q1("select count(*) as n from lot_genealogy where child_lot_id = %s and relation = '투입'", (r["lot_id"],))["n"] == n_in
    # splice · 슬리팅
    assert fz["relation"] == "splice" and fz["parents"] == [r1["lot_no"], r2["lot_no"]]
    assert lineage.state(r1["lot_id"]) == "소진" and lineage.state(r2["lot_id"]) == "소진" and lineage.state(fz["id"]) == "소진"
    ext = conn.q("select l.lot_no, x.process_type, x.slit_seq, l.attrs from x_printfilm_lot_ext x join lot l on l.id = x.id where x.id = any(%s) order by x.slit_seq", ([s1["id"], s2["id"], s3["id"]],))
    assert [e["slit_seq"] for e in ext] == [1, 2, 3] and {e["process_type"] for e in ext} == {"슬리팅"} and [e["attrs"]["width_mm"] for e in ext] == [300, 300, 400]
    assert conn.q1("select process_type from x_printfilm_lot_ext where id = %s", (fz["id"],))["process_type"] == "후가공"
    # 검사 합격 S①② (D-504 — 코어 스캔이 미검사 422 라 검사가 먼저) → 출하 등록 · 스캔 2 · 승인
    inspect(s1["lot_no"], "합격", delta_e=0.8)
    inspect(s2["lot_no"], "합격", delta_e=1.1)
    ship = new_shipment()
    scan(ship["shipment_no"], s1["lot_no"])
    scan(ship["shipment_no"], s2["lot_no"])
    assert approve(ship["id"])["status"] == "승인"
    xlot = conn.q1("select id, lot_no, kind, kind_base from lot where shipment_id = %s and kind_base = 'SHIPMENT'", (ship["id"],))
    ids = [m1["lot_id"], m2["lot_id"], r1["lot_id"], r2["lot_id"], fz["id"], s1["id"], s2["id"], s3["id"], xlot["id"]]
    rel, base, n = genealogy_by_relation(ids)
    assert n == 10 and rel == {"투입": 3, "splice": 2, "슬리팅": 3, "출하": 2}, (n, rel)
    assert base == {"투입": 3, "합병": 2, "분할": 3, "출하": 2}, base
    assert conn.q1("select count(*) as n from lot where id = any(%s) and kind = 'ROLL'", (ids,))["n"] == 6
    assert conn.q1("select count(*) as n from x_printfilm_lot_ext where id = any(%s)", (ids,))["n"] == 6
    # 역추적 출하 LOT → M①② (edges 9) · 정방향 M① (edges 9 · S③ 재고 · M②→R② 는 안 나온다)
    bw = lineage.trace_backward(xlot["id"])
    assert {m.no for m in bw.materials()} == {m1["lot_no"], m2["lot_no"]} and len(bw.edges) == 9
    fw = lineage.trace_forward(m1["lot_id"])
    assert len(fw.edges) == 9 and [s.no for s in fw.shipments()] == [xlot["lot_no"]] and [s.id for s in fw.stock()] == [s3["id"]]
    assert all(not (e.parent.id == m2["lot_id"]) for e in fw.edges)
    assert lineage.state(s3["id"]) == "재고" and lineage.state(s1["id"]) == "출하" and lineage.state(s2["id"]) == "출하"
    # 화면 — TRC-02 역방향 · TRC-01 정방향 (관리자 · 모바일) 200 · Roll 용어
    a = client("admin")
    b = a.get(P["TRC-02"], params={"no": xlot["lot_no"]}, headers=HTML)
    f = a.get(P["TRC-01"], params={"no": m1["lot_no"]}, headers=HTML)
    assert b.status_code == 200 and m1["lot_no"] in b.text and m2["lot_no"] in b.text
    assert f.status_code == 200 and s3["lot_no"] in f.text
    # G-C08 — 롤 번호 하나로 Job · 실적
    assert lineage.resolve(s2["lot_no"]).work_order_no == job["work_order_no"]
    assert conn.q1("select product_lot_id from pop_work_result where id = %s", (r2["result_id"],))["product_lot_id"] == r2["lot_id"]
    # 라벨 (F-X-RLL-07) — 바코드 값 = 롤 번호 · 공정 구분 · 분할 순번
    html = client("field").get(f"{P['X-RLL-03']}/{s2['lot_no']}/label", headers=HTML).text
    assert f'aria-label="{s2["lot_no"]}"' in html and "슬리팅" in html and "#2" in html and "생산 LOT" not in html
    # 요약 — 보고용
    print("\nS1 lot_genealogy:", n, "행 ·", rel, "· base", base)


@pytest.mark.fn("F-X-RLL-03")
def test_genealogy_direct_sql_in_pack_is_zero():
    """R8 — rll 라우터 · hooks.py 에 lot_genealogy INSERT 0 (gates.yaml S1.expect.genealogy_direct_sql_in_pack)."""
    import re
    from pathlib import Path

    pdir = Path(__file__).resolve().parents[1]
    hits = []
    for p in list((pdir / "routers").glob("*.py")) + [pdir / "hooks.py"]:
        for m in re.finditer(r"\b(insert\s+into|update|delete\s+from)\s+(lot_genealogy|sys_number_seq)\b", p.read_text(encoding="utf-8"), re.I):
            hits.append(f"{p.name}:{m.group(0)}")
    assert hits == []
