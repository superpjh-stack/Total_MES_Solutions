"""스키마가 계보를 감당하는가 — G-C06 코어 시나리오(db-schema.md §3.3)를 SQL 로 직접 넣어 본다 (아키텍트).

이것은 **스키마** 검사다. 같은 시나리오를 API 로 만드는 것은 개발2 의 `tests/test_lineage_scenario.py`(G-C06)이고 추적 함수는 `app/lineage.py`(G-C07)다.
여기서는 그 둘이 기대는 바닥 — 테이블 52 · 공통 컬럼 · 10행 · 재귀 조회 · 순환 · 자기참조 · 불변 · 뷰 — 만 본다.
모든 행은 트랜잭션 안에서 넣고 마지막에 되돌린다(DB 에 아무것도 남기지 않는다). `make db-schema` 가 적용돼 있어야 한다.
"""

import time
from pathlib import Path

import psycopg
import pytest

from mescore.db import conn

VIEWS_SQL = Path(__file__).resolve().parents[1] / "src" / "mescore" / "db" / "views.sql"


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


def _one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def _lot(cur, no, kind, item=None, qty=100, shipment=None):
    base = {"MATERIAL": "MATERIAL", "PRODUCT": "PRODUCT", "SHIPMENT": "SHIPMENT"}[kind]
    return _one(cur, """insert into lot (lot_no, kind, kind_base, item_id, qty, unit, insp_status, shipment_id, created_by)
                        values (%s, %s, %s, %s, %s, 'EA', '합격', %s, 't') returning id""", (no, kind, base, item, qty, shipment))["id"]


def _edge(cur, parent, child, relation, qty=None):
    cur.execute("insert into lot_genealogy (parent_lot_id, child_lot_id, relation, relation_base, qty, linked_by) values (%s, %s, %s, %s, %s, 't')",
                (parent, child, relation, relation, qty))


def _scenario(cur) -> dict:
    """원재료 2 → 생산 LOT 2(①은 둘 다에 투입) → 합병 1 → 분할 3 → 출하 1(①② 출하 · ③ 재고) = 10행."""
    raw = _one(cur, "insert into bas_item (item_code, item_name, item_type, created_by) values ('T-RAW', '원재료 (예시)', '원재료', 't') returning id")["id"]
    prd = _one(cur, "insert into bas_item (item_code, item_name, item_type, created_by) values ('T-PRD', '제품 (예시)', '제품', 't') returning id")["id"]
    partner = _one(cur, "insert into bas_partner (partner_code, partner_name, partner_type, created_by) values ('T-CUST', '고객 (예시)', '고객', 't') returning id")["id"]
    ship = _one(cur, "insert into shp_shipment (shipment_no, partner_id, ship_date, created_by) values ('T-SHIP', %s, current_date, 't') returning id", (partner,))["id"]
    m1, m2 = _lot(cur, "T-M1", "MATERIAL", raw), _lot(cur, "T-M2", "MATERIAL", raw)
    p1, p2 = _lot(cur, "T-P1", "PRODUCT", prd, 50), _lot(cur, "T-P2", "PRODUCT", prd, 50)
    mg = _lot(cur, "T-MG", "PRODUCT", prd, 100)
    s1, s2, s3 = (_lot(cur, f"T-S{i}", "PRODUCT", prd, q) for i, q in ((1, 30), (2, 30), (3, 40)))   # 분할 30·30·40 = 합병 100 (D-43)
    x = _lot(cur, "T-X1", "SHIPMENT", None, 60, shipment=ship)
    _edge(cur, m1, p1, "투입", 50); _edge(cur, m1, p2, "투입", 50); _edge(cur, m2, p2, "투입", 50)
    _edge(cur, p1, mg, "합병", 50); _edge(cur, p2, mg, "합병", 50)
    for s, q in ((s1, 30), (s2, 30), (s3, 40)):
        _edge(cur, mg, s, "분할", q)
    _edge(cur, s1, x, "출하", 30); _edge(cur, s2, x, "출하", 30)
    return {"m": [m1, m2], "p": [p1, p2], "mg": mg, "s": [s1, s2, s3], "x": x, "ship": ship}


UP = """with recursive up as (
            select g.* from lot_genealogy g where g.child_lot_id = %s
            union
            select g.* from lot_genealogy g join up on g.child_lot_id = up.parent_lot_id)
        select * from up"""
DOWN = """with recursive down as (
              select g.* from lot_genealogy g where g.parent_lot_id = %s
              union
              select g.* from lot_genealogy g join down on g.parent_lot_id = down.child_lot_id)
          select * from down"""


