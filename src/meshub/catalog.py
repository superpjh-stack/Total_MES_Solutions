"""정형 데이터 — 코어 · 팩 업무 테이블(public 스키마)의 카탈로그 · 미리보기 · CSV 내보내기.

허브는 정형 데이터를 복사하지 않는다. 업무 테이블이 원본이고, 여기서는 얼마나 · 언제까지 쌓였는지 보고 읽기 전용으로 꺼낸다.
테이블 이름은 information_schema 에 있는 것만 받고(화이트리스트) SQL 식별자로 인용한다.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from functools import lru_cache

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from mescore.app import rbac
from mescore.app.settings import ROOT
from mescore.db import conn

from . import access

EXPORT_MAX = 50_000
PREVIEW = 50
TIMEOUT_MS = 10_000


@dataclass
class TableInfo:
    name: str
    kind: str                 # table | view
    module: str
    module_name: str
    rows: int
    bytes: int
    last_at: object = None
    new_7d: int | None = None
    description: str = ""


def relations() -> dict[str, dict]:
    rows = conn.q("""select t.table_name, t.table_type, array_agg(c.column_name::text order by c.ordinal_position) as cols
                       from information_schema.tables t join information_schema.columns c
                         on c.table_schema = t.table_schema and c.table_name = t.table_name
                      where t.table_schema = 'public' group by t.table_name, t.table_type""")
    return {r["table_name"]: {"kind": "view" if r["table_type"] == "VIEW" else "table", "cols": list(r["cols"])} for r in rows}


@lru_cache(maxsize=1)
def descriptions() -> dict[str, str]:
    f = ROOT / "contracts" / "db-schema.md"
    out, cur, buf = {}, None, []
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^###\s+`([a-z_0-9]+)`", line)
        if m:
            if cur:
                out[cur] = " ".join(buf).strip()[:200]
            cur, buf = m.group(1), []
        elif cur and line.startswith("## "):
            out[cur] = " ".join(buf).strip()[:200]
            cur = None
        elif cur and line.strip() and not line.startswith("|"):
            buf.append(line.strip())
    if cur:
        out[cur] = " ".join(buf).strip()[:200]
    return out


def _stats(name: str, info: dict) -> TableInfo:
    cols = set(info["cols"])
    ident = sql.Identifier(name)
    parts = [sql.SQL("count(*)::bigint as n")]
    stamp = [c for c in ("updated_at", "created_at", "ts", "logged_at", "received_at") if c in cols]
    if stamp:
        parts.append(sql.SQL("max(greatest({})) as last_at").format(sql.SQL(", ").join(sql.Identifier(c) for c in stamp)))
    if "created_at" in cols:
        parts.append(sql.SQL("count(*) filter (where created_at >= now() - interval '7 days')::bigint as new_7d"))
    with psycopg.connect(conn.dsn(), row_factory=dict_row) as c:
        r = c.execute(sql.SQL("select {} from {}").format(sql.SQL(", ").join(parts), ident)).fetchone()
        size = c.execute("select coalesce(pg_total_relation_size(to_regclass(%s)), 0)::bigint as b", (f"public.{name}",)).fetchone()["b"] if info["kind"] == "table" else 0
    mod = access.module_of(name)
    return TableInfo(name, info["kind"], mod, access.module_name(mod), int(r["n"]), int(size), r.get("last_at"), r.get("new_7d"),
                     descriptions().get(name, ""))


def catalog(user: rbac.User) -> list[TableInfo]:
    out = []
    for name, info in sorted(relations().items()):
        if access.can_read(user, name):
            out.append(_stats(name, info))
    return out


def summary(tables: list[TableInfo]) -> dict:
    by_mod: dict[str, dict] = {}
    for t in tables:
        m = by_mod.setdefault(t.module, {"module": t.module, "name": t.module_name, "tables": 0, "rows": 0, "bytes": 0, "new_7d": 0})
        m["tables"] += 1
        m["rows"] += t.rows
        m["bytes"] += t.bytes
        m["new_7d"] += t.new_7d or 0
    return {"tables": sum(1 for t in tables if t.kind == "table"), "views": sum(1 for t in tables if t.kind == "view"),
            "rows": sum(t.rows for t in tables if t.kind == "table"), "bytes": sum(t.bytes for t in tables),
            "new_7d": sum(t.new_7d or 0 for t in tables), "modules": sorted(by_mod.values(), key=lambda m: -m["rows"])}


def check_name(user: rbac.User, name: str) -> dict:
    rels = relations()
    if name not in rels:
        raise KeyError(name)
    if not access.can_read(user, name):
        raise PermissionError(name)
    return rels[name]


def _select(name: str, cols: list[str], days: int | None, limit: int) -> sql.Composed:
    where = sql.SQL("")
    if days and "created_at" in cols:
        where = sql.SQL(" where created_at >= now() - make_interval(days => {})").format(sql.Literal(int(days)))
    order = sql.SQL(" order by id desc") if "id" in cols else sql.SQL("")
    return sql.SQL("select * from {}{}{} limit {}").format(sql.Identifier(name), where, order, sql.Literal(limit))


def _read(q: sql.Composed) -> tuple[list[str], list[tuple]]:
    with psycopg.connect(conn.dsn()) as c:
        try:
            cur = c.cursor()
            cur.execute("begin read only")
            cur.execute(f"set local statement_timeout = {TIMEOUT_MS}")
            cur.execute(q)
            return [d.name for d in cur.description or []], cur.fetchall()
        finally:
            c.rollback()


def preview(name: str, cols: list[str]) -> dict:
    names, rows = _read(_select(name, cols, None, PREVIEW))
    return {"columns": names, "rows": [dict(zip(names, r)) for r in rows]}


def export_csv(name: str, cols: list[str], days: int | None) -> tuple[str, int, bool]:
    names, rows = _read(_select(name, cols, days, EXPORT_MAX + 1))
    truncated = len(rows) > EXPORT_MAX
    buf = io.StringIO()
    buf.write("﻿")                                            # 엑셀이 한글을 바로 읽게
    w = csv.writer(buf)
    w.writerow(names)
    for r in rows[:EXPORT_MAX]:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue(), min(len(rows), EXPORT_MAX), truncated


def daily(user: rbac.User, days: int = 14) -> list[dict]:
    """읽을 수 있는 테이블 전체의 날짜별 신규 행 수(created_at 기준)."""
    names = [n for n, i in relations().items() if i["kind"] == "table" and "created_at" in i["cols"] and access.can_read(user, n)]
    if not names:
        return []
    union = sql.SQL(" union all ").join(
        sql.SQL("select created_at::date as day, count(*) as n from {} where created_at >= current_date - {} group by 1").format(
            sql.Identifier(n), sql.Literal(days - 1)) for n in names)
    q = sql.SQL("""select d::date as day, coalesce(sum(u.n), 0)::bigint as n
                     from generate_series(current_date - {}, current_date, interval '1 day') d
                     left join ({}) u on u.day = d::date group by 1 order by 1""").format(sql.Literal(days - 1), union)
    with psycopg.connect(conn.dsn(), row_factory=dict_row) as c:
        return c.execute(q).fetchall()
