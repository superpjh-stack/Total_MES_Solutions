"""공통 시드 — 역할 · 권한 표(모듈 × 역할 전 칸) · 계정 · 채번 규칙 · 공통코드 코어 그룹 · (예시) 기준정보 몇 개. **두 번 돌려도 행 수가 같다**(G-C09).

    uv run python -m mescore.db.seed_core             # 코어 → 팩(seeds[] 공정 · 품목 · 설비 → process_params → inspection_items → 나머지 seeds[]) → 계정 → 개발 시드(seed_dev1~3 · 있는 것만)
    uv run python -m mescore.db.seed_core --core-only
    uv run python -m mescore.db.seed_core --reset     # 권한 표 · 채번 규칙을 core.yaml(+팩) 기본값으로 되돌린다

- 기대값은 전부 `packs.current()`(core.yaml + pack.yaml 병합본)에서 온다 — 여기 박힌 수는 없다. `MES_PACK=<팩>` 이면 팩 역할 · 칸 · 채번이 들어간다.
- 이미 있는 권한 칸 · 채번 규칙은 건드리지 않는다(SYS-03 · SYS-05 에서 바꾼 값을 시드가 되돌리면 안 된다). `--reset` 만 덮어쓴다.
- 계정 비밀번호는 `MES_SEED_PASSWORD` 로만 받는다. 없으면 **실패한다** — 기본 비밀번호를 지어내지 않는다(G-C19).
- 회사 실데이터는 없다. 표시명에는 `(예시)` 를 붙이고 코드에 `-EX-` 를 넣는다.
"""

from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

from ..app import auth, packs
from ..app.settings import get_settings
from ..app.util.screen import example
from . import conn

SEEDED_BY = "seed"
#: 역할별 시드 계정 — 로그인 ID = 역할 코드 소문자 (D-08). admin 은 반드시, 나머지는 그 역할이 병합본에 있을 때만
USERS: list[tuple[str, str, str]] = [
    ("admin", "관리자", "ADMIN"),
    ("prod", "생산 담당", "PROD"),
    ("qa", "품질 담당", "QA"),
    ("field", "현장 작업자", "FIELD"),
]
DEV_SEEDS = ("seed_dev1", "seed_dev2", "seed_dev3")

#: (예시) 기준정보 — 코어 한 바퀴 · 테스트용. 코드 -EX- · 이름 (예시)
EXAMPLE_PROCESSES = [("PRC-EX-01", "공정 1", 1), ("PRC-EX-02", "공정 2", 2)]
EXAMPLE_ITEMS = [("PRD-EX-01", "제품 1", "제품", "EA"), ("RAW-EX-01", "원재료 1", "원재료", "kg"), ("RAW-EX-02", "원재료 2", "원재료", "kg")]
EXAMPLE_EQUIPMENT = [("EQ-EX-01", "설비 1", "PRC-EX-01", "N")]
EXAMPLE_PARTNERS = [("CUST-EX-01", "고객사 1", "고객"), ("SUP-EX-01", "공급사 1", "공급")]
EXAMPLE_WORKERS = [("WK-EX-01", "작업자 1", "PRC-EX-01")]
EXAMPLE_DEFECTS = [("DF-EX-01", "불량 1", None)]


def seed_roles() -> None:
    for r in packs.current().roles:
        conn.x("""insert into sys_role (role_code, role_name, use_yn, created_by) values (%s, %s, 'Y', %s)
                  on conflict (role_code) do update set role_name = excluded.role_name, use_yn = 'Y', updated_at = now(), updated_by = %s""",
               (r["code"], r["name"], SEEDED_BY, SEEDED_BY))


def permission_rows() -> list[tuple[str, str, str, list[str]]]:
    """(role_code, menu_code, level, scopes) — 병합본의 모듈 × 역할 전 칸."""
    p = packs.current()
    rows = []
    for m in p.modules:
        for r in p.roles:
            c = p.permission(m["code"], r["code"])
            rows.append((r["code"], m["code"], c["level"], list(c["scopes"])))
    return rows


