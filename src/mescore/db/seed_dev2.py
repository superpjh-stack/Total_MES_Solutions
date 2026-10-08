"""개발2 시드 — (예시) 입고 2 · 원재료 LOT 2(입고검사 합격) · 검사 계획(입고/공정/최종 항목) · 설비 수집값 몇 행 · 이상 번호 채번 규칙(D-202). **두 번 돌려도 행 수가 같다**(G-C09).

    uv run python -m mescore.db.seed_dev2            # seed_core 가 run_dev_seeds 로도 부른다

- 공통 시드(RAW-EX-01/02 · PRD-EX-01 · PRC-EX-01 · SUP-EX-01)와 개발1 시드(EQ-EX-02 수집 설비 · 측정값 정의 3행) 위에 얹는다.
- LOT 번호는 시드 고정값 `M-EX-0001` · `M-EX-0002`(채번을 소비하지 않는다 — 이관과 같은 `lineage.make_material_lot(lot_no=…)`). 회사 실데이터는 없다.
- 계보 · LOT 은 `lineage` 로, 수집값은 `collect.receive` 로 넣는다(쓰기 경계 그대로).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..app import collect, lineage
from . import conn

BY = "seed_dev2"
RECEIPTS = [("M-EX-0001", "RAW-EX-01", 250, "kg"), ("M-EX-0002", "RAW-EX-02", 100, "kg")]
#: 검사 계획 — (유형, 품목 코드, 공정 코드, 키, 라벨, 단위, 형식, 기준, 하한, 상한)
PLANS = [
    ("입고", "RAW-EX-01", None, "moisture", "수분 (예시)", "%", "number", "15 이하", None, 15),
    ("입고", "RAW-EX-01", None, "appearance", "외관 (예시)", None, "text", "이물 없음", None, None),
    ("공정", None, "PRC-EX-01", "thickness", "두께 (예시)", "mm", "number", "0.8 ~ 1.2", 0.8, 1.2),
    ("최종", "PRD-EX-01", None, "pack_weight", "포장 중량 (예시)", "g", "number", "980 ~ 1020", 980, 1020),
    ("최종", "PRD-EX-01", None, "label_ok", "표시 사항 (예시)", None, "bool", "예", None, None),
]
COLLECT_EQUIP = "EQ-EX-02"
COLLECT_BASE = datetime(2026, 10, 9, 8, 0, tzinfo=timezone(timedelta(hours=9)))
COLLECT_ROWS = [(0, {"run_state": 1, "count": 10}), (1, {"run_state": 1, "count": 24}), (2, {"run_state": 0, "count": 24}), (3, {"run_state": 1, "count": 41})]


def _id(sql: str, params) -> int | None:
    r = conn.q1(sql, params)
    return r["id"] if r else None


def seed_number_rule() -> None:
    """이상 번호 `ISSUE` — core.yaml: numbering 에 없다(D-202 가설). 있으면 건드리지 않는다."""
    conn.x("""insert into sys_number_rule (kind, prefix, date_format, seq_digits, created_by) values ('ISSUE', 'Q', 'YYMMDD-', 3, %s)
              on conflict (kind) do nothing""", (BY,))


def seed_receipts() -> int:
    n = 0
    sup = _id("select id from bas_partner where partner_code = 'SUP-EX-01'", ())
    for lot_no, item_code, qty, unit in RECEIPTS:
        if conn.q1("select 1 from lot where lot_no = %s", (lot_no,)):
            continue
        item = _id("select id from bas_item where item_code = %s", (item_code,))
        if item is None:
            raise SystemExit(f"시드 품목 {item_code} 없음 — seed_core 먼저")
        with conn.tx() as cur:
            lot = lineage.make_material_lot(cur, item_id=item, qty=qty, unit=unit, by=BY, partner_id=sup, lot_no=lot_no, insp_status="합격",
                                            note="(예시)", attrs={"seed": BY})
            cur.execute("""insert into mat_receipt (receipt_no, item_id, partner_id, receipt_date, qty, unit, lot_id, note, attrs, created_by)
                           values (%s, %s, %s, current_date, %s, %s, %s, '(예시)', '{"seed": "seed_dev2"}', %s) returning id""",
                        (lot_no, item, sup, qty, unit, lot["id"], BY))
            rid = cur.fetchone()["id"]
            cur.execute("insert into mat_stock_trx (item_id, lot_id, trx_type, qty, unit, ref_table, ref_id, created_by) values (%s, %s, '입고', %s, %s, 'mat_receipt', %s, %s)",
                        (item, lot["id"], qty, unit, rid, BY))
            cur.execute("""insert into mat_stock (item_id, qty, unit, created_by) values (%s, %s, %s, %s)
                           on conflict (item_id) do update set qty = mat_stock.qty + excluded.qty, updated_at = now(), updated_by = excluded.created_by""", (item, qty, unit, BY))
            cur.execute("""insert into qua_inspection (lot_id, insp_type, inspected_at, inspector, judgement, judged_at, judged_by, note, created_by)
                           values (%s, '입고', now(), %s, '합격', now(), %s, '(예시)', %s)""", (lot["id"], BY, BY, BY))
        n += 1
    return n


def seed_plans() -> None:
    for insp_type, item_code, proc_code, key, label, unit, vtype, std, lo, hi in PLANS:
        conn.x("""insert into qua_insp_plan (insp_type, item_id, process_id, item_key, label, unit, value_type, standard, min_value, max_value, seq, created_by)
                  values (%s, (select id from bas_item where item_code = %s), (select id from bas_process where process_code = %s), %s, %s, %s, %s, %s, %s, %s, 0, %s)
                  on conflict (insp_type, coalesce(item_id, 0), coalesce(process_id, 0), item_key) do nothing""",
               (insp_type, item_code, proc_code, key, label, unit, vtype, std, lo, hi, BY))


def seed_collect() -> int:
    if conn.q1("select 1 from bas_equipment where equip_code = %s", (COLLECT_EQUIP,)) is None:
        return 0                       # 개발1 시드의 수집 설비가 아직 없으면 넣지 않는다 (지어내지 않는다)
    n = 0
    with conn.tx() as cur:
        for minutes, tags in COLLECT_ROWS:
            res = collect.receive(cur, collect.CollectMessage(equip_code=COLLECT_EQUIP, ts=COLLECT_BASE + timedelta(minutes=minutes), tags=tags, source="seed"))
            n += 0 if res.duplicate else 1
    return n


def main() -> int:
    seed_number_rule()
    n_rcv = seed_receipts()
    seed_plans()
    n_col = seed_collect()
    c = {t: conn.q1(f"select count(*) as n from {t}")["n"] for t in ("mat_receipt", "lot", "qua_insp_plan", "eqp_collect")}
    print(f"seed_dev2 완료 — 입고 추가 {n_rcv} (mat_receipt {c['mat_receipt']}) · lot {c['lot']} · 검사 계획 {c['qua_insp_plan']} · 수집값 추가 {n_col} (eqp_collect {c['eqp_collect']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
