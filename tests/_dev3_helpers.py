"""개발3 테스트 공용 — 로그인 클라이언트 · 예시 이관 데이터 적재 · 출하 시나리오 픽스처(생산 LOT 은 개발2 `lineage.make_product_lot` 로).

- DB 는 공통 시드(`make db-reset`)가 들어 있어야 한다. 시드 비밀번호는 `.env` 의 `MES_SEED_PASSWORD`.
- `load_examples()` 는 `migrate/examples/` 4종을 멱등 적재한다(M-EX-0001 … X-EX-0001 · S-EX-0001 — 계보 10행). 추적 · 집계 테스트의 고정 데이터.
- 생산 LOT 픽스처는 `job_work_order` · `pop_work_result` 행을 테스트 전용으로 넣고 `lineage.make_product_lot` 로 만든다(계보는 lineage 만).
  검사 판정은 qua 모듈의 일이지만 테스트 픽스처로 `lot.insp_status` 를 직접 둔다.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from mescore.app.settings import get_settings
from mescore.db import conn

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "src" / "mescore" / "migrate" / "examples"
HTML = {"accept": "text/html"}
BY = "test"


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
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def load_examples() -> None:
    """migrate/examples 4종을 멱등 적재 — 두 번째부터는 적재 0 · 갱신 n."""
    from mescore import migrate

    for cmd in ("basics", "orders", "lots", "history"):
        rep = migrate.run(cmd, EXAMPLES, run_by=BY)
        assert rep.ok, rep.text()


def ref(table: str, col: str, code: str) -> int:
    r = conn.q1(f"select id from {table} where {col} = %s", (code,))
    assert r, f"{table}.{col}={code} 없음 — make db-seed"
    return r["id"]


def new_work_order(cur, item_code: str = "PRD-EX-01", qty: float = 100) -> dict:
    cur.execute("""insert into job_work_order (work_order_no, item_id, process_id, equipment_id, plan_qty, unit, plan_date, status, created_by)
                   values (%s, %s, %s, %s, %s, 'EA', %s, '진행', 'test') returning *""",
                (uniq("T-W"), ref("bas_item", "item_code", item_code), ref("bas_process", "process_code", "PRC-EX-01"),
                 ref("bas_equipment", "equip_code", "EQ-EX-01"), qty, date.today()))
    return dict(cur.fetchone())


def product_lot(cur, wo: dict, qty: float = 10, insp_status: str = "합격") -> dict:
    """실적 1건(종료) → `lineage.make_product_lot` → 생산 LOT. 검사 상태는 픽스처로 둔다."""
    from mescore.app import lineage

    cur.execute("""insert into pop_work_result (work_order_id, process_id, equipment_id, started_at, ended_at, good_qty, unit, created_by)
                   values (%s, %s, %s, now() - interval '2 hour', now() - interval '1 hour', %s, 'EA', 'test') returning *""",
                (wo["id"], wo["process_id"], wo["equipment_id"], qty))
    r = dict(cur.fetchone())
    lot = lineage.make_product_lot(cur, work_result_id=r["id"], by=BY, qty=qty, unit="EA")
    cur.execute("update lot set insp_status = %s where id = %s", (insp_status, lot["id"]))
    lot["insp_status"] = insp_status
    return lot


def scenario_lots(n: int = 2, insp_status: str = "합격") -> list[dict]:
    """커밋된 생산 LOT n개 (같은 작업지시). 출하 스캔 테스트용."""
    with conn.tx() as cur:
        wo = new_work_order(cur)
        return [product_lot(cur, wo, qty=10 * (i + 1), insp_status=insp_status) for i in range(n)]


def new_shipment(c: TestClient, partner_code: str = "CUST-EX-01", order_no: str = "") -> dict:
    r = c.post("/shp/shipments", data={"partner_code": partner_code, "ship_date": date.today().isoformat(), "order_no": order_no})
    assert r.status_code == 200, r.text
    return r.json()


def lot_state(lot_id: int) -> str:
    return conn.q1("select state from v_lot_state where lot_id = %s", (lot_id,))["state"]


def genealogy_count(lot_no: str, relation_base: str = "출하") -> int:
    return conn.q1("""select count(*)::int as n from lot_genealogy g join lot l on l.id = g.parent_lot_id where l.lot_no = %s and g.relation_base = %s""",
                   (lot_no, relation_base))["n"]
