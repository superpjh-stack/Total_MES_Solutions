"""생산실적 pop — F-POP-01~08 + 분할/합병 API(D-12) 를 TestClient(JSON) 로 한 기능씩 (개발2). 역할: 생산(prod) · 현장(field) 입력 · 관리자(admin) 조회."""

from __future__ import annotations

import pytest

from mescore.app import lineage, nav
from mescore.db import conn

from _dev2_helpers import HTML, client, item_id, new_work_order, partner_id

POP01, POP02, POP03, POP04, MAT01, MAT02 = (nav.path_of(s) for s in ("POP-01", "POP-02", "POP-03", "POP-04", "MAT-01", "MAT-02"))


def approved_material(qty: float = 100, item_code: str = "RAW-EX-01") -> dict:
    """입고 → 입고검사 합격 (API). {lot_id, lot_no}"""
    body = client("prod").post(MAT01, data={"item_id": item_id(item_code), "qty": qty, "partner_id": partner_id("SUP-EX-01")}).json()
    assert body["ok"]
    assert client("qa").post(MAT02, data={"lot_id": body["lot_id"], "judgement": "합격"}).status_code == 200
    return body


def start(c, wo: dict | None = None) -> dict:
    """PRC-EX-02 — 측정값 선언이 없는 공정(선언이 있는 PRC-EX-01 은 test_measure.py 가 쓴다)."""
    wo = wo or new_work_order(process_code="PRC-EX-02")
    r = c.post(f"{POP02}/start", data={"work_order_id": wo["id"]})
    assert r.status_code == 200, r.text
    return {**r.json(), "wo": wo}


@pytest.mark.fn("F-POP-01")
def test_work_list_scan_entry_redirects_or_rerenders_422():
    c = client("field", device="pop")
    wo = new_work_order()
    j = c.get(POP01).json()
    assert j["screen_id"] == "POP-01" and any(r["work_order_no"] == wo["work_order_no"] for r in j["rows"])
    ok = c.get(POP01, params={"no": wo["work_order_no"]})
    assert ok.status_code == 200 and ok.json()["next"] == f"{POP02}?wo={wo['id']}"
    html = c.get(POP01, params={"no": wo["work_order_no"]}, headers=HTML, follow_redirects=False)
    assert html.status_code == 303 and html.headers["location"] == f"{POP02}?wo={wo['id']}"
    miss = c.get(POP01, params={"no": "NO-SUCH-WO"})
    assert miss.status_code == 422 and miss.json()["code"] == "validation_error" and miss.json()["screen_id"] == "POP-01"
    page = c.get(POP01, params={"no": "NO-SUCH-WO"}, headers=HTML)
    assert page.status_code == 422 and page.text.count("data-scan") == 1 and 'id="scan-result"' in page.text and 'class="ch-pop"' in page.text
    closed = new_work_order(status="마감")
    assert c.get(POP01, params={"no": closed["work_order_no"]}).status_code == 422
    assert client("admin").get(POP01).status_code == 200                     # 관리자 조회


@pytest.mark.fn("F-POP-02")
def test_result_start_locks_order_and_refuses_double_start():
    c = client("prod")
    s = start(c)
    row = conn.q1("select * from pop_work_result where id = %s", (s["id"],))
    assert row["ended_at"] is None and row["work_order_id"] == s["wo"]["id"] and row["equipment_id"] == s["wo"]["equipment_id"]
    assert c.post(f"{POP02}/start", data={"work_order_id": s["wo"]["id"]}).status_code == 422          # 미종료 실적
    assert c.post(f"{POP02}/start", data={"work_order_no": "NO-SUCH"}).status_code == 422
    assert c.post(f"{POP02}/start", data={"work_order_id": new_work_order(status="취소")["id"]}).status_code == 422
    assert client("admin").post(f"{POP02}/start", data={"work_order_id": new_work_order()["id"]}).status_code == 403
    assert client("qa").post(f"{POP02}/start", data={"work_order_id": new_work_order()["id"]}).status_code == 403
    scr = c.get(POP02, params={"id": s["id"]}).json()
    assert scr["screen_id"] == "POP-02" and scr["result"]["id"] == s["id"] and isinstance(scr["params"], list)
    assert c.get(POP02, params={"wo": s["wo"]["id"]}).json()["results"][0]["id"] == s["id"]
    assert c.get(POP02).status_code == 200 and c.get(POP02, params={"id": 999999}).status_code == 404
    assert conn.q1("select count(*) as n from sys_access_log where kind = 'change' and fn_id = 'F-POP-02' and target = %s", (f"pop_work_result:{s['id']}",))["n"] == 1


