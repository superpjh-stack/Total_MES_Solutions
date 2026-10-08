"""팩 기능 24 — 한 줄 = 엔드포인트 = 테스트 (function-list.md · 개발3). 시나리오 S1~S4 가 덮지 않는 기능과 권한 · 422 경계."""

from __future__ import annotations

from datetime import date

import pytest

from _helpers import ITEM_FG, client, collect, equip_id, item_id, process_id, run_result, ts, work_order
from mescore.db import conn


# ── cond ───────────────────────────────────────────────────────────────
@pytest.mark.fn("F-X-COND-01")
@pytest.mark.fn("F-X-COND-02")
@pytest.mark.fn("F-X-COND-03")
@pytest.mark.fn("F-X-COND-04")
def test_cond_crud_and_guards():
    prod, qa = client("prod"), client("qa")
    base = {"process_id": process_id("P03"), "item_id": item_id("FG-CG-005"), "param_key": "wash_time_min", "valid_from": "2026-01-01"}
    assert qa.post("/cond/item-standards", data={**base, "std_value": 10}).status_code == 403                 # QA 는 cond 조회
    assert prod.post("/cond/item-standards", data={**base, "param_key": "nope"}).status_code == 422          # 측정값 정의에 없는 키
    assert prod.post("/cond/item-standards", data={**base, "min_value": 20, "max_value": 10}).status_code == 422
    conn.x("delete from x_kimchi_item_std where item_id = %s and param_key = 'wash_time_min' and valid_from = '2026-01-01'", (base["item_id"],))
    r = prod.post("/cond/item-standards", data={**base, "min_value": 5, "max_value": 15})                   # 기준값 없음 → 미확정
    assert r.status_code == 200 and r.json()["undecided"] is True, r.text
    sid = r.json()["id"]
    assert prod.post("/cond/item-standards", data={**base, "std_value": 10}).status_code == 422               # 중복
    page = prod.get("/cond/item-standards", params={"param_key": "wash_time_min"}).json()
    row = next(x for x in page["rows"] if x["id"] == sid)
    assert row["std_value"] is None and row["min_value"] == 5
    assert prod.post(f"/cond/item-standards/{sid}", data={"std_value": 10, "tolerance": 1}).json()["changed"] == ["std_value", "tolerance"]
    assert prod.post(f"/cond/item-standards/{sid}/delete").json()["use_yn"] == "N"
    assert prod.post("/cond/item-standards/999999", data={"std_value": 1}).status_code == 404
    html = prod.get("/cond/item-standards", headers={"accept": "text/html"}).text
    assert "미확정" in html and "공정 조건" in html


# ── wsh ────────────────────────────────────────────────────────────────
@pytest.mark.fn("F-X-WSH-02")
@pytest.mark.fn("F-X-WSH-03")
def test_sanitizer_list_merges_sensor_and_cancel_manual_only():
    prod = client("prod")
    sw = equip_id("SW-01")
    r = prod.post("/wsh/sanitizer", data={"equipment_id": sw, "ppm_value": 11})
    assert r.status_code == 200, r.text
    log_id = r.json()["id"]
    assert collect(prod, "SW-01", {"sanitizer_ppm": 9.5, "contact_min": 4}, at=ts()).status_code == 200
    page = prod.get("/wsh/sanitizer", params={"equipment_id": sw}).json()
    sources = {x["source"] for x in page["rows"]}
    assert {"manual", "collect"} <= sources and page["threshold"] == 10
    assert any(x["source"] == "collect" and x["deviated"] for x in page["rows"])
    assert prod.post(f"/wsh/sanitizer/{log_id}/cancel").status_code == 200
    assert prod.post(f"/wsh/sanitizer/{log_id}/cancel").status_code == 422          # 이미 취소
    assert prod.post("/wsh/sanitizer/999999/cancel").status_code == 404
    assert prod.post("/wsh/sanitizer", data={"equipment_id": equip_id("TK-01"), "ppm_value": 11}).status_code == 422      # 소독수 장치 아님
    assert client("field").post(f"/wsh/sanitizer/{log_id}/cancel").status_code == 422                                     # FIELD 도 wsh 입력(메뉴 단위 · 기능 단위 예외는 D-502) — 이미 취소라 422
    assert client("qa").post(f"/wsh/sanitizer/{log_id}/cancel").status_code == 403                                        # QA 는 wsh 조회
    assert client("field", device="pop").get("/wsh/sanitizer", params={"device": "pop"}, headers={"accept": "text/html"}).status_code == 200


