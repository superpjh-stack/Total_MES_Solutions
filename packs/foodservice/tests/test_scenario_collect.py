"""S6 냉장 온도조절기 이탈 기록 — on_collect → x_foodservice_env_alarm (gates.yaml S6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from mescore.db import conn

from _helpers import client, equipment_id, ok, token


def _send(c, equip: str, ts: datetime, **tags) -> dict:
    return ok(c.post("/ifc/collect", json={"equip_code": equip, "ts": ts.isoformat(), "source": "gateway", "tags": tags}, headers=token()), "수집")


@pytest.mark.fn("F-IFC-01")
def test_env_alarm():
    c = client("admin")
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    eq = equipment_id("EQ-TC-05")
    ext = conn.q1("select storage_kind, temp_limit from x_foodservice_equipment_ext where id = %s", (eq,))
    assert ext["storage_kind"] == "냉장" and ext["temp_limit"] == 5, "시드 EQ-TC-05 (냉장 · 5 ℃) — seed_pack.py"
    r1 = _send(c, "EQ-TC-05", t0, PV_TEMP=7.2)                                             # 상한 초과
    r2 = _send(c, "EQ-TC-05", t0 + timedelta(minutes=1), PV_TEMP=4.8)                     # 정상
    assert not r1["duplicate"] and not r2["duplicate"]
    alarms = conn.q("select * from x_foodservice_env_alarm where equipment_id = %s and ts in (%s, %s) order by ts", (eq, t0, t0 + timedelta(minutes=1)))
    assert len(alarms) == 1 and alarms[0]["kind"] == "상한 초과" and alarms[0]["value_num"] == Decimal("7.2") and alarms[0]["limit_value"] == Decimal("5") and alarms[0]["tag"] == "PV_TEMP"
    assert alarms[0]["collect_id"] == conn.q1("select id from eqp_collect where equipment_id = %s and tag = 'PV_TEMP' and ts = %s", (eq, t0))["id"]
    assert conn.q1("select count(*) as n from eqp_collect where equipment_id = %s and ts in (%s, %s)", (eq, t0, t0 + timedelta(minutes=1)))["n"] == 2   # collect_rows 2
    # 같은 메시지 재전송 → duplicate · 알람 그대로 1 (멱등)
    assert _send(c, "EQ-TC-05", t0, PV_TEMP=7.2)["duplicate"] is True
    assert conn.q1("select count(*) as n from x_foodservice_env_alarm where equipment_id = %s and ts in (%s, %s)", (eq, t0, t0 + timedelta(minutes=1)))["n"] == 1
    # 구분 (미확정) 인 EQ-TC-06 → 판정하지 않는다 (알람 0) · 교반기 TEMP 도 여기서 판정하지 않는다
    eq6 = equipment_id("EQ-TC-06")
    _send(c, "EQ-TC-06", t0, PV_TEMP=7.2)
    assert conn.q1("select count(*) as n from x_foodservice_env_alarm where equipment_id = %s", (eq6,))["n"] == 0
    _send(c, "EQ-STIR-02", t0, TEMP=180.0, RPM=70)
    assert conn.q1("select count(*) as n from x_foodservice_env_alarm where equipment_id = %s", (equipment_id("EQ-STIR-02"),))["n"] == 0
    # kpi_extra 건수에 잡힌다
    from packs.foodservice import hooks
    today = datetime.now().date()
    cnt = {m["key"]: m["value"] for m in hooks.kpi_extra(today, today)}["env_alarm_count"]
    assert cnt >= 1
