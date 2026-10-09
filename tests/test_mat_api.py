"""자재 mat — F-MAT-01~11 을 TestClient(JSON · D-18) 로 한 기능씩 (개발2). 역할: 생산(prod) 입력 · 품질(qa) 입고검사 · 현장(field) 입력 · 관리자(admin) 조회만."""

from __future__ import annotations

from datetime import date

import pytest

from mescore.app import nav
from mescore.db import conn

from _dev2_helpers import HTML, client, item_id, partner_id, process_id, uniq

MAT01, MAT02, MAT03, MAT04, MAT05 = (nav.path_of(s) for s in ("MAT-01", "MAT-02", "MAT-03", "MAT-04", "MAT-05"))


def _receipt(c, item_code: str = "RAW-EX-01", qty: float = 100, **extra) -> dict:
    r = c.post(MAT01, data={"item_id": item_id(item_code), "qty": qty, "partner_id": partner_id("SUP-EX-01"), **extra})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.fn("F-MAT-01")
def test_receipt_create_makes_lot_stock_and_trx():
    c = client("prod")
    before = conn.q1("select coalesce(qty, 0) as q from mat_stock where item_id = %s", (item_id("RAW-EX-01"),))
    before_q = before["q"] if before else 0
    body = _receipt(c, qty=100)
    assert body["ok"] and body["receipt_no"] == body["lot_no"] and body["label_url"].endswith(f"/{body['lot_id']}/label")
    lot = conn.q1("select * from lot where id = %s", (body["lot_id"],))
    assert lot["kind"] == "MATERIAL" and lot["kind_base"] == "MATERIAL" and lot["insp_status"] == "미검사" and lot["qty"] == 100
    assert conn.q1("select qty from mat_stock where item_id = %s", (item_id("RAW-EX-01"),))["qty"] == before_q + 100
    assert conn.q1("select count(*) as n from mat_stock_trx where lot_id = %s and trx_type = '입고'", (lot["id"],))["n"] == 1
    assert conn.q1("select count(*) as n from sys_access_log where kind = 'change' and fn_id = 'F-MAT-01' and target = %s", (f"mat_receipt:{body['receipt_no']}",))["n"] == 1
    # 422 — 수량 0 · 없는 품목 / 403 — 관리자(조회) · 품질(입고검사 범위만)
    assert c.post(MAT01, data={"item_id": item_id("RAW-EX-01"), "qty": 0}).status_code == 422
    assert c.post(MAT01, data={"item_id": 999999, "qty": 1}).status_code == 422
    assert client("admin").post(MAT01, data={"item_id": item_id("RAW-EX-01"), "qty": 1}).status_code == 403
    assert client("qa").post(MAT01, data={"item_id": item_id("RAW-EX-01"), "qty": 1}).status_code == 403
    # 브라우저 폼은 303 + 알림
    r = c.post(MAT01, data={"item_id": item_id("RAW-EX-01"), "qty": 5}, headers=HTML, follow_redirects=False)
    assert r.status_code == 303


@pytest.mark.fn("F-MAT-02")
def test_receipt_update_adjusts_stock_and_refuses_consumed_lot():
    c = client("prod")
    body = _receipt(c, qty=100)
    r = c.post(f"{MAT01}/{body['id']}", data={"qty": 80, "note": "수정"})
    assert r.status_code == 200 and r.json()["qty_diff"] == -20
    assert conn.q1("select qty from lot where id = %s", (body["lot_id"],))["qty"] == 80
    assert conn.q1("select sum(qty) as s from mat_stock_trx where lot_id = %s", (body["lot_id"],))["s"] == 80
    assert c.post(f"{MAT01}/999999", data={"qty": 1}).status_code == 404
    # 투입된 LOT 은 422 — 합격시킨 뒤 투입해 본다
    assert client("qa").post(MAT02, data={"lot_id": body["lot_id"], "judgement": "합격"}).status_code == 200
    from _dev2_helpers import new_work_order
    wo = new_work_order()
    rs = c.post(f"{nav.path_of('POP-02')}/start", data={"work_order_id": wo["id"]}).json() if nav.path_of("POP-02") else None
    if rs and rs.get("ok"):
        assert c.post(nav.path_of("POP-03"), data={"work_result_id": rs["id"], "barcode": body["lot_no"], "qty": 1}).status_code == 200
        assert c.post(f"{MAT01}/{body['id']}", data={"qty": 70}).status_code == 422


