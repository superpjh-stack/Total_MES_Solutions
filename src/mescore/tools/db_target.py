#!/usr/bin/env python
"""`Makefile` 의 DB 대상 — `MES_PG_DSN`(셸 · `.env`) 을 앱과 **같은 규칙**(`conn.dsn()`)으로 푼다 (DEF-QA1-008).

    uv run python src/mescore/tools/db_target.py name    # DB 이름 (예: mes_qa_db)
    uv run python src/mescore/tools/db_target.py dsn     # psql -d 에 줄 conninfo (host 가 없으면 PGHOST · 기본 /tmp)
    uv run python src/mescore/tools/db_target.py admin   # 같은 서버의 postgres DB (createdb 대신 CREATE DATABASE 용)

`MES_PG_DSN` 이 비면 `MES_PACK` 에 따라 `mes_core_db` / `mes_<팩>_db` — `db-seed`(seed_core) 와 `db-schema` 가 언제나 같은 DB 를 본다.
비밀번호가 DSN 에 있으면 conninfo 에 그대로 실린다 — make 는 명령 줄을 찍으므로 `db-*` 목표는 psql 줄을 `@` 로 숨긴다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from psycopg.conninfo import conninfo_to_dict, make_conninfo  # noqa: E402

from mescore.db import conn  # noqa: E402


def target(kind: str) -> str:
    params = {k: str(v) for k, v in conninfo_to_dict(conn.dsn()).items() if v is not None}
    if not params.get("dbname"):
        raise SystemExit("MES_PG_DSN 에 DB 이름이 없다 — 어느 DB 인지 지어내지 않는다")
    params.setdefault("host", os.environ.get("PGHOST") or "/tmp")
    if kind == "name":
        return params["dbname"]
    if kind == "admin":
        params["dbname"] = "postgres"
    return make_conninfo(**params)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("name", "dsn", "admin"):
        raise SystemExit(__doc__)
    print(target(sys.argv[1]))
