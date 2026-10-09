"""job 작업지시 (F-JOB-01~07 · 개발1) — 번호는 numbering 만 · job_lot 은 BOM 소요 줄 · 행 잠금 · 훅 자리 · 출력 404. JSON 으로 판정.

공통 시드 + seed_dev1(PRD-EX-01 의 BOM) 이 들어 있어야 한다(`make db-seed`).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from mescore.app import numbering
from mescore.app.main import app
from mescore.app.settings import get_settings
from mescore.db import conn

SFX = uuid.uuid4().hex[:6].upper()
HTML = {"accept": "text/html"}


def _client(login_id: str = "admin") -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/login", data={"login_id": login_id, "password": get_settings().seed_password})
    assert r.status_code == 200, f"{login_id} 로그인 실패 — make db-seed"
    return c


@pytest.fixture(scope="module")
def admin() -> TestClient:
    return _client("admin")


@pytest.fixture(scope="module")
def qa() -> TestClient:
    return _client("qa")        # job 칸 = 조회


@pytest.fixture(scope="module")
def base(admin):
    item = conn.q1("select id, unit from bas_item where item_code = 'PRD-EX-01'")
    prc = conn.q1("select id from bas_process where process_code = 'PRC-EX-01'")
    assert item and prc, "공통 시드 (예시) 품목 · 공정이 없다 — make db-seed"
    bom = conn.q1("select id, (select count(*) from bas_bom_dtl d where d.bom_id = b.id) as n from bas_bom b where item_id = %s and use_yn = 'Y' order by created_at desc limit 1", (item["id"],))
    return {"item_id": item["id"], "process_id": prc["id"], "bom_id": bom["id"] if bom else None, "bom_lines": int(bom["n"]) if bom else 0}


def _cleanup(wo_id: int) -> None:
    conn.x("delete from pop_work_result where work_order_id = %s", (wo_id,))
    conn.x("delete from job_lot where work_order_id = %s", (wo_id,))
    conn.x("delete from job_work_order where id = %s", (wo_id,))


@pytest.mark.fn("F-JOB-01")
def test_create_numbers_and_bom_lines(admin, qa, base):
    expected_no = numbering.peek("WORK_ORDER")
    r = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "100", "plan_date": date.today().isoformat(), "note": SFX})
    assert r.status_code == 200 and r.json()["work_order_no"] == expected_no and r.json()["status"] == "대기"
    wo = conn.q1("select * from job_work_order where id = %s", (r.json()["id"],))
    assert wo["status"] == "대기" and wo["bom_id"] == base["bom_id"] and wo["unit"] is not None
    lots = conn.q("select * from job_lot where work_order_id = %s", (wo["id"],))
    assert len(lots) == base["bom_lines"] and all(l["lot_id"] is None for l in lots)                      # LOT 은 비움
    if base["bom_lines"]:
        d = conn.q1("select qty, loss_rate from bas_bom_dtl where bom_id = %s and component_item_id = %s", (base["bom_id"], lots[0]["item_id"]))
        assert float(lots[0]["required_qty"]) == pytest.approx(float(d["qty"]) * 100 * (1 + float(d["loss_rate"]) / 100), abs=0.001)
    assert conn.q1("select count(*) as n from lot where work_order_id = %s", (wo["id"],))["n"] == 0        # LOT 을 미리 만들지 않는다
    assert admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "0"}).status_code == 422
    assert admin.post("/job/work-orders", data={"item_id": base["item_id"], "plan_qty": "1"}).status_code == 422
    assert admin.post("/job/work-orders", data={"item_id": "999999999", "process_id": base["process_id"], "plan_qty": "1"}).status_code == 422
    assert admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "1", "plan_date": "2026-13-01"}).status_code == 422
    assert qa.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "1"}).status_code == 403
    assert conn.q1("select count(*) as n from sys_access_log where kind = 'change' and fn_id = 'F-JOB-01' and target = %s", (f"job_work_order:{expected_no}",))["n"] == 1
    assert _client("prod").post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "1"}).status_code == 200   # 생산도 등록


@pytest.mark.fn("F-JOB-01")
def test_create_links_order_detail_and_plan(admin, base):
    partner = conn.q1("select id from bas_partner limit 1")
    o = conn.q1("insert into ord_order (order_no, partner_id, order_date, created_by) values (%s, %s, current_date, 'test') returning id", (f"T-O-{SFX}", partner["id"]))
    d = conn.q1("insert into ord_order_dtl (order_id, line_no, item_id, qty, created_by) values (%s, 1, %s, 10, 'test') returning id", (o["id"], base["item_id"]))
    p = conn.q1("insert into ord_plan (plan_no, order_dtl_id, item_id, plan_date, plan_qty, created_by) values (%s, %s, %s, current_date, 10, 'test') returning id, status", (f"T-N-{SFX}", d["id"], base["item_id"]))
    assert p["status"] == "계획"
    r = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10", "order_dtl_id": d["id"], "plan_id": p["id"]})
    assert r.status_code == 422 and r.json()["fields"][0]["name"] == "plan_id"                                # D-101: 확정된 계획만 지시로 이어진다
    assert conn.q1("select status from ord_order_dtl where id = %s", (d["id"],))["status"] == "대기"           # 422 면 아무것도 안 바뀐다
    conn.x("update ord_plan set status = '확정' where id = %s", (p["id"],))                                     # F-ORD-09 의 몫 — 테스트는 직접 올린다
    r = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10", "order_dtl_id": d["id"], "plan_id": p["id"]})
    assert r.status_code == 200
    assert conn.q1("select status from ord_order_dtl where id = %s", (d["id"],))["status"] == "지시"
    assert conn.q1("select status from ord_plan where id = %s", (p["id"],))["status"] == "확정"                 # 지시는 계획 상태를 바꾸지 않는다 (D-101)
    assert any(v == str(p["id"]) for v, _ in admin.get("/job/work-orders").json()["options"]["plan_id"])        # 선택지는 확정 계획만
    conn.x("update ord_plan set status = '취소' where id = %s", (p["id"],))
    assert admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10", "plan_id": p["id"]}).status_code == 422
    assert not any(v == str(p["id"]) for v, _ in admin.get("/job/work-orders").json()["options"]["plan_id"])
    conn.x("update ord_plan set status = '확정' where id = %s", (p["id"],))
    assert admin.post(f"/job/work-orders/{r.json()['id']}/cancel").status_code == 200
    assert conn.q1("select status from ord_order_dtl where id = %s", (d["id"],))["status"] == "대기"       # 취소하면 되돌린다
    _cleanup(r.json()["id"])
    conn.x("delete from ord_plan where id = %s", (p["id"],))
    conn.x("delete from ord_order_dtl where id = %s", (d["id"],))
    conn.x("delete from ord_order where id = %s", (o["id"],))


@pytest.mark.fn("F-JOB-02")
def test_update_locks_and_limits_when_started(admin, qa, base):
    wo = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10"}).json()
    r = admin.post(f"/job/work-orders/{wo['id']}", data={"plan_qty": "12", "plan_date": "2026-10-10", "note": "n"})
    assert r.status_code == 200 and set(r.json()["changed"]) == {"plan_qty", "plan_date", "note"}
    assert admin.post(f"/job/work-orders/{wo['id']}", data={"status": "마감"}).status_code == 422
    assert admin.post(f"/job/work-orders/{wo['id']}", data={}).status_code == 422
    assert admin.post("/job/work-orders/999999999", data={"plan_qty": "1"}).status_code == 404
    assert qa.post(f"/job/work-orders/{wo['id']}", data={"plan_qty": "1"}).status_code == 403
    res = conn.q1("insert into pop_work_result (work_order_id, process_id, created_by) values (%s, %s, 'test') returning id", (wo["id"], base["process_id"]))
    assert admin.post(f"/job/work-orders/{wo['id']}", data={"plan_qty": "15"}).status_code == 200            # 진행 중 — 수량 · 설비만
    r = admin.post(f"/job/work-orders/{wo['id']}", data={"plan_date": "2026-10-11"})
    assert r.status_code == 422 and "수량 · 설비" in r.json()["message"]
    conn.x("delete from pop_work_result where id = %s", (res["id"],))
    _cleanup(wo["id"])


@pytest.mark.fn("F-JOB-03")
def test_close_refuses_open_result(admin, qa, base):
    wo = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10"}).json()
    res = conn.q1("insert into pop_work_result (work_order_id, process_id, created_by) values (%s, %s, 'test') returning id", (wo["id"], base["process_id"]))
    r = admin.post(f"/job/work-orders/{wo['id']}/close")
    assert r.status_code == 422 and r.json()["fields"][0]["name"] == "open_count"
    conn.x("update pop_work_result set ended_at = now(), good_qty = 10 where id = %s", (res["id"],))
    assert qa.post(f"/job/work-orders/{wo['id']}/close").status_code == 403
    r = admin.post(f"/job/work-orders/{wo['id']}/close")
    assert r.status_code == 200 and r.json()["status"] == "마감"
    row = conn.q1("select status, closed_at, closed_by from job_work_order where id = %s", (wo["id"],))
    assert row["status"] == "마감" and row["closed_at"] is not None and row["closed_by"] == "admin"
    assert admin.post(f"/job/work-orders/{wo['id']}/close").status_code == 422
    assert admin.post(f"/job/work-orders/{wo['id']}", data={"plan_qty": "1"}).status_code == 422               # 마감은 수정 불가
    assert admin.post("/job/work-orders/999999999/close").status_code == 404
    conn.x("delete from pop_work_result where id = %s", (res["id"],))
    _cleanup(wo["id"])


@pytest.mark.fn("F-JOB-04")
def test_cancel_refuses_when_result_exists(admin, qa, base):
    wo = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10"}).json()
    res = conn.q1("insert into pop_work_result (work_order_id, process_id, created_by) values (%s, %s, 'test') returning id", (wo["id"], base["process_id"]))
    assert admin.post(f"/job/work-orders/{wo['id']}/cancel").status_code == 422
    conn.x("delete from pop_work_result where id = %s", (res["id"],))
    assert qa.post(f"/job/work-orders/{wo['id']}/cancel").status_code == 403
    r = admin.post(f"/job/work-orders/{wo['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "취소"
    assert admin.post(f"/job/work-orders/{wo['id']}/cancel").status_code == 422
    assert admin.post("/job/work-orders/999999999/cancel").status_code == 404
    _cleanup(wo["id"])


@pytest.mark.fn("F-JOB-05")
def test_list_filters_and_progress_is_computed(admin, qa, base):
    wo = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10", "plan_date": "2026-01-15"}).json()
    j = admin.get("/job/work-orders?date_from=2026-01-15&date_to=2026-01-15&status=대기").json()
    assert j["screen_id"] == "JOB-01" and any(r["id"] == wo["id"] and r["progress"] == "대기" for r in j["rows"])
    res = conn.q1("insert into pop_work_result (work_order_id, process_id, created_by) values (%s, %s, 'test') returning id", (wo["id"], base["process_id"]))
    j = admin.get("/job/work-orders?status=진행").json()
    assert j["rows"][0]["id"] == wo["id"] and j["rows"][0]["progress"] == "진행" and j["rows"][0]["status"] == "대기"   # 저장 안 함 — 실적 유무 · 최신 등록이 첫 줄(잔존 데이터 무관)
    j = admin.get(f"/job/work-orders?status=진행&no={wo['work_order_no']}").json()                            # 번호로 좁혀도 같은 행
    assert len(j["rows"]) == 1 and j["rows"][0]["id"] == wo["id"] and j["rows"][0]["progress"] == "진행"
    assert not any(r["id"] == wo["id"] for r in admin.get("/job/work-orders?status=대기").json()["rows"])
    assert not any(r["id"] == wo["id"] for r in admin.get(f"/job/work-orders?status=대기&no={wo['work_order_no']}").json()["rows"])
    assert admin.get(f"/job/work-orders?item_id={base['item_id']}&process_id={base['process_id']}&no={wo['work_order_no']}").json()["rows"][0]["id"] == wo["id"]
    assert admin.get("/job/work-orders?date_from=bad").status_code == 422
    assert admin.get(f"/job/work-orders?edit={wo['id']}", headers=HTML).status_code == 200
    assert qa.get("/job/work-orders").status_code == 200
    assert _client("field").get("/job/work-orders").status_code == 200                                      # 현장 = 조회
    conn.x("delete from pop_work_result where id = %s", (res["id"],))
    _cleanup(wo["id"])


@pytest.mark.fn("F-JOB-06")
def test_status_board_today_week_and_drilldown(admin, base):
    wo = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10", "plan_date": date.today().isoformat()}).json()
    res = conn.q1("insert into pop_work_result (work_order_id, process_id, ended_at, good_qty, defect_qty, created_by) values (%s, %s, now(), 4, 1, 'test') returning id", (wo["id"], base["process_id"]))
    j = admin.get("/job/status").json()
    assert j["screen_id"] == "JOB-02" and j["summary"]["전체"] >= 1
    assert j["rows"][0]["id"] == wo["id"], "최신 등록 지시가 첫 줄 (w.id desc) — 잔존 데이터가 LIST_LIMIT 를 넘어도"
    row = j["rows"][0]
    assert row["progress"] == "진행" and float(row["good_qty"]) == 4 and row["achieve_pct"] == 40.0 and j["summary"]["진행"] >= 1
    j = admin.get(f"/job/status?range=week&wo={wo['id']}").json()                                              # ?wo= 드릴다운 (D-604) — 목록 상한과 무관
    assert j["detail"]["id"] == wo["id"] and j["detail"]["work_order_no"] == wo["work_order_no"]
    assert len(j["results"]) == 1 and float(j["results"][0]["good_qty"]) == 4 and float(j["results"][0]["defect_qty"]) == 1
    conn.x("insert into pop_measure (work_result_id, param_key, value_num, unit, deviated) values (%s, 'temp', 95, '℃', true), (%s, 'zz_old', 1, null, false)", (res["id"], res["id"]))
    ms = {m["param_key"]: m for m in admin.get(f"/job/status?wo={wo['work_order_no']}").json()["results"][0]["measures"]}     # D-604 실적별 측정값
    declared = {r["param_key"] for r in conn.q("select param_key from bas_process_param where process_id = %s and use_yn = 'Y'", (base["process_id"],))}
    assert declared <= set(ms) and ms["temp"]["value"] == "95" and ms["temp"]["deviated"] is True and ms["temp"]["recorded"] is True
    assert ms["zz_old"]["recorded_only"] is True                                                               # 선언 없이 기록만 남은 키도 보인다
    assert all(ms[k]["value"] == "미수집" for k in declared - {"temp"})
    h = admin.get(f"/job/status?wo={wo['id']}", headers=HTML).text
    assert "95" in h and "zz_old" in h
    conn.x("delete from pop_measure where work_result_id = %s", (res["id"],))
    assert j["range"] == "week" and j["frm"] <= date.today().isoformat() <= j["to"]
    assert admin.get("/job/status?range=bad").status_code == 422
    assert admin.get("/job/status?wo=999999999").status_code == 404
    j = admin.get(f"/job/status?wo={wo['work_order_no']}").json()                                            # D-604 — 추적 링크는 지시 번호를 넘긴다
    assert j["detail"]["id"] == wo["id"] and len(j["results"]) == 1
    assert admin.get(f"/job/print?id={wo['work_order_no']}").json()["work_order"]["id"] == wo["id"]
    assert admin.get("/job/status?wo=W-NO-SUCH-" + SFX).status_code == 404
    assert admin.post(f"/job/work-orders/{wo['work_order_no']}/close").status_code == 404                    # 경로 {id} 는 숫자만 (api-contract §1)
    assert admin.get("/job/status?device=mobile", headers=HTML).status_code == 200                             # 모바일 채널 허용
    conn.x("delete from pop_work_result where id = %s", (res["id"],))
    _cleanup(wo["id"])


@pytest.mark.fn("F-JOB-07")
def test_print_work_order(admin, qa, base):
    wo = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10"}).json()
    j = admin.get(f"/job/print?id={wo['id']}").json()
    assert j["screen_id"] == "JOB-03" and j["work_order"]["work_order_no"] == wo["work_order_no"] and len(j["lots"]) == base["bom_lines"]
    h = admin.get(f"/job/print?id={wo['id']}", headers=HTML)
    assert h.status_code == 200 and wo["work_order_no"] in h.text and ("<svg" in h.text or "미확정" in h.text)   # 바코드 또는 미확정 자리
    assert admin.get("/job/print?id=999999999").status_code == 404
    assert admin.get("/job/print?id=abc").status_code == 404
    assert admin.get("/job/print").json()["template"] == "job/print_pick.html"
    assert qa.get(f"/job/print?id={wo['id']}").status_code == 200
    _cleanup(wo["id"])


@pytest.mark.fn("F-JOB-01")
def test_create_from_confirmed_plan_inherits_order_and_date(admin, base):
    """DEF-QA3-002 — 확정 계획만 고르면 계획의 수주 상세 · 계획일이 지시로 이어진다 → 작업지시서 수주 · 납기 · 수주 상세 `지시`."""
    partner = conn.q1("select id from bas_partner limit 1")
    o = conn.q1("insert into ord_order (order_no, partner_id, order_date, due_date, created_by) values (%s, %s, current_date, current_date + 7, 'test') returning id, due_date", (f"T-P-{SFX}", partner["id"]))
    d = conn.q1("insert into ord_order_dtl (order_id, line_no, item_id, qty, created_by) values (%s, 1, %s, 10, 'test') returning id", (o["id"], base["item_id"]))
    d2 = conn.q1("insert into ord_order_dtl (order_id, line_no, item_id, qty, created_by) values (%s, 2, %s, 5, 'test') returning id", (o["id"], base["item_id"]))
    p = conn.q1("insert into ord_plan (plan_no, order_dtl_id, item_id, plan_date, plan_qty, status, created_by) values (%s, %s, %s, current_date + 3, 10, '확정', 'test') returning id, plan_date",
                (f"T-Q-{SFX}", d["id"], base["item_id"]))
    r = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10", "plan_id": p["id"], "order_dtl_id": d2["id"]})
    assert r.status_code == 422 and r.json()["fields"][0]["name"] == "order_dtl_id"                           # 계획과 다른 수주 상세는 막는다
    r = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10", "plan_id": p["id"]})
    assert r.status_code == 200
    w = conn.q1("select order_dtl_id, plan_date from job_work_order where id = %s", (r.json()["id"],))
    assert w["order_dtl_id"] == d["id"] and w["plan_date"] == p["plan_date"]
    assert conn.q1("select status from ord_order_dtl where id = %s", (d["id"],))["status"] == "지시"
    j = admin.get(f"/job/print?id={r.json()['id']}").json()["work_order"]
    assert j["order_no"] == f"T-P-{SFX}" and j["due_date"] == o["due_date"].isoformat()
    r2 = admin.post("/job/work-orders", data={"item_id": base["item_id"], "process_id": base["process_id"], "plan_qty": "10", "plan_id": p["id"], "plan_date": "2030-01-02"})
    assert r2.status_code == 200 and str(conn.q1("select plan_date from job_work_order where id = %s", (r2.json()["id"],))["plan_date"]) == "2030-01-02"   # 폼 값이 있으면 그것
    for wid in (r.json()["id"], r2.json()["id"]):
        _cleanup(wid)
    conn.x("delete from ord_plan where id = %s", (p["id"],))
    conn.x("delete from ord_order_dtl where order_id = %s", (o["id"],))
    conn.x("delete from ord_order where id = %s", (o["id"],))
