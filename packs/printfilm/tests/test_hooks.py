"""hooks.md 의 훅 6 — on_result_closed(ROLL retag · 인쇄 공정만) · validate_job_work_order(수주 필수 · 코드 검증) · after_save ext · kpi_extra (개발2)."""

from __future__ import annotations

from datetime import date

import pytest

from mescore.app import packs, stats
from mescore.db import conn

from _helpers import P, client, inspect, new_job, receive, run_print, s1_upto_slitting, uniq


@pytest.mark.fn("F-X-RLL-06")
def test_result_closed_retags_roll():
    m = receive("EX-RM-01", 50)
    job = new_job()
    r = run_print(job, [(m["lot_no"], 20)], 300, delta_e=0.7)
    lot = conn.q1("select l.kind, l.kind_base, x.process_type, x.equipment_id from lot l join x_printfilm_lot_ext x on x.id = l.id where l.id = %s", (r["lot_id"],))
    assert lot == {"kind": "ROLL", "kind_base": "PRODUCT", "process_type": "인쇄", "equipment_id": conn.q1("select id from bas_equipment where equip_code = 'EX-EQ-01'")["id"]}
    assert conn.q1("select count(*) as n from lot_genealogy where child_lot_id = %s and relation = '투입'", (r["lot_id"],))["n"] == \
        conn.q1("select count(*) as n from pop_input where work_result_id = %s and canceled_yn = 'N'", (r["result_id"],))["n"] == 1
    assert r["measures"]["delta_e"]["value_num"] == 0.7
    # 응답 문구에 '생산 LOT' 대신 'Roll' (terms)
    assert "Roll" in r["message"] and "생산 LOT" not in r["message"]


@pytest.mark.fn("F-X-RLL-06")
def test_result_closed_rejects_non_print_process():
    """후가공 공정(attrs.process_type=후가공)의 실적 종료 → 422 hook_rejected — 롤은 X-RLL 화면에서 만든다 (D-13)."""
    m = receive("EX-RM-01", 10)
    job = new_job(process_code="EX-PR-20", equip_code="EX-EQ-02")
    c = client("field")
    s = c.post(f"{P['POP-02']}/start", data={"work_order_id": job["id"]}).json()
    assert c.post(P["POP-03"], data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": "1"}).status_code == 200
    e = c.post(f"{P['POP-02']}/{s['id']}/end", data={"good_qty": "1"})
    assert e.status_code == 422 and e.json()["code"] == "hook_rejected" and "인쇄 공정" in e.json()["message"], e.text
    assert conn.q1("select ended_at, product_lot_id from pop_work_result where id = %s", (s["id"],)) == {"ended_at": None, "product_lot_id": None}   # 전체 되돌림


@pytest.mark.fn("F-X-PRT-04")
def test_job_plate_code_unknown_422():
    body = new_job(plate="NOPE", expect=422)
    assert body["code"] == "hook_rejected" and "판사양" in body["message"] and body["fields"][0]["name"] == "attrs.plate_code"
    # 미사용 코드도 422
    admin = client("admin")
    pid = admin.post(P["X-PRT-01"], data={"plate_code": uniq("T-PL"), "plate_name": "임시 판 (예시)"}).json()["id"]
    code = conn.q1("select plate_code from x_printfilm_plate where id = %s", (pid,))["plate_code"]
    assert admin.post(f"{P['X-PRT-01']}/{pid}", data={"use_yn": "N"}).status_code == 200
    assert new_job(plate=code, expect=422)["message"].startswith("미사용")
    assert new_job(anilox="NOPE", expect=422)["fields"][0]["name"] == "attrs.anilox_code"
    assert new_job(ink="NOPE", expect=422)["fields"][0]["name"] == "attrs.ink_code"


@pytest.mark.fn("F-X-PRT-12")
def test_job_without_order_422_and_ext_rows():
    """D-506 수주 상세 없는 Job 422 · 제품 아닌 품목 422 · 등록 · 수정 모두 ext 행 (after_save_job_work_order)."""
    c = client("prod")
    r = c.post(P["JOB-01"], data={"item_id": conn.q1("select id from bas_item where item_code = 'EX-FG-01'")["id"], "process_id": conn.q1("select id from bas_process where process_code = 'EX-PR-10'")["id"],
                                   "plan_qty": "10"})
    assert r.status_code == 422 and r.json()["code"] == "hook_rejected" and "수주 상세" in r.json()["message"]
    assert new_job(item_code="EX-RM-01", expect=422)["message"].startswith("Job 의 품목은 제품만")
    job = new_job(plate="EX-PL-01", anilox=None, ink="EX-INK-02")
    ext = conn.q1("""select p.plate_code, e.anilox_id, k.ink_code from x_printfilm_job_work_order_ext e left join x_printfilm_plate p on p.id = e.plate_id
                      left join x_printfilm_ink_formula k on k.id = e.ink_formula_id where e.id = %s""", (job["id"],))
    assert ext == {"plate_code": "EX-PL-01", "anilox_id": None, "ink_code": "EX-INK-02"}
    assert c.post(f"{P['JOB-01']}/{job['id']}", data={"attr_anilox_code": "EX-AN-02"}).status_code == 200
    ext = conn.q1("select a.anilox_code, e.plate_id from x_printfilm_job_work_order_ext e join x_printfilm_anilox a on a.id = e.anilox_id where e.id = %s", (job["id"],))
    assert ext["anilox_code"] == "EX-AN-02" and ext["plate_id"] is not None
    # 셋 다 비우면 ext 없음
    job2 = new_job(plate=None, anilox=None, ink=None)
    assert conn.q1("select 1 from x_printfilm_job_work_order_ext where id = %s", (job2["id"],)) is None
    # 작업지시서 출력 — 팩 양식에 판사양 · 아니록스 · 잉크조성
    html = c.get(P["JOB-03"], params={"id": job["id"]}, headers={"accept": "text/html"}).text
    assert "EX-PL-01" in html and "EX-AN-02" in html and "EX-INK-02" in html and "판사양" in html


@pytest.mark.fn("F-X-CLR-05")
def test_kpi_extra_metrics():
    x = s1_upto_slitting()
    inspect(x["s1"]["lot_no"], "합격", delta_e=2.0)
    inspect(x["s2"]["lot_no"], "불합격", delta_e=4.0, defect="EX-DF-04")
    today = date.today()
    rows = {m["key"]: m for m in stats.kpi_extra(today, today)}
    assert set(rows) == {"avg_delta_e", "fail_roll_count", "stock_roll_count", "splice_count"}
    assert rows["avg_delta_e"]["value"] is not None and rows["fail_roll_count"]["value"] >= 1 and rows["stock_roll_count"]["value"] >= 1 and rows["splice_count"]["value"] >= 1
    assert rows["fail_roll_count"]["unit"] == "개"
    ind = {i["indicator_key"]: i for i in stats.indicators(today, today)}
    assert ind["splice_count"]["calc_kind"] == "pack:splice_count" and ind["splice_count"]["value"] >= 1
    assert packs.has_hook("kpi_extra") and packs.has_hook("validate_shipment") and packs.has_hook("on_result_closed")
    assert client("admin").get(P["KPI-03"]).status_code == 200
