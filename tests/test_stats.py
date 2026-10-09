"""stats — 집계 값을 시드(migrate/examples)로 **손으로 계산한 기대값**과 대조 (G-C10 — QA2 가 자기 SQL 로 다시 센다). 쓰기는 snapshot 뿐(되돌린다). 개발3.

고정 데이터 (migrate/examples · 2026-10-01 ~ 02)
  W-EX-0001: plan_qty 100 · plan_date 2026-10-01 · 실적 2건(종료 10-01 12:00 / 17:00) good 50+50 · defect 2+1
  측정값 temp_c(범위 10~30): 22.5 · 31.0(이탈) · weight_kg 101.2
  검사: P-EX-0004 최종 합격(10-02 10:00) · P-EX-0005 최종 합격(10-02 10:05)
  수주 O-EX-0001 납기 10-05 · 출하 S-EX-0001 승인 ship_date 10-02 → 준수
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from mescore.app import packs, stats
from mescore.db import conn

from _dev3_helpers import load_examples

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)


@pytest.fixture(scope="module", autouse=True)
def _examples():
    load_examples()


def test_rate_and_period():
    assert stats.rate(1, 4) == 25.0 and stats.rate(0, 0) is None and stats.rate(3, None) is None
    assert stats.period("2026-10-01", "2026-10-02") == (D1, D2)
    assert stats.period(None, None, today=D2) == (D1, D2)
    with pytest.raises(ValueError):
        stats.period("2026-10-09", "2026-10-01")
    with pytest.raises(ValueError):
        stats.parse_date("2026-13-01")


def test_production_by_item_hand_computed():
    rows = stats.production(D1, D2, by="item")
    r = next(x for x in rows if x["code"] == "PRD-EX-91")
    assert r["wo_count"] == 1 and r["plan_qty"] == Decimal("100.000") and r["result_count"] == 2
    assert r["good_qty"] == Decimal("100.000") and r["defect_qty"] == Decimal("3.000")
    assert r["good_rate"] == pytest.approx(100 / 103 * 100) and r["achieve_rate"] == pytest.approx(100.0)
    by_day = {x["day"]: x for x in stats.production(D1, D2, by="day")}
    assert by_day[D1]["result_count"] == 2 and by_day[D1]["plan_qty"] == Decimal("100.000")
    tot = stats.totals("production", rows)
    assert tot["good_qty"] >= Decimal("100") and tot["achieve_rate"] is not None
    for by in ("process", "equipment"):
        assert any(x["result_count"] for x in stats.production(D1, D2, by=by))
    with pytest.raises(ValueError):
        stats.production(D1, D2, by="x")


def test_quality_pass_rate_conditional_not_passed():
    rows = stats.quality(D2, D2, by="day")
    r = next(x for x in rows if x["day"] == D2)
    assert r["inspection_count"] >= 2 and r["pass_count"] >= 2 and r["pass_rate"] == pytest.approx(r["pass_count"] / r["inspection_count"] * 100)
    item = next(x for x in stats.quality(D2, D2, by="item") if x["code"] == "PRD-EX-91")
    assert item["pass_count"] >= 2
    assert isinstance(stats.quality(D1, D2, by="defect"), list)
    assert stats.totals("quality", []) is None


def test_delivery_on_time_from_first_approved_shipment():
    rows = stats.delivery(D1, date(2026, 10, 5), by="day", today=date(2026, 10, 9))
    r = next(x for x in rows if x["day"] == date(2026, 10, 5))
    assert r["due_count"] >= 1 and r["on_time"] >= 1 and r["shipped_count"] >= 1 and r["on_time_rate"] == pytest.approx(r["on_time"] / (r["on_time"] + r["late"]) * 100)
    partner = next(x for x in stats.delivery(D1, date(2026, 10, 5), by="partner") if x["code"] == "CUST-EX-91")
    assert partner["on_time"] >= 1
    late = stats.late_orders(today=date(2026, 10, 30), limit=10000)
    assert any(o["order_no"] == "O-EX-0002" for o in late) and all("item_name" in o for o in late)   # 미출하 · 납기 지남


def test_equipment_none_without_logs_and_clipped_seconds():
    rows = stats.equipment(D1, D2)
    eq = next(x for x in rows if x["code"] == "EQ-EX-91")
    assert eq["logged_seconds"] >= 0 and (eq["run_rate"] is None or 0 <= eq["run_rate"] <= 100)
    # 가동 구간을 넣고 같은 트랜잭션 밖에서 잴 수 없으므로 커밋 → 측정 → 삭제
    eid = eq["equipment_id"]
    gid = conn.q1("""insert into eqp_run_log (equipment_id, state, started_at, ended_at, created_by) values (%s, '가동', '2026-09-30 22:00:00+09', '2026-10-01 02:00:00+09', 'test') returning id""", (eid,))["id"]
    try:
        eq2 = next(x for x in stats.equipment(D1, D1) if x["equipment_id"] == eid)
        assert eq2["run_seconds"] == pytest.approx(2 * 3600, abs=1)                          # 기간 밖(09-30) 2시간은 잘린다
        assert eq2["run_rate"] == pytest.approx(100.0)
    finally:
        conn.x("delete from eqp_run_log where id = %s", (gid,))


def test_equipment_totals_mttr_is_weighted_over_all_fixed_faults():
    """DEF-QA2-005 — 합계 줄 MTTR = 복구된 고장 전체 평균(Σ 복구 시간 / Σ 복구 건수). 설비별 MTTR 의 평균이 아니다."""
    base = {"run_seconds": 0.0, "logged_seconds": 0.0, "stop_count": 0}
    rows = [{**base, "fault_count": 1, "fixed_count": 1, "mttr_hours": 0.5},          # 설비 A: 0.5h 1건
            {**base, "fault_count": 3, "fixed_count": 2, "mttr_hours": 1 / 3},        # 설비 B: 0.25h · 0.4167h 2건 (미복구 1)
            {**base, "fault_count": 0, "fixed_count": 0, "mttr_hours": None}]
    tot = stats.totals("equipment", rows)
    assert tot["fixed_count"] == 3 and tot["fault_count"] == 4
    assert tot["mttr_hours"] == pytest.approx((0.5 + 2 / 3) / 3)                      # 0.3889 — 평균의 평균(0.4167)이 아니다
    assert stats.totals("equipment", [{**base, "fault_count": 1, "fixed_count": 0, "mttr_hours": None}])["mttr_hours"] is None
    assert all("fixed_count" in r for r in stats.equipment(D1, D2))


def test_measure_series_avg_last_and_deviation():
    rows = stats.measure_series("temp_c", D1, D2, by="day", agg="avg")
    r = next(x for x in rows if x["day"] == D1)
    assert r["value"] == pytest.approx((22.5 + 31.0) / 2) and r["n"] == 2 and r["deviated_count"] == 1 and r["max_value"] == 31.0
    last = next(x for x in stats.measure_series("temp_c", D1, D2, by="day", agg="last") if x["day"] == D1)
    assert last["value"] == 31.0
    wo = next(x for x in stats.measure_series("temp_c", D1, D2, by="work_order") if x["code"] == "W-EX-0001")
    assert wo["n"] == 2
    assert stats.measure_series("nope_key", D1, D2) == []
    assert any(k["param_key"] == "temp_c" for k in stats.measure_keys())
    with pytest.raises(ValueError):
        stats.measure_series("temp_c", D1, D2, agg="median")


def test_core_metrics_and_indicators_status():
    m = stats.core_metrics(D1, D2)
    assert set(m) == set(stats.CORE_METRIC_KEYS) and m["production.good_rate"] == pytest.approx(100 / 103 * 100)
    inds = stats.indicators(D1, D2)
    byk = {i["indicator_key"]: i for i in inds}
    assert byk["production.good_rate"]["value"] == pytest.approx(100 / 103 * 100) and byk["production.good_rate"]["status"] is None   # 목표 NULL
    assert stats.kpi_extra(D1, D2) == []                                                       # 코어 단독: 훅 없음
    assert stats.status_of(None, 90) is None and stats.status_of(50, None) is None


def test_kpi_extra_hook_merged(monkeypatch):
    monkeypatch.setattr(packs, "hook", lambda name: (lambda frm, to: [{"key": "x1", "label": "팩 지표", "value": 7, "unit": "건"}]) if name == "kpi_extra" else packs.NOOP_HOOK)
    assert stats.kpi_extra(D1, D2) == [{"key": "x1", "label": "팩 지표", "value": 7.0, "unit": "건"}]
    vals = stats._metric_values(D1, D2)
    assert vals["pack:x1"] == 7.0
    monkeypatch.setattr(packs, "hook", lambda name: (lambda frm, to: ["bad"]) if name == "kpi_extra" else packs.NOOP_HOOK)
    with pytest.raises(ValueError):
        stats.kpi_extra(D1, D2)


def test_board_keys_and_dashboard():
    b = stats.board(D2)
    assert b["today"] == "2026-10-02" and b["source"] == "실시간" and b["undecided"] == "미확정 (D-602)"   # G-C11 (DEF-QA2-003)
    assert b["quality"]["inspection_count"] >= 2 and b["production"]["good_qty"] is None or b["production"]["good_qty"] >= 0
    assert isinstance(b["work_orders"], list) and b["work_orders_count"] == len(b["work_orders"])
    d = stats.dashboard(D2)
    assert set(d["today"]) == {"date", "work_orders", "results", "inspections_pending", "shipments_pending"}
    assert {"deviated", "faults", "late_orders", "approvals_pending", "issues_open", "labels_today"} <= set(d["extra"])
    assert isinstance(d["recent"], list) and len(d["recent"]) <= 5
    assert all({"logged_at", "login_id", "fn_id", "screen_id", "target", "name"} <= set(r) for r in d["recent"])
    ats = [r["logged_at"] for r in d["recent"]]
    assert ats == sorted(ats, reverse=True)                                                             # 최신 순


def test_today_counts_modules_and_hand_count():
    tc = stats.today_counts(D2)
    assert set(tc) == set(stats.TODAY_COUNT_SOURCES) and len(tc) == 12 and all(isinstance(v, int) for v in tc.values())
    assert tc["mat"] == conn.q1("select count(*)::int as n from mat_receipt where receipt_date = %s", (D2,))["n"]     # 손계산 — 10-02 입고
    assert tc["ord"] == conn.q1("select count(*)::int as n from ord_order where due_date = %s and status <> '취소'", (D2,))["n"]
    assert stats.today_counts()["sys"] >= 0                                                             # 기본 = 오늘


def test_shipment_due_days_per_row():
    row = conn.q1("""select s.id, s.ship_date, o.due_date from shp_shipment s join ord_order o on o.id = s.order_id
                      where o.due_date is not null order by s.id desc limit 1""")
    assert stats.shipment_due([]) == {}
    if row is not None:
        d = stats.shipment_due([row["id"]])[row["id"]]
        assert d["due_days"] == (row["ship_date"] - row["due_date"]).days
        assert d["due_state"] == ("지연" if d["due_days"] > 0 else "당일" if d["due_days"] == 0 else "앞섬")


def test_snapshot_writes_then_board_reads_it():
    class _Rollback(Exception):
        pass
    try:
        with conn.tx() as cur:
            n = stats.snapshot(cur, D2)
            assert n == len(stats.CORE_METRIC_KEYS)
            cur.execute("select indicator_key, value from kpi_snapshot where snap_date = %s", (D2,))
            rows = {r["indicator_key"]: r["value"] for r in cur.fetchall()}
            assert set(rows) == set(stats.CORE_METRIC_KEYS) and rows["quality.pass_rate"] is not None       # 10-02 판정 2건 → 값 있음
            assert rows["production.good_rate"] is None                                                    # 10-02 종료 실적 없음 → NULL (지어내지 않는다)
            raise _Rollback
    except _Rollback:
        pass
    assert conn.q1("select count(*)::int as n from kpi_snapshot where snap_date = %s", (D2,))["n"] == 0
