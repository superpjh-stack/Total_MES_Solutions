"""허브 저장소 — `hub` 스키마 DDL 과 파일 보관 폴더. 처음 쓰일 때 한 번 만든다(멱등)."""

from __future__ import annotations

import os
from pathlib import Path

from mescore.app.settings import ROOT
from mescore.db import conn

DDL = """
create schema if not exists hub;
create table if not exists hub.file (
    id            bigserial primary key,
    file_no       text unique,
    title         text not null,
    category      text not null,
    original_name text not null,
    ext           text not null,
    mime          text not null,
    size_bytes    bigint not null,
    sha256        text not null,
    stored_name   text not null,
    link_kind     text,
    link_ref      text,
    tags          text[] not null default '{}',
    note          text,
    text_excerpt  text,
    text_chars    integer not null default 0,
    created_at    timestamptz not null default now(),
    created_by    text not null,
    deleted_at    timestamptz,
    deleted_by    text
);
create index if not exists hub_file_created on hub.file (created_at desc) where deleted_at is null;
create table if not exists hub.ts_hourly (
    equipment_id  bigint not null,
    tag           text not null,
    hour          timestamptz not null,
    n             integer not null,
    v_min         numeric,
    v_max         numeric,
    v_avg         numeric,
    v_last        numeric,
    rolled_at     timestamptz not null default now(),
    primary key (equipment_id, tag, hour)
);
create table if not exists hub.rollup_log (
    id        bigserial primary key,
    ran_at    timestamptz not null default now(),
    ran_by    text not null,
    hours     integer not null,
    rows_in   integer not null
);
"""

_ready = False


def ensure() -> None:
    global _ready
    if _ready:
        return
    with conn.tx() as cur:
        cur.execute(DDL)
    _ready = True


def files_dir() -> Path:
    d = Path(os.environ.get("MES_HUB_DIR") or (ROOT / "var" / "hub"))
    d.mkdir(parents=True, exist_ok=True)
    return d