def seed_permissions(reset: bool = False) -> None:
    role_ids = {r["role_code"]: r["id"] for r in conn.q("select id, role_code from sys_role")}
    for role_code, menu_code, level, scopes in permission_rows():
        sql = """insert into sys_permission (role_id, menu_code, level, scopes, created_by) values (%s, %s, %s, %s, %s)
                 on conflict (role_id, menu_code) do """ + (
            "update set level = excluded.level, scopes = excluded.scopes, updated_at = now(), updated_by = excluded.created_by"
            if reset else "nothing")
        conn.x(sql, (role_ids[role_code], menu_code, level, scopes, SEEDED_BY))


def seed_users() -> None:
    """시드 계정을 환경변수 비밀번호로 맞춘다. 비밀번호가 이미 그 값이면 해시를 다시 쓰지 않는다 — 다시 쓰면 트리거가 그 계정의 세션을 끊는다(D-19).
    코어 단독은 `USERS`(역할 4), 팩은 `pack_user_rows()`(팩 역할마다 하나 + `seed/users.csv`)."""
    password = get_settings().seed_password
    if not password:
        raise SystemExit("MES_SEED_PASSWORD 미설정 — 시드 계정을 만들 수 없다. `make setup` 으로 `.env` 를 만들거나 환경변수로 준다. 기본 비밀번호는 두지 않는다(G-C19).")
    role_ids = {r["role_code"]: r["id"] for r in conn.q("select id, role_code from sys_role where use_yn = 'Y'")}
    if "ADMIN" not in role_ids:
        raise SystemExit("역할 ADMIN 이 없다 — core.yaml/pack.yaml: roles 에 ADMIN 은 필수다")
    if packs.current().is_core_only:
        rows = [{"login_id": lid, "user_name": name, "role_code": code, "worker_code": None} for lid, name, code in USERS if code in role_ids]
    else:
        rows = pack_user_rows()
    for u in rows:
        login_id, role_code = u["login_id"], u["role_code"]
        if role_code not in role_ids:
            raise SystemExit(f"계정 {login_id}: 역할 {role_code!r} 가 없다 — pack.yaml: roles 에 둔다")
        worker_id = None
        if u.get("worker_code"):
            w = conn.q1("select id from bas_worker where worker_code = %s", (u["worker_code"],))
            if w is None:
                raise SystemExit(f"계정 {login_id}: 작업자 {u['worker_code']!r} 가 없다 — seeds[] 의 workers* 에 둔다")
            worker_id = w["id"]
        cur = conn.q1("select password_hash from sys_user where login_id = %s", (login_id,))
        if cur is not None and auth.verify(password, cur["password_hash"]):
            conn.x("""update sys_user set role_id = %s, user_name = %s, worker_id = coalesce(%s, worker_id), status = '사용', fail_count = 0,
                             updated_at = now(), updated_by = %s
                       where login_id = %s""", (role_ids[role_code], example(u["user_name"]), worker_id, SEEDED_BY, login_id))
            continue
        conn.x("""insert into sys_user (login_id, user_name, password_hash, role_id, worker_id, created_by) values (%s, %s, %s, %s, %s, %s)
                  on conflict (login_id) do update
                     set password_hash = excluded.password_hash, role_id = excluded.role_id, user_name = excluded.user_name,
                         worker_id = coalesce(excluded.worker_id, sys_user.worker_id), status = '사용', fail_count = 0,
                         updated_at = now(), updated_by = excluded.created_by""",
               (login_id, example(u["user_name"]), auth.hash_password(password), role_ids[role_code], worker_id, SEEDED_BY))