@pytest.mark.fn("F-MAT-03")
def test_receipts_screen_lists_with_filters():
    c = client("prod")
    body = _receipt(c, qty=3)
    j = c.get(MAT01, params={"frm": date.today().isoformat(), "to": date.today().isoformat(), "item_id": item_id("RAW-EX-01")}).json()
    assert j["screen_id"] == "MAT-01" and any(r["receipt_no"] == body["receipt_no"] for r in j["rows"])
    assert j["rows"][0]["lot_no"] and "insp_status" in j["rows"][0]
    assert c.get(MAT01, params={"frm": "bad"}).status_code == 422
    assert c.get(MAT01, headers=HTML).status_code == 200
    assert client("field").get(MAT01 + "?device=pop").status_code == 200


@pytest.mark.fn("F-MAT-04")
def test_incoming_inspection_judges_lot_with_plan_items():
    c = client("prod")
    body = _receipt(c, qty=10)
    key = uniq("K").lower().replace("-", "_")
    conn.x("""insert into qua_insp_plan (insp_type, item_id, item_key, label, unit, value_type, min_value, max_value, seq, created_by)
              values ('입고', %s, %s, '입고 항목 (예시)', 'mm', 'number', 1, 5, 99, 'test')""", (item_id("RAW-EX-01"), key))
    q = client("qa")
    r = q.post(MAT02, data={"lot_no": body["lot_no"], "judgement": "합격", f"i_{key}": "7"})      # 범위 이탈 저장 + deviated
    assert r.status_code == 200 and r.json()["judgement"] == "합격" and r.json()["items"] == 1
    assert conn.q1("select insp_status from lot where id = %s", (body["lot_id"],))["insp_status"] == "합격"
    insp = conn.q1("select * from qua_inspection where id = %s", (r.json()["id"],))
    assert insp["insp_type"] == "입고" and insp["judgement"] == "합격" and insp["judged_by"] == "qa"
    it = conn.q1("select * from qua_insp_item where inspection_id = %s", (insp["id"],))
    assert it["item_key"] == key and it["deviated"] is True and it["value_num"] == 7
    # 항목 0건(계획 없는 품목)도 판정된다 (D-513)
    body2 = _receipt(c, item_code="RAW-EX-02", qty=1)
    r2 = q.post(MAT02, data={"lot_id": body2["lot_id"], "judgement": "불합격"})
    assert r2.status_code == 200 and r2.json()["items"] == 0
    assert conn.q1("select insp_status from lot where id = %s", (body2["lot_id"],))["insp_status"] == "불합격"
    # 422 — 없는 번호 · 모르는 판정 · 숫자 아님 / 403 — 생산 · 현장(입고검사 범위 없음)
    assert q.post(MAT02, data={"lot_no": "NO-SUCH", "judgement": "합격"}).status_code == 422
    assert q.post(MAT02, data={"lot_no": body["lot_no"], "judgement": "보류"}).status_code == 422
    assert q.post(MAT02, data={"lot_no": body["lot_no"], "judgement": "합격", f"i_{key}": "abc"}).status_code == 422
    assert c.post(MAT02, data={"lot_no": body["lot_no"], "judgement": "합격"}).status_code == 403
    assert client("field").post(MAT02, data={"lot_no": body["lot_no"], "judgement": "합격"}).status_code == 403


