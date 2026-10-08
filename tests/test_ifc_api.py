"""ifc — F-IFC-01~04 (수집 수신 · 수신 현황 · ERP 로그 · 재전송). 수신은 토큰, 재전송은 관리자(범위 재전송) · 어댑터 501 그대로. 개발3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mescore.app.settings import get_settings
from mescore.db import conn

from _dev3_helpers import client


def _token() -> str:
    tok = get_settings().collect_token
    assert tok, "MES_COLLECT_TOKEN 미설정 — make setup"
    return tok


@pytest.mark.fn("F-IFC-01")
def test_collect_receive_token_idempotent_unknown_equipment():
    c = client()
    ts = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    msg = {"equip_code": "EQ-EX-01", "ts": ts, "source": "gateway", "tags": {"run_state": 1, "count": 12, "t3_unknown": 7.5}}
    assert c.post("/ifc/collect", json=msg).status_code == 401                               # 토큰 없음
    assert c.post("/ifc/collect", json=msg, headers={"X-Collect-Token": "wrong"}).status_code == 401
    r = c.post("/ifc/collect", json=msg, headers={"X-Collect-Token": _token()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["raw_id"] and not body["duplicate"] and body["unknown_tags"] == ["t3_unknown"] and body["saved"] == 3
    r2 = c.post("/ifc/collect", json=msg, headers={"X-Collect-Token": _token()})
    assert r2.status_code == 200 and r2.json()["duplicate"] and r2.json()["raw_id"] == body["raw_id"]   # 멱등
    bad = c.post("/ifc/collect", json={**msg, "equip_code": "EQ-NOPE", "ts": ts}, headers={"X-Collect-Token": _token()})
    assert bad.status_code == 422
    assert conn.q1("select rejected_reason from ifc_collect_raw where equip_code = 'EQ-NOPE' and ts = %s", (ts,))["rejected_reason"]   # 거부 기록
    assert c.post("/ifc/collect", json={"equip_code": "EQ-EX-01"}, headers={"X-Collect-Token": _token()}).status_code == 422
    assert c.post("/ifc/collect", content=b"not json", headers={"X-Collect-Token": _token(), "content-type": "application/json"}).status_code == 422
    assert client("admin").post("/ifc/collect", json=msg).status_code == 401                 # 사용자 세션으로는 안 된다


@pytest.mark.fn("F-IFC-02")
def test_collect_status_per_equipment_and_rejections():
    c = client("admin")
    r = c.get("/ifc/collect")
    assert r.status_code == 200
    body = r.json()
    eq = next(x for x in body["rows"] if x["equip_code"] == "EQ-EX-01")
    assert {"last_received_at", "received", "rejected", "unknown_tags", "tags"} <= set(eq)
    assert body["counts"]["total"] >= body["counts"]["rejected"] and "run_state" in body["known_tags"]
    assert c.get("/ifc/collect", params={"frm": "x"}).status_code == 422
    assert client("prod").get("/ifc/collect").status_code == 200 and client("qa").get("/ifc/collect").status_code == 403


@pytest.mark.fn("F-IFC-03")
def test_erp_log_shows_queue_as_undecided():
    c = client("admin")
    r = c.get("/ifc/erp")
    assert r.status_code == 200
    body = r.json()
    assert body["adapter_undecided"] and body["decision"] == "D-02"
    seed = next(x for x in body["rows"] if x["created_by"] == "seed:dev3")
    assert "미확정 (D-02)" in seed["display_status"]
    assert c.get("/ifc/erp", params={"status": "x"}).status_code == 422
    assert client("field").get("/ifc/erp").status_code == 403


@pytest.mark.fn("F-IFC-04")
def test_erp_retry_returns_501_and_marks_row():
    admin = client("admin")
    with conn.tx() as cur:
        cur.execute("insert into ifc_outbox (event, payload, status, created_by) values ('shipment_approved', '{\"test\": true}'::jsonb, '대기', 'test') returning id")
        oid = cur.fetchone()["id"]
    r = admin.post(f"/ifc/erp/{oid}/retry")
    assert r.status_code == 501 and r.json()["code"] == "undecided" and r.json()["decision"] == "D-02"      # 501 그대로
    row = conn.q1("select status, attempts, last_error from ifc_outbox where id = %s", (oid,))
    assert row["status"] == "미확정" and row["attempts"] == 1 and "D-02" in row["last_error"]
    link = conn.q1("select status from ifc_erp_link where ref_table = 'ifc_outbox' and ref_id = %s order by id desc", (oid,))
    assert link["status"] == "미확정"
    assert admin.post("/ifc/erp/999999999/retry").status_code == 404
    assert client("prod").post(f"/ifc/erp/{oid}/retry").status_code == 403