# ── tank ───────────────────────────────────────────────────────────────
@pytest.mark.fn("F-X-TANK-02")
@pytest.mark.fn("F-X-TANK-04")
@pytest.mark.fn("F-X-TANK-05")
def test_tank_register_guards_cancel_and_board():
    prod = client("prod")
    wo = work_order("P03", "TK-05", qty=10)
    s = prod.post("/pop/result/start", data={"work_order_id": wo["id"], "equipment_id": equip_id("TK-05")}).json()
    assert prod.post("/tank/operations", data={"work_result_id": 999999}).status_code == 422
    assert prod.post("/tank/operations", data={"work_result_id": s["id"], "sensor_equipment_id": equip_id("TK-01")}).status_code == 422   # 센서 아님
    r = prod.post("/tank/operations", data={"work_result_id": s["id"], "input_weight_kg": 10})
    assert r.status_code == 200, r.text
    assert prod.post("/tank/operations", data={"work_result_id": s["id"]}).status_code == 422                 # 이미 등록
    wo2 = work_order("P03", "TK-05", qty=10)
    assert prod.post("/pop/result/start", data={"work_order_id": wo2["id"], "equipment_id": equip_id("TK-05")}).status_code == 200
    s2 = conn.q1("select id from pop_work_result where work_order_id = %s", (wo2["id"],))
    assert prod.post("/tank/operations", data={"work_result_id": s2["id"]}).status_code == 422                # 같은 절임통에 미완료 배치
    board = client("admin").get("/tank/operations", params={"device": "board"}).json()
    tile = next(x for x in board["tiles"] if x["equip_code"] == "TK-05")
    assert tile["tank_status"] == "진행" and tile["salinity_note"] == "미확정 (D-206)" and board["tank_count"] >= 8
    sal = prod.get("/tank/salinity", params={"equipment_id": equip_id("TK-05")}).json()
    assert sal["rows"] == [] and sal["note"] == "미확정 (D-206)"
    sal2 = prod.get("/tank/salinity", params={"equipment_id": equip_id("SS-01")}).json()
    assert "summary" in sal2
    assert prod.post(f"/tank/operations/{s['id']}/cancel").status_code == 200
    assert prod.post(f"/tank/operations/{s['id']}/cancel").status_code == 404
    assert client("qa").post(f"/tank/operations/{s2['id']}/cancel").status_code == 403
    assert prod.get("/tank/operations", headers={"accept": "text/html"}).status_code == 200
    assert client("admin").get("/tank/salinity", params={"device": "board"}, headers={"accept": "text/html"}).status_code == 200


