"""shp — F-SHP-01~10 (출하 등록 · LOT 스캔/승인 · 현황 · 성적서) + D-601 출하 라벨. TestClient JSON 판정. 개발3.

권한(D-13): 등록 · 수정 · 취소 · 스캔 · 성적서 발행은 생산 · 현장(범위 일반), 승인은 관리자만(범위 승인) — 관리자는 등록 403, 생산은 승인 403.
생산 LOT 픽스처는 개발2 `lineage.make_product_lot` 로 만든다. 출하 LOT · 출하 계보는 `lineage.ship/unship` 만이 쓴다.
"""

from __future__ import annotations

from datetime import date

import pytest

from mescore.app import packs
from mescore.db import conn

from _dev3_helpers import HTML, client, genealogy_count, lot_state, new_shipment, scenario_lots

TODAY = date.today()


def _scan(c, shipment_no: str, lot_no: str):
    return c.post("/shp/scan", data={"shipment_no": shipment_no, "barcode": lot_no})


def _ship_with_lots(n: int = 2):
    prod = client("prod")
    s = new_shipment(prod, order_no="O-EX-S001")
    lots = scenario_lots(n)
    for l in lots:
        assert _scan(prod, s["shipment_no"], l["lot_no"]).status_code == 200
    return prod, s, lots


@pytest.mark.fn("F-SHP-01")
def test_shipment_create_number_status_and_roles():
    prod = client("prod")
    s = new_shipment(prod)
    assert s["shipment_no"].startswith("S")
    row = conn.q1("select * from shp_shipment where id = %s", (s["id"],))
    assert row["status"] == "등록" and row["approved_at"] is None
    assert prod.post("/shp/shipments", data={"partner_code": "NOPE", "ship_date": TODAY.isoformat()}).status_code == 422
    assert prod.post("/shp/shipments", data={"partner_code": "CUST-EX-01", "ship_date": "x"}).status_code == 422
    assert prod.post("/shp/shipments", data={"partner_code": "CUST-EX-01", "order_no": "NOPE"}).status_code == 422
    assert client("admin").post("/shp/shipments", data={"partner_code": "CUST-EX-01"}).status_code == 403     # 관리자는 승인만 (D-13)
    assert client("qa").post("/shp/shipments", data={"partner_code": "CUST-EX-01"}).status_code == 403
    assert client("field").post("/shp/shipments", data={"partner_code": "CUST-EX-01"}).status_code == 200


@pytest.mark.fn("F-SHP-02")
def test_shipment_update_before_approval_only():
    prod, s, lots = _ship_with_lots(1)
    r = prod.post(f"/shp/shipments/{s['id']}", data={"note": "바뀜", "clear_order": "1"})
    assert r.status_code == 200
    row = conn.q1("select note, order_id from shp_shipment where id = %s", (s["id"],))
    assert row["note"] == "바뀜" and row["order_id"] is None
    assert client("admin").post(f"/shp/shipments/{s['id']}/approve").status_code == 200
    assert prod.post(f"/shp/shipments/{s['id']}", data={"note": "x"}).status_code == 422
    assert prod.post("/shp/shipments/999999999", data={"note": "x"}).status_code == 404


@pytest.mark.fn("F-SHP-03")
def test_shipment_cancel_unships_every_lot():
    prod, s, lots = _ship_with_lots(2)
    assert all(lot_state(l["id"]) == "출하" for l in lots)
    r = prod.post(f"/shp/shipments/{s['id']}/cancel")
    assert r.status_code == 200 and r.json()["unshipped"] == 2
    assert conn.q1("select status from shp_shipment where id = %s", (s["id"],))["status"] == "취소"
    assert all(lot_state(l["id"]) == "재고" for l in lots) and all(genealogy_count(l["lot_no"]) == 0 for l in lots)
    assert prod.post(f"/shp/shipments/{s['id']}/cancel").status_code == 422
    prod2, s2, _ = _ship_with_lots(1)
    assert client("admin").post(f"/shp/shipments/{s2['id']}/approve").status_code == 200
    assert prod2.post(f"/shp/shipments/{s2['id']}/cancel").status_code == 422                 # 승인 후 취소 불가


