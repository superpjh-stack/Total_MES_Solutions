"""품질 qua — F-QUA-01~11 을 TestClient(JSON) 로 한 기능씩 (개발2). 역할: 품질(qa) 입력 · 그 밖 조회."""

from __future__ import annotations

from datetime import date

import pytest

from mescore.app import nav
from mescore.db import conn

from _dev2_helpers import HTML, client, item_id, new_work_order, process_id, uniq

QUA01, QUA02, QUA03, QUA04, POP02 = (nav.path_of(s) for s in ("QUA-01", "QUA-02", "QUA-03", "QUA-04", "POP-02"))


def product_lot(good: float = 10) -> dict:
    c = client("prod")
    wo = new_work_order(process_code="PRC-EX-02")
    s = c.post(f"{POP02}/start", data={"work_order_id": wo["id"]}).json()
    body = c.post(f"{POP02}/{s['id']}/end", data={"good_qty": good}).json()
    assert body["ok"], body
    return body


@pytest.mark.fn("F-QUA-01")
def test_plan_create_n_lines():
    c = client("qa")
    k1, k2 = uniq("K").lower(), uniq("K").lower()
    r = c.post(QUA01, data={"insp_type": "최종", "item_id": item_id("PRD-EX-01"), "item_key": [k1, k2], "label": ["항목 1 (예시)", "항목 2 (예시)"],
                            "unit": ["mm", ""], "value_type": ["number", "text"], "standard": ["", "양호"], "min_value": ["1", ""], "max_value": ["5", ""]})
    assert r.status_code == 200 and r.json()["items"] == 2
    rows = conn.q("select * from qua_insp_plan where id = any(%s) order by seq", (r.json()["ids"],))
    assert [x["item_key"] for x in rows] == [k1, k2] and rows[0]["min_value"] == 1 and rows[1]["value_type"] == "text"
    assert c.post(QUA01, data={"insp_type": "최종", "item_id": item_id("PRD-EX-01"), "item_key": k1, "label": "x"}).status_code == 422     # 중복 키
    assert c.post(QUA01, data={"insp_type": "최종", "item_key": "x"}).status_code == 422                                                 # 품목 · 공정 둘 다 없음
    assert c.post(QUA01, data={"insp_type": "검수", "item_id": item_id("PRD-EX-01"), "item_key": "x"}).status_code == 422                # 모르는 유형
    assert c.post(QUA01, data={"insp_type": "최종", "item_id": item_id("PRD-EX-01")}).status_code == 422                                 # 항목 0줄
    assert client("prod").post(QUA01, data={"insp_type": "최종", "item_id": item_id("PRD-EX-01"), "item_key": "y"}).status_code == 403


@pytest.mark.fn("F-QUA-02")
def test_plan_update_keeps_recorded_keys():
    c = client("qa")
    key = uniq("K").lower()
    pid = c.post(QUA01, data={"insp_type": "공정", "process_id": process_id("PRC-EX-02"), "item_key": key, "label": "항목 (예시)", "min_value": "1", "max_value": "2"}).json()["ids"][0]
    r = c.post(f"{QUA01}/{pid}", data={"max_value": "9", "standard": "1~9"})
    assert r.status_code == 200 and conn.q1("select max_value, standard from qua_insp_plan where id = %s", (pid,)) == {"max_value": 9, "standard": "1~9"}
    assert c.post(f"{QUA01}/{pid}", data={"use_yn": "N"}).status_code == 200                       # 기록 없으면 끌 수 있다
    assert c.post(f"{QUA01}/{pid}", data={"use_yn": "Y"}).status_code == 200
    lot = product_lot()
    assert c.post(QUA02, data={"insp_type": "공정", "lot_no": lot["lot_no"], f"i_{key}": "1.5"}).status_code == 200
    assert c.post(f"{QUA01}/{pid}", data={"use_yn": "N"}).status_code == 422                       # 기록된 키는 못 지운다
    assert c.post(f"{QUA01}/999999", data={"label": "x"}).status_code == 404
    assert client("field").post(f"{QUA01}/{pid}", data={"label": "x"}).status_code == 403


@pytest.mark.fn("F-QUA-03")
def test_plans_screen_filters():
    c = client("admin")
    j = c.get(QUA01, params={"insp_type": "입고"}).json()
    assert j["screen_id"] == "QUA-01" and all(r["insp_type"] == "입고" for r in j["rows"])
    assert c.get(QUA01, params={"insp_type": "검수"}).status_code == 422
    assert c.get(QUA01, headers=HTML).status_code == 200


