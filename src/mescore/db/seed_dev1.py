"""개발1 시드 — (예시) 기준정보 · BOM · 공정 측정값 정의 3 (G-C24 기대: 필수 1 · 범위 1 · collect 1). **두 번 돌려도 행 수가 같다**(G-C09).

    uv run python -m mescore.db.seed_dev1          # seed_core 가 run_dev_seeds() 로 부른다 (make db-seed)

- 공통 시드(`seed_core.seed_examples`)의 (예시) 행(PRC-EX-01 · PRD-EX-01 · RAW-EX-01/02 · EQ-EX-01 …) 위에 얹는다 — 같은 코드는 건드리지 않는다.
- 회사 실데이터는 없다. 이름에 `(예시)` · 코드에 `-EX-`. 규격 · 범위 숫자는 화면 시연 · 테스트용 값이지 어느 사업의 값도 아니다.
- 작업지시는 넣지 않는다 — 번호는 `numbering.next('WORK_ORDER')` 만 만들고 시드가 번호를 지어내지 않는다.
- 이미 있는 코드는 건드리지 않는다(`on conflict do nothing`) — 화면에서 고친 값을 시드가 되돌리지 않는다.
"""

from __future__ import annotations

import json

from ..app.util.screen import example
from . import conn

SEEDED_BY = "seed_dev1"

# (코드, 이름, 구분, 규격, 단위)
ITEMS = [
    ("PRD-EX-02", "제품 2", "제품", "10 kg 포장", "EA"),
    ("SEMI-EX-01", "반제품 1", "반제품", None, "kg"),
    ("SUB-EX-01", "부자재 1", "부자재", "포장재", "EA"),
]
# (공정 코드, 이름, 순서)
PROCESSES = [("PRC-EX-03", "공정 3", 3)]
# 공정 측정값 정의 3 — G-C24 기대: 필수 1 · 범위 1 · collect 1 (process_params.csv 와 같은 열)
#  (공정 코드, 키, 라벨, 단위, 형식, 하한, 상한, 필수, 수집원, 수집 태그, 대표값, 순서)
PROCESS_PARAMS = [
    ("PRC-EX-01", "weight", "중량", "kg", "number", None, None, "Y", "manual", None, "last", 1),          # 필수 (누락 422)
    ("PRC-EX-01", "temp", "온도", "℃", "number", 60, 80, "N", "manual", None, "last", 2),                 # 범위 (이탈은 저장 + deviated)
    ("PRC-EX-01", "count", "생산 수량", "EA", "number", None, None, "N", "collect", "count", "last", 3),   # collect (core.yaml: collect_tags 의 count)
]
# (설비 코드, 이름, 공정 코드, 수집 여부)
EQUIPMENT = [("EQ-EX-02", "설비 2", "PRC-EX-01", "Y"), ("EQ-EX-03", "설비 3", "PRC-EX-02", "N")]
# (거래처 코드, 이름, 구분, 연락처)
PARTNERS = [("OUT-EX-01", "외주사 1", "외주", None)]
# (작업자 코드, 이름, 공정 코드)
WORKERS = [("WK-EX-02", "작업자 2", "PRC-EX-02")]
# 시드 계정 ↔ 예시 작업자 연결 (F-SYS-01 작업자 연결 · POP-02 기본 작업자 = sys_user.worker_id). 둘 다 비어 있을 때만 — 화면에서 바꾼 연결은 그대로
USER_WORKERS = [("field", "WK-EX-02")]
# (불량 코드, 이름, 공정 코드)
DEFECTS = [("DF-EX-02", "불량 2", "PRC-EX-02"), ("DF-EX-03", "불량 3", None)]
# BOM — (상위 품목 코드, 버전, [(구성품 코드, 소요량, 단위, 손실률)])
BOMS = [
    ("PRD-EX-01", "1", [("RAW-EX-01", "2.500", "kg", "1.000"), ("RAW-EX-02", "1.000", "kg", "0"), ("SUB-EX-01", "1", "EA", "0")]),
    ("PRD-EX-02", "1", [("SEMI-EX-01", "10.000", "kg", "0.500")]),
    ("SEMI-EX-01", "1", [("RAW-EX-01", "1.000", "kg", "0")]),
]