@pytest.mark.fn("F-MAT-05")
def test_inspection_screen_scan_entry_rerenders_422_on_unknown_no():
    c = client("qa")
    body = _receipt(client("prod"), qty=1)
    j = c.get(MAT02).json()
    assert j["screen_id"] == "MAT-02" and any(r["lot_no"] == body["lot_no"] for r in j["rows"])
    ok = c.get(MAT02, params={"no": body["lot_no"]})
    assert ok.status_code == 200 and ok.json()["lot"]["no"] == body["lot_no"] and isinstance(ok.json()["fields"], list)
    miss = c.get(MAT02, params={"no": "NO-SUCH-LOT"})
    assert miss.status_code == 422 and miss.json()["code"] == "validation_error" and miss.json()["screen_id"] == "MAT-02"
    html = c.get(MAT02, params={"no": "NO-SUCH-LOT", "device": "pop"}, headers=HTML)
    assert html.status_code == 422 and html.text.count("data-scan") == 1 and 'id="scan-result"' in html.text and 'class="ch-pop"' in html.text


@pytest.mark.fn("F-MAT-06")
def test_material_lot_list_shows_remain_state_and_usage():
    c = client("admin")
    body = _receipt(client("prod"), qty=12)
    j = c.get(MAT03, params={"no": body["lot_no"]}).json()
    assert len(j["rows"]) == 1 and j["rows"][0]["remain_qty"] == 12 and j["rows"][0]["state"] == "재고" and j["rows"][0]["insp_status"] == "미검사"
    assert c.get(MAT03, params={"insp": "미검사"}).status_code == 200
    assert client("field").get(MAT03 + "?device=pop").status_code == 200


@pytest.mark.fn("F-MAT-07")
def test_material_lot_label_has_inline_barcode_of_lot_no():
    c = client("admin")
    body = _receipt(client("prod"), qty=1)
    j = c.get(f"{MAT03}/{body['lot_id']}/label").json()
    assert j["lot_no"] == body["lot_no"] and j["kind_label"] == "원재료 LOT" and j["size"] == "100x50" and j["template"] == "print/label_lot.html"
    html = c.get(f"{MAT03}/{body['lot_id']}/label", headers=HTML).text
    assert f'aria-label="{body["lot_no"]}"' in html and 'data-symbology="code128"' in html and "cdn" not in html.lower()
    assert c.get(f"{MAT03}/{body['lot_id']}/label", params={"size": "50x30"}, headers=HTML).status_code == 200
    assert c.get(f"{MAT03}/{body['lot_id']}/label", params={"size": "1x1"}).status_code == 422
    assert c.get(f"{MAT03}/999999/label").status_code == 404
    # 바코드 값 → 스캔 왕복: resolve 가 같은 LOT
    from mescore.app import lineage
    assert lineage.resolve(body["lot_no"]).id == body["lot_id"]


@pytest.mark.fn("F-MAT-08")
def test_stock_screen_lists_items_with_lots():
    c = client("admin")
    body = _receipt(client("prod"), qty=4)
    j = c.get(MAT04, params={"item_id": item_id("RAW-EX-01")}).json()
    assert len(j["rows"]) == 1 and j["rows"][0]["item_code"] == "RAW-EX-01" and any(l["lot_no"] == body["lot_no"] for l in j["rows"][0]["lots"])
    assert j["rows"][0]["qty"] == j["rows"][0]["trx_sum"]           # 현재고 = 거래 합
    assert c.get(MAT04 + "?device=mobile").status_code == 200


@pytest.mark.fn("F-MAT-09")
def test_stock_adjust_requires_reason():
    c = client("prod")
    iid = item_id("RAW-EX-02")
    before = (conn.q1("select qty from mat_stock where item_id = %s", (iid,)) or {"qty": 0})["qty"]
    assert c.post(f"{MAT04}/adjust", data={"item_id": iid, "qty": -1}).status_code == 422          # 사유 없음
    assert c.post(f"{MAT04}/adjust", data={"item_id": iid, "qty": 0, "reason": "x"}).status_code == 422
    r = c.post(f"{MAT04}/adjust", data={"item_id": iid, "qty": 2.5, "reason": "실사 (예시)"})
    assert r.status_code == 200 and r.json()["stock_qty"] == float(before) + 2.5
    assert client("admin").post(f"{MAT04}/adjust", data={"item_id": iid, "qty": 1, "reason": "x"}).status_code == 403


