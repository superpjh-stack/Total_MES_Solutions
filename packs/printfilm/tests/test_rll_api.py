"""rll — F-X-RLL-01~07 (개발2). 권한: 생산 · 현장 입력, 관리자 · 품질 조회. 계보는 lineage.merge/split 만."""

from __future__ import annotations

import pytest

from mescore.app import lineage
from mescore.db import conn

from _helpers import HTML, P, client, equipment_id, new_job, receive, run_print, slit, splice

FN, SL, HI = P["X-RLL-01"], P["X-RLL-02"], P["X-RLL-03"]


def _two_rolls(job=None) -> tuple[dict, dict, dict]:
    m = receive("EX-RM-01", 100)
    job = job or new_job()
    return job, run_print(job, [(m["lot_no"], 10)], 100), run_print(job, [(m["lot_no"], 10)], 100)


@pytest.mark.fn("F-X-RLL-01")
def test_finishing_one_to_one():
    c = client("field")
    job, r1, r2 = _two_rolls()
    r = c.post(FN, data={"roll_no": r1["lot_no"], "equipment_id": equipment_id("EX-EQ-02"), "length_m": "900", "width_mm": "1000"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["relation"] == "후가공" and body["label_url"].endswith("/label")
    g = conn.q1("select relation, relation_base from lot_genealogy where child_lot_id = %s", (body["id"],))
    assert g == {"relation": "후가공", "relation_base": "합병"}
    lot = conn.q1("select l.kind, l.process_id, l.equipment_id, l.attrs, l.work_order_id, x.process_type from lot l join x_printfilm_lot_ext x on x.id = l.id where l.id = %s", (body["id"],))
    assert lot["kind"] == "ROLL" and lot["process_type"] == "후가공" and lot["equipment_id"] == equipment_id("EX-EQ-02") and lot["attrs"] == {"length_m": 900, "width_mm": 1000}
    assert lot["process_id"] == conn.q1("select process_id from bas_equipment where id = %s", (equipment_id("EX-EQ-02"),))["process_id"] and lot["work_order_id"] == job["id"]
    assert lineage.state(r1["lot_id"]) == "소진"
    assert c.post(FN, data={"roll_no": r1["lot_no"]}).status_code == 422                                                 # 소진된 롤
    assert "splice" in c.post(FN, data={"roll_no": f"{r2['lot_no']},{r2['lot_no']}"}).json()["message"]                   # 2개 이상 → splice 로
    assert c.post(FN, data={"roll_no": "NOPE"}).status_code == 422
    assert client("qc").post(FN, data={"roll_no": r2["lot_no"]}).status_code == 403


@pytest.mark.fn("F-X-RLL-02")
def test_splice_rules():
    job, r1, r2 = _two_rolls()
    assert splice([r1["lot_no"]], expect=422)["message"].startswith("splice 는 롤 2개")
    assert splice([r1["lot_no"], r1["lot_no"]], expect=422)["code"] == "validation_error"                               # 중복
    assert splice([r1["lot_no"], "NOPE"], expect=422)["code"] == "validation_error"
    # 다른 Job 의 롤 — work_order_no 필수 · 부모 Job 중 하나
    other = new_job()
    m = receive("EX-RM-02", 10)
    r3 = run_print(other, [(m["lot_no"], 1)], 10)
    assert "서로 다릅니다" in splice([r1["lot_no"], r3["lot_no"]], expect=422)["message"]
    third = new_job()
    assert "중 하나" in splice([r1["lot_no"], r3["lot_no"]], work_order_no=third["work_order_no"], expect=422)["message"]
    ok = splice([r1["lot_no"], r3["lot_no"]], work_order_no=other["work_order_no"])
    assert conn.q1("select work_order_id from lot where id = %s", (ok["id"],))["work_order_id"] == other["id"]
    assert conn.q1("select count(*) as n from lot_genealogy where child_lot_id = %s and relation = 'splice'", (ok["id"],))["n"] == 2
    # 마감된 Job 의 롤 → 422 (lineage._lock_work_order)
    m2 = receive("EX-RM-01", 10)
    jc = new_job()
    a, b = run_print(jc, [(m2["lot_no"], 1)], 10), run_print(jc, [(m2["lot_no"], 1)], 10)
    assert client("prod").post(f"{P['JOB-01']}/{jc['id']}/close").status_code == 200
    assert splice([a["lot_no"], b["lot_no"]], expect=422)["code"] == "validation_error"


@pytest.mark.fn("F-X-RLL-03")
def test_finishing_screen_stacks_rolls():
    c = client("field")
    job, r1, r2 = _two_rolls()
    body = c.get(FN, params={"rolls": r1["lot_no"]}).json()
    assert [n["no"] for n in body["stack"]] == [r1["lot_no"]] and body["template"] == "rll/finishing.html"
    body = c.get(FN, params={"stacked": r1["lot_no"], "rolls": r2["lot_no"]}).json()
    assert [n["no"] for n in body["stack"]] == [r1["lot_no"], r2["lot_no"]]
    dup = c.get(FN, params={"rolls": f"{r1['lot_no']},{r1['lot_no']}"})
    assert dup.status_code == 422 and dup.json()["code"] == "validation_error" and len(dup.json()["stack"]) == 1
    miss = c.get(FN, params={"rolls": "NOPE"}, headers=HTML)
    assert miss.status_code == 422 and miss.text.count("data-scan") == 1
    splice([r1["lot_no"], r2["lot_no"]])
    assert c.get(FN, params={"rolls": r1["lot_no"]}).status_code == 422                                                   # 재고 아님
    rows = c.get(FN).json()["rows"]
    assert rows and rows[0]["parents"] and all(x["state"] in ("재고", "소진", "출하") for x in rows)


@pytest.mark.fn("F-X-RLL-04")
def test_slitting_create():
    job, r1, r2 = _two_rolls()
    body = slit(r1["lot_no"], 3, "300,300,400")
    assert body["relation"] == "슬리팅" and [l["slit_seq"] for l in body["lots"]] == [1, 2, 3]
    ids = [l["id"] for l in body["lots"]]
    assert conn.q1("select count(*) as n from lot_genealogy where parent_lot_id = %s and relation = '슬리팅' and relation_base = '분할'", (r1["lot_id"],))["n"] == 3
    ext = conn.q("select x.slit_seq, l.attrs, l.equipment_id from x_printfilm_lot_ext x join lot l on l.id = x.id where x.id = any(%s) order by x.slit_seq", (ids,))
    assert [e["attrs"]["width_mm"] for e in ext] == [300, 300, 400] and all(e["attrs"]["length_m"] == 2000 for e in ext) and all(e["equipment_id"] == equipment_id("EX-EQ-03") for e in ext)
    assert lineage.state(r1["lot_id"]) == "소진"
    assert slit(r1["lot_no"], 2, expect=422)["code"] == "validation_error"                                                 # 재고 아님
    assert slit(r2["lot_no"], 0, expect=422)["message"].startswith("슬리팅 수는 1")   # t(): 분할 → 슬리팅
    assert slit(r2["lot_no"], 1, expect=422)["message"].startswith("슬리팅은 2")
    assert "개수" in slit(r2["lot_no"], 2, "100", expect=422)["message"]
    assert client("admin").post(SL, data={"roll_no": r2["lot_no"], "count": "2"}).status_code == 403
    no_w = slit(r2["lot_no"], 2, "")
    assert all(conn.q1("select attrs from lot where id = %s", (l["id"],))["attrs"] == {"length_m": 2000} for l in no_w["lots"])


@pytest.mark.fn("F-X-RLL-05")
def test_slitting_screen_labels():
    c = client("field")
    job, r1, r2 = _two_rolls()
    body = slit(r1["lot_no"], 2, "500,500")
    j = c.get(SL, params={"parent": r1["lot_no"]}).json()
    assert j["parent"]["no"] == r1["lot_no"] and [l["lot_no"] for l in j["labels"]] == [l["lot_no"] for l in body["lots"]] and j["labels"][0]["slit_seq"] == 1
    html = c.get(SL, params={"parent": r1["lot_no"]}, headers=HTML).text
    assert html.count('data-barcode="') == 2 and all(f'aria-label="{l["lot_no"]}"' in html for l in body["lots"]) and html.count("data-scan") == 1
    miss = c.get(SL, params={"parent": "NOPE"})
    assert miss.status_code == 422 and miss.json()["code"] == "validation_error"
    rows = c.get(SL).json()["rows"]
    assert {r["slit_seq"] for r in rows} >= {1, 2}


@pytest.mark.fn("F-X-RLL-06")
def test_history_screen():
    c = client("field")
    job, r1, r2 = _two_rolls()
    fz = splice([r1["lot_no"], r2["lot_no"]])
    sp = slit(fz["lot_no"], 2, "500,500")
    s1 = sp["lots"][0]
    body = c.get(HI, params={"no": s1["lot_no"]}).json()
    assert body["roll"]["process_type"] == "슬리팅" and body["roll"]["slit_seq"] == 1 and body["roll"]["work_order_no"] == job["work_order_no"] and body["roll"]["state"] == "재고"
    assert [e["parent"]["no"] for e in body["parents"]] == [fz["lot_no"]] and body["children"] == []
    assert {r["lot_no"] for r in body["results"]} == {r1["lot_no"], r2["lot_no"]}                                          # 조상 인쇄 롤의 실적
    assert all(r["inputs"] and r["good_qty"] == 100 for r in body["results"])
    m = conn.q1("select lot_no from lot where kind_base = 'MATERIAL' order by id desc limit 1")["lot_no"]
    miss = c.get(HI, params={"no": m}, headers=HTML)
    assert miss.status_code == 422 and miss.text.count("data-scan") == 1 and "롤이 아닌" in miss.text
    assert c.get(HI, params={"no": "NOPE"}).status_code == 422
    assert c.get(HI).status_code == 200 and client("qc").get(HI, params={"no": fz["lot_no"]}).status_code == 200


@pytest.mark.fn("F-X-RLL-07")
def test_roll_label():
    c = client("field")
    job, r1, r2 = _two_rolls()
    html = c.get(f"{HI}/{r1['lot_no']}/label", headers=HTML).text
    assert f'aria-label="{r1["lot_no"]}"' in html and "인쇄" in html and job["work_order_no"] in html and "생산 LOT" not in html
    assert c.get(f"{HI}/{r1['lot_no']}/label", params={"size": "50x30"}, headers=HTML).status_code == 200
    assert c.get(f"{HI}/{r1['lot_no']}/label", params={"size": "1x1"}).status_code == 422
    assert c.get(f"{HI}/NOPE/label").status_code == 404
    # 코어 POP-04 로 같은 롤을 찍어도 팩 양식 (kind=ROLL 분기 · 바코드 = 번호)
    pop = c.get(P["POP-04"], params={"lot": r1["lot_id"]}, headers=HTML).text
    assert f'aria-label="{r1["lot_no"]}"' in pop and "data-kind=\"ROLL\"" in pop
    assert lineage.resolve(r1["lot_no"]).id == r1["lot_id"]