def test_schema_has_52_tables_and_3_views_with_common_columns():
    tables = conn.q("select table_name from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE'")
    core = [t["table_name"] for t in tables if not t["table_name"].startswith("x_")]
    assert len(core) == 52
    views = {v["viewname"] for v in conn.q("select viewname from pg_views where schemaname = 'public'")}
    assert {"v_lot_state", "v_lot_stock", "v_work_order_progress"} <= views
    for t in core:
        cols = {c["column_name"] for c in conn.q("select column_name from information_schema.columns where table_schema = 'public' and table_name = %s", (t,))}
        assert {"id", "created_at", "created_by", "updated_at", "updated_by", "attrs"} <= cols, t


def test_scenario_is_exactly_10_rows(cur):
    e = _scenario(cur)
    cur.execute("select relation, count(*) as n from lot_genealogy where child_lot_id = any(%s) group by relation",
                (e["p"] + [e["mg"]] + e["s"] + [e["x"]],))
    got = {r["relation"]: r["n"] for r in cur.fetchall()}
    assert got == {"투입": 3, "합병": 2, "분할": 3, "출하": 2} and sum(got.values()) == 10


def test_backward_trace_reaches_both_material_lots(cur):
    e = _scenario(cur)
    cur.execute(UP, (e["x"],))
    rows = cur.fetchall()
    parents = {r["parent_lot_id"] for r in rows}
    assert set(e["m"]) <= parents
    assert len(rows) == 9                       # 10행 중 재고 ③ 으로 가는 분할 한 줄만 빠진다
    assert e["s"][2] not in {r["child_lot_id"] for r in rows}


def test_forward_trace_and_lot_state_view(cur):
    e = _scenario(cur)
    cur.execute(DOWN, (e["m"][0],))
    rows = cur.fetchall()
    assert {r["child_lot_id"] for r in rows} == set(e["p"] + [e["mg"]] + e["s"] + [e["x"]])
    assert len(rows) == 9                       # LOT ② 의 투입 한 줄만 빠진다
    cur.execute("select lot_no, state from v_lot_state where lot_id = any(%s)", (e["p"] + [e["mg"]] + e["s"] + [e["x"]] + e["m"],))
    state = {r["lot_no"]: r["state"] for r in cur.fetchall()}
    assert state == {"T-P1": "소진", "T-P2": "소진", "T-MG": "소진", "T-S1": "출하", "T-S2": "출하", "T-S3": "재고", "T-X1": "출하",
                     "T-M1": "재고", "T-M2": "재고"}
    cur.execute("select lot_no, remain_qty from v_lot_stock where lot_no in ('T-MG', 'T-S3')")
    remain = {r["lot_no"]: r["remain_qty"] for r in cur.fetchall()}
    assert remain["T-MG"] == 0 and remain["T-S3"] == 40       # 합병 100 을 30·30·40 으로 다 나눔 → 잔량 0 → 소진 (D-43)


