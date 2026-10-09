"""kpi — F-KPI-01~08 (현황판 · 집계 4 · 지표 정의). 라우터 쓰기는 kpi_indicator 뿐. 개발3."""

from __future__ import annotations

from datetime import date

import pytest

from mescore.app import stats
from mescore.db import conn

from _dev3_helpers import HTML, client, load_examples, uniq

BOARD_KEYS = {"today", "source", "undecided", "production", "quality", "delivery", "equipment", "work_orders_count", "work_orders", "measure", "indicators"}


@pytest.fixture(scope="module", autouse=True)
def _examples():
    load_examples()


@pytest.mark.fn("F-KPI-01")
def test_board_json_keys_and_html_polling_skeleton():
    c = client("admin")
    r = c.get("/kpi/board", params={"device": "board"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert set(body) == BOARD_KEYS and body["today"] == date.today().isoformat() and body["source"] == "실시간"
    assert set(body["production"]) == {"plan_qty", "actual_qty", "good_qty", "defect_qty", "unit", "achieve_rate", "good_rate", "good_rate_target", "by_hour"}
    assert set(body["quality"]) == {"inspection_count", "pass_count", "fail_count", "pass_rate", "pass_rate_target", "top_defects"}
    assert set(body["delivery"]) == {"due_count", "shipped_count", "late_count", "pending_count", "on_time_rate", "late_orders"}
    assert set(body["equipment"]) == {"run", "stop", "check", "fault", "items"} and set(body["measure"]) == {"measured_count", "deviated_count"}
    assert all(set(i) == {"indicator_key", "name", "unit", "value", "target_value", "status"} for i in body["indicators"])
    h = c.get("/kpi/board", params={"device": "board"}, headers=HTML)
    assert h.status_code == 200 and 'data-key="production.actual_qty"' in h.text and "/kpi/board?device=board" in h.text and "data-list=" in h.text
    assert client("field").get("/kpi/board").status_code == 200                              # 현장: kpi 조회
    assert client("prod").get("/kpi/board", params={"device": "pop"}).status_code == 403     # 채널 밖


@pytest.mark.fn("F-KPI-02")
def test_summary_production_by_item_process_equipment():
    c = client("prod")
    for by in ("day", "item", "process", "equipment"):
        r = c.get("/kpi/summary", params={"kind": "production", "frm": "2026-10-01", "to": "2026-10-02", "by": by})
        assert r.status_code == 200 and r.json()["section"]["by"] == by, by
    body = c.get("/kpi/summary", params={"kind": "production", "frm": "2026-10-01", "to": "2026-10-02", "by": "item"}).json()
    row = next(x for x in body["section"]["rows"] if x["code"] == "PRD-EX-91")
    assert row["good_qty"] == 100 and row["defect_qty"] == 3 and row["result_count"] == 2
    assert c.get("/kpi/summary", params={"kind": "production", "by": "x"}).status_code == 422
    assert c.get("/kpi/summary", params={"kind": "nope"}).status_code == 422
    assert c.get("/kpi/summary", params={"frm": "2026-10-09", "to": "2026-10-01"}).status_code == 422


@pytest.mark.fn("F-KPI-03")
def test_summary_quality_defect_and_measure_series():
    c = client("qa")
    body = c.get("/kpi/summary", params={"kind": "quality", "frm": "2026-10-02", "to": "2026-10-02", "by": "day", "param_key": "temp_c"}).json()
    assert body["section"]["total"]["pass_count"] >= 2 and body["series"] is not None
    assert c.get("/kpi/summary", params={"kind": "quality", "by": "defect"}).status_code == 200
    assert c.get("/kpi/summary", params={"kind": "quality", "param_key": "temp_c", "agg": "x"}).status_code == 422
    m = client("qa", device="mobile").get("/kpi/summary", params={"kind": "quality", "frm": "2026-10-02", "to": "2026-10-02"}, headers=HTML)
    assert m.status_code == 200 and "m-card" in m.text


@pytest.mark.fn("F-KPI-04")
def test_summary_delivery_by_day_and_partner():
    c = client("admin")
    body = c.get("/kpi/summary", params={"kind": "delivery", "frm": "2026-10-01", "to": "2026-10-05", "by": "partner"}).json()
    row = next(x for x in body["section"]["rows"] if x["code"] == "CUST-EX-91")
    assert row["on_time"] >= 1 and {"due_count", "shipped_count", "late", "pending", "on_time_rate"} <= set(row)
    assert c.get("/kpi/summary", params={"kind": "delivery", "by": "day"}).status_code == 200


@pytest.mark.fn("F-KPI-05")
def test_summary_equipment_rows_and_none_rates():
    c = client("field")
    body = c.get("/kpi/summary", params={"kind": "equipment", "frm": "2026-10-01", "to": "2026-10-02"}).json()
    rows = body["section"]["rows"]
    assert any(r["code"] == "EQ-EX-91" for r in rows) and all({"run_rate", "stop_count", "fault_count", "mttr_hours", "current_state"} <= set(r) for r in rows)
    assert body["section"]["total"]["equipment_count"] == len(rows)


@pytest.mark.fn("F-KPI-06")
def test_indicator_create_admin_only_calc_kind_validated():
    admin = client("admin")
    key = uniq("IND").lower()
    r = admin.post("/kpi/indicators", data={"indicator_key": key, "name": "테스트 지표", "unit": "%", "target_value": "95", "calc_kind": "core:quality.pass_rate"})
    assert r.status_code == 200 and r.json()["indicator_key"] == key
    assert conn.q1("select target_value from kpi_indicator where indicator_key = %s", (key,))["target_value"] == 95
    assert admin.post("/kpi/indicators", data={"indicator_key": key, "name": "중복", "calc_kind": "core:quality.pass_rate"}).status_code == 422
    assert admin.post("/kpi/indicators", data={"indicator_key": uniq("I"), "name": "x", "calc_kind": "core:nope"}).status_code == 422
    assert admin.post("/kpi/indicators", data={"indicator_key": uniq("I"), "name": "x", "calc_kind": "pack:extra"}).status_code == 422   # 코어 단독: kpi_extra 없음
    assert admin.post("/kpi/indicators", data={"indicator_key": uniq("I"), "name": "x", "calc_kind": "core:quality.pass_rate", "target_value": "abc"}).status_code == 422
    assert client("prod").post("/kpi/indicators", data={"indicator_key": uniq("I"), "name": "x", "calc_kind": "core:quality.pass_rate"}).status_code == 403


@pytest.mark.fn("F-KPI-07")
def test_indicator_update_target_and_visibility():
    admin = client("admin")
    iid = admin.post("/kpi/indicators", data={"indicator_key": uniq("IND").lower(), "name": "n", "calc_kind": "core:production.good_rate"}).json()["id"]
    r = admin.post(f"/kpi/indicators/{iid}", data={"target_value": "90.5", "visible_yn": "N"})
    assert r.status_code == 200 and r.json()["visible_yn"] == "N"
    row = conn.q1("select target_value, visible_yn from kpi_indicator where id = %s", (iid,))
    assert float(row["target_value"]) == 90.5 and row["visible_yn"] == "N"
    assert admin.post(f"/kpi/indicators/{iid}", data={"clear_target": "1"}).status_code == 200
    assert conn.q1("select target_value from kpi_indicator where id = %s", (iid,))["target_value"] is None
    assert admin.post("/kpi/indicators/999999999", data={"target_value": "1"}).status_code == 404
    assert client("qa").post(f"/kpi/indicators/{iid}", data={"target_value": "1"}).status_code == 403


@pytest.mark.fn("F-KPI-08")
def test_indicator_list_shows_value_target_status():
    c = client("prod")
    r = c.get("/kpi/indicators", params={"frm": "2026-10-02", "to": "2026-10-02"})
    assert r.status_code == 200
    rows = {x["indicator_key"]: x for x in r.json()["rows"]}
    seed = rows["quality.pass_rate"]
    assert seed["calc_kind"] == "core:quality.pass_rate" and seed["known"] and seed["value"] is not None
    assert seed["target_value"] is None and seed["status"] is None                            # 목표 NULL → 미확정 (D-602)
    assert stats.status_of(96.0, 95.0) == "good" and stats.status_of(91.0, 95.0) == "warn" and stats.status_of(80.0, 95.0) == "critical"
    assert c.get("/kpi/indicators", params={"id": "x"}).status_code == 404


def test_dashboard_recent_five_and_html_block():
    """CMN-04 — recent[{at kind text href}] 최근 변경 5건 (접근 로그 change · 읽기만). 권한 없는 화면은 링크 없이 글자만."""
    admin = client("admin")
    body = admin.get("/dashboard").json()
    assert len(body["recent"]) <= 5 and all({"at", "kind", "text", "href"} <= set(r) for r in body["recent"])
    field = client("field").get("/dashboard").json()
    for r in field["recent"]:
        if r["href"]:
            assert not r["href"].startswith("/sys/")                                    # 현장은 sys 화면 권한 없음 → 링크 없음
    h = admin.get("/dashboard", headers=HTML)
    assert h.status_code == 200 and 'class="recent"' in h.text
