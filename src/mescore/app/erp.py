"""ERP 연계 어댑터 + 외부 전송 큐 — `interfaces.md` §7 · D-02 · D-20 · G-C16.

담당 **개발3**. 연계 범위 · 방식이 정해지지 않았다(D-02). 기본 어댑터 `ErpAdapter` 는 무엇을 부르든 **501 `ERP 연계 미확정 (D-02)`** 을 올린다 —
빈 목록 · "성공" 을 돌려주는 조용한 폴백은 없다. 팩은 `pack.yaml: adapters.erp` 로 모듈 파일을 주고 그 안에 `class Adapter(ErpAdapter)`
또는 `def adapter() -> ErpAdapter` 를 둔다(E7). 부르는 쪽(`flush` · `retry`)은 바뀌지 않는다.

    enqueue(cur, kind, payload) -> int   ifc_outbox 에 `대기` 한 행 — after_commit_* 훅(팩)이 쓴다 (D-20). 같은 tx 커서를 받는다
    flush(limit=100) -> dict             큐의 대기 · 실패 · 미확정 행을 어댑터로 보낸다. 어댑터가 501 이면 그 행은 `미확정` 으로 남긴다(G-C16)
    retry(outbox_id) -> dict             F-IFC-04 — 한 행만. 어댑터가 501 이면 행을 `미확정` 으로 적고 **501 을 그대로** 올린다

쓰는 테이블: `ifc_outbox` · `ifc_erp_link` 뿐 (db-schema.md §2 ifc 행). 전송 한 번마다 `ifc_erp_link` 에 기록 한 줄(대기/성공/실패/미확정).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..db import conn
from . import packs
from .util import http

DECISION = "D-02"
WHAT = "ERP 연계"
WAITING, SENT, FAILED, UNDECIDED = "대기", "전송", "실패", "미확정"
LINK_WAITING, LINK_OK, LINK_FAILED, LINK_UNDECIDED = "대기", "성공", "실패", "미확정"
RETRYABLE: tuple[str, ...] = (WAITING, FAILED, UNDECIDED)


@dataclass(frozen=True)
class ErpResult:
    ok: bool
    message: str = ""
    ref: str | None = None            # ERP 쪽 참조 번호 (있으면)


class ErpAdapter:
    """기본 어댑터 — 전부 501. 팩이 상속해 `push` · `pull` 을 구현한다."""

    name = "undecided"

    def push(self, kind: str, payload: dict) -> ErpResult:
        raise http.undecided(DECISION, WHAT)

    def pull(self, kind: str, since: datetime) -> list[dict]:
        raise http.undecided(DECISION, WHAT)


def adapter() -> ErpAdapter:
    """현재 팩의 ERP 어댑터. 선언이 없으면 기본(501). 선언한 파일이 깨졌으면 그대로 올린다(조용히 기본으로 가지 않는다)."""
    pack = packs.current()
    rel = (pack.adapters or {}).get("erp")
    if not rel or pack.dir is None:
        return ErpAdapter()
    path = Path(pack.dir) / rel
    name = f"packs.{pack.name}.adapters.{path.stem}"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    if hasattr(mod, "adapter"):
        return mod.adapter()
    if hasattr(mod, "Adapter"):
        return mod.Adapter()
    raise RuntimeError(f"ERP 어댑터 모듈에 Adapter 클래스나 adapter() 가 없다: {path}")


def is_undecided() -> bool:
    return type(adapter()) is ErpAdapter


# ── 큐 ─────────────────────────────────────────────────────────────────
def _json(payload: Any) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, default=str)


def enqueue(cur, kind: str, payload: dict, *, by: str | None = None) -> int:
    """`ifc_outbox` 에 `대기` 한 행. 같은 트랜잭션의 커서를 받는다 — 본 거래가 되돌아가면 큐도 되돌아간다."""
    cur.execute("""insert into ifc_outbox (event, payload, status, attempts, created_by) values (%s, %s::jsonb, %s, 0, %s) returning id""",
                (kind, _json(payload), WAITING, by or "erp"))
    return cur.fetchone()["id"]


def outbox(limit: int = 200, *, status: str | None = None) -> list[dict]:
    return conn.q("""select id, event, payload, status, attempts, last_error, sent_at, created_at, created_by
                       from ifc_outbox where (%(st)s::text is null or status = %(st)s::text)
                      order by id desc limit %(n)s""", {"st": status, "n": limit})


def links(limit: int = 200) -> list[dict]:
    return conn.q("""select id, kind, direction, ref_table, ref_id, status, message, linked_at
                       from ifc_erp_link order by id desc limit %s""", (limit,))


def _record(cur, row: dict, status: str, message: str | None, *, sent: bool) -> None:
    cur.execute("""update ifc_outbox set status = %s, attempts = attempts + 1, last_error = %s,
                          sent_at = case when %s then now() else sent_at end, updated_at = now(), updated_by = 'erp'
                    where id = %s""", (status, message, sent, row["id"]))
    link_status = {SENT: LINK_OK, FAILED: LINK_FAILED, UNDECIDED: LINK_UNDECIDED}[status]
    cur.execute("""insert into ifc_erp_link (kind, direction, ref_table, ref_id, status, message, created_by)
                   values (%s, 'push', 'ifc_outbox', %s, %s, %s, 'erp')""",
                (row["event"], row["id"], link_status, message))


def _send_one(cur, row: dict) -> tuple[str, HTTPException | None, str | None]:
    """한 행을 어댑터로. 돌려주는 값 (새 상태, 501 예외 또는 None, 메시지)."""
    try:
        result = adapter().push(row["event"], row["payload"] or {})
    except HTTPException as exc:
        if exc.status_code == 501:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            msg = detail.get("message") or f"{WHAT} 미확정 ({DECISION})"
            _record(cur, row, UNDECIDED, msg, sent=False)
            return UNDECIDED, exc, msg
        raise
    except Exception as exc:  # noqa: BLE001 — 어댑터의 전송 실패. 삼키지 않고 행에 남긴다
        msg = f"{type(exc).__name__}: {exc}"[:500]
        _record(cur, row, FAILED, msg, sent=False)
        return FAILED, None, msg
    if result.ok:
        _record(cur, row, SENT, result.message or result.ref, sent=True)
        return SENT, None, result.message
    _record(cur, row, FAILED, result.message or "어댑터가 실패를 돌려줌", sent=False)
    return FAILED, None, result.message


def flush(limit: int = 100) -> dict:
    """큐 비우기(`make erp-flush`). 어댑터가 501 이면 그 행은 `미확정` 으로 남고 결과의 `undecided` 에 센다 — 조용한 폴백 0."""
    rows = conn.q("""select id, event, payload, status from ifc_outbox where status = any(%s) order by id limit %s""", (list(RETRYABLE), limit))
    out = {"processed": 0, "sent": 0, "failed": 0, "undecided": 0, "decision": DECISION if rows else None, "ids": []}
    for row in rows:
        with conn.tx() as cur:
            status, _exc, _msg = _send_one(cur, row)
        out["processed"] += 1
        out["ids"].append(row["id"])
        out[{SENT: "sent", FAILED: "failed", UNDECIDED: "undecided"}[status]] += 1
    return out


def retry(outbox_id: int) -> dict:
    """F-IFC-04 — 한 행 재전송. 없는 ID 는 404 · 이미 `전송` 된 행은 422. 어댑터가 501 이면 행을 `미확정` 으로 적은 뒤 **501 을 그대로** 올린다."""
    row = conn.q1("select id, event, payload, status from ifc_outbox where id = %s", (outbox_id,))
    if row is None:
        raise http.not_found()
    if row["status"] == SENT:
        raise http.validation_error("이미 전송된 항목입니다", fields=[{"name": "id", "reason": f"{outbox_id} 상태 {row['status']}"}])
    with conn.tx() as cur:
        status, exc, msg = _send_one(cur, row)
    if exc is not None:
        raise exc
    return {"id": outbox_id, "status": status, "message": msg}