@pytest.mark.fn("F-SHP-04")
def test_shipment_list_counts_lots_and_qty():
    prod, s, lots = _ship_with_lots(2)
    r = prod.get("/shp/shipments", params={"no": s["shipment_no"], "frm": TODAY.isoformat(), "to": TODAY.isoformat()})
    assert r.status_code == 200
    row = next(x for x in r.json()["rows"] if x["shipment_no"] == s["shipment_no"])
    assert row["lot_count"] == 2 and row["total_qty"] == 30.0 and row["status"] == "등록"
    body = prod.get("/shp/shipments", params={"id": str(s["id"])}).json()
    assert [l["lot_no"] for l in body["lots"]] == [l["lot_no"] for l in lots] and body["summary"]["lot_count"] == 2
    assert prod.get("/shp/shipments", params={"status": "x"}).status_code == 422
    assert client("qa").get("/shp/shipments").status_code == 200


@pytest.mark.fn("F-SHP-05")
def test_scan_lot_rules_422_and_creates_shipment_lot():
    prod = client("prod")
    s = new_shipment(prod)
    ok, uninspected = scenario_lots(1)[0], scenario_lots(1, insp_status="미검사")[0]
    failed = scenario_lots(1, insp_status="불합격")[0]
    r = _scan(prod, s["shipment_no"], ok["lot_no"])
    assert r.status_code == 200 and r.json()["lot_count"] == 1
    x = conn.q1("select lot_no, kind_base from lot where shipment_id = %s", (s["id"],))
    assert x["kind_base"] == "SHIPMENT" and x["lot_no"].startswith("X")
    assert lot_state(ok["id"]) == "출하" and genealogy_count(ok["lot_no"]) == 1
    assert _scan(prod, s["shipment_no"], ok["lot_no"]).status_code == 422                 # 이미 출하
    assert _scan(prod, s["shipment_no"], uninspected["lot_no"]).status_code == 422         # 미검사
    assert _scan(prod, s["shipment_no"], failed["lot_no"]).status_code == 422              # 불합격
    assert _scan(prod, s["shipment_no"], "NOPE-0000").status_code == 422                   # 없는 번호
    assert _scan(prod, s["shipment_no"], "M-EX-0001").status_code == 422                   # 원재료 LOT
    assert _scan(prod, "NOPE", ok["lot_no"]).status_code == 422
    assert client("admin").post("/shp/scan", data={"shipment_no": s["shipment_no"], "barcode": ok["lot_no"]}).status_code == 403
    # 스캔 진입 GET — 없는 출하 번호는 그 화면을 422 로 다시 그린다 (data-scan 유지)
    h = prod.get("/shp/scan", params={"no": "NOPE"}, headers=HTML)
    assert h.status_code == 422 and "data-scan" in h.text and "alert-422" in h.text
    assert prod.get("/shp/scan", params={"no": "NOPE"}).status_code == 422
    assert prod.get("/shp/scan", params={"no": s["shipment_no"]}).json()["summary"]["lot_count"] == 1


@pytest.mark.fn("F-SHP-06")
def test_unscan_lot_before_approval():
    prod, s, lots = _ship_with_lots(2)
    r = prod.post("/shp/scan/cancel", data={"shipment_no": s["shipment_no"], "barcode": lots[0]["lot_no"]})
    assert r.status_code == 200 and r.json()["removed"] == 1
    assert lot_state(lots[0]["id"]) == "재고" and lot_state(lots[1]["id"]) == "출하"
    assert prod.post("/shp/scan/cancel", data={"shipment_no": s["shipment_no"], "barcode": lots[0]["lot_no"]}).status_code == 422
    assert client("admin").post(f"/shp/shipments/{s['id']}/approve").status_code == 200
    assert prod.post("/shp/scan/cancel", data={"shipment_no": s["shipment_no"], "barcode": lots[1]["lot_no"]}).status_code == 422