@pytest.mark.fn("F-MAT-10")
def test_requirements_calc_is_idempotent_and_keeps_hook_rows():
    c = client("prod")
    prd, raw = item_id("PRD-EX-01"), item_id("RAW-EX-01")
    bom = conn.q1("select id from bas_bom where item_id = %s and version = 'T-REQ'", (prd,))
    if bom is None:
        bom = conn.q1("insert into bas_bom (item_id, version, created_by) values (%s, 'T-REQ', 'test') returning id", (prd,))
        conn.x("insert into bas_bom_dtl (bom_id, component_item_id, qty, unit, created_by) values (%s, %s, 2, 'kg', 'test')", (bom["id"], raw))
    frm, to = "2031-01-01", "2031-01-07"
    conn.x("""insert into job_work_order (work_order_no, item_id, process_id, plan_qty, unit, plan_date, status, created_by)
              values (%s, %s, %s, 10, 'EA', '2031-01-03', '대기', 'test')""", (uniq("T-W"), prd, process_id()))
    conn.x("""insert into mat_requirement (period_from, period_to, item_id, required_qty, source, created_by) values (%s, %s, %s, 1, 'hook', 'test')
              on conflict do nothing""", (frm, to, item_id("RAW-EX-02")))
    r1 = c.post(f"{MAT05}/calc", data={"frm": frm, "to": to})
    assert r1.status_code == 200 and r1.json()["rows"] >= 1
    n1 = conn.q1("select count(*) as n from mat_requirement where period_from = %s and period_to = %s", (frm, to))["n"]
    r2 = c.post(f"{MAT05}/calc", data={"frm": frm, "to": to})
    n2 = conn.q1("select count(*) as n from mat_requirement where period_from = %s and period_to = %s", (frm, to))["n"]
    assert r2.json()["rows"] == r1.json()["rows"] and n1 == n2                                       # 재실행 멱등
    row = conn.q1("select * from mat_requirement where period_from = %s and period_to = %s and item_id = %s and source = 'calc'", (frm, to, raw))
    assert row["required_qty"] >= 20 and row["shortage_qty"] == max(row["required_qty"] - row["stock_qty"], 0)
    assert conn.q1("select count(*) as n from mat_requirement where period_from = %s and period_to = %s and source = 'hook'", (frm, to))["n"] == 1
    assert client("admin").post(f"{MAT05}/calc", data={"frm": frm, "to": to}).status_code == 403


@pytest.mark.fn("F-MAT-11")
def test_requirements_screen_by_period():
    c = client("admin")
    j = c.get(MAT05, params={"frm": "2031-01-01", "to": "2031-01-07"}).json()
    assert j["screen_id"] == "MAT-05" and isinstance(j["rows"], list)
    assert c.get(MAT05, params={"frm": "2031-01-09", "to": "2031-01-01"}).status_code == 422


@pytest.mark.fn("F-MAT-03")
def test_receipts_scan_entry_by_item_code():
    """MAT-01 ?item_code= 스캔 진입 — 품목 바코드 → 등록 폼의 품목 칸 · 없는 품목은 이 화면 422 재렌더 (디자이너2 이식 요청 4)."""
    c = client("field", device="pop")
    j = c.get(MAT01, params={"item_code": "RAW-EX-01"}).json()
    assert j["item_id_default"] == item_id("RAW-EX-01") and j["scan_item"]["item_code"] == "RAW-EX-01"
    html = c.get(MAT01, params={"item_code": "RAW-EX-01"}, headers=HTML).text
    assert html.count("data-scan") == 1 and f'value="{item_id("RAW-EX-01")}" selected' in html
    miss = c.get(MAT01, params={"item_code": "NO-SUCH-ITEM"})
    assert miss.status_code == 422 and miss.json()["code"] == "validation_error" and miss.json()["screen_id"] == "MAT-01"
    page = c.get(MAT01, params={"item_code": "NO-SUCH-ITEM"}, headers=HTML)
    assert page.status_code == 422 and page.text.count("data-scan") == 1 and 'id="scan-result"' in page.text
    assert c.get(MAT01, params={"item_code": "PRD-EX-01"}).status_code == 422          # 제품은 입고 품목이 아니다
