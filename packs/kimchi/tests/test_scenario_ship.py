"""S2 — 금속검출 미통과 배치 출하 승인 금지 (gates.yaml S2 · validate_shipment · on_inspection_judged · 개발3).

X2 금속검출 NG 판정 → qua_issue(source=hook) +1 · 재판정 +0 → 포장 K2 → 최종 합격 → SHP-02 스캔 → 승인 **422 hook_rejected** · 출하 `등록` 그대로 · 계보 변화 0.
변형: 금속검출 검사를 아예 하지 않은 X3 → K3 → 승인 422(합격 기록 없음). 재검사 OK 뒤에는 승인 통과.
"""

from __future__ import annotations

import pytest

from _helpers import ITEM_GARLIC, ITEM_PEPPER, approve, client, inspect, lot_by_no, new_shipment, receive_and_pass, run_result, scan_ship, work_order
from mescore.db import conn


def _mix_batch(prod, qa) -> dict:
    m2, m3 = receive_and_pass(ITEM_PEPPER, 50, prod=prod, qa=qa), receive_and_pass(ITEM_GARLIC, 10, prod=prod, qa=qa)
    return run_result(prod, work_order("P06", "FL-01", qty=60), [(m2["lot_no"], 50), (m3["lot_no"], 10)], 60, equip_code="FL-01")


def _pack(prod, qa, x_lot_no: str, qty: float = 60) -> dict:
    k = run_result(prod, work_order("P08", "AP-01", qty=qty), [(x_lot_no, qty)], qty, equip_code="AP-01")
    inspect(qa, k["lot_no"], "최종", "합격", pack_weight_kg=10)
    return k


def _hook_issues() -> int:
    return conn.q1("select count(*) as n from qua_issue where source = 'hook'")["n"]


@pytest.mark.fn("F-X-ALM-03")
def test_s2_block_metal_ng():
    prod, qa = client("prod"), client("qa")
    x2 = _mix_batch(prod, qa)
    before = _hook_issues()
    j = inspect(qa, x2["lot_no"], "공정", "불합격", metal_detect="NG", inspect_qty=85, ng_qty=2, defect_qty=2)
    assert _hook_issues() == before + 1
    issue = conn.q1("select * from qua_issue where inspection_id = %s and source = 'hook'", (j["inspection_id"],))
    assert "CCP 이탈" in issue["content"] and "[metal_detect]" in issue["content"] and "NG" in issue["content"] and "불합격 수량 2" in issue["content"]
    assert issue["status"] == "발생" and issue["lot_id"] == x2["lot_id"]
    # 알람 이력 화면에 읽기 전용 행으로 합쳐 보인다
    alm = client("qa").get("/alm/alarms").json()
    assert any(r["alarm_no"] == issue["issue_no"] and r["source"] == "qua_issue" for r in alm["rows"])
    # 포장 K2 (코어 F-POP-06 은 PRODUCT 재고면 받는다) → 최종 합격 → 출하 승인 422
    k2 = _pack(prod, qa, x2["lot_no"])
    s = new_shipment(prod)
    assert scan_ship(prod, s["shipment_no"], k2["lot_no"]).status_code == 200
    g_before = conn.q1("select count(*) as n from lot_genealogy")["n"]
    r = approve(prod, s["id"])
    assert r.status_code == 422 and r.json()["code"] == "hook_rejected", r.text
    assert "CCP 불합격" in r.json()["message"] and k2["lot_no"] in r.json()["message"]
    assert conn.q1("select status from shp_shipment where id = %s", (s["id"],))["status"] == "등록"
    assert conn.q1("select count(*) as n from lot_genealogy")["n"] == g_before
    assert _hook_issues() == before + 1                                         # 승인 시도는 이슈를 더 만들지 않는다
    # 재검사 OK → 합격 → 승인 통과
    inspect(qa, x2["lot_no"], "공정", "합격", metal_detect="OK", inspect_qty=85, ng_qty=0)
    assert _hook_issues() == before + 1
    ok = approve(prod, s["id"])
    assert ok.status_code == 200, ok.text


@pytest.mark.fn("F-X-AGE-04")
def test_s2_variant_no_metal_inspection_blocks():
    prod, qa = client("prod"), client("qa")
    x3 = _mix_batch(prod, qa)                                                   # 금속검출 검사를 하지 않았다
    k3 = _pack(prod, qa, x3["lot_no"])
    s = new_shipment(prod)
    assert scan_ship(prod, s["shipment_no"], k3["lot_no"]).status_code == 200    # 스캔은 통과 (K3 자체는 최종 합격)
    r = approve(client("admin"), s["id"])
    assert r.status_code == 422 and r.json()["code"] == "hook_rejected" and "금속검출 합격 기록" in r.json()["message"], r.text
    assert conn.q1("select status from shp_shipment where id = %s", (s["id"],))["status"] == "등록"
    # 숙성 배치 라벨 — 코어 양식 재사용 (F-X-AGE-04) : 포장 LOT 으로 바코드 왕복
    html = prod.get(f"/age/stock/{k3['lot_id']}/label", headers={"accept": "text/html"}).text
    assert f'aria-label="{k3["lot_no"]}"' in html
    assert lot_by_no(k3["lot_no"])["id"] == k3["lot_id"]