@pytest.mark.fn("F-POP-03")
def test_result_end_creates_product_lot_with_input_lineage():
    c = client("prod")
    s = start(c)
    m = approved_material(50)
    assert c.post(POP03, data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": 20}).status_code == 200
    assert c.post(f"{POP02}/{s['id']}/end", data={"defect_qty": 1}).status_code == 422                 # 양품 필수
    r = c.post(f"{POP02}/{s['id']}/end", data={"good_qty": 40, "defect_qty": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    lot = conn.q1("select * from lot where id = %s", (body["lot_id"],))
    assert lot["kind"] == "PRODUCT" and lot["work_result_id"] == s["id"] and lot["qty"] == 40 and lot["work_order_id"] == s["wo"]["id"]
    g = conn.q("select * from lot_genealogy where child_lot_id = %s", (lot["id"],))
    assert len(g) == 1 and g[0]["parent_lot_id"] == m["lot_id"] and g[0]["relation"] == "투입" and g[0]["qty"] == 20
    assert conn.q1("select product_lot_id, ended_at, good_qty from pop_work_result where id = %s", (s["id"],))["product_lot_id"] == lot["id"]
    assert body["label_url"] == f"{POP04}?lot={lot['id']}"
    assert c.post(f"{POP02}/{s['id']}/end", data={"good_qty": 1}).status_code == 422                   # 재종료
    assert c.post(f"{POP02}/999999/end", data={"good_qty": 1}).status_code == 404
    assert client("admin").post(f"{POP02}/{s['id']}/end", data={"good_qty": 1}).status_code == 403
    # 종료 뒤 같은 지시를 다시 시작할 수 있다 (생산 LOT ②)
    assert c.post(f"{POP02}/start", data={"work_order_id": s["wo"]["id"]}).status_code == 200


@pytest.mark.fn("F-POP-04")
def test_stop_opens_then_closes():
    c = client("field")
    s = start(c)
    assert c.post(f"{POP02}/{s['id']}/stop", data={}).status_code == 422                                 # 사유 없음
    assert c.post(f"{POP02}/{s['id']}/stop", data={"reason_code": "NO-SUCH"}).status_code == 422
    r1 = c.post(f"{POP02}/{s['id']}/stop", data={"reason_code": "ETC"})
    assert r1.status_code == 200 and r1.json()["action"] == "opened"
    r2 = c.post(f"{POP02}/{s['id']}/stop", data={"reason_code": "ETC"})                                 # 열린 정지를 닫는다
    assert r2.status_code == 200 and r2.json()["action"] == "closed" and r2.json()["id"] == r1.json()["id"]
    assert conn.q1("select ended_at from pop_stop where id = %s", (r1.json()["id"],))["ended_at"] is not None
    r3 = c.post(f"{POP02}/{s['id']}/stop", data={"reason_code": "ETC", "started_at": "2026-10-09T10:00:00", "ended_at": "2026-10-09T10:12:00"})
    assert r3.status_code == 200 and r3.json()["action"] == "recorded"
    assert client("qa").post(f"{POP02}/{s['id']}/stop", data={"reason_code": "ETC"}).status_code == 403


@pytest.mark.fn("F-POP-05")
def test_scrap_is_allowed_after_end():
    c = client("prod")
    s = start(c)
    r = c.post(f"{POP02}/{s['id']}/scrap", data={"qty": 3, "defect_code_id": conn.q1("select id from bas_defect_code limit 1")["id"]})
    assert r.status_code == 200 and r.json()["qty"] == 3
    assert c.post(f"{POP02}/{s['id']}/scrap", data={"qty": 0}).status_code == 422
    assert c.post(f"{POP02}/{s['id']}/scrap", data={"qty": 1, "defect_code_id": 999999}).status_code == 422
    assert c.post(f"{POP02}/{s['id']}/end", data={"good_qty": 10}).status_code == 200
    assert c.post(f"{POP02}/{s['id']}/scrap", data={"qty": 2}).status_code == 200                       # 종료 후에도
    assert conn.q1("select sum(qty) as s from pop_scrap where work_result_id = %s", (s["id"],))["s"] == 5


@pytest.mark.fn("F-POP-06")
def test_input_scan_one_scan_one_row_and_422_cases():
    c = client("field", device="pop")
    s = start(c)
    m = approved_material(10)
    r1 = c.post(POP03, data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": 4})
    r2 = c.post(POP03, data={"work_result_id": s["id"], "barcode": f" {m['lot_no']} ", "qty": 6})
    assert r1.status_code == 200 and r2.status_code == 200 and r1.json()["id"] != r2.json()["id"]        # 두 번 스캔 = 2건
    assert conn.q1("select count(*) as n from pop_input where work_result_id = %s", (s["id"],))["n"] == 2
    assert conn.q1("select remain_qty from v_lot_stock where lot_id = %s", (m["lot_id"],))["remain_qty"] == 0
    assert conn.q1("select state from v_lot_state where lot_id = %s", (m["lot_id"],))["state"] == "소진"
    assert c.post(POP03, data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": 1}).status_code == 422       # 소진
    assert c.post(POP03, data={"work_result_id": s["id"], "barcode": "NO-SUCH-LOT", "qty": 1}).status_code == 422     # 없는 번호
    un = client("prod").post(MAT01, data={"item_id": item_id("RAW-EX-02"), "qty": 5}).json()                           # 미검사
    assert c.post(POP03, data={"work_result_id": s["id"], "barcode": un["lot_no"], "qty": 1}).status_code == 422
    assert client("qa").post(MAT02, data={"lot_id": un["lot_id"], "judgement": "불합격"}).status_code == 200           # 불합격
    assert c.post(POP03, data={"work_result_id": s["id"], "barcode": un["lot_no"], "qty": 1}).status_code == 422
    assert c.post(POP03, data={"work_result_id": 999999, "barcode": m["lot_no"]}).status_code == 404
    # 브라우저: 폼 POST 422 는 303 + 알림 (스캔칸 유지), 화면 ?no= 없는 번호는 422 재렌더
    r = c.post(POP03, data={"work_result_id": s["id"], "barcode": "NO-SUCH-LOT"}, headers=HTML, follow_redirects=False)
    assert r.status_code == 303
    page = c.get(POP03, params={"result": s["id"], "no": "NO-SUCH-LOT"}, headers=HTML)
    assert page.status_code == 422 and page.text.count("data-scan") == 1 and 'id="scan-result"' in page.text
    assert c.get(POP03, params={"result": s["id"]}).json()["rows"][0]["lot_no"] == m["lot_no"]
    assert c.get(POP03).status_code == 200
    assert client("admin").post(POP03, data={"work_result_id": s["id"], "barcode": m["lot_no"]}).status_code == 403


@pytest.mark.fn("F-POP-07")
def test_input_cancel_only_before_end_and_restores_stock():
    c = client("prod")
    s = start(c)
    m = approved_material(10)
    stock_before = conn.q1("select qty from mat_stock where item_id = %s", (item_id("RAW-EX-01"),))["qty"]
    i = c.post(POP03, data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": 7}).json()
    assert conn.q1("select qty from mat_stock where item_id = %s", (item_id("RAW-EX-01"),))["qty"] == stock_before - 7
    r = c.post(f"{POP03}/{i['id']}/cancel")
    assert r.status_code == 200 and conn.q1("select canceled_yn from pop_input where id = %s", (i["id"],))["canceled_yn"] == "Y"
    assert conn.q1("select qty from mat_stock where item_id = %s", (item_id("RAW-EX-01"),))["qty"] == stock_before
    assert conn.q1("select remain_qty from v_lot_stock where lot_id = %s", (m["lot_id"],))["remain_qty"] == 10
    assert c.post(f"{POP03}/{i['id']}/cancel").status_code == 422                                          # 이미 취소
    i2 = c.post(POP03, data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": 1}).json()
    assert c.post(f"{POP02}/{s['id']}/end", data={"good_qty": 1}).status_code == 200
    assert c.post(f"{POP03}/{i2['id']}/cancel").status_code == 422                                         # 종료 후
    assert c.post(f"{POP03}/999999/cancel").status_code == 404
    # 취소된 투입은 계보에 가지 않는다
    lot = conn.q1("select product_lot_id from pop_work_result where id = %s", (s["id"],))["product_lot_id"]
    assert conn.q1("select count(*) as n, sum(qty) as q from lot_genealogy where child_lot_id = %s", (lot,)) == {"n": 1, "q": 1}


@pytest.mark.fn("F-POP-08")
def test_product_lot_label_and_barcode_round_trip():
    c = client("prod")
    s = start(c)
    body = c.post(f"{POP02}/{s['id']}/end", data={"good_qty": 9}).json()
    j = c.get(POP04, params={"lot": body["lot_id"]}).json()
    assert j["lot_no"] == body["lot_no"] and j["kind_label"] == "생산 LOT" and j["work_order_no"] == s["wo"]["work_order_no"] and j["template"] == "print/label_lot.html"
    html = c.get(POP04, params={"lot": body["lot_id"]}, headers=HTML).text
    assert f'aria-label="{body["lot_no"]}"' in html and "<rect" in html and "cdn" not in html.lower()
    # 라벨의 바코드 값을 스캔칸에 넣으면 그 LOT 이 열린다 (G-C14) — POP-04 ?no= · lineage.resolve
    assert c.get(POP04, params={"no": body["lot_no"]}).json()["lot_no"] == body["lot_no"]
    assert lineage.resolve(body["lot_no"]).id == body["lot_id"]
    assert c.get(POP04, params={"no": "NO-SUCH"}).status_code == 422
    assert c.get(POP04).status_code == 200 and any(r["lot_no"] == body["lot_no"] for r in c.get(POP04).json()["rows"])
    assert c.get(POP04, params={"lot": 999999}).status_code == 404


def test_split_and_merge_api_d12():
    c = client("prod")
    s = start(c)
    body = c.post(f"{POP02}/{s['id']}/end", data={"good_qty": 90}).json()
    sp = c.post(f"{POP02}/{s['id']}/split", data={"count": 3, "qtys": "30,30,30"})
    assert sp.status_code == 200 and len(sp.json()["lots"]) == 3 and all(l["qty"] == 30 for l in sp.json()["lots"])
    assert conn.q1("select state from v_lot_state where lot_id = %s", (body["lot_id"],))["state"] == "소진"
    assert c.post(f"{POP02}/{s['id']}/split", data={"count": 2}).status_code == 422                     # 이미 소진
    ids = [l["id"] for l in sp.json()["lots"]]
    mg = c.post(f"{POP02}/{s['id']}/merge", data={"lot_ids": f"{ids[0]},{sp.json()['lots'][1]['lot_no']}"})
    assert mg.status_code == 200 and mg.json()["qty"] == 60
    assert conn.q1("select count(*) as n from lot_genealogy where child_lot_id = %s and relation = '합병'", (mg.json()["id"],))["n"] == 2
    assert c.post(f"{POP02}/{s['id']}/merge", data={"lot_ids": str(ids[2])}).status_code == 422          # 1개
    assert c.post(f"{POP02}/{s['id']}/merge", data={"lot_ids": "NO-SUCH"}).status_code == 422
    assert client("admin").post(f"{POP02}/{s['id']}/split", data={"count": 2}).status_code == 403
    page = c.get(POP02, params={"id": s["id"]}).json()
    assert {n["id"] for n in page["stock_lots"]} == {ids[2], mg.json()["id"]}


@pytest.mark.fn("F-POP-02")
def test_start_screen_defaults_worker_and_filters_equipment_by_process():
    """POP-02 — 작업자 기본 = 로그인 사용자의 sys_user.worker_id · 설비 선택지 = 지시 공정의 설비(+ 지시 지정 설비)만 (디자이너2 이식 요청 5)."""
    field_worker = conn.q1("select worker_id from sys_user where login_id = 'field'")["worker_id"]
    wo = new_work_order(process_code="PRC-EX-01", equip_code="EQ-EX-01")
    j = client("field", device="pop").get(POP02, params={"wo": wo["id"]}).json()
    assert j["worker_id_default"] == field_worker
    allowed = {r["id"] for r in conn.q("""select e.id from bas_equipment e join bas_process p on p.id = e.process_id
                                           where e.use_yn = 'Y' and p.process_code = 'PRC-EX-01'""")} | {wo["equipment_id"]}
    got = {int(v) for v, _ in j["equipment_options"]}
    assert got == allowed and got
    other = new_work_order(process_code="PRC-EX-02", equip_code="EQ-EX-03")
    got2 = {int(v) for v, _ in client("prod").get(POP02, params={"wo": other["id"]}).json()["equipment_options"]}
    assert other["equipment_id"] in got2 and not (got2 & (allowed - {other["equipment_id"]}))
    html = client("field", device="pop").get(POP02, params={"wo": wo["id"]}, headers=HTML).text
    if field_worker is not None:
        assert f'name="worker_id" value="{field_worker}" checked' in html


@pytest.mark.fn("F-POP-03")
def test_result_end_with_merge_parents_makes_one_lot():
    """F-POP-03 종료 폼의 합병 옵션 — 재고 생산 LOT(번호 · id 쉼표)을 이 실적의 LOT 에 `합병` 으로 잇는다. 별도 합병 LOT 없음 (개발3 §3-19)."""
    c = client("prod")
    s1 = start(c)
    b1 = c.post(f"{POP02}/{s1['id']}/end", data={"good_qty": 20}).json()
    s2 = start(c)
    b2 = c.post(f"{POP02}/{s2['id']}/end", data={"good_qty": 30}).json()
    s3 = start(c)
    m = approved_material(10)
    assert c.post(POP03, data={"work_result_id": s3["id"], "barcode": m["lot_no"], "qty": 5}).status_code == 200
    assert c.post(f"{POP02}/{s3['id']}/end", data={"good_qty": 55, "merge_lot_ids": "NO-SUCH"}).status_code == 422
    assert conn.q1("select ended_at from pop_work_result where id = %s", (s3["id"],))["ended_at"] is None       # 422 면 종료도 되돌린다
    r = c.post(f"{POP02}/{s3['id']}/end", data={"good_qty": 55, "merge_lot_ids": f"{b1['lot_no']}, {b2['lot_id']}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(body["merged"]) == sorted([b1["lot_id"], b2["lot_id"]])
    g = {(x["parent_lot_id"], x["relation"]) for x in conn.q("select * from lot_genealogy where child_lot_id = %s", (body["lot_id"],))}
    assert g == {(m["lot_id"], "투입"), (b1["lot_id"], "합병"), (b2["lot_id"], "합병")}
    assert conn.q1("select count(*) as n from lot where work_result_id = %s", (s3["id"],))["n"] == 1
    # 이미 합병된 LOT 을 다시 합병 → 422
    s4 = start(c)
    assert c.post(f"{POP02}/{s4['id']}/end", data={"good_qty": 1, "merge_lot_ids": b1["lot_no"]}).status_code == 422


@pytest.mark.fn("F-POP-06")
def test_input_screen_last_qty_skips_canceled():
    """POP-03 「투입량 직전 값 유지」 — 취소되지 않은 마지막 투입의 수량 (디자이너2 이식 요청 6)."""
    c = client("prod")
    s = start(c)
    m = approved_material(20)
    assert c.get(POP03, params={"result": s["id"]}).json()["last_qty"] is None
    c.post(POP03, data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": 3})
    i2 = c.post(POP03, data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": 7}).json()
    assert float(c.get(POP03, params={"result": s["id"]}).json()["last_qty"]) == 7.0
    c.post(f"{POP03}/{i2['id']}/cancel")
    assert float(c.get(POP03, params={"result": s["id"]}).json()["last_qty"]) == 3.0
    assert 'value="3' in c.get(POP03, params={"result": s["id"]}, headers=HTML).text


@pytest.mark.fn("F-POP-06")
def test_product_lot_open_inputs_count_against_remain():
    """DEF-QA2-001 — 반제품(PRODUCT) LOT 20 을 종료 전 실적 E 에 15 스캔 → 실적 F 에 15 스캔은 422 (열린 pop_input 도 잔량에서 뺀다). QA2 재현 절차 그대로."""
    c = client("prod")
    s0 = start(c)
    p = c.post(f"{POP02}/{s0['id']}/end", data={"good_qty": 20}).json()
    e, f = start(c), start(c)
    assert c.post(POP03, data={"work_result_id": e["id"], "barcode": p["lot_no"], "qty": 15}).status_code == 200
    r = c.post(POP03, data={"work_result_id": f["id"], "barcode": p["lot_no"], "qty": 15})
    assert r.status_code == 422 and r.json()["code"] == "validation_error", r.text
    assert conn.q1("select count(*) as n from pop_input where work_result_id = %s", (f["id"],))["n"] == 0
    assert c.post(POP03, data={"work_result_id": f["id"], "barcode": p["lot_no"], "qty": 5}).status_code == 200      # 잔량 5 까지는 받는다
    assert c.post(POP03, data={"work_result_id": f["id"], "barcode": p["lot_no"], "qty": 1}).status_code == 422
    # E 를 취소하면 그만큼 돌아온다
    i_e = conn.q1("select id from pop_input where work_result_id = %s", (e["id"],))["id"]
    assert c.post(f"{POP03}/{i_e}/cancel").status_code == 200
    assert c.post(POP03, data={"work_result_id": e["id"], "barcode": p["lot_no"], "qty": 15}).status_code == 200
    # 종료 뒤(계보 투입 행으로 셈)에도 두 번 세지 않고 넘치지 않는다
    assert c.post(f"{POP02}/{e['id']}/end", data={"good_qty": 15}).status_code == 200
    assert c.post(f"{POP02}/{f['id']}/end", data={"good_qty": 5}).status_code == 200
    k = conn.q1("select consumed_qty, remain_qty from v_lot_stock where lot_id = %s", (p["lot_id"],))
    assert float(k["consumed_qty"]) == 20.0 and float(k["remain_qty"]) == 0.0
    assert lineage.state(p["lot_id"]) == lineage.CONSUMED