def seed_numbering(reset: bool = False) -> None:
    for kind, rule in packs.current().numbering.items():
        sql = """insert into sys_number_rule (kind, prefix, date_format, seq_digits, created_by) values (%s, %s, %s, %s, %s)
                 on conflict (kind) do """ + (
            "update set prefix = excluded.prefix, date_format = excluded.date_format, seq_digits = excluded.seq_digits, updated_at = now(), updated_by = excluded.created_by"
            if reset else "nothing")
        conn.x(sql, (kind, str(rule.get("prefix", "")), str(rule.get("date", "")), int(rule.get("digits", 3)), SEEDED_BY))


def seed_codes() -> None:
    for group, spec in packs.current().code_groups.items():
        for seq, c in enumerate(spec.get("codes", []), start=1):
            code, name = (c["code"], c["name"]) if isinstance(c, dict) else (str(c), str(c))
            conn.x("""insert into bas_code (group_code, code, code_name, seq, is_core, created_by) values (%s, %s, %s, %s, 'Y', %s)
                      on conflict (group_code, code) do update set code_name = excluded.code_name, seq = excluded.seq, is_core = 'Y'""",
                   (group, code, name, seq, SEEDED_BY))


def seed_examples() -> None:
    for code, name, seq in EXAMPLE_PROCESSES:
        conn.x("insert into bas_process (process_code, process_name, seq, created_by) values (%s, %s, %s, %s) on conflict (process_code) do nothing",
               (code, example(name), seq, SEEDED_BY))
    for code, name, typ, unit in EXAMPLE_ITEMS:
        conn.x("insert into bas_item (item_code, item_name, item_type, unit, created_by) values (%s, %s, %s, %s, %s) on conflict (item_code) do nothing",
               (code, example(name), typ, unit, SEEDED_BY))
    for code, name, proc, collect in EXAMPLE_EQUIPMENT:
        conn.x("""insert into bas_equipment (equip_code, equip_name, process_id, collect_yn, created_by)
                  values (%s, %s, (select id from bas_process where process_code = %s), %s, %s) on conflict (equip_code) do nothing""",
               (code, example(name), proc, collect, SEEDED_BY))
    for code, name, typ in EXAMPLE_PARTNERS:
        conn.x("insert into bas_partner (partner_code, partner_name, partner_type, created_by) values (%s, %s, %s, %s) on conflict (partner_code) do nothing",
               (code, example(name), typ, SEEDED_BY))
    for code, name, proc in EXAMPLE_WORKERS:
        conn.x("""insert into bas_worker (worker_code, worker_name, process_id, created_by)
                  values (%s, %s, (select id from bas_process where process_code = %s), %s) on conflict (worker_code) do nothing""",
               (code, example(name), proc, SEEDED_BY))
    for code, name, proc in EXAMPLE_DEFECTS:
        conn.x("""insert into bas_defect_code (defect_code, defect_name, process_id, created_by)
                  values (%s, %s, (select id from bas_process where process_code = %s), %s) on conflict (defect_code) do nothing""",
               (code, example(name), proc, SEEDED_BY))


# ── 팩 시드 (E1 · E3 · CR-9) ─────────────────────────────────────────
#: 파일 이름(접두) → (테이블, 키 열). `seeds[]` 의 문자열 항목은 이름으로 대상을 고른다 (pack-contract.md §2)
NAMED_SEEDS: list[tuple[str, str, tuple[str, ...]]] = [
    ("processes", "bas_process", ("process_code",)),
    ("items", "bas_item", ("item_code",)),
    ("equipment", "bas_equipment", ("equip_code",)),
    ("partners", "bas_partner", ("partner_code",)),
    ("workers", "bas_worker", ("worker_code",)),
    ("defect_codes", "bas_defect_code", ("defect_code",)),
    ("codes", "bas_code", ("group_code", "code")),
    ("kpi_indicators", "kpi_indicator", ("indicator_key",)),
]
#: 적재 순서 — 공정 → 품목 → 설비 → (process_params · inspection_items) → 나머지 seeds[] 선언 순서 (개발1 ② · 개발3 12 · CR-9 ③)
EARLY_TABLES = ("bas_process", "bas_item", "bas_equipment")
NOTE_COLUMNS = ("note",)      # 설명용 열 — 테이블에 그 열이 없으면 적재하지 않는다
USER_COLUMNS = ("login_id", "user_name", "role_code", "worker_code")


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k is not None} for row in csv.DictReader(f)]


