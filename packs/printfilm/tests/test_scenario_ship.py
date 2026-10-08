"""G-P04 S2 — 불합격 롤 출하 금지: 스캔 422(코어 F-SHP-05) + 승인 422 hook_rejected(validate_shipment) · 다른 Job 의 롤 422 (gates.yaml: S2 · 개발2)."""

from __future__ import annotations

import pytest

from mescore.db import conn

from _helpers import P, approve, client, inspect, inspect_register, judge, new_job, new_shipment, receive, run_print, s1_upto_slitting, scan


@pytest.mark.fn("F-X-RLL-04")
def test_block_failed_roll():
    x = s1_upto_slitting()
    s1, s2, s3 = x["s1"], x["s2"], x["s3"]
    # 2. S① 불합격 (불량코드 1줄)
    inspect(s1["lot_no"], "불합격", delta_e=5.0, defect="EX-DF-04", position="좌")
    assert conn.q1("select insp_status from lot where id = %s", (s1["id"],))["insp_status"] == "불합격"
    assert conn.q1("select count(*) as n from qua_defect d join qua_inspection i on i.id = d.inspection_id where i.lot_id = %s", (s1["id"],))["n"] == 1
    # 3 · 4. 스캔 422 (코어 — 불합격 · 미검사 D-504)
    ship = new_shipment()
    body = scan(ship["shipment_no"], s1["lot_no"], expect=422)
    assert body["code"] == "validation_error"
    body = scan(ship["shipment_no"], s3["lot_no"], expect=422)
    assert body["code"] == "validation_error"
    assert conn.q1("select count(*) as n from lot_genealogy g join lot l on l.id = g.child_lot_id where l.shipment_id = %s", (ship["id"],))["n"] == 0
    # 5. S② 합격 → 스캔 200
    inspect(s2["lot_no"], "합격", delta_e=1.0)
    pending = inspect_register(s2["lot_no"], delta_e=6.0)          # 재검사는 스캔 **전에** 등록돼 있어야 한다 — 스캔 뒤 새 검사 등록은 코어 F-QUA-04 가 422 (출하된 LOT · D-304)
    scan(ship["shipment_no"], s2["lot_no"])
    assert client("qc").post(P["QUA-02"], data={"insp_type": "최종", "lot_no": s2["lot_no"], "i_delta_e": "6"}).status_code == 422
    # 6. 스캔 뒤 (등록돼 있던 재검사를) 불합격 판정 — 승인 전이라 판정은 된다 → lot.insp_status 불합격
    judge(pending, "불합격", defect="EX-DF-01")
    assert conn.q1("select insp_status from lot where id = %s", (s2["id"],))["insp_status"] == "불합격"
    # 7. 승인 → 422 hook_rejected · 메시지에 S② · 상태 등록 그대로 · 출하 계보 1행 그대로
    body = approve(ship["id"], expect=422)
    assert body["code"] == "hook_rejected" and s2["lot_no"] in body["message"], body
    assert conn.q1("select status from shp_shipment where id = %s", (ship["id"],))["status"] == "등록"
    assert conn.q1("select count(*) as n from lot_genealogy g join lot l on l.id = g.child_lot_id where l.shipment_id = %s and g.relation = '출하'", (ship["id"],))["n"] == 1
    print("\nS2:", body["code"], "·", body["message"])


@pytest.mark.fn("F-X-RLL-02")
def test_block_mixed_job():
    """8. 다른 Job 의 롤을 같은 출하에 → 승인 422 hook_rejected '한 Job 의 롤만' (엘컴화인 D-16 · CR-3)."""
    m = receive("EX-RM-01", 100)
    ja, jb = new_job(), new_job()
    ra = run_print(ja, [(m["lot_no"], 10)], 100)
    rb = run_print(jb, [(m["lot_no"], 10)], 100)
    inspect(ra["lot_no"], "합격")
    inspect(rb["lot_no"], "합격")
    ship = new_shipment()
    scan(ship["shipment_no"], ra["lot_no"])
    scan(ship["shipment_no"], rb["lot_no"])
    body = approve(ship["id"], expect=422)
    assert body["code"] == "hook_rejected" and "한 Job" in body["message"], body
    assert conn.q1("select status from shp_shipment where id = %s", (ship["id"],))["status"] == "등록"


@pytest.mark.fn("F-X-RLL-01")
def test_block_non_roll_lot():
    """롤이 아닌 LOT(코어 PRODUCT — 인쇄가 아닌 공정의 실적은 훅이 거부하므로 lineage 로 직접 만든 LOT) 은 승인 422."""
    from mescore.app import lineage

    m = receive("EX-RM-01", 10)
    with conn.tx() as cur:
        plain = lineage.make_material_lot(cur, item_id=conn.q1("select id from bas_item where item_code = 'EX-FG-01'")["id"], qty=1, unit="m", by="test",
                                          insp_status="합격", kind="MATERIAL")
    ship = new_shipment()
    # 원재료 LOT 은 코어 스캔(lineage.ship)이 먼저 422 — 훅까지 오지 않는다 (코어가 더 엄격 · D-504 와 같은 취지)
    assert scan(ship["shipment_no"], plain["lot_no"], expect=422)["code"] == "validation_error"
    assert scan(ship["shipment_no"], m["lot_no"], expect=422)["code"] == "validation_error"
    assert client("field").get(P["SHP-02"], params={"no": ship["shipment_no"]}).status_code == 200
