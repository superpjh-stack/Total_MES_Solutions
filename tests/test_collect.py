"""수집 collect — receive 멱등(ifc_collect_raw 유니크) · 모르는 설비 422 + 거부 기록 · eqp_collect 정제 · unknown_tags · latest/series/aggregate (개발2).
엔드포인트 `POST /ifc/collect` 는 개발3 의 ifc 라우터(F-IFC-01)가 collect.receive 를 부른다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from mescore.app import collect
from mescore.db import conn

from _dev2_helpers import uniq


@pytest.fixture(scope="module")
def equip() -> dict:
    code = "EQ-T-COL"
    row = conn.q1("select id, equip_code from bas_equipment where equip_code = %s", (code,)) or conn.q1(
        "insert into bas_equipment (equip_code, equip_name, collect_yn, created_by) values (%s, '수집 설비 2 (예시)', 'Y', 'test') returning id, equip_code", (code,))
    conn.x("delete from eqp_collect where equipment_id = %s", (row["id"],))                      # 지난 실행의 수집값은 지운다
    conn.x("delete from ifc_collect_raw where equip_code = %s", (code,))
    return row


def _msg(code: str, ts: datetime, **tags) -> collect.CollectMessage:
    return collect.CollectMessage(equip_code=code, ts=ts, tags=tags)


def test_receive_is_idempotent_and_refines(equip):
    ts = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=3)
    with conn.tx() as cur:
        r1 = collect.receive(cur, _msg(equip["equip_code"], ts, run_state=1, count=12, temp_x=72.5, note="ok"))
        r2 = collect.receive(cur, collect.CollectMessage(equip_code=equip["equip_code"], ts=ts.isoformat(), tags={"count": 999}, resend=True))
    assert not r1.duplicate and r1.saved == 4 and set(r1.unknown_tags) == {"temp_x", "note"} and int(r1) == r1.raw_id
    assert r2.duplicate and r2.raw_id == r1.raw_id and r2.saved == 0
    raw = conn.q1("select * from ifc_collect_raw where id = %s", (r1.raw_id,))
    assert raw["rejected_reason"] is None and raw["payload"]["tags"]["count"] == 12
    rows = {r["tag"]: r for r in conn.q("select * from eqp_collect where equipment_id = %s and ts = %s", (equip["id"], ts))}
    assert rows["count"]["value_num"] == 12 and rows["note"]["value_text"] == "ok" and rows["run_state"]["raw_id"] == r1.raw_id and rows["temp_x"]["value_num"] == 72.5


def test_unknown_equipment_is_422_and_recorded(equip):
    code = uniq("EQ-NONE")
    ts = datetime.now(timezone.utc).replace(microsecond=0)
    with pytest.raises(HTTPException) as ex:
        with conn.tx() as cur:
            collect.receive(cur, _msg(code, ts, count=1))
    assert ex.value.status_code == 422
    raw = conn.q1("select * from ifc_collect_raw where equip_code = %s", (code,))
    assert raw is not None and raw["rejected_reason"] and "모르는 설비" in raw["rejected_reason"]     # 트랜잭션이 되돌아가도 거부 기록은 남는다
    assert conn.q1("select count(*) as n from eqp_collect where raw_id = %s", (raw["id"],))["n"] == 0
    with pytest.raises(HTTPException):
        collect.CollectMessage.from_payload({"equip_code": code})                                    # 본문 형식 오류 422
    with pytest.raises(HTTPException):
        with conn.tx() as cur:
            collect.receive(cur, _msg(equip["equip_code"], "not-a-time", count=1))


def test_latest_series_aggregate(equip):
    base = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2)
    with conn.tx() as cur:
        for i, v in enumerate((1.0, 3.0, 8.0)):
            collect.receive(cur, _msg(equip["equip_code"], base + timedelta(minutes=i), count=v, run_state=1 if i < 2 else 0))
    lv = collect.latest(equip["id"])
    assert lv["tags"]["count"]["value"] == 8.0 and lv["tags"]["run_state"]["value"] == 0 and lv["ts"] >= base + timedelta(minutes=2)
    s = collect.series(equip["id"], "count", base, base + timedelta(minutes=1))
    assert [x["value"] for x in s] == [1.0, 3.0]
    assert collect.aggregate(equip["id"], "count", base, base + timedelta(minutes=2), "avg") == 4.0
    assert collect.aggregate(equip["id"], "count", base, base + timedelta(minutes=2), "max") == 8.0
    assert collect.aggregate(equip["id"], "count", base, base + timedelta(minutes=2), "min") == 1.0
    assert collect.aggregate(equip["id"], "count", base, base + timedelta(minutes=2), "last") == 8.0
    assert collect.aggregate(equip["id"], "count", base - timedelta(days=400), base - timedelta(days=399), "avg") is None    # 수신 0 → None
    assert collect.latest(999999) is None
    with pytest.raises(ValueError):
        collect.aggregate(equip["id"], "count", base, base, "median")
    assert collect.counts()["total"] >= 3


def test_known_tags_include_core_and_declared():
    k = collect.known_tags()
    assert {"run_state", "count"} <= k


def test_counts_with_none_and_bounds():
    """IFC-01 수신 현황 — 경계 None 은 조건에서 빠진다(AmbiguousParameter 없음 · 개발3 §3-6). 미래 구간은 0 · 정수."""
    whole = collect.counts(None, None)
    assert collect.counts()["total"] >= whole["total"] and isinstance(whole["total"], int) and whole["total"] >= whole["rejected"] >= 0
    now = datetime.now(timezone.utc)
    assert collect.counts(now - timedelta(days=36500), None)["total"] >= whole["total"]
    assert collect.counts(None, now + timedelta(days=1))["total"] >= whole["total"]
    assert collect.counts("", "")["total"] >= whole["total"]
    future = collect.counts(now + timedelta(days=365), now + timedelta(days=366))
    assert future["total"] == 0 and future["last_at"] is None