@pytest.mark.fn("F-QUA-04")
def test_inspection_create_pending_judgement_and_shipped_lot_422():
    c = client("qa")
    key = uniq("K").lower()
    c.post(QUA01, data={"insp_type": "최종", "item_id": item_id("PRD-EX-01"), "item_key": key, "label": "최종 항목 (예시)", "min_value": "0", "max_value": "1"})
    lot = product_lot()
    r = c.post(QUA02, data={"insp_type": "최종", "lot_no": lot["lot_no"], f"i_{key}": "2"})
    assert r.status_code == 200 and r.json()["items"] == 1 and r.json()["deviated"] == [key]
    insp = conn.q1("select * from qua_inspection where id = %s", (r.json()["id"],))
    assert insp["judgement"] is None and insp["insp_type"] == "최종" and insp["inspector"] == "qa"
    assert conn.q1("select insp_status from lot where id = %s", (lot["lot_id"],))["insp_status"] == "미검사"      # 판정 전
    assert c.post(QUA02, data={"insp_type": "최종", "lot_no": "NO-SUCH"}).status_code == 422
    assert c.post(QUA02, data={"insp_type": "최종", "lot_no": lot["lot_no"], f"i_{key}": "x"}).status_code == 422
    # 출하된 LOT 422
    from mescore.app import lineage
    from _dev2_helpers import new_shipment
    ship = new_shipment()
    with conn.tx() as cur:
        lineage.ship(cur, shipment_id=ship["id"], lot_id=lot["lot_id"], by="test")
    assert c.post(QUA02, data={"insp_type": "최종", "lot_no": lot["lot_no"]}).status_code == 422
    assert client("prod").post(QUA02, data={"insp_type": "최종", "lot_no": lot["lot_no"]}).status_code == 403


@pytest.mark.fn("F-QUA-05")
def test_judge_sets_lot_status_and_defects():
    c = client("qa")
    lot = product_lot()
    insp_id = c.post(QUA02, data={"insp_type": "공정", "lot_no": lot["lot_no"]}).json()["id"]
    assert c.post(f"{QUA02}/{insp_id}/judge", data={"judgement": "불합격"}).status_code == 422                   # 불량코드 없음
    dc = conn.q1("select id from bas_defect_code limit 1")["id"]
    r = c.post(f"{QUA02}/{insp_id}/judge", data={"judgement": "불합격", "defect_code_id": [str(dc)], "defect_qty": ["2"]})
    assert r.status_code == 200 and r.json()["defects"] == 1
    assert conn.q1("select insp_status from lot where id = %s", (lot["lot_id"],))["insp_status"] == "불합격"
    assert conn.q1("select judgement, judged_by from qua_inspection where id = %s", (insp_id,)) == {"judgement": "불합격", "judged_by": "qa"}
    assert conn.q1("select qty from qua_defect where inspection_id = %s", (insp_id,))["qty"] == 2
    assert c.post(f"{QUA02}/{insp_id}/judge", data={"judgement": "합격"}).status_code == 422                      # 판정 뒤 수정은 새 검사로
    insp2 = c.post(QUA02, data={"insp_type": "공정", "lot_no": lot["lot_no"]}).json()["id"]
    assert c.post(f"{QUA02}/{insp2}/judge", data={"judgement": "합격"}).status_code == 200
    assert conn.q1("select insp_status from lot where id = %s", (lot["lot_id"],))["insp_status"] == "합격"           # 최신 검사 기준
    assert c.post(f"{QUA02}/999999/judge", data={"judgement": "합격"}).status_code == 404
    assert client("admin").post(f"{QUA02}/{insp2}/judge", data={"judgement": "합격"}).status_code == 403
    assert conn.q1("select count(*) as n from sys_access_log where kind = 'change' and fn_id = 'F-QUA-05' and target = %s", (f"qua_inspection:{insp2}",))["n"] == 1


@pytest.mark.fn("F-QUA-06")
def test_inspections_screen_scan_and_rerender_422():
    c = client("qa")
    lot = product_lot()
    j = c.get(QUA02, params={"no": lot["lot_no"]}).json()
    assert j["lot"]["no"] == lot["lot_no"] and j["insp_type"] == "공정" and isinstance(j["fields"], list)
    miss = c.get(QUA02, params={"no": "NO-SUCH"})
    assert miss.status_code == 422 and miss.json()["code"] == "validation_error" and miss.json()["screen_id"] == "QUA-02"
    html = c.get(QUA02, params={"no": "NO-SUCH", "device": "pop"}, headers=HTML)
    assert html.status_code == 422 and html.text.count("data-scan") == 1 and 'id="scan-result"' in html.text
    assert c.get(QUA02, params={"frm": date.today().isoformat(), "judgement": "합격"}).status_code == 200
    assert c.get(QUA02, params={"judgement": "보류"}).status_code == 422
    assert client("field").get(QUA02 + "?device=pop").status_code == 200


@pytest.mark.fn("F-QUA-07")
def test_defect_stats_uses_stats_quality():
    c = client("admin")
    j = c.get(QUA03, params={"frm": date.today().isoformat(), "to": date.today().isoformat()}).json()
    assert j["screen_id"] == "QUA-03" and isinstance(j["rows"], list)
    assert c.get(QUA03, headers=HTML).status_code == 200