def _num(v):
    return None if v in (None, "") else float(v)


def _attrs_of(r: dict) -> dict:
    return {k[6:]: v for k, v in r.items() if k.startswith("attrs.") and v not in (None, "")}


class _Meta:
    """테이블 열 · 형 · FK(열 → 참조 테이블.열) · 단일 열 유니크 — 시드 CSV 헤더를 열로 옮길 때 쓴다."""

    _cache: dict[str, "_Meta"] = {}

    def __init__(self, table: str):
        self.table = table
        self.cols = {r["column_name"]: r["udt_name"] for r in conn.q(
            "select column_name, udt_name from information_schema.columns where table_schema = 'public' and table_name = %s", (table,))}
        if not self.cols:
            raise SystemExit(f"팩 시드: 테이블 {table} 이 DB 에 없다 — 스키마(schema_ext.sql)를 먼저 올린다")
        self.fks = {r["col"]: (r["ref_table"], r["ref_col"]) for r in conn.q(
            """select a.attname as col, c.confrelid::regclass::text as ref_table, af.attname as ref_col
                 from pg_constraint c
                 join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
                 join pg_attribute af on af.attrelid = c.confrelid and af.attnum = c.confkey[1]
                where c.contype = 'f' and c.conrelid = %s::regclass and array_length(c.conkey, 1) = 1""", (table,))}

    @classmethod
    def of(cls, table: str) -> "_Meta":
        if table not in cls._cache:
            cls._cache[table] = cls(table)
        return cls._cache[table]

    def unique_cols(self) -> set[str]:
        return {r["col"] for r in conn.q(
            """select a.attname as col from pg_index i join pg_attribute a on a.attrelid = i.indrelid and a.attnum = i.indkey[0]
                where i.indrelid = %s::regclass and i.indisunique and i.indnatts = 1 and i.indexprs is null""", (self.table,))}

    def lookup_for(self, header: str) -> tuple[str, str, str, str] | None:
        """헤더가 열이 아니면 FK 로 푼다 — `process_code` → (`process_id`, `bas_process`, `process_code`, `id`)."""
        hits = [(col, rt, header, rc) for col, (rt, rc) in self.fks.items() if header in _Meta.of(rt).unique_cols()]
        if len(hits) > 1:      # 같은 참조 테이블을 두 열이 가리키면 헤더 앞부분과 이름이 맞는 열
            hits = [h for h in hits if h[0].removesuffix("_id") == header.removesuffix("_code")] or hits
        return hits[0] if len(hits) == 1 else None


def _lookup(rt: str, col: str, val: str, ref_col: str, cache: dict) -> object:
    key = (rt, col, val)
    if key not in cache:
        row = conn.q1(f"select {ref_col} as v from {rt} where {col} = %s", (val,))
        if row is None:
            raise SystemExit(f"팩 시드: {rt}.{col} = {val!r} 가 없다 — 참조하는 시드 파일을 먼저 둔다(seeds[] 순서)")
        cache[key] = row["v"]
    return cache[key]


