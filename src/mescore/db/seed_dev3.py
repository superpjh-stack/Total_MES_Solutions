"""개발3 시드 — (예시) 수주 2 · 생산계획 2 · 지표 정의 4 · ERP 큐 1. **두 번 돌려도 행 수가 같다**(G-C09). `seed_core` 가 `seed_dev1~3` 순으로 부른다.

- 번호는 고정(`-EX-S` · 채번을 소비하지 않는다) — 바코드 허용 글자(A-Z 0-9 -)만.
- 지표 4 (양품률 · 검사 합격률 · 납기 준수율 · 가동률)는 목표값 NULL → 화면은 `미확정` (D-602). 산식은 `core:<집계 키>`.
- ERP 큐 1행은 어댑터가 없을 때 IFC-02 가 `대기 — 미확정 (D-02)` 를 보여 주고 F-IFC-04 재전송이 501 을 내는 것을 확인하기 위한 (예시).
- 기준정보(품목 · 거래처)는 `seed_core` 의 (예시) 를 가리킨다 — 없으면 실패한다(지어내지 않는다).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from ..app.util.screen import example
from . import conn

SEEDED_BY = "seed:dev3"

#: (번호, 거래처 코드, 수주일 오프셋, 납기 오프셋, 상태, 상세[(품목 코드, 수량, 단위)])
ORDERS = [
    ("O-EX-S001", "CUST-EX-01", -10, -3, "진행", [("PRD-EX-01", 100, "EA")]),      # 납기 지남 · 미출하 → 현황판 지연 수주 (예시)
    ("O-EX-S002", "CUST-EX-01", -2, 7, "등록", [("PRD-EX-01", 50, "EA")]),
]
#: (번호, 수주 번호 · 줄, 품목 코드, 계획일 오프셋, 수량, 단위, 상태)
PLANS = [
    ("N-EX-S001", ("O-EX-S001", 1), "PRD-EX-01", -5, 100, "EA", "확정"),
    ("N-EX-S002", ("O-EX-S002", 1), "PRD-EX-01", 3, 50, "EA", "계획"),
]
#: (키, 이름, 단위, 산식, 순서) — 목표값은 NULL (미확정 · D-602)
INDICATORS = [
    ("production.good_rate", "생산 양품률", "%", "core:production.good_rate", 1),
    ("quality.pass_rate", "검사 합격률", "%", "core:quality.pass_rate", 2),
    ("delivery.on_time_rate", "납기 준수율", "%", "core:delivery.on_time_rate", 3),
    ("equipment.run_rate", "가동률", "%", "core:equipment.run_rate", 4),
]
OUTBOX_EVENT = "shipment_approved"


def _partner(code: str) -> int:
    r = conn.q1("select id from bas_partner where partner_code = %s", (code,))
    if r is None:
        raise SystemExit(f"seed_dev3: 거래처 {code} 가 없다 — seed_core 의 (예시) 기준정보가 먼저다")
    return r["id"]


def _item(code: str) -> int:
    r = conn.q1("select id from bas_item where item_code = %s", (code,))
    if r is None:
        raise SystemExit(f"seed_dev3: 품목 {code} 가 없다 — seed_core 의 (예시) 기준정보가 먼저다")
    return r["id"]


def seed_orders(today: date) -> None:
    for no, partner, d_order, d_due, status, lines in ORDERS:
        conn.x("""insert into ord_order (order_no, partner_id, order_date, due_date, status, note, created_by) values (%s, %s, %s, %s, %s, %s, %s)
                  on conflict (order_no) do nothing""",
               (no, _partner(partner), today + timedelta(days=d_order), today + timedelta(days=d_due), status, example("시드 수주"), SEEDED_BY))
        order_id = conn.q1("select id from ord_order where order_no = %s", (no,))["id"]
        for line_no, (item, qty, unit) in enumerate(lines, start=1):
            conn.x("""insert into ord_order_dtl (order_id, line_no, item_id, qty, unit, created_by) values (%s, %s, %s, %s, %s, %s)
                      on conflict (order_id, line_no) do nothing""", (order_id, line_no, _item(item), qty, unit, SEEDED_BY))
        if conn.q1("select 1 from ord_order_hist where order_id = %s and field = '등록'", (order_id,)) is None:
            conn.x("insert into ord_order_hist (order_id, changed_by, field, before_value, after_value, created_by) values (%s, %s, '등록', null, %s, %s)",
                   (order_id, SEEDED_BY, no, SEEDED_BY))


def seed_plans(today: date) -> None:
    for no, (order_no, line_no), item, d_plan, qty, unit, status in PLANS:
        dtl = conn.q1("select d.id from ord_order_dtl d join ord_order o on o.id = d.order_id where o.order_no = %s and d.line_no = %s", (order_no, line_no))
        conn.x("""insert into ord_plan (plan_no, order_dtl_id, item_id, plan_date, plan_qty, unit, status, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s)
                  on conflict (plan_no) do nothing""",
               (no, dtl["id"] if dtl else None, _item(item), today + timedelta(days=d_plan), qty, unit, status, SEEDED_BY))


def seed_indicators() -> None:
    for key, name, unit, calc, seq in INDICATORS:
        conn.x("""insert into kpi_indicator (indicator_key, name, unit, target_value, calc_kind, visible_yn, seq, created_by)
                  values (%s, %s, %s, null, %s, 'Y', %s, %s) on conflict (indicator_key) do nothing""",
               (key, example(name), unit, calc, seq, SEEDED_BY))


def seed_outbox() -> None:
    if conn.q1("select 1 from ifc_outbox where created_by = %s and event = %s", (SEEDED_BY, OUTBOX_EVENT)):
        return
    payload = {"seed": "dev3", "note": example("ERP 큐 시드 — 어댑터가 정해지면 flush 로 보낸다"), "shipment_no": "S-EX-S001"}
    conn.x("insert into ifc_outbox (event, payload, status, attempts, created_by) values (%s, %s::jsonb, '대기', 0, %s)",
           (OUTBOX_EVENT, json.dumps(payload, ensure_ascii=False), SEEDED_BY))


def main() -> int:
    today = date.today()
    seed_orders(today)
    seed_plans(today)
    seed_indicators()
    seed_outbox()
    c = conn.table_counts()
    print(f"seed_dev3 — 수주 {c.get('ord_order')} · 상세 {c.get('ord_order_dtl')} · 계획 {c.get('ord_plan')} · 지표 {c.get('kpi_indicator')} · ERP 큐 {c.get('ifc_outbox')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