@pytest.mark.fn("F-QUA-08")
def test_issue_create_numbered():
    c = client("qa")
    r = c.post(QUA04, data={"content": "이상 (예시)", "process_id": process_id(), "cause": "원인 (예시)"})
    assert r.status_code == 200 and r.json()["status"] == "발생" and r.json()["issue_no"]
    row = conn.q1("select * from qua_issue where id = %s", (r.json()["id"],))
    assert row["source"] == "manual" and row["status"] == "발생" and row["issue_no"] == r.json()["issue_no"]
    assert c.post(QUA04, data={"content": ""}).status_code == 422
    assert c.post(QUA04, data={"content": "x", "lot_no": "NO-SUCH"}).status_code == 422
    assert client("prod").post(QUA04, data={"content": "x"}).status_code == 403


@pytest.mark.fn("F-QUA-09")
def test_issue_action():
    c = client("qa")
    iid = c.post(QUA04, data={"content": "이상 (예시)"}).json()["id"]
    assert c.post(f"{QUA04}/{iid}/action", data={"action": ""}).status_code == 422
    r = c.post(f"{QUA04}/{iid}/action", data={"action": "조치 (예시)", "action_by": "담당 (예시)"})
    assert r.status_code == 200 and conn.q1("select status, action_by from qua_issue where id = %s", (iid,)) == {"status": "조치", "action_by": "담당 (예시)"}
    assert c.post(f"{QUA04}/999999/action", data={"action": "x"}).status_code == 404


@pytest.mark.fn("F-QUA-10")
def test_issue_close_requires_action():
    c = client("qa")
    iid = c.post(QUA04, data={"content": "이상 (예시)"}).json()["id"]
    assert c.post(f"{QUA04}/{iid}/close").status_code == 422                       # 조치 없음
    c.post(f"{QUA04}/{iid}/action", data={"action": "조치 (예시)"})
    assert c.post(f"{QUA04}/{iid}/close").status_code == 200
    assert conn.q1("select status from qua_issue where id = %s", (iid,))["status"] == "종결"
    assert c.post(f"{QUA04}/{iid}/close").status_code == 422                       # 이미 종결
    assert c.post(f"{QUA04}/{iid}/action", data={"action": "x"}).status_code == 422   # 종결 뒤 조치 추가 불가


@pytest.mark.fn("F-QUA-11")
def test_issues_screen_filters():
    c = client("admin")
    j = c.get(QUA04, params={"status": "발생"}).json()
    assert j["screen_id"] == "QUA-04" and all(r["status"] == "발생" for r in j["rows"])
    assert c.get(QUA04, params={"status": "삭제"}).status_code == 422


@pytest.mark.fn("F-QUA-04")
def test_inspection_process_choice_defaults_to_lot_process():
    """QUA-02 검사 공정 — 기본은 LOT 의 공정 · 고르면 그 공정의 계획 항목 (혼합 LOT 에 다른 공정 검사 · 개발3 §3-18)."""
    c = client("qa")
    own, other = uniq("K").lower(), uniq("K").lower()
    assert c.post(QUA01, data={"insp_type": "공정", "process_id": process_id("PRC-EX-02"), "item_key": own, "label": "LOT 공정 항목 (예시)"}).status_code == 200
    assert c.post(QUA01, data={"insp_type": "공정", "process_id": process_id("PRC-EX-01"), "item_key": other, "label": "다른 공정 항목 (예시)",
                               "min_value": "0", "max_value": "1"}).status_code == 200
    lot = product_lot()                                                                        # PRC-EX-02 LOT
    j = c.get(QUA02, params={"no": lot["lot_no"]}).json()
    keys = {x["param_key"] for x in j["fields"]}
    assert j["insp_process_id"] == process_id("PRC-EX-02") and own in keys and other not in keys
    j2 = c.get(QUA02, params={"no": lot["lot_no"], "process_id": process_id("PRC-EX-01")}).json()
    keys2 = {x["param_key"] for x in j2["fields"]}
    assert j2["insp_process_id"] == process_id("PRC-EX-01") and other in keys2 and own not in keys2
    assert any(int(v) == process_id("PRC-EX-01") for v, _ in j2["process_options"])
    r = c.post(QUA02, data={"insp_type": "공정", "lot_no": lot["lot_no"], "process_id": process_id("PRC-EX-01"), f"i_{other}": "3"})
    assert r.status_code == 200 and r.json()["process_id"] == process_id("PRC-EX-01") and r.json()["deviated"] == [other]
    assert c.post(QUA02, data={"insp_type": "공정", "lot_no": lot["lot_no"], "process_id": "999999"}).status_code == 422
    assert c.get(QUA02, params={"no": lot["lot_no"], "process_id": "999999"}).status_code == 422
    html = c.get(QUA02, params={"no": lot["lot_no"]}, headers=HTML).text
    assert html.count("data-scan") == 1 and 'name="process_id"' in html