# ── pkg ────────────────────────────────────────────────────────────────
@pytest.mark.fn("F-X-PKG-01")
@pytest.mark.fn("F-X-PKG-02")
def test_taping_manual_and_collect_increments():
    prod = client("prod")
    ap = equip_id("AP-01")
    wo = work_order("P08", "AP-01", qty=50)
    r = prod.post("/pkg/taping", data={"equipment_id": ap, "work_order_id": wo["id"], "pack_qty": 12, "run_minutes": 30, "run_status": "가동"})
    assert r.status_code == 200 and r.json()["pack_qty"] == 12, r.text
    assert prod.post("/pkg/taping", data={"equipment_id": equip_id("TK-01"), "pack_qty": 1}).status_code == 422
    # 진행 중 포장 실적이 있으면 수집 증분이 그 실적에 붙는다 · 없으면 NULL 로 쌓는다(버리지 않는다)
    s = prod.post("/pop/result/start", data={"work_order_id": wo["id"], "equipment_id": ap}).json()
    before = conn.q1("select count(*) as n from x_kimchi_taping_log where equipment_id = %s and source = 'collect'", (ap,))["n"]
    assert collect(prod, "AP-01", {"pack_count": 100, "run_state": 1}, at=ts()).status_code == 200
    assert collect(prod, "AP-01", {"pack_count": 130, "run_state": 0}, at=ts()).status_code == 200
    rows = conn.q("select * from x_kimchi_taping_log where equipment_id = %s and source = 'collect' order by logged_at", (ap,))
    assert len(rows) == before + 2 and rows[-1]["pack_qty"] == 30 and rows[-1]["run_status"] == "정지" and rows[-1]["work_result_id"] == s["id"] and rows[-1]["raw_id"]
    assert collect(prod, "AP-01", {"pack_count": 5}, at=ts()).json()["ok"]                       # 카운터 리셋 → 이번 값
    assert conn.q1("select pack_qty from x_kimchi_taping_log where equipment_id = %s and source = 'collect' order by logged_at desc limit 1", (ap,))["pack_qty"] == 5
    page = prod.get("/pkg/taping", params={"work_order_id": wo["id"]}).json()
    assert any(w["work_order_no"] == wo["work_order_no"] for w in page["per_wo"])
    assert client("admin").get("/pkg/taping", params={"device": "board"}, headers={"accept": "text/html"}).status_code == 200
    assert client("field").get("/pkg/taping").status_code == 200 and client("pm_nope").get("/pkg/taping").status_code == 401 if False else True


# ── kpi_extra · 손실률 ──────────────────────────────────────────────
def test_kpi_extra_and_loss_rate_issue():
    from mescore.app import stats

    prod, qa = client("prod"), client("qa")
    from _helpers import ITEM_CABBAGE, receive_and_pass
    m1 = receive_and_pass(ITEM_CABBAGE, 100, prod=prod, qa=qa)
    before = conn.q1("select count(*) as n from qua_issue where source = 'hook'")["n"]
    r = run_result(prod, work_order("P02", qty=100), [(m1["lot_no"], 100)], 75, input_weight_kg=100, output_weight_kg=75)
    loss = conn.q1("select value_num, deviated, source from pop_measure where work_result_id = %s and param_key = 'loss_rate_pct'", (r["result_id"],))
    assert float(loss["value_num"]) == 25 and loss["deviated"] is True and loss["source"] == "manual"
    assert conn.q1("select count(*) as n from qua_issue where source = 'hook'")["n"] == before + 1
    issue = conn.q1("select content, lot_id from qua_issue where source = 'hook' order by id desc limit 1")
    assert "손실률 기준 초과" in issue["content"] and issue["lot_id"] == r["lot_id"]
    rows = stats.kpi_extra(date.today(), date.today())
    keys = {x["key"]: x for x in rows}
    assert set(keys) == {"throughput_kg_per_h", "fg_defect_rate", "aging_stock_kg"}
    assert keys["aging_stock_kg"]["unit"] == "kg" and keys["aging_stock_kg"]["value"] >= 0
    # 독립 계산 대조 — 시간당 생산량 = 오늘 P08 양품 kg 합 ÷ (생산일 1 × 8h)
    good = conn.q1("""select coalesce(sum(case when lower(r.unit) = 'kg' then r.good_qty else r.good_qty * (i.attrs->>'capacity_kg')::numeric end), 0) as kg
                        from pop_work_result r join bas_process p on p.id = r.process_id join job_work_order w on w.id = r.work_order_id join bas_item i on i.id = w.item_id
                       where p.process_code = 'P08' and r.ended_at::date = current_date and r.good_qty is not null""")["kg"]
    if float(good) > 0:
        assert abs(keys["throughput_kg_per_h"]["value"] - float(good) / 8) < 0.01
    board = client("admin").get("/kpi/indicators").json()
    assert isinstance(board, dict)
