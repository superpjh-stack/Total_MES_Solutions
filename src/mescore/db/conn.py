"""DB 접속 — `contracts/interfaces.md` §1.

    q(sql, params) -> list[dict]   SELECT. 항상 dict 리스트
    q1(sql, params) -> dict|None   첫 행
    x(sql, params) -> int          INSERT/UPDATE/DELETE. rowcount
    tx()                           컨텍스트 매니저 (with tx() as cur:) — 여러 문장을 한 트랜잭션으로

DSN 은 `MES_PG_DSN` (비우면 `MES_PACK` 에 따라 `postgresql:///mes_core_db` · `postgresql:///mes_<팩>_db`).
**DB 연결 실패를 삼키지 않는다.** `DbUnavailable` 로 올려 보내고 main.py 가 503 `서비스 일시 중단` 으로 렌더링한다.
조용한 폴백(빈 리스트 반환 등)은 하지 않는다. 제약 위반(`psycopg.errors.IntegrityError`)도 그대로 올라가 main.py 가 422 로 바꾼다.

접속 문자열은 **어디에도 내보내지 않는다** — 응답에는 싣지 않고(`/health` 포함), 서버 로그에 남는 `DbUnavailable` 의 사유 문구에서는
비밀번호를 가린다. 접속 문자열 자체가 틀려 드라이버가 그 조각을 되읊는 경우는 원문을 버리고 예외 종류만 남긴다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from urllib.parse import quote

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from ..app.settings import get_settings


class DbUnavailable(RuntimeError):
    """DB 연결 자체가 되지 않는 상태. 503 `서비스 일시 중단` 으로 매핑된다."""


def dsn() -> str:
    return os.environ.get("MES_PG_DSN") or get_settings().pg_dsn


BAD_DSN = "접속 문자열(MES_PG_DSN)을 해석하지 못했다 — 형식을 확인한다 (원문은 접속 문자열 조각을 담을 수 있어 남기지 않는다)"


def _passwords() -> list[str]:
    try:
        found = [str(conninfo_to_dict(dsn()).get("password") or ""), os.environ.get("PGPASSWORD") or ""]
    except psycopg.Error as exc:
        raise DbUnavailable(f"{BAD_DSN} [{type(exc).__name__}]") from None
    return [v for pw in found if pw for v in {pw, quote(pw, safe="")}]


def unavailable(exc: psycopg.Error) -> DbUnavailable:
    """연결 실패 → `DbUnavailable`. 호스트 · 소켓 경로는 운영자가 봐야 하므로 두고 **비밀번호만** 가린다."""
    if not isinstance(exc, psycopg.OperationalError):
        return DbUnavailable(f"{BAD_DSN} [{type(exc).__name__}]")
    text = str(exc).strip()
    for secret in _passwords():
        text = text.replace(secret, "***")
    return DbUnavailable(text)


def connect() -> psycopg.Connection:
    """새 커넥션(autocommit). 연결 실패는 DbUnavailable 로 올린다(쿼리 오류는 그대로 통과시킨다)."""
    try:
        return psycopg.connect(dsn(), row_factory=dict_row, autocommit=True)
    except psycopg.Error as exc:
        raise unavailable(exc) from None


def q(sql: str, params: Sequence | Mapping | None = None) -> list[dict]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        return [dict(r) for r in cur.fetchall()]


def q1(sql: str, params: Sequence | Mapping | None = None) -> dict | None:
    rows = q(sql, params)
    return rows[0] if rows else None


def x(sql: str, params: Sequence | Mapping | None = None) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


@contextmanager
def tx() -> Iterator[psycopg.Cursor]:
    """트랜잭션 커서. 예외가 나면 되돌림하고 그대로 올린다."""
    try:
        conn = psycopg.connect(dsn(), row_factory=dict_row)
    except psycopg.Error as exc:
        raise unavailable(exc) from None
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except psycopg.OperationalError as exc:
        conn.rollback()
        raise unavailable(exc) from None
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def ping() -> bool:
    """`/health` 용. 실패는 DbUnavailable 로 올라간다 — True/False 로 뭉개지 않는다."""
    return q("select 1 as ok")[0]["ok"] == 1


def table_counts(exclude: tuple[str, ...] = ("sys_access_log", "sys_session")) -> dict[str, int]:
    """public 스키마의 테이블별 행 수 — 시드 멱등(G-C09) · 백업 대조용. 요청마다 늘어나는 로그 · 세션은 뺀다."""
    names = [r["table_name"] for r in q(
        "select table_name from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE' order by 1")]
    return {n: q1(f'select count(*) as n from "{n}"')["n"] for n in names if n not in exclude}