def upsert_csv(table: str, keys: tuple[str, ...] | list[str], rows: list[dict], *, source: str, strict: bool) -> tuple[int, list[str]]:
    """CSV 행을 `table` 에 키 열로 멱등 upsert. 헤더 = 열 이름 · `attrs.<키>` → attrs(기존 attrs 에 합친다) · 열이 아닌 `<x>_code` 는 FK 로 푼다.
    빈 칸은 넣지 않는다(열 기본값 · 기존 값 유지). strict 면 모르는 헤더가 오류, 아니면 무시한 헤더 목록을 돌려준다(`note` 는 늘 조용히 뺀다)."""
    meta = _Meta.of(table)
    cache: dict = {}
    headers = list(rows[0].keys()) if rows else []
    plan: dict[str, tuple] = {}         # 헤더 → ("col", 열) | ("fk", 열, 참조 테이블, 참조 열(코드), 참조 값 열)
    ignored: list[str] = []
    for h in headers:
        if h.startswith("attrs."):
            continue
        if h in meta.cols and h not in ("id", "attrs", "created_at", "created_by", "updated_at", "updated_by"):
            plan[h] = ("col", h)
            continue
        lk = meta.lookup_for(h)
        if lk is not None:
            plan[h] = ("fk", lk[0], lk[1], lk[2], lk[3])
        elif h in NOTE_COLUMNS:
            continue
        else:
            ignored.append(h)
    if ignored and strict:
        raise SystemExit(f"팩 시드 {source}: {table} 에 없는 열 {ignored} — 열 이름 · `attrs.<키>` · FK 코드 열(`<x>_code`)만 받는다")
    key_cols = []
    for k in keys:
        if k not in plan:
            raise SystemExit(f"팩 시드 {source}: 키 열 {k!r} 가 CSV 헤더에 없다 (헤더 {headers})")
        key_cols.append(plan[k][1])
    has_attrs = any(h.startswith("attrs.") for h in headers) and "attrs" in meta.cols
    n = 0
    for r in rows:
        values: dict[str, object] = {}
        for h, how in plan.items():
            v = r.get(h)
            if v in (None, ""):
                continue
            if how[0] == "fk":
                values[how[1]] = _lookup(how[2], how[3], v, how[4], cache)
            else:
                udt = meta.cols[how[1]]
                values[how[1]] = v.upper() if udt == "bpchar" and how[1].endswith("_yn") else v
        missing = [c for c in key_cols if c not in values]
        if missing:
            raise SystemExit(f"팩 시드 {source}: 키 {missing} 가 빈 행 — {r}")
        cols = list(values)
        exprs = [f"%s::{meta.cols[c]}" for c in cols]
        params = [values[c] for c in cols]
        if has_attrs:
            cols.append("attrs")
            exprs.append("%s::jsonb")
            params.append(json.dumps(_attrs_of(r), ensure_ascii=False))
        if "created_by" in meta.cols:
            cols.append("created_by")
            exprs.append("%s")
            params.append(source)
        sets = [f"{c} = excluded.{c}" for c in values if c not in key_cols]
        if has_attrs:
            sets.append(f"attrs = coalesce({table}.attrs, '{{}}'::jsonb) || excluded.attrs")
        sql = (f"insert into {table} ({', '.join(cols)}) values ({', '.join(exprs)}) on conflict ({', '.join(key_cols)}) do "
               + (f"update set {', '.join(sets)}" if sets else "nothing"))
        conn.x(sql, params)
        n += 1
    return n, ignored


def _seed_entries(p) -> list[dict]:
    """`seeds[]` → [{file, table, key, strict}] — 문자열은 이름 접두로, `{file, table, key}` 는 그대로(엄격)."""
    out = []
    for e in p.seeds:
        if e.get("table"):
            out.append({"file": e["file"], "table": e["table"], "key": tuple(e["key"]), "strict": True})
            continue
        stem = Path(e["file"]).stem
        if stem.startswith("users"):
            out.append({"file": e["file"], "table": "sys_user", "key": ("login_id",), "strict": True})
            continue
        hit = next(((t, k) for prefix, t, k in NAMED_SEEDS if stem.startswith(prefix)), None)
        if hit is None:
            raise SystemExit(f"모르는 팩 시드 파일 {e['file']} — 이름이 {' · '.join(x[0] + '*' for x in NAMED_SEEDS)} · users* 로 시작하거나 "
                             "`{file, table, key}` 로 적는다 (pack-contract.md §2)")
        out.append({"file": e["file"], "table": hit[0], "key": hit[1], "strict": False})
    return out