@pytest.mark.fn("F-SHP-07")
def test_approve_requires_lots_admin_hook_and_after_commit(monkeypatch):
    prod = client("prod")
    empty = new_shipment(prod)
    admin = client("admin")
    assert admin.post(f"/shp/shipments/{empty['id']}/approve").status_code == 422          # LOT 0건
    prod, s, lots = _ship_with_lots(2)
    assert prod.post(f"/shp/shipments/{s['id']}/approve").status_code == 403               # 생산은 승인 범위 없음
    called = {}

    def fake_hook(name):
        if name == "validate_shipment":
            return lambda cur, shipment, lot_rows, user: called.setdefault("validate", (shipment["shipment_no"], len(lot_rows), user.login_id))
        if name == "after_commit_shipment_approved":
            return lambda payload: called.setdefault("after_commit", payload)
        return packs.NOOP_HOOK
    monkeypatch.setattr(packs, "hook", fake_hook)
    r = admin.post(f"/shp/shipments/{s['id']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "승인" and r.json()["lot_count"] == 2
    row = conn.q1("select status, approved_by, approved_at from shp_shipment where id = %s", (s["id"],))
    assert row["status"] == "승인" and row["approved_by"] == "admin" and row["approved_at"] is not None
    assert called["validate"] == (s["shipment_no"], 2, "admin")                            # validate_shipment 직전 호출
    assert called["after_commit"]["shipment_no"] == s["shipment_no"] and len(called["after_commit"]["lots"]) == 2   # after_commit 이벤트 (D-20)
    assert admin.post(f"/shp/shipments/{s['id']}/approve").status_code == 422              # 두 번 승인 불가
    assert _scan(prod, s["shipment_no"], scenario_lots(1)[0]["lot_no"]).status_code == 422  # 승인 후 스캔 불가


@pytest.mark.fn("F-SHP-07")
def test_approve_hook_rejection_rolls_back(monkeypatch):
    from mescore.app.util.http import HookError

    prod, s, lots = _ship_with_lots(1)
    monkeypatch.setattr(packs, "hook", lambda name: (lambda cur, shipment, lot_rows, user: (_ for _ in ()).throw(HookError("팩 규칙 거부", fields=[{"name": "x", "reason": "y"}])))
                        if name == "validate_shipment" else packs.NOOP_HOOK)
    r = client("admin").post(f"/shp/shipments/{s['id']}/approve")
    assert r.status_code == 422 and r.json()["code"] == "hook_rejected"
    assert conn.q1("select status from shp_shipment where id = %s", (s["id"],))["status"] == "등록"


@pytest.mark.fn("F-SHP-08")
def test_shipment_status_today_week_and_mobile_cards():
    prod, s, lots = _ship_with_lots(1)
    r = prod.get("/shp/status")
    assert r.status_code == 200
    body = r.json()
    assert body["stat"]["today_count"] >= 1 and any(x["shipment_no"] == s["shipment_no"] for x in body["today_rows"])
    assert "delivery" in body and body["stat"]["week_lots"] >= 1
    assert body["total"] >= len(body["rows"])
    mine = next(x for x in body["rows"] if x["shipment_no"] == s["shipment_no"])
    due = conn.q1("select due_date from ord_order where order_no = 'O-EX-S001'")
    if due and due["due_date"]:
        assert mine["due_days"] == (TODAY - due["due_date"]).days and mine["due_state"] in ("지연", "당일", "앞섬")
    else:
        assert mine["due_days"] is None and mine["due_state"] is None
    assert prod.get("/shp/shipments").json()["total"] >= 1
    m = client("field", device="mobile").get("/shp/status", headers=HTML)
    assert m.status_code == 200 and "m-card" in m.text and "ch-mobile" in m.text
    assert prod.get("/shp/status", params={"frm": "bad"}).status_code == 422


@pytest.mark.fn("F-SHP-09")
def test_document_issue_snapshot_latest_inspection_and_reissue():
    prod, s, lots = _ship_with_lots(2)
    assert prod.post("/shp/documents", data={"shipment_id": str(s["id"])}).status_code == 422          # 미승인
    assert client("admin").post(f"/shp/shipments/{s['id']}/approve").status_code == 200
    # 검사 2건 중 최신(나중) 것이 스냅샷에 든다 — 항목 값 포함
    with conn.tx() as cur:
        for when, judge, val in (("now() - interval '2 day'", "불합격", 9.0), ("now() - interval '1 day'", "합격", 12.5)):
            cur.execute(f"""insert into qua_inspection (lot_id, insp_type, inspected_at, inspector, judgement, judged_at, created_by)
                            values (%s, '최종', {when}, 'qa', %s, {when}, 'test') returning id""", (lots[0]["id"], judge))
            iid = cur.fetchone()["id"]
            cur.execute("insert into qua_insp_item (inspection_id, item_key, value_num, unit, item_judgement, created_by) values (%s, 'moisture', %s, '%%', %s, 'test')",
                        (iid, val, judge))
    r = prod.post("/shp/documents", data={"shipment_id": str(s["id"])})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document_no"].startswith("C") and body["lot_count"] == 2 and body["judgement"] == "미확정"   # lots[1] 검사 없음 → 미확정
    snap = conn.q1("select snapshot from shp_document where id = %s", (body["id"],))["snapshot"]
    l0 = next(l for l in snap["lots"] if l["lot_no"] == lots[0]["lot_no"])
    assert l0["inspection"]["judgement"] == "합격" and l0["inspection"]["values"]["moisture"]["value"] == 12.5
    assert [c["item_key"] for c in snap["columns"]] == ["moisture"] and snap["shipment"]["shipment_no"] == s["shipment_no"]
    assert snap["summary"] == {"lot_count": 2, "passed": 1, "failed": 0, "conditional": 0, "uninspected": 1, "judgement": "미확정"}
    r2 = prod.post("/shp/documents", data={"shipment_id": str(s["id"])})
    assert r2.status_code == 200 and r2.json()["document_no"] != body["document_no"]                   # 재발행 = 새 번호
    assert prod.post("/shp/documents", data={"shipment_id": "x"}).status_code == 422
    assert client("admin").post("/shp/documents", data={"shipment_id": str(s["id"])}).status_code == 403
    assert prod.get("/shp/documents", params={"no": body["document_no"]}).json()["rows"][0]["document_no"] == body["document_no"]


@pytest.mark.fn("F-SHP-10")
def test_document_print_draws_snapshot_not_live_data():
    prod, s, lots = _ship_with_lots(1)
    assert client("admin").post(f"/shp/shipments/{s['id']}/approve").status_code == 200
    doc = prod.post("/shp/documents", data={"shipment_id": str(s["id"])}).json()
    conn.x("insert into qua_inspection (lot_id, insp_type, inspected_at, judgement, judged_at, created_by) values (%s, '최종', now(), '불합격', now(), 'test')", (lots[0]["id"],))
    r = prod.get(f"/shp/documents/{doc['id']}/print")
    assert r.status_code == 200
    body = r.json()
    assert body["doc"]["document_no"] == doc["document_no"] and body["snapshot"]["summary"]["uninspected"] == 1   # 발행 뒤 검사가 생겨도 발행본 불변
    h = prod.get(f"/shp/documents/{doc['id']}/print", headers=HTML)
    assert h.status_code == 200 and doc["document_no"] in h.text and "<svg" in h.text and 'data-print="document"' in h.text
    assert prod.get("/shp/documents/999999999/print").status_code == 404


def test_shipment_label_d601():
    prod, s, lots = _ship_with_lots(1)
    r = prod.get(f"/shp/shipments/{s['id']}/label", headers=HTML)
    assert r.status_code == 200 and s["shipment_no"] in r.text and "<svg" in r.text
    assert prod.get(f"/shp/shipments/{s['id']}/label").json()["lot_count"] == 1
    assert prod.get("/shp/shipments/999999999/label").status_code == 404
