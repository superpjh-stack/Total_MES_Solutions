"""migrate — B-MIG-01~04. 2회 실행 행 수 diff 0 · 오류 줄 리포트 · 계보 10행(lineage.link 경유) · dry-run 은 쓰지 않는다 · sys_migration_log. 개발3."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mescore import migrate
from mescore.db import conn

from _dev3_helpers import EXAMPLES

LOT_NOS = ["M-EX-0001", "M-EX-0002", "P-EX-0001", "P-EX-0002", "P-EX-0003", "P-EX-0004", "P-EX-0005", "P-EX-0006", "X-EX-0001"]


def _run_twice(command: str) -> tuple[migrate.MigrateReport, migrate.MigrateReport, dict, dict]:
    first = migrate.run(command, EXAMPLES, run_by="test")
    c1 = conn.table_counts()
    second = migrate.run(command, EXAMPLES, run_by="test")
    c2 = conn.table_counts()
    return first, second, c1, c2


def _assert_idempotent(first, second, c1, c2):
    assert first.ok and second.ok, first.text() + "\n" + second.text()
    assert second.totals()["inserted"] == 0, second.text()
    diff = {k: (c1.get(k), c2.get(k)) for k in set(c1) | set(c2) if c1.get(k) != c2.get(k) and k != "sys_migration_log"}
    assert diff == {}, diff


@pytest.mark.fn("B-MIG-01")
def test_basics_idempotent_and_logged():
    first, second, c1, c2 = _run_twice("basics")
    _assert_idempotent(first, second, c1, c2)
    assert [f.file for f in first.files] == list(migrate.COMMANDS["basics"]) and all(f.present for f in first.files)
    log = conn.q1("select * from sys_migration_log where command = 'basics' and file = '01_items.csv' order by id desc")
    assert log["read_count"] == 3 and log["errors"] == 0 and log["run_by"] == "test" and log["ended_at"] is not None and not log["dry_run"]
    assert conn.q1("select count(*)::int as n from bas_bom_dtl d join bas_bom b on b.id = d.bom_id join bas_item i on i.id = b.item_id where i.item_code = 'PRD-EX-01' and d.created_by = 'migrate'")["n"] == 2


@pytest.mark.fn("B-MIG-02")
def test_orders_and_work_orders_reference_resolution():
    first, second, c1, c2 = _run_twice("orders")
    _assert_idempotent(first, second, c1, c2)
    wo = conn.q1("""select w.plan_qty, w.status, d.line_no, o.order_no from job_work_order w join ord_order_dtl d on d.id = w.order_dtl_id
                     join ord_order o on o.id = d.order_id where w.work_order_no = 'W-EX-0001'""")
    assert wo["order_no"] == "O-EX-0001" and wo["line_no"] == 1 and wo["status"] == "마감"
    assert conn.q1("select count(*)::int as n from sys_number_seq where kind in ('ORDER', 'WORK_ORDER') and last_seq > 0 and seq_scope = ''")["n"] == 0   # 채번 안 함


@pytest.mark.fn("B-MIG-03")
def test_lots_and_genealogy_10_rows_via_lineage():
    first, second, c1, c2 = _run_twice("lots")
    _assert_idempotent(first, second, c1, c2)
    assert second.files[1].skipped == 10 and second.files[1].inserted == 0                   # 계보는 불변 — 두 번째는 전부 건너뜀
    ids = [r["id"] for r in conn.q("select id from lot where lot_no = any(%s)", (LOT_NOS,))]
    assert len(ids) == 9
    rows = conn.q("select relation_base, count(*)::int as n from lot_genealogy where parent_lot_id = any(%s) and child_lot_id = any(%s) group by 1", (ids, ids))
    assert {r["relation_base"]: r["n"] for r in rows} == {"투입": 3, "합병": 2, "분할": 3, "출하": 2}   # G-C06 10행
    assert conn.q1("select linked_by from lot_genealogy where parent_lot_id = any(%s) limit 1", (ids,))["linked_by"] == "migrate"
    x = conn.q1("select shipment_id, kind_base from lot where lot_no = 'X-EX-0001'")
    assert x["kind_base"] == "SHIPMENT" and x["shipment_id"] is not None                     # 34 의 헤더로 (D-301)
    assert conn.q1("select state from v_lot_state where lot_no = 'P-EX-0006'")["state"] == "재고"


@pytest.mark.fn("B-MIG-04")
def test_history_results_measures_inspections_shipments():
    first, second, c1, c2 = _run_twice("history")
    _assert_idempotent(first, second, c1, c2)
    r = conn.q1("""select r.good_qty, r.defect_qty, l.lot_no from pop_work_result r join lot l on l.id = r.product_lot_id
                    join job_work_order w on w.id = r.work_order_id where w.work_order_no = 'W-EX-0001' order by r.started_at""")
    assert r["good_qty"] == 50 and r["defect_qty"] == 2 and r["lot_no"] == "P-EX-0001"
    m = conn.q("select param_key, value_num, deviated from pop_measure m join pop_work_result r on r.id = m.work_result_id join job_work_order w on w.id = r.work_order_id where w.work_order_no = 'W-EX-0001' order by m.measured_at, m.param_key")
    assert [(x["param_key"], float(x["value_num"]), x["deviated"]) for x in m] == [("temp_c", 22.5, False), ("weight_kg", 101.2, False), ("temp_c", 31.0, True)]
    assert conn.q1("select insp_status from lot where lot_no = 'P-EX-0004'")["insp_status"] == "합격"   # 최신 검사 → lot.insp_status
    assert conn.q1("select count(*)::int as n from qua_insp_item i join qua_inspection n on n.id = i.inspection_id join lot l on l.id = n.lot_id where l.lot_no = 'P-EX-0004'")["n"] == 2
    s = conn.q1("select status, approved_by from shp_shipment where shipment_no = 'S-EX-0001'")
    assert s["status"] == "승인" and s["approved_by"] == "admin"


def test_error_rows_reported_exit_code_1_and_dry_run_writes_nothing(tmp_path: Path):
    d = tmp_path / "bad"
    d.mkdir()
    shutil.copy(EXAMPLES / "01_items.csv", d / "01_items.csv")
    (d / "02_partners.csv").write_text("partner_code,partner_name,partner_type\nBAD-EX-01,거래처 (예시),모르는구분\nBAD-EX-02,,고객\nBAD-EX-03,중복 (예시),고객\nBAD-EX-03,중복 (예시),고객\n", encoding="utf-8")
    (d / "05_equipment.csv").write_text("equip_code,equip_name,process_code\nBAD-EQ-01,설비 (예시),PRC-NOPE\n", encoding="utf-8")
    before = conn.table_counts()
    dry = migrate.run("basics", d, dry_run=True, run_by="test")
    assert dry.exit_code == 1 and dry.dry_run
    after = conn.table_counts()
    assert {k: v for k, v in before.items() if k != "sys_migration_log"} == {k: v for k, v in after.items() if k != "sys_migration_log"}   # dry-run 은 쓰지 않는다
    assert after["sys_migration_log"] == before["sys_migration_log"] + 3                     # 있는 파일 3 → 로그 3 (dry_run=true)
    rep = {f.file: f for f in dry.files}
    assert rep["02_partners.csv"].error_count == 3 and rep["02_partners.csv"].inserted == 1  # 구분 · 필수 · 중복 — 좋은 줄 1은 "적재될" 것으로 센다(되돌림)
    assert [e.line for e in rep["02_partners.csv"].errors] == [2, 3, 5]
    assert rep["05_equipment.csv"].error_count == 1 and "PRC-NOPE" in rep["05_equipment.csv"].errors[0].reason
    assert not rep["03_processes.csv"].present
    log = conn.q1("select errors, error_detail, dry_run from sys_migration_log where command = 'basics' and file = '02_partners.csv' order by id desc")
    assert log["dry_run"] and log["errors"] == 3 and log["error_detail"][0]["line"] == 2
    real = migrate.run("basics", d, run_by="test")
    assert real.exit_code == 1 and conn.q1("select 1 from bas_partner where partner_code = 'BAD-EX-03'")   # 좋은 줄은 적재, 나쁜 줄만 오류
    assert conn.q1("select 1 from bas_partner where partner_code = 'BAD-EX-01'") is None
    conn.x("delete from bas_partner where partner_code like 'BAD-EX-%%'")
    with pytest.raises(ValueError):
        migrate.run("nope", d)
    with pytest.raises(FileNotFoundError):
        migrate.run("basics", d / "missing")
    assert migrate.main(["basics", "--dir", str(d), "--dry-run"]) == 1