def _seed_process_params(p, path: Path) -> None:
    by = f"seed:{p.name}"
    for r in _read_csv(path):
        if conn.q1("select 1 from bas_process where process_code = %s", (r["process_code"],)) is None:
            raise SystemExit(f"팩 시드 {path.name}: 공정 {r['process_code']!r} 가 없다 — seeds[] 의 processes* 에 둔다")
        conn.x("""insert into bas_process_param (process_id, param_key, label, unit, value_type, min_value, max_value, required_yn, source, collect_tag, agg, seq, attrs, created_by)
                  values ((select id from bas_process where process_code = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                  on conflict (process_id, param_key) do update set label = excluded.label, unit = excluded.unit, value_type = excluded.value_type,
                      min_value = excluded.min_value, max_value = excluded.max_value, required_yn = excluded.required_yn, source = excluded.source,
                      collect_tag = excluded.collect_tag, agg = excluded.agg, seq = excluded.seq,
                      attrs = coalesce(bas_process_param.attrs, '{}'::jsonb) || excluded.attrs""",
               (r["process_code"], r["param_key"], r["label"], r.get("unit") or None, r.get("value_type") or "number", _num(r.get("min_value")),
                _num(r.get("max_value")), (r.get("required_yn") or "N").upper(), r.get("source") or "manual", r.get("collect_tag") or None,
                r.get("agg") or "last", int(r.get("seq") or 0), json.dumps(_attrs_of(r), ensure_ascii=False), by))


def _seed_inspection_items(p, path: Path) -> None:
    by = f"seed:{p.name}"
    for r in _read_csv(path):
        for col, table, label in (("item_code", "bas_item", "품목"), ("process_code", "bas_process", "공정")):
            if r.get(col) and conn.q1(f"select 1 from {table} where {col} = %s", (r[col],)) is None:
                raise SystemExit(f"팩 시드 {path.name}: {label} {r[col]!r} 가 없다 — seeds[] 에 먼저 둔다 (NULL 로 넣지 않는다)")
        conn.x("""insert into qua_insp_plan (insp_type, item_id, process_id, item_key, label, unit, value_type, standard, min_value, max_value, seq, attrs, created_by)
                  values (%s, (select id from bas_item where item_code = %s), (select id from bas_process where process_code = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                  on conflict (insp_type, coalesce(item_id, 0), coalesce(process_id, 0), item_key) do update set label = excluded.label, unit = excluded.unit,
                      value_type = excluded.value_type, standard = excluded.standard, min_value = excluded.min_value, max_value = excluded.max_value, seq = excluded.seq,
                      attrs = coalesce(qua_insp_plan.attrs, '{}'::jsonb) || excluded.attrs""",
               (r["insp_type"], r.get("item_code") or None, r.get("process_code") or None, r["item_key"], r["label"], r.get("unit") or None,
                r.get("value_type") or "number", r.get("standard") or None, _num(r.get("min_value")), _num(r.get("max_value")),
                int(r.get("seq") or 0), json.dumps(_attrs_of(r), ensure_ascii=False), by))


