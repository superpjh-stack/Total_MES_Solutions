"""개발2 테스트 공용 — 로그인 클라이언트 · 기준정보 조회 · 작업지시 픽스처 · 채번 대체(개발1 `numbering.py` 가 없을 때만).

채번 대체는 **`mescore.app.numbering` 가 import 되지 않을 때만** `interfaces.md` §3 의 규칙(prefix + to_char(date_format) + seq · `sys_number_rule` ·
`sys_number_seq` 행 잠금)으로 `sys.modules` 에 끼운다. 개발1 모듈이 생기면 이 코드는 한 줄도 돌지 않는다. 번호를 지어내지 않는다 —
`sys_number_rule` 에 종류가 없으면 똑같이 `RuntimeError`.
"""

from __future__ import annotations

import sys
import types
import uuid
from datetime import date

from fastapi.testclient import TestClient

from mescore.app.settings import get_settings
from mescore.db import conn

HTML = {"accept": "text/html"}


def ensure_numbering() -> str:
    """개발1 모듈이 있으면 'dev1', 없으면 대체를 끼우고 'stub'."""
    try:
        import mescore.app.numbering  # noqa: F401
        return "dev1"
    except ModuleNotFoundError:
        pass
    if "mescore.app.numbering" in sys.modules:
        return "stub"
    mod = types.ModuleType("mescore.app.numbering")
    mod.__doc__ = "테스트 전용 채번 대체 — 개발1 app/numbering.py 가 생기면 쓰이지 않는다"

    def rule(kind: str):
        return conn.q1("select * from sys_number_rule where kind = %s and use_yn = 'Y'", (kind,))

    def _scope(r, at, cur):
        sql = "select to_char(coalesce(%s::timestamptz, now()), %s) as s"
        if cur is None:
            return conn.q1(sql, (at, r["date_format"]))["s"]
        cur.execute(sql, (at, r["date_format"]))
        return cur.fetchone()["s"]

    def _bump(cur, kind, scope):
        cur.execute("""insert into sys_number_seq (kind, seq_scope, last_seq, created_by) values (%s, %s, 1, 'numbering')
                       on conflict (kind, seq_scope) do update set last_seq = sys_number_seq.last_seq + 1, updated_at = now()
                       returning last_seq""", (kind, scope))
        return cur.fetchone()["last_seq"]

    def next(kind: str, *, cur=None, at=None) -> str:  # noqa: A001 — 계약의 이름
        r = rule(kind)
        if r is None:
            raise RuntimeError(f"채번 규칙 없음: {kind} — sys_number_rule 에 행이 없다 (D-16 · core.yaml: numbering)")
        scope = _scope(r, at, cur)
        if cur is None:
            with conn.tx() as c:
                seq = _bump(c, kind, scope)
        else:
            seq = _bump(cur, kind, scope)
        return f"{r['prefix']}{scope}{str(seq).zfill(int(r['seq_digits']))}"

    def peek(kind: str, *, at=None) -> str:
        r = rule(kind)
        if r is None:
            raise RuntimeError(f"채번 규칙 없음: {kind}")
        scope = _scope(r, at, None)
        row = conn.q1("select last_seq from sys_number_seq where kind = %s and seq_scope = %s", (kind, scope))
        return f"{r['prefix']}{scope}{str((row['last_seq'] if row else 0) + 1).zfill(int(r['seq_digits']))}"

    mod.rule, mod.next, mod.peek = rule, next, peek
    sys.modules["mescore.app.numbering"] = mod
    import mescore.app as app_pkg
    app_pkg.numbering = mod
    return "stub"


NUMBERING_SOURCE = ensure_numbering()


def client(login_id: str | None = None, device: str | None = None) -> TestClient:
    from mescore.app.main import app

    c = TestClient(app, raise_server_exceptions=False)
    if login_id:
        data = {"login_id": login_id, "password": get_settings().seed_password}
        if device:
            data["device"] = device
        r = c.post("/login", data=data)
        assert r.status_code == 200 and r.json()["ok"], f"{login_id} 로그인 실패 {r.status_code} — make db-seed · .env 확인"
    return c


def uniq(prefix: str = "T") -> str:
    """바코드 허용 문자(A-Z 0-9 -)만으로 유일한 코드."""
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def item_id(code: str) -> int:
    r = conn.q1("select id from bas_item where item_code = %s", (code,))
    assert r, f"시드 품목 {code} 없음 — make db-seed"
    return r["id"]


def process_id(code: str = "PRC-EX-01") -> int:
    return conn.q1("select id from bas_process where process_code = %s", (code,))["id"]


def equipment_id(code: str = "EQ-EX-01") -> int:
    return conn.q1("select id from bas_equipment where equip_code = %s", (code,))["id"]


def partner_id(code: str) -> int:
    return conn.q1("select id from bas_partner where partner_code = %s", (code,))["id"]


def _one(cur, sql: str, params) -> dict:
    if cur is None:
        return conn.q1(sql, params)
    cur.execute(sql, params)
    return dict(cur.fetchone())


def new_work_order(cur=None, item_code: str = "PRD-EX-01", process_code: str = "PRC-EX-01", qty: float = 100, status: str = "대기",
                   equip_code: str = "EQ-EX-01") -> dict:
    """작업지시 1행 — job 모듈(개발1)의 테이블이지만 테스트 픽스처로 직접 넣는다. 번호는 테스트 전용 `T-W-…`(numbering 을 소비하지 않는다).
    `cur` 를 주면 그 트랜잭션 안에(되돌림 가능), 없으면 바로 커밋."""
    return _one(cur, """insert into job_work_order (work_order_no, item_id, process_id, equipment_id, plan_qty, unit, plan_date, status, created_by)
                        values (%s, %s, %s, %s, %s, 'EA', %s, %s, 'test') returning *""",
                (uniq("T-W"), item_id(item_code), process_id(process_code), equipment_id(equip_code), qty, date.today(), status))


def new_shipment(cur=None, partner_code: str = "CUST-EX-01") -> dict:
    return _one(cur, """insert into shp_shipment (shipment_no, partner_id, ship_date, created_by) values (%s, %s, current_date, 'test') returning *""",
                (uniq("T-S"), partner_id(partner_code)))
