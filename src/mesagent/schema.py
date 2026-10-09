"""스키마 카탈로그 — 실제 DB(information_schema) + 계약 설명(contracts/db-schema.md §4) + 역할별 읽기 허용 테이블.

허용 테이블 = 지금 역할이 그 모듈 메뉴를 읽을 수 있는 테이블(rbac.can_read_menu). 비밀번호 해시 · 세션은 어느 역할에도 주지 않는다.
LOT · 계보 · LOT 뷰는 추적 · 자재 · 생산실적 · 출하 중 하나라도 읽을 수 있으면 허용한다.
"""

from __future__ import annotations

import re
from functools import lru_cache

from mescore.app import rbac
from mescore.app.settings import ROOT
from mescore.db import conn

NEVER = {"sys_session", "sys_user", "sys_number_seq"}           # 비밀번호 해시 · 세션 토큰 · 내부 카운터
SHARED = {"lot": ("trc", "mat", "pop", "shp"), "lot_genealogy": ("trc", "mat", "pop", "shp"),
          "v_lot_state": ("trc", "mat", "pop", "shp"), "v_lot_stock": ("trc", "mat", "pop", "shp"),
          "v_work_order_progress": ("job", "pop")}
PREFIX_MODULE = {p: p for p in ("bas", "ord", "job", "mat", "pop", "qua", "eqp", "shp", "kpi", "sys", "ifc")}


@lru_cache(maxsize=1)
def relations() -> dict[str, dict]:
    """공개 스키마의 테이블 · 뷰 → {kind, columns[(name, type)]}."""
    rows = conn.q("""select c.table_name, c.column_name, c.data_type, t.table_type
                       from information_schema.columns c join information_schema.tables t
                         on t.table_name = c.table_name and t.table_schema = c.table_schema
                      where c.table_schema = 'public' order by c.table_name, c.ordinal_position""")
    out: dict[str, dict] = {}
    for r in rows:
        d = out.setdefault(r["table_name"], {"kind": "view" if r["table_type"] == "VIEW" else "table", "columns": []})
        d["columns"].append((r["column_name"], r["data_type"]))
    return out


@lru_cache(maxsize=1)
def foreign_keys() -> list[tuple[str, str, str, str]]:
    rows = conn.q("""select tc.table_name, kcu.column_name, ccu.table_name as ref_table, ccu.column_name as ref_column
                       from information_schema.table_constraints tc
                       join information_schema.key_column_usage kcu on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema
                       join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name and ccu.table_schema = tc.table_schema
                      where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'public'""")
    return [(r["table_name"], r["column_name"], r["ref_table"], r["ref_column"]) for r in rows]


@lru_cache(maxsize=1)
def descriptions() -> dict[str, str]:
    """contracts/db-schema.md 의 `### \\`table\\`` 절 → 설명 한 단락."""
    f = ROOT / "contracts" / "db-schema.md"
    if not f.exists():
        return {}
    out, cur, buf = {}, None, []
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+`([a-z_0-9]+)`", line)
        if m:
            if cur:
                out[cur] = " ".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur and line.startswith("## "):
            out[cur] = " ".join(buf).strip()
            cur, buf = None, []
        elif cur and line.strip():
            buf.append(line.strip())
    if cur:
        out[cur] = " ".join(buf).strip()
    return {k: v[:700] for k, v in out.items()}


def module_of(rel: str) -> tuple[str, ...]:
    if rel in SHARED:
        return SHARED[rel]
    p = rel.split("_", 1)[0]
    return (PREFIX_MODULE[p],) if p in PREFIX_MODULE else ()


def allowed(user: rbac.User) -> list[str]:
    out = []
    for rel in relations():
        if rel in NEVER or rel.startswith("x_"):
            continue
        mods = module_of(rel)
        if mods and any(rbac.can_read_menu(user.role_code, m) for m in mods):
            out.append(rel)
    return sorted(out)


def table_list_text(names: list[str]) -> str:
    d = descriptions()
    return "\n".join(f"- {n}{' (뷰)' if relations()[n]['kind'] == 'view' else ''}: {d.get(n, '')[:160]}" for n in names)


def detail_text(names: list[str]) -> str:
    rels, d = relations(), descriptions()
    fks = [fk for fk in foreign_keys() if fk[0] in names]
    parts = []
    for n in names:
        cols = ", ".join(f"{c} {t}" for c, t in rels[n]["columns"] if c not in ("password_hash",))
        parts.append(f"### {n}{' (뷰)' if rels[n]['kind'] == 'view' else ''}\n설명: {d.get(n, '(없음)')}\n컬럼: {cols}")
    if fks:
        parts.append("### 외래키\n" + "\n".join(f"{a}.{b} → {c}.{e}" for a, b, c, e in fks))
    return "\n\n".join(parts)