def seed_pack() -> list[str]:
    """팩 시드를 멱등으로 넣는다. 순서: seeds[] 의 공정 → 품목 → 설비 → `process_params` → `inspection_items` → 나머지 seeds[](선언 순서 —
    codes · partners · workers · defect_codes · kpi_indicators · `{file, table, key}`(x_<팩>_* 등) · users*). 돌린 파일 목록을 돌려준다."""
    p = packs.current()
    if p.dir is None:
        return []
    entries = _seed_entries(p)
    early = sorted((e for e in entries if e["table"] in EARLY_TABLES), key=lambda e: EARLY_TABLES.index(e["table"]))
    late = [e for e in entries if e["table"] not in EARLY_TABLES and e["table"] != "sys_user"]
    done: list[str] = []

    def run(e: dict) -> None:
        rows = _read_csv(p.dir / e["file"])
        _n, ignored = upsert_csv(e["table"], e["key"], rows, source=f"seed:{p.name}", strict=e["strict"])
        if ignored:
            print(f"  [팩 시드 {e['file']}] {e['table']} 에 없는 열 {ignored} 는 넣지 않았다 — `attrs.<키>` 로 적으면 attrs 에 들어간다", file=sys.stderr)
        done.append(e["file"])

    for e in early:
        run(e)
    if p.process_params:
        _seed_process_params(p, p.dir / p.process_params)
        done.append(p.process_params)
    if p.inspection_items:
        _seed_inspection_items(p, p.dir / p.inspection_items)
        done.append(p.inspection_items)
    for e in late:
        run(e)
    return done


def pack_user_rows() -> list[dict]:
    """팩 계정 — ① 역할마다 하나(로그인 ID = 역할 코드 소문자 · 코어 4 역할은 `USERS` 이름) ② `seed/users.csv`(또는 seeds[] 의 users*) 행.
    비밀번호 열은 받지 않는다 — 전부 `MES_SEED_PASSWORD`(G-C19)."""
    p = packs.current()
    core_names = {code: (lid, name) for lid, name, code in USERS}
    rows = {}
    for r in p.roles:
        lid, name = core_names.get(r["code"], (r["code"].lower(), r["name"]))
        rows[lid] = {"login_id": lid, "user_name": name, "role_code": r["code"]}
    files = [e["file"] for e in p.seeds if not e.get("table") and Path(e["file"]).stem.startswith("users")]
    if p.dir is not None and (p.dir / "seed" / "users.csv").exists() and "seed/users.csv" not in files:
        files.append("seed/users.csv")
    for f in files:
        for r in _read_csv(p.dir / f):
            bad = [k for k in r if k not in USER_COLUMNS and k not in NOTE_COLUMNS]
            if bad:
                raise SystemExit(f"팩 계정 {f}: 모르는 열 {bad} — {USER_COLUMNS} (비밀번호는 MES_SEED_PASSWORD 로만)")
            if not r.get("login_id") or not r.get("role_code"):
                raise SystemExit(f"팩 계정 {f}: login_id · role_code 가 빈 행 — {r}")
            rows[r["login_id"]] = {k: r.get(k) or None for k in USER_COLUMNS} | {"user_name": r.get("user_name") or r["login_id"]}
    return list(rows.values())


def run_dev_seeds() -> list[str]:
    ran: list[str] = []
    here = Path(__file__).resolve().parent
    for name in DEV_SEEDS:
        if not (here / f"{name}.py").exists():
            continue
        mod = importlib.import_module(f"mescore.db.{name}")
        rc = mod.main()
        if rc:
            raise SystemExit(f"{name} 실패 (rc={rc})")
        ran.append(name)
    return ran


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    reset = "--reset" in argv
    seed_roles()
    seed_permissions(reset=reset)
    seed_numbering(reset=reset)
    seed_codes()
    seed_examples()
    pack_files = seed_pack()
    seed_users()                      # 팩 users.csv 가 작업자(bas_worker)를 가리킬 수 있어 팩 시드 뒤
    ran = [] if "--core-only" in argv else run_dev_seeds()
    counts = conn.table_counts()
    p = packs.current()
    print(f"시드 완료 — 팩 {p.name or '(코어 단독)'} · 역할 {counts.get('sys_role')} · 권한 칸 {counts.get('sys_permission')} · 계정 {counts.get('sys_user')} "
          f"· 채번 규칙 {counts.get('sys_number_rule')} · 공통코드 {counts.get('bas_code')} · 팩 시드 {pack_files or '없음'} · 개발 시드 {ran or '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
