"""erp — 어댑터 기본 501 · enqueue → ifc_outbox · flush 가 501 을 `미확정` 으로 남긴다(조용한 폴백 0 · G-C16 · D-02). 개발3."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from mescore.app import erp
from mescore.db import conn


def test_default_adapter_is_501_everywhere():
    a = erp.adapter()
    assert erp.is_undecided()
    for call in (lambda: a.push("shipment_approved", {}), lambda: a.pull("order", None)):
        with pytest.raises(HTTPException) as ei:
            call()
        assert ei.value.status_code == 501 and ei.value.detail["decision"] == "D-02"


def test_enqueue_then_flush_leaves_undecided_rows():
    with conn.tx() as cur:
        oid = erp.enqueue(cur, "shipment_approved", {"shipment_no": "T-1"}, by="test")
    row = conn.q1("select status, attempts, payload from ifc_outbox where id = %s", (oid,))
    assert row["status"] == "대기" and row["attempts"] == 0 and row["payload"]["shipment_no"] == "T-1"
    out = erp.flush(limit=1000)
    assert out["processed"] >= 1 and oid in out["ids"] and out["undecided"] >= 1 and out["sent"] == 0 and out["decision"] == "D-02"
    row = conn.q1("select status, attempts, last_error from ifc_outbox where id = %s", (oid,))
    assert row["status"] == "미확정" and row["attempts"] == 1 and "D-02" in row["last_error"]
    assert conn.q1("select count(*)::int as n from ifc_erp_link where ref_id = %s and status = '미확정'", (oid,))["n"] == 1
    with pytest.raises(HTTPException) as ei:
        erp.retry(oid)
    assert ei.value.status_code == 501
    assert conn.q1("select attempts from ifc_outbox where id = %s", (oid,))["attempts"] == 2


def test_enqueue_rolls_back_with_transaction():
    before = conn.q1("select count(*)::int as n from ifc_outbox")["n"]
    class _Boom(Exception):
        pass
    with pytest.raises(_Boom):
        with conn.tx() as cur:
            erp.enqueue(cur, "x", {})
            raise _Boom
    assert conn.q1("select count(*)::int as n from ifc_outbox")["n"] == before
