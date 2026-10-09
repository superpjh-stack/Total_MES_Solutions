"""SQL 검사 · 읽기 전용 실행 — 에이전트가 쓴 SQL 은 이 관문을 지나야만 DB 에 닿는다.

검사: 주석 제거 · 한 문장 · SELECT/WITH 로 시작 · 쓰기/관리/파일/네트워크 키워드 없음 · 시스템 카탈로그 없음 · 참조한 테이블이 전부 허용 목록 안.
실행: 새 연결 · `BEGIN READ ONLY` · `statement_timeout` · 행 상한(바깥에서 LIMIT) · 끝나면 무조건 ROLLBACK. DB 는 바뀌지 않는다.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import time

import psycopg
from psycopg.rows import dict_row

from mescore.db import conn

MAX_ROWS = 200
TIMEOUT_MS = 5000
BLOCKED = re.compile(
    r"\b(insert|update|delete|merge|upsert|drop|alter|create|truncate|grant|revoke|copy|call|do|execute|prepare|deallocate|vacuum|analyze|cluster|"
    r"reindex|refresh|comment|security|lock|listen|notify|unlisten|set|reset|discard|begin|commit|rollback|savepoint|into|"
    r"pg_sleep\w*|pg_read\w*|pg_ls\w*|pg_stat_file|pg_terminate\w*|pg_cancel\w*|lo_\w+|dblink\w*|set_config|pg_advisory\w*|query_to_xml|xpath)\b",
    re.I)
CATALOG = re.compile(r"\b(pg_catalog|information_schema|pg_[a-z_]+)\b", re.I)


class SqlRejected(ValueError):
    pass


def _strip(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return sql.strip().rstrip(";").strip()


def _no_strings(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check(sql: str, known: set[str], allowed: set[str]) -> str:
    s = _strip(sql)
    if not s:
        raise SqlRejected("빈 SQL")
    bare = _no_strings(s)
    if ";" in bare:
        raise SqlRejected("한 문장만 실행한다 (세미콜론으로 이어진 여러 문장)")
    if not re.match(r"^(select|with)\b", bare, re.I):
        raise SqlRejected("SELECT 또는 WITH 로 시작하는 조회만 실행한다")
    m = BLOCKED.search(bare)
    if m:
        raise SqlRejected(f"허용하지 않는 키워드: {m.group(0)}")
    m = CATALOG.search(bare)
    if m:
        raise SqlRejected(f"시스템 카탈로그는 조회하지 않는다: {m.group(0)}")
    used = {t for t in re.findall(r"\b([a-z_][a-z0-9_]*)\b", bare.lower()) if t in known}
    denied = sorted(used - allowed)
    if denied:
        raise SqlRejected(f"지금 역할이 읽을 수 없는 테이블: {', '.join(denied)}")
    if not used:
        raise SqlRejected("MES 테이블을 하나도 참조하지 않는다")
    return s


def _plain(v):
    if isinstance(v, decimal.Decimal):
        return float(v) if v != v.to_integral_value() else int(v)
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat(sep=" ", timespec="minutes") if isinstance(v, dt.datetime) else v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "(이진)"
    return v


def run(sql: str) -> dict:
    """검사를 통과한 SQL 을 읽기 전용으로 실행. 실패는 psycopg.Error 그대로 올린다(에이전트가 고치게)."""
    t0 = time.perf_counter()
    with psycopg.connect(conn.dsn(), row_factory=dict_row) as c:
        try:
            with c.cursor() as cur:
                cur.execute("begin read only")
                cur.execute(f"set local statement_timeout = {TIMEOUT_MS}")
                cur.execute(f"select * from ({sql}) as agent_q limit {MAX_ROWS + 1}")
                rows = cur.fetchall()
                cols = [d.name for d in cur.description or []]
        finally:
            c.rollback()
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    return {"columns": cols, "rows": [{k: _plain(v) for k, v in r.items()} for r in rows], "row_count": len(rows),
            "truncated": truncated, "ms": round((time.perf_counter() - t0) * 1000)}
