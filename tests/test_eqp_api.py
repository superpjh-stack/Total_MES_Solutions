"""설비 eqp — F-EQP-01~08 을 TestClient(JSON) 로 한 기능씩 (개발2). 설비 제어 엔드포인트 0 — 가동 상태 기록은 기록이다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mescore.app import collect, nav
from mescore.app.main import app
from mescore.db import conn

from _dev2_helpers import HTML, client, uniq

EQP01, EQP02, EQP03, EQP04 = (nav.path_of(s) for s in ("EQP-01", "EQP-02", "EQP-03", "EQP-04"))


@pytest.fixture()
def equip() -> dict:
    return conn.q1("insert into bas_equipment (equip_code, equip_name, collect_yn, created_by) values (%s, '시험 설비 (예시)', 'Y', 'test') returning id, equip_code", (uniq("EQ-T"),))


def test_no_control_endpoints():
    paths = {getattr(r, "path", "") for r in app.routes}
    bad = [p for p in paths if p.startswith("/eqp/") and any(w in p for w in ("control", "start", "stop", "command", "run"))]
    assert bad == []


@pytest.mark.fn("F-EQP-02")
def test_state_record_closes_previous_segment(equip):
    c = client("prod")
    r1 = c.post(EQP01, data={"equipment_id": equip["id"], "state": "가동"})
    assert r1.status_code == 200 and r1.json()["state"] == "가동"
    r2 = c.post(EQP01, data={"equipment_id": equip["id"], "state": "정지", "note": "교대 (예시)"})
    assert r2.status_code == 200
    rows = conn.q("select * from eqp_run_log where equipment_id = %s order by id", (equip["id"],))
    assert len(rows) == 2 and rows[0]["ended_at"] is not None and rows[1]["ended_at"] is None and rows[1]["state"] == "정지" and rows[1]["source"] == "manual"
    assert c.post(EQP01, data={"equipment_id": equip["id"], "state": "정지"}).json()["id"] == r2.json()["id"]      # 같은 상태면 새 구간 없음
    assert c.post(EQP01, data={"equipment_id": equip["id"], "state": "폭주"}).status_code == 422
    assert c.post(EQP01, data={"equipment_id": 999999, "state": "가동"}).status_code == 422
    assert c.post(EQP01, data={"equipment_id": equip["id"], "state": "가동", "at": "2000-01-01T00:00:00"}).status_code == 422     # 열린 구간보다 이른 시각
    assert client("qa").post(EQP01, data={"equipment_id": equip["id"], "state": "가동"}).status_code == 403
    assert client("admin").post(EQP01, data={"equipment_id": equip["id"], "state": "가동"}).status_code == 403


@pytest.mark.fn("F-EQP-01")
def test_status_screen_shows_state_and_latest_or_not_collected(equip):
    c = client("field", device="pop")
    client("prod").post(EQP01, data={"equipment_id": equip["id"], "state": "가동"})
    j = c.get(EQP01).json()
    me = next(r for r in j["rows"] if r["id"] == equip["id"])
    assert me["state"] == "가동" and me["latest"] is None and me["last_received_at"] is None
    html = c.get(EQP01, headers=HTML).text
    assert "미수집" in html and 'class="ch-pop"' in html
    with conn.tx() as cur:
        collect.receive(cur, collect.CollectMessage(equip_code=equip["equip_code"], ts=datetime.now(timezone.utc), tags={"run_state": 1, "count": 3}))
    me = next(r for r in c.get(EQP01).json()["rows"] if r["id"] == equip["id"])
    assert me["latest"]["tags"]["count"]["value"] == 3 and me["last_received_at"]


@pytest.mark.fn("F-EQP-03")
def test_check_create(equip):
    c = client("field")
    r = c.post(EQP02, data={"equipment_id": equip["id"], "item": "윤활 (예시)", "result": "양호", "checked_at": "2026-10-09T09:00:00"})
    assert r.status_code == 200
    row = conn.q1("select * from eqp_check where id = %s", (r.json()["id"],))
    assert row["item"] == "윤활 (예시)" and row["checker"] and row["checked_at"].hour == 9
    assert c.post(EQP02, data={"equipment_id": equip["id"], "item": ""}).status_code == 422
    assert c.post(EQP02, data={"equipment_id": equip["id"], "item": "x", "checked_at": "bad"}).status_code == 422
    assert client("qa").post(EQP02, data={"equipment_id": equip["id"], "item": "x"}).status_code == 403


@pytest.mark.fn("F-EQP-04")
def test_checks_screen(equip):
    c = client("admin")
    client("prod").post(EQP02, data={"equipment_id": equip["id"], "item": "점검 (예시)"})
    j = c.get(EQP02, params={"equipment_id": equip["id"]}).json()
    assert j["screen_id"] == "EQP-02" and len(j["rows"]) == 1 and j["rows"][0]["equip_code"] == equip["equip_code"]
    assert c.get(EQP02, params={"frm": "x"}).status_code == 422


@pytest.mark.fn("F-EQP-05")
def test_fault_create_opens_fault_segment(equip):
    c = client("prod")
    c.post(EQP01, data={"equipment_id": equip["id"], "state": "가동"})
    r = c.post(EQP03, data={"equipment_id": equip["id"], "symptom": "이상음 (예시)"})
    assert r.status_code == 200
    fault = conn.q1("select * from eqp_fault where id = %s", (r.json()["id"],))
    seg = conn.q1("select * from eqp_run_log where id = %s", (fault["run_log_id"],))
    assert seg["state"] == "고장" and seg["ended_at"] is None
    assert conn.q1("select count(*) as n from eqp_run_log where equipment_id = %s and ended_at is null", (equip["id"],))["n"] == 1
    assert c.post(EQP03, data={"equipment_id": equip["id"], "symptom": ""}).status_code == 422
    assert client("admin").post(EQP03, data={"equipment_id": equip["id"], "symptom": "x"}).status_code == 403


@pytest.mark.fn("F-EQP-06")
def test_fault_fix_closes_segment(equip):
    c = client("field")
    fid = c.post(EQP03, data={"equipment_id": equip["id"], "symptom": "정지 (예시)", "occurred_at": "2026-01-01T10:00:00"}).json()["id"]
    assert c.post(f"{EQP03}/{fid}/fix", data={"fix_action": "x", "fixed_at": "2026-01-01T09:00:00"}).status_code == 422     # 발생보다 이름
    assert c.post(f"{EQP03}/{fid}/fix", data={"fix_action": ""}).status_code == 422
    r = c.post(f"{EQP03}/{fid}/fix", data={"fix_action": "부품 교체 (예시)", "next_state": "가동"})
    assert r.status_code == 200 and r.json()["next_state"] == "가동"
    fault = conn.q1("select * from eqp_fault where id = %s", (fid,))
    assert fault["fixed_at"] is not None and fault["fixed_by"] == "field"
    assert conn.q1("select ended_at from eqp_run_log where id = %s", (fault["run_log_id"],))["ended_at"] is not None
    assert conn.q1("select state from eqp_run_log where equipment_id = %s and ended_at is null", (equip["id"],))["state"] == "가동"
    assert c.post(f"{EQP03}/{fid}/fix", data={"fix_action": "x"}).status_code == 422                                      # 이미 조치
    assert c.post(f"{EQP03}/999999/fix", data={"fix_action": "x"}).status_code == 404


@pytest.mark.fn("F-EQP-07")
def test_faults_screen(equip):
    c = client("admin")
    client("prod").post(EQP03, data={"equipment_id": equip["id"], "symptom": "고장 (예시)"})
    j = c.get(EQP03, params={"equipment_id": equip["id"], "fixed": "N"}).json()
    assert j["screen_id"] == "EQP-03" and len(j["rows"]) == 1 and j["rows"][0]["fixed_at"] is None
    assert c.get(EQP03, params={"equipment_id": equip["id"], "fixed": "Y"}).json()["rows"] == []
    assert c.get(EQP03, params={"fixed": "X"}).status_code == 422


@pytest.mark.fn("F-EQP-08")
def test_collect_screen_series_or_not_collected(equip):
    c = client("admin")
    today = datetime.now().date().isoformat()
    j = c.get(EQP04, params={"equipment_id": equip["id"], "tag": "count", "frm": today, "to": today}).json()
    assert j["screen_id"] == "EQP-04" and j["rows"] == [] and j["summary"]["n"] == 0
    assert "미수집" in c.get(EQP04, params={"equipment_id": equip["id"], "tag": "count"}, headers=HTML).text
    with conn.tx() as cur:
        for i, v in enumerate((5, 7)):
            collect.receive(cur, collect.CollectMessage(equip_code=equip["equip_code"], ts=datetime.now(timezone.utc) - timedelta(minutes=i), tags={"count": v}))
    j = c.get(EQP04, params={"equipment_id": equip["id"], "tag": "count", "frm": today, "to": today}).json()
    assert j["summary"] == {"n": 2, "min": 5.0, "max": 7.0, "avg": 6.0, "last": 5.0}
    assert c.get(EQP04).status_code == 200
    assert client("field").get(EQP04).status_code == 200 and client("field").get(EQP04 + "?device=pop").status_code == 403    # EQP-04 는 Web 만
