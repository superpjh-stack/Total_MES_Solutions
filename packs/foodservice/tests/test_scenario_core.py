"""S1 핵심 — 수주(식수) → 조리 지시 → 소요량 자동(144.000 / 42.000 / 부족 24.000) → 배치 실적 ×2 (RPM · 온도 collect) → 검식 → 출고 → 역추적 (gates.yaml S1 · scenarios.md §1).

코어 API 만 부른다. 기대값은 전부 TD3 목업 또는 시나리오 입력값 검산 (gates.yaml 의 expect 그대로).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from mescore.db import conn

from _helpers import (HTML, MENU, ONION, P, PORK, approve, clear_recent_collect, client, end_batch, final_inspection, free_plan_date, hook_rejected, item_id, new_order,
                      new_shipment, new_work_order, ok, pass_incoming, receive, scan_input, scan_ship, send_collect, start_batch, token, zero_stock)


def _req(period: date, code: str) -> dict | None:
    return conn.q1("select required_qty, stock_qty, shortage_qty, unit from mat_requirement where period_from = %s and period_to = %s and item_id = %s and source = 'hook'",
                   (period, period, item_id(code)))


@pytest.mark.fn("F-JOB-01")
def test_order_to_ship():
    admin, worker, nutri, shipping = client("admin"), client("worker", "pop"), client("nutritionist"), client("shipping")
    plan_date = free_plan_date()
    today = date.today()

    # 1-3 입고 — 돈육 120.000 kg (유통기한 D+4) · 양파 80.000 kg (D+10) → 원료 LOT 2 · 입고검사 합격 2. 현재고는 입고량만 (목업 '가용 120.000 · 80.000')
    zero_stock(admin, PORK)
    zero_stock(admin, ONION)
    pork = ok(receive(admin, PORK, 120.0, today + timedelta(days=4)), "돈육 입고")
    onion = ok(receive(admin, ONION, 80.0, today + timedelta(days=10), storage_loc="실온보관실"), "양파 입고")
    assert re.fullmatch(r"L[0-9]{6}[0-9]{2,}", pork["lot_no"]), pork["lot_no"]                     # D-510 원료 LOT L{YYMMDD}{NN}
    assert conn.q1("select expiry_date from x_foodservice_lot_ext where id = %s", (pork["lot_id"],))["expiry_date"] == today + timedelta(days=4)
    # 1-3b 유통기한관리 자재를 유통기한 없이 → 422 hook_rejected
    r = receive(admin, PORK, 10.0, None)
    assert hook_rejected(r) and "유통기한" in r.json()["message"], r.text
    pass_incoming(worker, pork["lot_no"], 120.4)
    pass_incoming(worker, onion["lot_no"])

    # 1-4 수주 — CUS-001 · 납기 D · 11:30 · 위탁급식 · 제육볶음 1,200 인분
    order = new_order(admin, 1200, due=plan_date)
    assert re.fullmatch(r"SO-[0-9]{6}-[0-9]{2,}", order["order_no"]), order["order_no"]
    oe = conn.q1("select due_time, service_type from x_foodservice_order_ext where id = %s", (order["id"],))
    order_attrs = conn.q1("select attrs from ord_order where id = %s", (order["id"],))["attrs"]
    assert order_attrs == {"due_time": "11:30", "service_type": "위탁급식"}, order_attrs     # 코어 read_attrs(Request) 수정(733074f) 뒤 — 우회 없음
    assert str(oe["due_time"]) == "11:30:00" and oe["service_type"] == "위탁급식"           # after_save_ord_order 훅이 ext 로 복사

    # 1-5 조리 지시 — 메뉴 · PRC-060 · 1200 인분 → 훅 on_work_order_created
    before = conn.q1("select count(*) as n from mat_requirement where source = 'hook'")["n"]
    wo = ok(new_work_order(admin, qty=1200, plan_date=plan_date, order_dtl_id=order["dtl_id"]), "조리 지시")
    assert re.fullmatch(r"WO-[0-9]{6}-[0-9]{4,}", wo["work_order_no"]), wo["work_order_no"]       # D-510 WO-YYMMDD-0001 (4자리)
    row = conn.q1("select * from job_work_order where id = %s", (wo["id"],))
    assert row["unit"] == "인분" and row["bom_id"] == conn.q1("select id from bas_bom where item_id = %s and use_yn = 'Y'", (item_id(MENU),))["id"]
    assert row["attrs"]["recipe"]["batch_serve_qty"] == 100.0 and row["attrs"]["recipe"]["version"] == "V1.0"
    assert conn.q1("select count(*) as n from mat_requirement where source = 'hook'")["n"] == before + 2         # 돈육 · 양파 2행
    pork_req, onion_req = _req(plan_date, PORK), _req(plan_date, ONION)
    assert pork_req["required_qty"] == Decimal("144.000") and pork_req["stock_qty"] == Decimal("120.000") and pork_req["shortage_qty"] == Decimal("24.000"), pork_req
    assert onion_req["required_qty"] == Decimal("42.000") and onion_req["stock_qty"] == Decimal("80.000") and onion_req["shortage_qty"] == Decimal("0.000"), onion_req
    lots = conn.q("select jl.*, e.expiry_date from job_lot jl left join x_foodservice_lot_ext e on e.id = jl.lot_id where jl.work_order_id = %s order by jl.id", (wo["id"],))
    assert len(lots) == 2 and {l["required_qty"] for l in lots} == {Decimal("144.000"), Decimal("42.000")}
    pork_line = next(l for l in lots if l["item_id"] == item_id(PORK))
    earliest = conn.q1("""select l.id from lot l join v_lot_stock s on s.lot_id = l.id join x_foodservice_lot_ext e on e.id = l.id
                           where l.kind_base = 'MATERIAL' and l.item_id = %s and l.insp_status in ('합격','조건부') and s.remain_qty > 0
                           order by e.expiry_date, l.made_at, l.id limit 1""", (item_id(PORK),))["id"]
    assert pork_line["lot_id"] == earliest                                                           # FIFO — 유통기한 가장 이른 돈육 LOT
    # 1-5b 소요량 화면 — source=hook 행 · 1-5c 조리 지시서 — 덮어쓴 양식(레시피 · 배치 기준인분 · 추천 LOT)
    req_screen = ok(admin.get(P["MAT-05"], params={"frm": plan_date.isoformat(), "to": plan_date.isoformat()}), "소요량")
    assert any(r["source"] == "hook" and r["item_code"] == PORK and float(r["shortage_qty"]) == 24.0 for r in req_screen["rows"])
    html = admin.get(P["JOB-03"], params={"id": wo["id"]}, headers=HTML)
    assert html.status_code == 200 and "배치(솥) 기준인분" in html.text and "100.00" in html.text and "12.000" in html.text and "0.1200" in html.text
    assert "작업지시" not in re.sub(r"<[^>]*>", " ", html.text) and "조리 지시" in html.text          # G-P05 — 출력물도 치환

    # 1-6 배치 ①: 조리 시작 → 수집 4점 → 원료 투입 2 → 조리 완료 (양품 100 · 불량 2)
    clear_recent_collect()
    s1 = start_batch(worker, wo["id"])
    sent = send_collect(worker, s1["started_at"])
    assert all(not x["duplicate"] and x["saved"] == 3 for x in sent)
    dup = ok(worker.post("/ifc/collect", json={"equip_code": "EQ-STIR-01", "ts": s1["started_at"].isoformat(), "source": "gateway",
                                                 "tags": {"RPM": 75.0, "STIR_TIME": 0, "TEMP": 150.0}}, headers=token()), "재전송")
    assert dup["duplicate"] is True
    ok(scan_input(worker, s1["id"], pork["lot_no"], 12.0), "돈육 투입")
    ok(scan_input(worker, s1["id"], onion["lot_no"], 3.5), "양파 투입")
    e1 = end_batch(worker, s1["id"], 100, 2)
    assert re.fullmatch(r"P[0-9]{6}-[0-9]{4,}", e1["lot_no"]), e1["lot_no"]                          # D-510 배치 LOT P{YYMMDD}-{NNNN}
    m = {k: v["value_num"] for k, v in e1["measures"].items()}
    assert m == {"RPM": 73.5, "STIR_TIME": 30, "TEMP": 161.25} and all(v["source"] == "collect" and not v["deviated"] for v in e1["measures"].values()), e1["measures"]
    lot1 = conn.q1("select l.kind, l.kind_base, l.qty, l.unit, e.batch_no, e.batch_seq, e.input_type from lot l join x_foodservice_lot_ext e on e.id = l.id where l.id = %s", (e1["lot_id"],))
    assert lot1["kind"] == "BATCH" and lot1["kind_base"] == "PRODUCT" and lot1["batch_no"] == "B-01" and lot1["qty"] == 100 and lot1["input_type"] == "자동(PLC)"
    assert conn.q1("select count(*) as n from pop_measure where work_result_id = %s and source = 'collect'", (s1["id"],))["n"] == 3

    # 1-6f 배치 ②: 수집 없이 (양품 100 · 불량 0) → 측정값 미수집 · B-02
    s2 = start_batch(worker, wo["id"], backdate_min=0)                                                # 구간이 배치 ① 수집 구간과 겹치지 않게 — 수집 0건
    ok(scan_input(worker, s2["id"], pork["lot_no"], 12.0), "돈육 투입 2")
    ok(scan_input(worker, s2["id"], onion["lot_no"], 3.5), "양파 투입 2")
    e2 = end_batch(worker, s2["id"], 100, 0)
    assert all(v["value_num"] is None for v in e2["measures"].values()), e2["measures"]             # 미수집 — 0 으로 뭉개지 않는다
    assert conn.q1("select batch_no from x_foodservice_lot_ext where id = %s", (e2["lot_id"],))["batch_no"] == "B-02"
    assert conn.q1("select count(*) as n from pop_work_result where work_order_id = %s and ended_at is not null", (wo["id"],))["n"] == 2
    assert conn.q1("select count(*) as n from lot where work_order_id = %s and kind = 'BATCH'", (wo["id"],))["n"] == 2
    assert conn.q1("select count(*) as n from lot_genealogy where child_lot_id in (%s, %s) and relation = '투입'", (e1["lot_id"], e2["lot_id"]))["n"] == 4

    # 1-7 검식 — 배치 ① 최종 · 측정온도 78.5 · 관능 86 · 이물 N → 합격 (영양사). 배치 ② 는 샘플링(같은 지시 합격 1건이면 통과 — 가설 R1')
    insp = final_inspection(nutri, e1["lot_no"], "합격")
    assert insp["judgement"] == "합격" and conn.q1("select insp_status from lot where id = %s", (e1["lot_id"],))["insp_status"] == "합격"
    assert conn.q1("select count(*) as n from qua_inspection where lot_id = %s and insp_type = '최종' and judgement = '합격'", (e1["lot_id"],))["n"] == 1
    assert conn.q1("select count(*) as n from qua_issue where lot_id = %s", (e1["lot_id"],))["n"] == 0
    # 배치 ② 는 코어 F-SHP-05 가 미검사 LOT 스캔을 막는다 → 검식 합격 ②도 등록한다 (시나리오 1-8b "배치 LOT 1 스캔 → 2 스캔")
    final_inspection(nutri, e2["lot_no"], "합격")

    # 1-8 출고 — 출고 담당 등록 · 스캔 2 · 관리자 승인 (scope 승인) → 출고 LOT 1 · 계보 총 6행
    sh = new_shipment(shipping, order["order_no"])
    assert re.fullmatch(r"SH-[0-9]{6}-[0-9]{2,}", sh["shipment_no"]), sh["shipment_no"]
    ok(scan_ship(shipping, sh["shipment_no"], e1["lot_no"]), "스캔 1")
    ok(scan_ship(shipping, sh["shipment_no"], e2["lot_no"]), "스캔 2")
    assert approve(shipping, sh["id"]).status_code == 403                                             # 출고 담당은 승인 scope 없음
    ap = ok(approve(admin, sh["id"]), "승인")
    assert ap["status"] == "승인" and ap["lot_count"] == 2
    x = conn.q1("select id, lot_no from lot where shipment_id = %s and kind_base = 'SHIPMENT'", (sh["id"],))
    ids = [pork["lot_id"], onion["lot_id"], e1["lot_id"], e2["lot_id"], x["id"]]
    rows = conn.q("select relation from lot_genealogy where parent_lot_id = any(%(i)s) or child_lot_id = any(%(i)s)", {"i": ids})
    assert len(rows) == 6 and sum(r["relation"] == "투입" for r in rows) == 4 and sum(r["relation"] == "출하" for r in rows) == 2

    # 1-9 역추적 — 출고 LOT → 배치 B-01 · B-02 → 돈육 · 양파 (원재료 2)
    tr = ok(admin.get(P["TRC-02"], params={"no": x["lot_no"]}), "역추적")
    assert {m["no"] for m in tr["materials"]} == {pork["lot_no"], onion["lot_no"]}
    assert tr["edge_count"] == 6

    # 1-10 KPI — kpi_extra: 시간당 생산량 값 있음 · 불량률 = 2 ÷ 202 × 100 = 0.990 (이 시나리오 입력값) · 레시피 표준화율 분모 (미확정 D-10)
    from mescore.app import stats
    from packs.foodservice import hooks
    extra = {m["key"]: m for m in hooks.kpi_extra(today, today)}                                     # 훅 원본 (note · target · base 포함)
    assert {m["key"]: m["value"] for m in stats.kpi_extra(today, today)} == {k: m["value"] for k, m in extra.items()}   # stats 가 그대로 병합
    assert extra["hourly_output"]["target"] == 350.0 and extra["hourly_output"]["base"] == 300.0 and extra["defect_rate"]["target"] == 6.5
    assert extra["hourly_output"]["value"] is not None and extra["hourly_output"]["value"] > 0
    own = round(Decimal(2) / Decimal(202) * 100, 3)
    assert own == Decimal("0.990")
    period = conn.q1("select sum(coalesce(defect_qty, 0)) as d, sum(coalesce(good_qty, 0) + coalesce(defect_qty, 0)) as t from pop_work_result where ended_at::date = %s", (today,))   # 불량 NULL = 0
    assert extra["defect_rate"]["value"] == round(float(period["d"]) / float(period["t"]) * 100, 3)      # 같은 날 다른 실적이 있으면 그 합 (QA 대조 SQL)
    if period["t"] == 202:
        assert extra["defect_rate"]["value"] == 0.990
    assert "D-10" in extra["recipe_std_rate"]["note"] and extra["recipe_std_rate"]["value"] is not None
    assert extra["insp_pass_rate"]["value"] is not None and 0 < extra["insp_pass_rate"]["value"] <= 100
    board = ok(admin.get(P["KPI-01"]), "현황판")
    assert board
    ind = ok(admin.get(P["KPI-03"], params={"frm": today.isoformat(), "to": today.isoformat()}), "지표")
    keys = {r["indicator_key"]: r for r in ind["rows"]}
    assert keys["defect_rate"]["value"] == extra["defect_rate"]["value"] and keys["defect_rate"]["target_value"] == 6.5