def seed_master(cur) -> None:
    for code, name, typ, spec, unit in ITEMS:
        cur.execute("insert into bas_item (item_code, item_name, item_type, spec, unit, created_by) values (%s, %s, %s, %s, %s, %s) on conflict (item_code) do nothing",
                    (code, example(name), typ, spec, unit, SEEDED_BY))
    for code, name, seq in PROCESSES:
        cur.execute("insert into bas_process (process_code, process_name, seq, created_by) values (%s, %s, %s, %s) on conflict (process_code) do nothing",
                    (code, example(name), seq, SEEDED_BY))
    for proc, key, label, unit, vtype, lo, hi, req, source, tag, agg, seq in PROCESS_PARAMS:
        cur.execute("""insert into bas_process_param (process_id, param_key, label, unit, value_type, min_value, max_value, required_yn, source, collect_tag, agg, seq, created_by)
                       values ((select id from bas_process where process_code = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       on conflict (process_id, param_key) do nothing""",
                    (proc, key, example(label), unit, vtype, lo, hi, req, source, tag, agg, seq, SEEDED_BY))
    for code, name, proc, collect in EQUIPMENT:
        cur.execute("""insert into bas_equipment (equip_code, equip_name, process_id, collect_yn, created_by)
                       values (%s, %s, (select id from bas_process where process_code = %s), %s, %s) on conflict (equip_code) do nothing""",
                    (code, example(name), proc, collect, SEEDED_BY))
    for code, name, typ, contact in PARTNERS:
        cur.execute("insert into bas_partner (partner_code, partner_name, partner_type, contact, created_by) values (%s, %s, %s, %s, %s) on conflict (partner_code) do nothing",
                    (code, example(name), typ, contact, SEEDED_BY))
    for code, name, proc in WORKERS:
        cur.execute("""insert into bas_worker (worker_code, worker_name, process_id, created_by)
                       values (%s, %s, (select id from bas_process where process_code = %s), %s) on conflict (worker_code) do nothing""",
                    (code, example(name), proc, SEEDED_BY))
    for code, name, proc in DEFECTS:
        cur.execute("""insert into bas_defect_code (defect_code, defect_name, process_id, created_by)
                       values (%s, %s, (select id from bas_process where process_code = %s), %s) on conflict (defect_code) do nothing""",
                    (code, example(name), proc, SEEDED_BY))


def seed_user_workers(cur) -> None:
    for login_id, worker_code in USER_WORKERS:
        cur.execute("""update sys_user u set worker_id = w.id from bas_worker w
                        where u.login_id = %s and w.worker_code = %s and u.worker_id is null
                          and not exists (select 1 from sys_user o where o.worker_id = w.id) returning u.id, w.id as worker_id""",
                    (login_id, worker_code))
        row = cur.fetchone()
        if row:
            cur.execute("update bas_worker set user_id = %s where id = %s and user_id is null", (row["id"], row["worker_id"]))


def seed_boms(cur) -> None:
    """헤더가 이미 있으면 구성품도 건드리지 않는다 (화면에서 고친 BOM 을 되돌리지 않는다)."""
    for item_code, version, lines in BOMS:
        cur.execute("""insert into bas_bom (item_id, version, attrs, created_by)
                       values ((select id from bas_item where item_code = %s), %s, %s::jsonb, %s)
                       on conflict (item_id, version) do nothing returning id""", (item_code, version, json.dumps({"note": example("시드")}, ensure_ascii=False), SEEDED_BY))
        row = cur.fetchone()
        if row is None:
            continue
        for seq, (comp, qty, unit, loss) in enumerate(lines, start=1):
            cur.execute("""insert into bas_bom_dtl (bom_id, component_item_id, qty, unit, loss_rate, seq, created_by)
                           values (%s, (select id from bas_item where item_code = %s), %s, %s, %s, %s, %s)""",
                        (row["id"], comp, qty, unit, loss, seq, SEEDED_BY))


def main() -> int:
    with conn.tx() as cur:
        seed_master(cur)
        seed_boms(cur)
        seed_user_workers(cur)
    n = {t: conn.q1(f"select count(*) as n from {t}")["n"] for t in ("bas_item", "bas_bom", "bas_bom_dtl", "bas_process", "bas_process_param", "bas_equipment", "bas_partner", "bas_worker", "bas_defect_code")}
    print("seed_dev1 — " + " · ".join(f"{k} {v}" for k, v in n.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