def test_self_reference_and_cycle_are_rejected(cur):
    e = _scenario(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("savepoint a")
        _edge(cur, e["p"][0], e["p"][0], "생산")
    cur.execute("rollback to savepoint a")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("savepoint b")
        _edge(cur, e["s"][0], e["p"][0], "생산")   # 분할 ① → 생산 ① 은 순환
    cur.execute("rollback to savepoint b")
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute("savepoint c")
        _edge(cur, e["m"][0], e["p"][0], "투입")    # 같은 (부모, 자식, 관계)
    cur.execute("rollback to savepoint c")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("savepoint d")
        cur.execute("update lot_genealogy set child_lot_id = %s where parent_lot_id = %s and child_lot_id = %s", (e["s"][2], e["s"][0], e["x"]))
    cur.execute("rollback to savepoint d")


def test_shipment_lot_requires_shipment_id(cur):
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("savepoint s")
        cur.execute("insert into lot (lot_no, kind, kind_base, qty, created_by) values ('T-BAD', 'SHIPMENT', 'SHIPMENT', 1, 't')")
    cur.execute("rollback to savepoint s")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("savepoint n")
        cur.execute("insert into lot (lot_no, kind, kind_base, qty, created_by) values ('bad no', 'PRODUCT', 'PRODUCT', 1, 't')")
    cur.execute("rollback to savepoint n")


def test_deep_chain_is_recursive(cur):
    """깊이 25 사슬 — 깊이를 가정하지 않는다."""
    item = _one(cur, "insert into bas_item (item_code, item_name, item_type, created_by) values ('T-DEEP', '제품 (예시)', '제품', 't') returning id")["id"]
    ids = [_lot(cur, f"T-D{i:02d}", "PRODUCT", item) for i in range(25)]
    for a, b in zip(ids, ids[1:]):
        _edge(cur, a, b, "생산")
    cur.execute(UP, (ids[-1],))
    assert len(cur.fetchall()) == 24


def _current_views(cur) -> str:
    """이 트랜잭션 안에서만 `views.sql`(코드의 뷰 정의)을 다시 깐다 — 오래된 뷰가 남은 DB(데이터 누적 · 예전 스키마)에서도
    **코드의 정의**를 판정한다(DEF-QA3-005). 끝나면 되돌림. 고유 접미사도 준다(누적 데이터의 번호와 겹치지 않게)."""
    cur.execute(VIEWS_SQL.read_text(encoding="utf-8"))
    return f"{time.time_ns() % 10**10}"


def test_product_lot_partial_input_stays_in_stock(cur):
    """PRODUCT LOT 을 다른 지시에 「투입」 만 하면 잔량으로 판정 — 한 LOT 을 두 통에 나눠 담기 (회전 4 · 개발3 17). 합병 · 생산 · 수량 없는 분할은 통째 소진(D-43).
    자기 데이터만 본다 — 고유 번호 · 트랜잭션 안 뷰 재적용 (DEF-QA3-005)."""
    sfx = _current_views(cur)
    item = _one(cur, "insert into bas_item (item_code, item_name, item_type, created_by) values (%s, '제품 (예시)', '제품', 't') returning id", (f"T-PART-{sfx}",))["id"]
    src, a, b, c = (_lot(cur, f"{n}-{sfx}", "PRODUCT", item) for n in ("T-PT0", "T-PTA", "T-PTB", "T-PTC"))

    def state(lot_id):
        cur.execute("select s.state, k.remain_qty from v_lot_state s join v_lot_stock k on k.lot_id = s.lot_id where s.lot_id = %s", (lot_id,))
        r = cur.fetchone()
        return r["state"], r["remain_qty"]

    _edge(cur, src, a, "투입", 40)
    assert state(src) == ("재고", 60)
    _edge(cur, src, b, "투입", 60)
    assert state(src) == ("소진", 0)
    other = _lot(cur, f"T-PT1-{sfx}", "PRODUCT", item)
    _edge(cur, other, c, "투입")                     # 수량 모르는 투입 → 소진
    assert state(other)[0] == "소진"
    whole = _lot(cur, f"T-PT2-{sfx}", "PRODUCT", item)
    _edge(cur, whole, a, "합병", 10)                 # 합병은 수량과 무관하게 통째 소진
    assert state(whole) == ("소진", 90)


def test_product_lot_partial_split_keeps_remainder(cur):
    """D-43(회전 8) — 분할 화살표가 전부 수량을 가지면 투입처럼 잔량으로 판정한다(20 → 5+5 는 잔량 10 `재고`).
    수량을 다 나누면 잔량 0 → `소진`. 수량 없는 분할 화살표가 하나라도 있으면 LOT 통째 `소진`."""
    sfx = _current_views(cur)
    item = _one(cur, "insert into bas_item (item_code, item_name, item_type, created_by) values (%s, '제품 (예시)', '제품', 't') returning id", (f"T-PS-{sfx}",))["id"]
    part, full, whole = (_lot(cur, f"{n}-{sfx}", "PRODUCT", item, qty=20) for n in ("T-PS-P", "T-PS-F", "T-PS-W"))
    kids = [_lot(cur, f"T-PS-C{i}-{sfx}", "PRODUCT", item, qty=5) for i in range(5)]

    def state(lot_id):
        r = _one(cur, "select s.state, k.remain_qty from v_lot_state s join v_lot_stock k on k.lot_id = s.lot_id where s.lot_id = %s", (lot_id,))
        return r["state"], r["remain_qty"]

    _edge(cur, part, kids[0], "분할", 5); _edge(cur, part, kids[1], "분할", 5)
    assert state(part) == ("재고", 10)                   # 부분 분할 — 남는 10 은 부모 재고
    _edge(cur, full, kids[2], "분할", 5); _edge(cur, full, kids[3], "분할", 15)
    assert state(full) == ("소진", 0)                    # 다 나눔 → 잔량 0 → 소진
    _edge(cur, whole, kids[4], "분할")                   # 수량 없는 분할 = LOT 통째
    assert state(whole)[0] == "소진"


def test_product_lot_open_input_counts_in_stock(cur):
    """DEF-QA2-001 — 종료 전 실적의 투입(pop_input)도 PRODUCT 잔량에서 뺀다. 종료되면 계보로 넘어가 한 번만 센다 · 취소는 빼지 않는다."""
    sfx = _current_views(cur)
    item = _one(cur, "insert into bas_item (item_code, item_name, item_type, created_by) values (%s, '제품 (예시)', '제품', 't') returning id", (f"T-OPN-{sfx}",))["id"]
    proc = _one(cur, "insert into bas_process (process_code, process_name, created_by) values (%s, '공정 (예시)', 't') returning id", (f"T-OPN-{sfx}",))["id"]
    wo = _one(cur, "insert into job_work_order (work_order_no, item_id, process_id, plan_qty, created_by) values (%s, %s, %s, 10, 't') returning id",
              (f"T-OPN-{sfx}", item, proc))["id"]
    lot = _lot(cur, f"T-OPN-P-{sfx}", "PRODUCT", item, qty=20)
    child = _lot(cur, f"T-OPN-C-{sfx}", "PRODUCT", item)

    def result():
        return _one(cur, "insert into pop_work_result (work_order_id, process_id, created_by) values (%s, %s, 't') returning id", (wo, proc))["id"]

    def remain():
        return _one(cur, "select remain_qty, consumed_qty from v_lot_stock where lot_id = %s", (lot,))

    e, f = result(), result()
    cur.execute("insert into pop_input (work_result_id, material_lot_id, qty, created_by) values (%s, %s, 15, 't')", (e, lot))
    assert remain()["remain_qty"] == 5                          # 열린 실적 E 의 투입 15
    cur.execute("insert into pop_input (work_result_id, material_lot_id, qty, canceled_yn, created_by) values (%s, %s, 15, 'Y', 't')", (f, lot))
    assert remain()["remain_qty"] == 5                          # 취소된 투입은 세지 않는다
    cur.execute("update pop_work_result set ended_at = now() where id = %s", (e,))
    _edge(cur, lot, child, "투입", 15)                           # 종료 → 계보 투입 15 (lineage 가 하는 일)
    assert (remain()["remain_qty"], remain()["consumed_qty"]) == (5, 15)


def test_product_lot_open_input_to_zero_is_consumed(cur):
    """D-41 · DEF-QA2-008 — 열린 투입(종료 전)으로 잔량 0 이 된 PRODUCT LOT 은 종료 전이라도 `소진`. 취소하면 다시 `재고`.
    열린 투입의 수량을 모르면(qty NULL) 통째로 쓴 것으로 보고 `소진`. 잔량이 남으면 `재고` 그대로(부분 투입)."""
    sfx = _current_views(cur)
    item = _one(cur, "insert into bas_item (item_code, item_name, item_type, created_by) values (%s, '제품 (예시)', '제품', 't') returning id", (f"T-OZ-{sfx}",))["id"]
    proc = _one(cur, "insert into bas_process (process_code, process_name, created_by) values (%s, '공정 (예시)', 't') returning id", (f"T-OZ-{sfx}",))["id"]
    wo = _one(cur, "insert into job_work_order (work_order_no, item_id, process_id, plan_qty, created_by) values (%s, %s, %s, 10, 't') returning id",
              (f"T-OZ-{sfx}", item, proc))["id"]
    r = _one(cur, "insert into pop_work_result (work_order_id, process_id, created_by) values (%s, %s, 't') returning id", (wo, proc))["id"]
    full, part, unknown = (_lot(cur, f"{n}-{sfx}", "PRODUCT", item, qty=20) for n in ("T-OZ-F", "T-OZ-P", "T-OZ-U"))

    def state(lot_id):
        return _one(cur, "select s.state, k.remain_qty from v_lot_state s join v_lot_stock k on k.lot_id = s.lot_id where s.lot_id = %s", (lot_id,))

    inp = _one(cur, "insert into pop_input (work_result_id, material_lot_id, qty, created_by) values (%s, %s, 20, 't') returning id", (r, full))["id"]
    assert (state(full)["state"], state(full)["remain_qty"]) == ("소진", 0)      # 종료 전이라도 소진 — 거짓 「재고」 없음
    cur.execute("update pop_input set canceled_yn = 'Y' where id = %s", (inp,))
    assert (state(full)["state"], state(full)["remain_qty"]) == ("재고", 20)     # 취소하면 되돌아온다
    cur.execute("insert into pop_input (work_result_id, material_lot_id, qty, created_by) values (%s, %s, 15, 't')", (r, part))
    assert (state(part)["state"], state(part)["remain_qty"]) == ("재고", 5)      # 부분 투입은 재고
    cur.execute("insert into pop_input (work_result_id, material_lot_id, qty, created_by) values (%s, %s, null, 't')", (r, unknown))
    assert state(unknown)["state"] == "소진"                                      # 수량 모르는 열린 투입 → 통째
