#!/usr/bin/env python
"""계약 렌더본 다시 찍기 — `make contracts` (D-23).

  contracts/db-schema.md §4   ← src/mescore/db/schema.sql (`-- @table 이름 | 모듈 | 설명 | 근거` · 컬럼 끝 `-- 설명`) + 실제 DB(타입 · NULL)
  contracts/screen-map.md §1  ← app/nav.py (core.yaml 병합본) + contracts/function-list.md (기능 범위)
  contracts/screen-map.md §4  ← 팩 화면 (MES_PACK 이 있을 때)

`<!-- BEGIN:generated <이름> -->` … `<!-- END:generated <이름> -->` 사이만 바꾼다. 수치(52 · 51)는 바꾸지 않는다 — 다르면 멈춘다.
tools/check_schema.py · check_trace.py 가 "렌더본 = 원본" 을 같은 함수로 대조한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from mescore.db import conn  # noqa: E402

DB_SCHEMA_MD = ROOT / "contracts" / "db-schema.md"
SCREEN_MAP_MD = ROOT / "contracts" / "screen-map.md"
SCHEMA_SQL = ROOT / "src" / "mescore" / "db" / "schema.sql"
COMMON_COLUMNS = ("id", "created_at", "created_by", "updated_at", "updated_by", "attrs")
TABLE_RE = re.compile(r"^-- @table (\w+) \| ([^|]+?) \| ([^|]+?)(?: \| (.+?))?\s*$", re.M)
COL_RE = re.compile(r"^    (\w+)\s+[^,]*?(?:,\s*)?(?:--\s*(.*))?$")


def parse_schema_sql() -> list[dict]:
    """schema.sql → [{name, module, desc, basis, columns: {컬럼: 설명}}] (파일 순서)."""
    text = SCHEMA_SQL.read_text(encoding="utf-8")
    out: list[dict] = []
    for m in TABLE_RE.finditer(text):
        name = m.group(1)
        body_m = re.search(rf"create table {name} \((.*?)\n\);", text[m.end():], re.S)
        if not body_m:
            raise SystemExit(f"schema.sql: `{name}` 의 create table 블록을 찾지 못했다")
        cols: dict[str, str] = {}
        for ln in body_m.group(1).splitlines():
            if not ln.startswith("    ") or ln.strip().startswith("constraint"):
                continue
            cm = COL_RE.match(ln.rstrip())
            if cm:
                cols[cm.group(1)] = (cm.group(2) or "").strip()
        out.append({"name": name, "module": m.group(2).strip(), "desc": m.group(3).strip(), "basis": (m.group(4) or "").strip(), "columns": cols})
    return out


def db_columns() -> dict[str, list[tuple[str, str, bool]]]:
    """실제 DB → {테이블: [(컬럼, 타입, NULL 허용)]}. 타입은 `format_type` 그대로."""
    rows = conn.q(
        """select c.relname as t, a.attname as col, format_type(a.atttypid, a.atttypmod) as typ, not a.attnotnull as nullable
             from pg_attribute a join pg_class c on c.oid = a.attrelid join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r' and a.attnum > 0 and not a.attisdropped
            order by c.relname, a.attnum""")
    out: dict[str, list[tuple[str, str, bool]]] = {}
    for r in rows:
        out.setdefault(r["t"], []).append((r["col"], r["typ"], r["nullable"]))
    return out


def render_tables() -> str:
    spec = parse_schema_sql()
    live = db_columns()
    core_live = {t: c for t, c in live.items() if not t.startswith("x_")}
    names = [t["name"] for t in spec]
    if set(names) != set(core_live):
        raise SystemExit(f"schema.sql 과 DB 의 코어 테이블이 다르다 — sql 에만 {sorted(set(names) - set(core_live))} · "
                         f"DB 에만 {sorted(set(core_live) - set(names))}. `make db-schema` 를 먼저 돌린다.")
    out: list[str] = []
    for t in spec:
        out.append(f"### `{t['name']}` — {t['module']} · {t['desc']}")
        if t["basis"]:
            out.append(f"근거: {t['basis']}")
        out.append("")
        out.append("| 컬럼 | 타입 | NULL | 설명 |")
        out.append("|---|---|---|---|")
        for col, typ, nullable in live[t["name"]]:
            if col in COMMON_COLUMNS:
                continue
            out.append(f"| `{col}` | `{typ}` | {'Y' if nullable else 'N'} | {t['columns'].get(col, '')} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_screens(pack: bool = False) -> str:
    from mescore.app import contracts, nav

    screens = nav.PACK_SCREENS if pack else nav.CORE_SCREENS
    if pack and not screens:
        return "(아직 없음 — 웨이브 B 에서 채워진다. 형식은 §1 과 같고 화면 ID 는 `X-<모듈>-nn`, 담당은 그 팩 담당.)\n"
    out = ["| # | 화면 ID | 모듈 | 메뉴 | 화면 | 경로 | 담당 | 채널 | 기능 |", "|---|---|---|---|---|---|---|---|---|"]
    for i, s in enumerate(screens, start=1):
        fns = contracts.functions_of(s.screen_id)
        if fns:
            ids = [f.id for f in fns]
            rng = ids[0] if len(ids) == 1 else f"{ids[0]} ~ {ids[-1].rsplit('-', 1)[1]}"
            fn_text = f"{rng} ({len(ids)})"
        else:
            fn_text = "(계약 없음)"
        out.append(f"| {i} | {s.screen_id} | {s.module} | {nav.menu(s.menu_code).name} | {s.name} | `{s.path}` | {s.owner} | {', '.join(s.channels)} | {fn_text} |")
    return "\n".join(out) + "\n"


def replace_block(text: str, name: str, new: str, path: Path) -> str:
    begin, end = f"<!-- BEGIN:generated {name} -->", f"<!-- END:generated {name} -->"
    if begin not in text or end not in text:
        raise SystemExit(f"{path.name} 에 {begin} … {end} 표식이 없다")
    head, rest = text.split(begin, 1)
    _old, tail = rest.split(end, 1)
    return f"{head}{begin}\n{new}{end}{tail}"


def main() -> int:
    import os

    text = DB_SCHEMA_MD.read_text(encoding="utf-8")
    new = replace_block(text, "tables", render_tables(), DB_SCHEMA_MD)
    changed = []
    if new != text:
        DB_SCHEMA_MD.write_text(new, encoding="utf-8")
        changed.append("db-schema.md §4")
    text = SCREEN_MAP_MD.read_text(encoding="utf-8")
    new = replace_block(text, "screens", render_screens(), SCREEN_MAP_MD)
    if os.environ.get("MES_PACK"):
        new = replace_block(new, "pack screens", render_screens(pack=True), SCREEN_MAP_MD)
    if new != text:
        SCREEN_MAP_MD.write_text(new, encoding="utf-8")
        changed.append("screen-map.md §1" + (" · §4" if os.environ.get("MES_PACK") else ""))
    n_tables = len(parse_schema_sql())
    print(f"contracts 렌더본 — 테이블 {n_tables} · 화면 51 · 바뀐 파일 {changed or '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
