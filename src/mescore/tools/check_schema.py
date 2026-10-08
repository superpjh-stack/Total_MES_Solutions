#!/usr/bin/env python
"""G-C04 스키마 · G-P02 팩 테이블 수 — `make check-schema`. (아키텍트 초판 → QA2 가 이어받아 넓힌다)

  1. 계약(db-schema.md §4 렌더본) 테이블 = 실제 DB 코어 테이블 (52)
  2. 계약 컬럼(이름 · 타입 · NULL) = 실제 DB 컬럼
  3. 공통 컬럼 6(id · created_at · created_by · updated_at · updated_by · attrs)이 전 테이블에
  4. 렌더본 = schema.sql + DB (`make contracts` 로 찍은 것과 같다)
  5. 모듈별 테이블 수 = spec.md §2.2 (bas 10 · ord 4 · job 2 · mat 4 · 공용 2 · pop 5 · qua 5 · eqp 4 · shp 2 · kpi 2 · sys 9 · ifc 3) · 테이블마다 PK
  6. lot_genealogy — (parent, child, relation) 유니크 · 자기참조 CHECK · 순환 금지 트리거 · relation_base CHECK · lot.kind_base CHECK
  7. 상태 · 추적 경로를 저장하는 테이블 없음 — 뷰 3(v_lot_state · v_lot_stock · v_work_order_progress)으로 계산
  8. schema.sql 의 제약 · 인덱스 · 트리거 · 뷰 이름 = 실제 DB
  9. (MES_PACK) x_<팩>_ 테이블 수 = gates.yaml: tables · 팩 테이블에도 공통 컬럼 6 → G-P02

출력: `G-nn  항목  PASS|FAIL  실측`. 종료코드 0 = FAIL 없음.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_contracts  # noqa: E402
from mescore.app import contracts  # noqa: E402
from mescore.db import conn  # noqa: E402

EXPECTED = {"bas": 10, "ord": 4, "job": 2, "mat": 4, "공용": 2, "pop": 5, "qua": 5, "eqp": 4, "shp": 2, "kpi": 2, "sys": 9, "ifc": 3}
VIEWS = {"v_lot_state", "v_lot_stock", "v_work_order_progress"}


def schema_sql_names() -> dict[str, set[str]]:
    text = gen_contracts.SCHEMA_SQL.read_text(encoding="utf-8")
    code = "\n".join(ln.split("--")[0] for ln in text.splitlines())
    views_text = (gen_contracts.SCHEMA_SQL.parent / "views.sql").read_text(encoding="utf-8")
    return {
        "constraint": set(re.findall(r"^\s*constraint\s+(\w+)\s", code, re.M)) | set(re.findall(r"add constraint\s+(\w+)\s", code)),
        "index": set(re.findall(r"^create\s+(?:unique\s+)?index\s+(\w+)\s", code, re.M)),
        "trigger": set(re.findall(r"^create\s+trigger\s+(\w+)", code, re.M)),
        "view": set(re.findall(r"^create\s+view\s+(\w+)", views_text, re.M)),
    }


def main() -> int:
    rows: list[tuple[str, str, bool, str]] = []

    def add(gate: str, item: str, ok: bool, actual: str) -> None:
        rows.append((gate, item, bool(ok), actual))

    g = "G-C04"
    try:
        spec = contracts.db_tables()
    except Exception as exc:  # noqa: BLE001
        print(f"{g}  db-schema.md 로드  FAIL  {type(exc).__name__}: {exc}")
        return 1
    live_all = gen_contracts.db_columns()
    live = {t: c for t, c in live_all.items() if not t.startswith("x_")}
    pack_tables = {t: c for t, c in live_all.items() if t.startswith("x_")}

    only_spec, only_live = sorted(set(spec) - set(live)), sorted(set(live) - set(spec))
    add(g, "계약 테이블 = 실제 DB 코어 테이블 (52)", len(spec) == 52 and not only_spec and not only_live,
        f"계약 {len(spec)} · DB {len(live)}" + (f" · 계약에만 {only_spec[:3]}" if only_spec else "") + (f" · DB 에만 {only_live[:3]}" if only_live else ""))

    diffs: list[str] = []
    n_spec = n_live = 0
    for name, t in spec.items():
        want = [(c.name, c.type, c.nullable) for c in t.columns]
        got = [c for c in live.get(name, []) if c[0] not in gen_contracts.COMMON_COLUMNS]
        n_spec += len(want)
        n_live += len(got)
        if want != got:
            w, gt = {c[0]: c for c in want}, {c[0]: c for c in got}
            diffs += [f"{name}.{col}" for col in sorted(set(w) | set(gt)) if w.get(col) != gt.get(col)]
    add(g, "계약 컬럼 = 실제 DB 컬럼 (이름 · 타입 · NULL · 순서)", not diffs, f"계약 {n_spec} · DB {n_live} · 불일치 {len(diffs)}" + (f" {diffs[:3]}" if diffs else ""))

    missing_common = [f"{t}.{c}" for t, cols in live.items() for c in gen_contracts.COMMON_COLUMNS if c not in {x[0] for x in cols}]
    add(g, "공통 컬럼 6 (id · created_at · created_by · updated_at · updated_by · attrs) 전 테이블", not missing_common,
        f"테이블 {len(live)} · 빠진 칸 {len(missing_common)}" + (f" {missing_common[:3]}" if missing_common else ""))

    try:
        text = gen_contracts.DB_SCHEMA_MD.read_text(encoding="utf-8")
        same = gen_contracts.replace_block(text, "tables", gen_contracts.render_tables(), gen_contracts.DB_SCHEMA_MD) == text
        add(g, "db-schema.md §4 렌더본 = schema.sql + DB", same, "일치" if same else "다르다 — `make contracts`")
    except SystemExit as exc:
        add(g, "db-schema.md §4 렌더본 = schema.sql + DB", False, str(exc)[:160])

    per_mod: dict[str, int] = {}
    for t in spec.values():
        per_mod[t.module] = per_mod.get(t.module, 0) + 1
    no_pk = sorted(t for t in live if not conn.q1("select 1 from pg_constraint where conrelid = %s::regclass and contype = 'p'", (t,)))
    add(g, "모듈별 테이블 수 = spec.md §2.2 · 테이블마다 PK", per_mod == EXPECTED and not no_pk,
        " · ".join(f"{k} {per_mod.get(k, 0)}" for k in EXPECTED) + (f" · 기대와 다름 {sorted(set(per_mod.items()) ^ set(EXPECTED.items()))}" if per_mod != EXPECTED else "")
        + (f" · PK 없는 테이블 {no_pk}" if no_pk else ""))

    cons = {r["conname"]: r["def"] for r in conn.q(
        "select conname, pg_get_constraintdef(oid) as def from pg_constraint where conrelid = 'lot_genealogy'::regclass")} if "lot_genealogy" in live else {}
    trg = [r["tgname"] for r in conn.q("select tgname from pg_trigger where tgrelid = 'lot_genealogy'::regclass and not tgisinternal")] if "lot_genealogy" in live else []
    lot_chk = {r["conname"] for r in conn.q("select conname from pg_constraint where conrelid = 'lot'::regclass and contype = 'c'")} if "lot" in live else set()
    ok6 = ({"lot_genealogy_uq", "lot_genealogy_self_chk", "lot_genealogy_base_chk"} <= set(cons) and "lot_genealogy_no_cycle" in trg
           and {"lot_kind_base_chk", "lot_shipment_chk"} <= lot_chk)
    add(g, "lot_genealogy 유니크 · 자기참조 CHECK · 순환 금지 트리거 · relation_base CHECK · lot.kind_base CHECK", ok6,
        f"제약 {sorted(cons)} · 트리거 {trg} · lot CHECK {sorted(lot_chk)}")

    path_tables = sorted(t for t in live if re.search(r"trace|path|cache|closure|ancest|descend|tree|summary|agg", t))
    state_cols = [f"lot.{c[0]}" for c in live.get("lot", []) if re.search(r"^(state|status|shipped|consumed)", c[0])]
    views = {r["viewname"] for r in conn.q("select viewname from pg_views where schemaname = 'public'")}
    matviews = conn.q1("select count(*) as n from pg_matviews where schemaname = 'public'")["n"]
    add(g, "상태 · 추적 경로 · 집계를 저장하지 않는다 — 뷰 3 으로 계산", not path_tables and not state_cols and matviews == 0 and VIEWS <= views,
        f"경로/캐시 테이블 {path_tables or 0} · lot 상태 컬럼 {state_cols or 0} · 구체화 뷰 {matviews} · 뷰 {sorted(views)}")

    want = schema_sql_names()
    have = {
        "constraint": {r["conname"] for r in conn.q("select conname from pg_constraint c join pg_namespace n on n.oid = c.connamespace where n.nspname = 'public'")},
        "index": {r["indexname"] for r in conn.q("select indexname from pg_indexes where schemaname = 'public'")},
        "trigger": {r["tgname"] for r in conn.q("select tgname from pg_trigger where not tgisinternal")},
        "view": views,
    }
    lost = {k: sorted(want[k] - have[k]) for k in want if want[k] - have[k]}
    add(g, "schema.sql · views.sql 의 제약 · 인덱스 · 트리거 · 뷰 이름이 실제 DB 에 전부 있다", not lost,
        " · ".join(f"{k} {len(want[k] & have[k])}/{len(want[k])}" for k in want) + (f" — DB 에 없는 것 {lost}" if lost else ""))

    pack = os.environ.get("MES_PACK") or ""
    if pack and not pack.startswith("_"):
        gp = "G-P02"
        import yaml
        gates_path = ROOT / "packs" / pack / "gates.yaml"
        want_n = None
        if gates_path.exists():
            want_n = (yaml.safe_load(gates_path.read_text(encoding="utf-8")) or {}).get("tables")
        mine = {t: c for t, c in pack_tables.items() if t.startswith(f"x_{pack}_")}
        others = sorted(t for t in pack_tables if t not in mine)
        miss = [f"{t}.{c}" for t, cols in mine.items() for c in gen_contracts.COMMON_COLUMNS if c not in {x[0] for x in cols}]
        add(gp, f"[{pack}] 팩 테이블 수 = gates.yaml · x_{pack}_ 접두 · 공통 컬럼 6",
            want_n is not None and len(mine) == int(want_n) and not others and not miss,
            f"x_{pack}_ {len(mine)} · gates.yaml {want_n if want_n is not None else '없음'} · 다른 접두 {others or 0} · 공통 컬럼 빠짐 {len(miss)}")

    w = max(len(i) for _, i, _, _ in rows)
    print("G-C04 스키마 ↔ 계약 ↔ 실제 DB (tools/check_schema.py)")
    print("-" * 100)
    for gt, item, ok, actual in rows:
        print(f"{gt}  {item:<{w}}  {'PASS' if ok else 'FAIL'}  {actual}")
    print("-" * 100)
    failed = sum(1 for _, _, ok, _ in rows if not ok)
    print(f"판정: {'PASS' if failed == 0 else 'FAIL'} (검사 {len(rows)} · 실패 {failed})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
