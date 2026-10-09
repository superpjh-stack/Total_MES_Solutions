"""kimchi 팩 테스트 공용 — 로그인 클라이언트 · 코어 API 로 입고/검사/실적/출하 · 수집 메시지 · 공정 조건 (개발3 · 2026-10-09).

실행: `MES_PACK=kimchi uv run pytest -q packs/kimchi/tests` — DB 는 `mes_kimchi_db`(시드: `MES_PACK=kimchi make db-seed` · 새 DB 는 `make pack-db NAME=kimchi`).
시나리오는 전부 **코어 API + 팩 API** 로 재현한다(gates.yaml). 작업지시 행만 코어 테스트(`tests/_dev2_helpers.py`)와 같이 테스트 픽스처로 직접 넣는다(번호 `T-W-…`).
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for p in (ROOT / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi.testclient import TestClient  # noqa: E402

from mescore.app.settings import get_settings  # noqa: E402
from mescore.db import conn  # noqa: E402

HTML = {"accept": "text/html"}
ITEM_FG, ITEM_CABBAGE, ITEM_PEPPER, ITEM_GARLIC = "FG-BC-010", "RM-001", "RM-003", "RM-004"
PARTNER = "CUST-EX-01"
SUPPLIER = "SUP-EX-01"


def client(login_id: str | None = None, device: str | None = None) -> TestClient:
    from mescore.app.main import app

    c = TestClient(app, raise_server_exceptions=False)
    if login_id:
        data = {"login_id": login_id, "password": get_settings().seed_password}
        if device:
            data["device"] = device
        r = c.post("/login", data=data)
        assert r.status_code == 200 and r.json()["ok"], f"{login_id} 로그인 실패 {r.status_code} — 시드 · .env 확인"
    return c


def token() -> str:
    tok = get_settings().collect_token
    assert tok, "MES_COLLECT_TOKEN 미설정 — make setup"
    return tok


def uniq(prefix: str = "T") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def ref(table: str, col: str, code: str) -> int:
    r = conn.q1(f"select id from {table} where {col} = %s", (code,))
    assert r, f"{table}.{col}={code} 없음 — 시드 확인"
    return r["id"]


def item_id(code: str) -> int:
    return ref("bas_item", "item_code", code)


def equip_id(code: str) -> int:
    return ref("bas_equipment", "equip_code", code)


def process_id(code: str) -> int:
    return ref("bas_process", "process_code", code)


# ── 코어 흐름 ──────────────────────────────────────────────────────────
def receive_and_pass(item_code: str, qty: float, *, prod=None, qa=None) -> dict:
    """MAT-01 입고 → MAT-02 입고검사 합격 → {lot_id, lot_no}."""
    prod, qa = prod or client("prod"), qa or client("qa")
    r = prod.post("/mat/receipts", data={"item_id": item_id(item_code), "qty": qty, "partner_id": ref("bas_partner", "partner_code", SUPPLIER)})
    assert r.status_code == 200, r.text
    body = r.json()
    j = qa.post("/mat/inspections", data={"lot_no": body["lot_no"], "judgement": "합격"})
    assert j.status_code == 200, j.text
    return body


def work_order(process_code: str, equip_code: str | None = None, *, item_code: str = ITEM_FG, qty: float = 100, unit: str = "kg") -> dict:
    """작업지시 1행 — 테스트 픽스처 (코어 tests/_dev2_helpers.new_work_order 와 같은 방식)."""
    return conn.q1("""insert into job_work_order (work_order_no, item_id, process_id, equipment_id, plan_qty, unit, plan_date, status, created_by)
                      values (%s, %s, %s, %s, %s, %s, %s, '대기', 'test') returning *""",
                   (uniq("T-W"), item_id(item_code), process_id(process_code), equip_id(equip_code) if equip_code else None, qty, unit, date.today()))


def start(c: TestClient, wo: dict, equip_code: str | None = None) -> dict:
    data = {"work_order_id": wo["id"]}
    if equip_code:
        data["equipment_id"] = equip_id(equip_code)
    r = c.post("/pop/result/start", data=data)
    assert r.status_code == 200, r.text
    return r.json()


def scan_input(c: TestClient, result_id: int, lot_no: str, qty: float) -> dict:
    r = c.post("/pop/inputs", data={"work_result_id": result_id, "barcode": lot_no, "qty": qty})
    assert r.status_code == 200, r.text
    return r.json()


def end(c: TestClient, result_id: int, good: float, **measures) -> dict:
    data = {"good_qty": good, **{f"m_{k}": v for k, v in measures.items()}}
    r = c.post(f"/pop/result/{result_id}/end", data=data)
    assert r.status_code == 200, r.text
    return r.json()


def run_result(c: TestClient, wo: dict, inputs: list[tuple[str, float]], good: float, equip_code: str | None = None, **measures) -> dict:
    s = start(c, wo, equip_code)
    for lot_no, qty in inputs:
        scan_input(c, s["id"], lot_no, qty)
    e = end(c, s["id"], good, **measures)
    return {**e, "result_id": s["id"]}


def inspect(qa: TestClient, lot_no: str, insp_type: str, judgement: str, *, defect_code: str | None = None, defect_qty: float = 1, **items) -> dict:
    """QUA-02 검사 등록(i_<key>) → 판정. 불합격이면 불량코드 한 줄."""
    r = qa.post("/qua/inspections", data={"insp_type": insp_type, "lot_no": lot_no, **{f"i_{k}": v for k, v in items.items()}})
    assert r.status_code == 200, r.text
    insp_id = r.json()["id"]
    data = {"judgement": judgement}
    if judgement == "불합격":
        data.update({"defect_code_id": [str(ref("bas_defect_code", "defect_code", defect_code or "DF-EX-01"))], "defect_qty": [str(defect_qty)]})
    j = qa.post(f"/qua/inspections/{insp_id}/judge", data=data)
    assert j.status_code == 200, j.text
    return {**j.json(), "inspection_id": insp_id}


def new_shipment(c: TestClient) -> dict:
    r = c.post("/shp/shipments", data={"partner_code": PARTNER, "ship_date": date.today().isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def scan_ship(c: TestClient, shipment_no: str, lot_no: str):
    return c.post("/shp/scan", data={"shipment_no": shipment_no, "barcode": lot_no})


def approve(c: TestClient, shipment_id: int):
    return c.post(f"/shp/shipments/{shipment_id}/approve")


def shipment_lot_no(shipment_id: int) -> str:
    return conn.q1("select lot_no from lot where shipment_id = %s and kind_base = 'SHIPMENT'", (shipment_id,))["lot_no"]


# ── 수집 ───────────────────────────────────────────────────────────────
def ts(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def collect(c: TestClient, equip_code: str, tags: dict, *, at: str | None = None, resend: bool = False):
    body = {"equip_code": equip_code, "ts": at or ts(), "tags": tags, "source": "test"}
    if resend:
        body["resend"] = True
    return c.post("/ifc/collect", json=body, headers={"X-Collect-Token": token()})


# ── 팩 ─────────────────────────────────────────────────────────────────
def item_std(prod: TestClient, param_key: str, *, item_code: str = ITEM_FG, process_code: str = "P03", std_value=None, min_value=None, max_value=None,
             tolerance=None, size_type: str | None = None, valid_from: date | None = None) -> dict:
    """X-COND-01 등록 (같은 키가 이미 있으면 그 행을 돌려준다 — 정본 값은 화면 입력이라 테스트가 넣는다)."""
    day = (valid_from or date.today()).isoformat()
    data = {"process_id": process_id(process_code), "item_id": item_id(item_code), "param_key": param_key, "valid_from": day}
    for k, v in (("std_value", std_value), ("min_value", min_value), ("max_value", max_value), ("tolerance", tolerance), ("size_type", size_type)):
        if v is not None:
            data[k] = v
    r = prod.post("/cond/item-standards", data=data)
    if r.status_code == 422 and "이미" in r.json().get("message", ""):
        row = conn.q1("""select * from x_kimchi_item_std where process_id = %s and item_id = %s and coalesce(size_type, '') = coalesce(%s, '') and param_key = %s and valid_from = %s""",
                      (data["process_id"], data["item_id"], size_type, param_key, day))
        conn.x("update x_kimchi_item_std set std_value = %s, min_value = %s, max_value = %s, tolerance = %s, use_yn = 'Y' where id = %s",
               (std_value, min_value, max_value, tolerance, row["id"]))
        return {"id": row["id"], "ok": True, "reused": True}
    assert r.status_code == 200, r.text
    return r.json()


def genealogy_rows(lot_ids: list[int]) -> list[dict]:
    return conn.q("select * from lot_genealogy where parent_lot_id = any(%(i)s) or child_lot_id = any(%(i)s) order by id", {"i": lot_ids})


def lot_row(lot_id: int) -> dict:
    return conn.q1("select l.*, s.state, k.remain_qty from lot l join v_lot_state s on s.lot_id = l.id join v_lot_stock k on k.lot_id = l.id where l.id = %s", (lot_id,))


def lot_by_no(lot_no: str) -> dict:
    return conn.q1("select l.*, s.state, k.remain_qty from lot l join v_lot_state s on s.lot_id = l.id join v_lot_stock k on k.lot_id = l.id where l.lot_no = %s", (lot_no,))


def set_param_range(process_code: str, param_key: str, min_value=None, max_value=None) -> None:
    """픽스처 — 미확정 범위를 임시로 넣는다 (시드에는 없음). 끝나면 되돌린다."""
    conn.x("update bas_process_param set min_value = %s, max_value = %s where process_id = %s and param_key = %s", (min_value, max_value, process_id(process_code), param_key))


def alarm_rows(**where) -> list[dict]:
    sql, params = "select * from x_kimchi_env_alarm", []
    if where:
        sql += " where " + " and ".join(f"{k} = %s" for k in where)
        params = list(where.values())
    return conn.q(sql + " order by id", params)
