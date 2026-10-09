"""ord — F-ORD-01~10 (수주 · 이력 · 납기 달력 · 생산계획). TestClient JSON 으로 판정(D-18). 개발3.

쓰기는 관리자 · 생산(범위 일반)만 — 품질(qa)은 403. 번호는 numbering(ORDER · PLAN). 이력 · 훅 자리(on_order_created · on_order_status_changed)까지 본다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from mescore.app import packs
from mescore.db import conn

from _dev3_helpers import client, ref, uniq

TODAY = date.today()


def _order(c, **over):
    data = {"partner_code": "CUST-EX-01", "order_date": TODAY.isoformat(), "due_date": (TODAY + timedelta(days=7)).isoformat(),
            "item_code": ["PRD-EX-01", "RAW-EX-01"], "qty": ["10", "5"], "unit": ["EA", "kg"], "note": "test"}
    data.update(over)
    return c.post("/ord/orders", data=data)


@pytest.mark.fn("F-ORD-01")
def test_order_create_two_lines_number_and_history(monkeypatch):
    seen = {}
    monkeypatch.setattr(packs, "hook", lambda name: (lambda cur, row, user: seen.setdefault(name, row)) if name == "on_order_created" else packs.NOOP_HOOK)
    c = client("prod")
    r = _order(c)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["lines"] == 2 and body["order_no"].startswith("O")
    o = conn.q1("select * from ord_order where order_no = %s", (body["order_no"],))
    assert o["status"] == "등록" and o["created_by"] == "prod"
    assert conn.q1("select count(*)::int as n from ord_order_dtl where order_id = %s", (o["id"],))["n"] == 2
    assert conn.q1("select count(*)::int as n from ord_order_hist where order_id = %s and field = '등록'", (o["id"],))["n"] == 1
    assert seen["on_order_created"]["order_no"] == body["order_no"]                    # 훅 자리 (interfaces.md §9)
    # 상세 0줄 · 없는 거래처 · 수량 0 → 422
    assert _order(c, item_code=[], qty=[]).status_code == 422
    assert _order(c, partner_code="NOPE").status_code == 422
    assert _order(c, qty=["0", "5"]).status_code == 422
    # 품질은 ord 조회만 → 403
    assert _order(client("qa")).status_code == 403


@pytest.mark.fn("F-ORD-02")
def test_order_update_due_and_qty_recorded_item_locked_by_work_order():
    c = client("prod")
    oid = _order(c).json()["id"]
    lines = conn.q("select * from ord_order_dtl where order_id = %s order by line_no", (oid,))
    new_due = (TODAY + timedelta(days=10)).isoformat()
    r = c.post(f"/ord/orders/{oid}", data={"due_date": new_due, "dtl_id": [str(lines[0]["id"])], "item_code": ["PRD-EX-01"], "qty": ["12"], "unit": ["EA"]})
    assert r.status_code == 200, r.text
    hist = {h["field"]: (h["before_value"], h["after_value"]) for h in conn.q("select * from ord_order_hist where order_id = %s", (oid,))}
    assert hist["due_date"][1] == new_due and hist["qty[1]"] == ("10.000", "12")
    # 지시가 붙은 상세의 품목은 못 바꾼다
    conn.x("""insert into job_work_order (work_order_no, item_id, process_id, order_dtl_id, plan_qty, unit, plan_date, status, created_by)
              values (%s, %s, %s, %s, 5, 'EA', current_date, '대기', 'test')""",
           (uniq("T-W"), ref("bas_item", "item_code", "PRD-EX-01"), ref("bas_process", "process_code", "PRC-EX-01"), lines[0]["id"]))
    r = c.post(f"/ord/orders/{oid}", data={"dtl_id": [str(lines[0]["id"])], "item_code": ["RAW-EX-02"], "qty": ["12"]})
    assert r.status_code == 422 and "품목" in r.json()["message"]
    assert c.post("/ord/orders/999999999", data={"note": "x"}).status_code == 404


@pytest.mark.fn("F-ORD-03")
def test_order_cancel_blocked_by_running_work_order_then_ok(monkeypatch):
    seen = {}
    monkeypatch.setattr(packs, "hook", lambda name: (lambda cur, row, user: seen.setdefault(name, row)) if name == "on_order_status_changed" else packs.NOOP_HOOK)
    c = client("prod")
    oid = _order(c).json()["id"]
    dtl = conn.q1("select id from ord_order_dtl where order_id = %s and line_no = 1", (oid,))
    wo_no = uniq("T-W")
    conn.x("""insert into job_work_order (work_order_no, item_id, process_id, order_dtl_id, plan_qty, unit, plan_date, status, created_by)
              values (%s, %s, %s, %s, 5, 'EA', current_date, '진행', 'test')""",
           (wo_no, ref("bas_item", "item_code", "PRD-EX-01"), ref("bas_process", "process_code", "PRC-EX-01"), dtl["id"]))
    r = c.post(f"/ord/orders/{oid}/cancel")
    assert r.status_code == 422 and r.json()["fields"][0]["reason"].startswith(wo_no)
    conn.x("update job_work_order set status = '취소' where work_order_no = %s", (wo_no,))
    r = c.post(f"/ord/orders/{oid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "취소"
    assert conn.q1("select status from ord_order where id = %s", (oid,))["status"] == "취소"
    assert seen["on_order_status_changed"]["before_status"] == "등록"                 # D-505 훅 자리
    assert c.post(f"/ord/orders/{oid}/cancel").status_code == 422
    assert client("qa").post(f"/ord/orders/{oid}/cancel").status_code == 403


@pytest.mark.fn("F-ORD-04")
def test_order_list_filters_and_line_quantities():
    c = client("prod")
    no = _order(c).json()["order_no"]
    r = c.get("/ord/orders", params={"frm": TODAY.isoformat(), "to": TODAY.isoformat(), "partner": "CUST-EX-01"})
    assert r.status_code == 200
    row = next(x for x in r.json()["rows"] if x["order_no"] == no)
    assert r.json()["total"] >= len(r.json()["rows"]) >= 1
    assert [l["line_no"] for l in row["lines"]] == [1, 2]                                  # 모든 수주의 상세 N줄 (열지 않아도)
    assert all(len(x["lines"]) == x["line_count"] for x in r.json()["rows"])
    assert row["line_count"] == 2 and row["qty"] == 15.0 and row["wo_count"] == 0 and row["shipped_count"] == 0
    oid = row["id"]
    body = c.get("/ord/orders", params={"id": str(oid)}).json()
    assert body["opened"]["order_no"] == no and [l["line_no"] for l in body["lines"]] == [1, 2]
    assert {"wo_qty", "shipped_qty"} <= set(body["lines"][0])
    assert c.get("/ord/orders", params={"status": "없는상태"}).status_code == 422
    assert c.get("/ord/orders", params={"frm": "2026-13-01"}).status_code == 422
    assert client("qa").get("/ord/orders").status_code == 200                           # 조회 이상
    assert client("field").get("/ord/orders").status_code == 200


@pytest.mark.fn("F-ORD-05")
def test_order_history_lists_before_after_values():
    c = client("prod")
    body = _order(c).json()
    c.post(f"/ord/orders/{body['id']}", data={"due_date": (TODAY + timedelta(days=3)).isoformat()})
    r = c.get("/ord/order-history", params={"order_no": body["order_no"]})
    assert r.status_code == 200
    fields = {h["field"] for h in r.json()["rows"]}
    assert {"등록", "due_date"} <= fields
    h = next(x for x in r.json()["rows"] if x["field"] == "due_date")
    assert h["changed_by"] == "prod" and h["before_value"] and h["after_value"]


@pytest.mark.fn("F-ORD-06")
def test_delivery_calendar_month_weeks_and_mobile():
    c = client("prod")
    due = TODAY + timedelta(days=2)
    no = _order(c, due_date=due.isoformat()).json()["order_no"]
    r = c.get("/ord/delivery-calendar", params={"ym": TODAY.strftime("%Y-%m")})
    assert r.status_code == 200
    body = r.json()
    day = next(d for d in body["days"] if d["date"] == due.isoformat()) if due.month == TODAY.month else None
    if day:
        assert day["due_count"] >= 1 and no in [o["order_no"] for o in day["orders"]]
    assert all(len(w["days"]) == 7 for w in body["weeks"]) and sum(1 for w in body["weeks"] if w["open"]) >= 1
    assert c.get("/ord/delivery-calendar", params={"ym": "2026-99"}).status_code == 422
    m = client("field", device="mobile").get("/ord/delivery-calendar", headers={"accept": "text/html"})
    assert m.status_code == 200 and "m-weeks" in m.text and "ch-mobile" in m.text


def _plan(c, **over):
    data = {"item_code": "PRD-EX-01", "plan_date": TODAY.isoformat(), "plan_qty": "30", "unit": "EA"}
    data.update(over)
    return c.post("/ord/plans", data=data)


@pytest.mark.fn("F-ORD-07")
def test_plan_create_with_and_without_order_detail():
    c = client("prod")
    r = _plan(c)
    assert r.status_code == 200 and r.json()["plan_no"].startswith("N")
    order = _order(c).json()
    r = _plan(c, order_no=order["order_no"], line_no="1", item_code="")
    assert r.status_code == 200
    p = conn.q1("select * from ord_plan where plan_no = %s", (r.json()["plan_no"],))
    assert p["status"] == "계획" and p["order_dtl_id"] is not None and p["plan_qty"] == 30
    assert _plan(c, plan_qty="0").status_code == 422
    assert _plan(c, plan_date="").status_code == 422
    assert _plan(c, order_no="NOPE-1", line_no="1").status_code == 422
    assert _plan(client("qa")).status_code == 403


@pytest.mark.fn("F-ORD-08")
def test_plan_update_only_qty_after_confirm():
    c = client("prod")
    pid = _plan(c).json()["id"]
    assert c.post(f"/ord/plans/{pid}", data={"plan_qty": "40", "item_code": "RAW-EX-01"}).status_code == 200
    assert c.post(f"/ord/plans/{pid}/confirm").status_code == 200
    assert c.post(f"/ord/plans/{pid}", data={"plan_qty": "45"}).status_code == 200
    assert conn.q1("select plan_qty from ord_plan where id = %s", (pid,))["plan_qty"] == 45
    r = c.post(f"/ord/plans/{pid}", data={"item_code": "PRD-EX-01"})
    assert r.status_code == 422 and "수량만" in r.json()["message"]
    assert c.post(f"/ord/plans/{pid}", data={"plan_date": (TODAY + timedelta(days=1)).isoformat()}).status_code == 422
    assert c.post("/ord/plans/999999999", data={"plan_qty": "1"}).status_code == 404


@pytest.mark.fn("F-ORD-09")
def test_plan_confirm_once():
    c = client("admin")
    pid = _plan(c).json()["id"]
    r = c.post(f"/ord/plans/{pid}/confirm")
    assert r.status_code == 200 and r.json()["status"] == "확정"
    assert c.post(f"/ord/plans/{pid}/confirm").status_code == 422
    assert client("field").post(f"/ord/plans/{pid}/confirm").status_code == 403


@pytest.mark.fn("F-ORD-10")
def test_plan_list_shows_work_order_and_actual_qty():
    c = client("prod")
    body = _plan(c).json()
    r = c.get("/ord/plans", params={"frm": TODAY.isoformat(), "to": TODAY.isoformat(), "status": "계획"})
    assert r.status_code == 200
    row = next(x for x in r.json()["rows"] if x["plan_no"] == body["plan_no"])
    assert row["wo_count"] == 0 and row["actual_qty"] is None and row["item_code"] == "PRD-EX-01"
    assert c.get("/ord/plans", params={"id": str(body["id"])}).json()["opened"]["plan_no"] == body["plan_no"]
    assert c.get("/ord/plans", params={"status": "x"}).status_code == 422
