"""foodservice 팩 테스트 공용 — 코어 API 만 부른다 (gates.yaml: scenarios · scenarios.md). 개발1.

실행: `MES_PACK=foodservice MES_PG_DSN=postgresql:///mes_foodservice_db uv run pytest -q packs/foodservice/tests`
준비: `make db-schema` → `uv run python packs/foodservice/seed_pack.py` (레시피 · KPI 지표 · 역할 6 계정). 비밀번호는 MES_SEED_PASSWORD 뿐.
시드 테이블(bas_*) 은 지우지 않는다. 지시 · 실적 · LOT 는 실행마다 새로 만들고 남겨 둔다(화면 확인용) — 기대값은 **증분**과 산식으로 판정한다.
"""

from __future__ import annotations

import os
import sys
import warnings
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parents[1]
PACK = PACK_DIR.name
ROOT = PACK_DIR.parents[1]
if str(ROOT) not in sys.path:                      # `packs.foodservice.hooks` 를 테스트에서 직접 부른다 (packs.py 의 훅 로더와 같은 모듈 이름)
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("MES_PACK", PACK)
assert os.environ["MES_PACK"] == PACK, f"MES_PACK={os.environ['MES_PACK']!r} — 이 테스트는 MES_PACK={PACK} 로만 돈다"
warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")

from fastapi.testclient import TestClient  # noqa: E402

from mescore.app import nav  # noqa: E402
from mescore.app.settings import get_settings  # noqa: E402
from mescore.db import conn  # noqa: E402

HTML = {"accept": "text/html"}
MENU, MENU_NO_RECIPE, PORK, ONION = "MENU-0001", "MENU-0003", "MAT-1001", "MAT-1002"
CUSTOMER, SUPPLIER = "CUS-001", "VEN-007"
STIRRER, COOK_PROCESS = "EQ-STIR-01", "PRC-060"
P = {s: nav.path_of(s) for s in ("MAT-01", "MAT-02", "MAT-04", "ORD-01", "JOB-01", "JOB-03", "POP-02", "POP-03", "QUA-02", "QUA-04", "SHP-01", "SHP-02", "TRC-02", "KPI-01", "KPI-02", "KPI-03", "MAT-05")}
COLLECT_POINTS = [(0, 75.0, 0, 150.0), (10, 74.0, 10, 157.5), (20, 73.0, 20, 165.0), (30, 72.0, 30, 172.5)]   # (분, RPM, STIR_TIME, TEMP) — scenarios.md 1-6c


def client(login_id: str = "admin", device: str | None = None) -> TestClient:
    from mescore.app.main import app

    c = TestClient(app, raise_server_exceptions=False)
    data = {"login_id": login_id, "password": get_settings().seed_password or ""}
    if device:
        data["device"] = device
    r = c.post("/login", data=data)
    assert r.status_code == 200 and r.json().get("ok"), f"{login_id} 로그인 실패 {r.status_code} — seed_pack.py · .env 확인"
    return c


def token() -> dict:
    tok = get_settings().collect_token
    assert tok, "MES_COLLECT_TOKEN 미설정"
    return {"X-Collect-Token": tok}


def ok(r, what: str = "") -> dict:
    assert r.status_code == 200, f"{what} {r.status_code}: {r.text[:300]}"
    return r.json()


def item_id(code: str) -> int:
    r = conn.q1("select id from bas_item where item_code = %s", (code,))
    assert r, f"시드 품목 {code} 없음 — seed_pack.py"
    return r["id"]


def process_id(code: str) -> int:
    return conn.q1("select id from bas_process where process_code = %s", (code,))["id"]


def equipment_id(code: str) -> int:
    return conn.q1("select id from bas_equipment where equip_code = %s", (code,))["id"]


def free_plan_date() -> date:
    """실행마다 다른 계획일 — `mat_requirement(period, item, source=hook)` 행이 지시마다 새로 생겨 144.000 · 42.000 을 증분이 아니라 그대로 읽는다."""
    r = conn.q1("select max(plan_date) as d from job_work_order where item_id = %s", (item_id(MENU),))
    today = date.today()
    if r and r["d"] and r["d"] >= today:
        return r["d"] + timedelta(days=1)
    return today


def zero_stock(c: TestClient, code: str) -> None:
    """F-MAT-09 로 품목 현재고를 0 으로 — 입고 뒤 stock_qty 가 그 입고량과 같아지도록 (TD3-015 목업 '가용 120.000 · 80.000')."""
    s = conn.q1("select qty from mat_stock where item_id = %s", (item_id(code),))
    if s and s["qty"]:
        ok(c.post(P["MAT-04"] + "/adjust", data={"item_id": item_id(code), "qty": str(-Decimal(str(s["qty"]))), "reason": "테스트 준비 — 현재고 0 (예시)"}), "재고 조정")


def receive(c: TestClient, code: str, qty: float, expiry: date | None, *, storage_loc: str = "냉장보관실", receipt_date: date | None = None):
    data = {"item_id": item_id(code), "qty": qty, "partner_id": conn.q1("select id from bas_partner where partner_code = %s", (SUPPLIER,))["id"],
            "receipt_date": (receipt_date or date.today() - timedelta(days=1)).isoformat(), "attr_storage_loc": storage_loc}
    if expiry is not None:
        data["attr_expiry_date"] = expiry.isoformat()
    return c.post(P["MAT-01"], data=data)


def pass_incoming(c: TestClient, lot_no: str, weight: float | None = None) -> dict:
    data = {"lot_no": lot_no, "judgement": "합격", "i_appearance_ok": "Y"}
    if weight is not None:
        data["i_insp_weight"] = weight
    return ok(c.post(P["MAT-02"], data=data), "입고검사")


def new_order(c: TestClient, qty: int = 1200, due: date | None = None, menu: str = MENU) -> dict:
    due = due or date.today()
    body = ok(c.post(P["ORD-01"], data={"partner_code": CUSTOMER, "order_date": (date.today() - timedelta(days=2)).isoformat(), "due_date": due.isoformat(),
                                        "item_code": [menu], "qty": [str(qty)], "unit": ["인분"], "attr_due_time": "11:30", "attr_service_type": "위탁급식"}), "수주")
    body["dtl_id"] = conn.q1("select id from ord_order_dtl where order_id = %s order by line_no limit 1", (body["id"],))["id"]
    return body


def new_work_order(c: TestClient, *, qty: int = 1200, plan_date: date | None = None, menu: str = MENU, process: str = COOK_PROCESS, order_dtl_id: int | None = None):
    data = {"item_id": item_id(menu), "process_id": process_id(process), "plan_qty": str(qty), "plan_date": (plan_date or date.today()).isoformat()}
    if order_dtl_id:
        data["order_dtl_id"] = order_dtl_id
    return c.post(P["JOB-01"], data=data)


def start_batch(c: TestClient, wo_id: int, *, equip: str = STIRRER, backdate_min: int = 40) -> dict:
    s = ok(c.post(P["POP-02"] + "/start", data={"work_order_id": wo_id, "equipment_id": equipment_id(equip)}), "조리 시작")
    # 테스트 픽스처: 시작 시각을 과거로 — 수집 4점(시작 +0/10/20/30분)이 실적 구간 안에 들어오고 가동 1분 이상이 된다 (kpi hourly_output)
    if backdate_min:
        conn.x("update pop_work_result set started_at = now() - make_interval(mins => %s) where id = %s", (backdate_min, s["id"]))
    s["started_at"] = conn.q1("select started_at from pop_work_result where id = %s", (s["id"],))["started_at"]
    return s


def clear_recent_collect(equip: str = STIRRER, hours: int = 2) -> int:
    """테스트 픽스처: 같은 설비의 최근 수집값(앞선 실행이 남긴 것)을 지운다 — 실적 구간(시작 −40분 ~ 종료)의 대표값이 이 실행의 4점만으로 계산되게.
    pop_measure 에 이미 옮겨진 값은 남는다. 원문(ifc_collect_raw)도 남는다."""
    return conn.x("delete from eqp_collect where equipment_id = %s and ts >= now() - make_interval(hours => %s)", (equipment_id(equip), hours))


def send_collect(c: TestClient, started_at: datetime, *, equip: str = STIRRER, points=COLLECT_POINTS) -> list[dict]:
    out = []
    for minute, rpm, stir, temp in points:
        ts = (started_at + timedelta(minutes=minute)).isoformat()
        out.append(ok(c.post("/ifc/collect", json={"equip_code": equip, "ts": ts, "source": "gateway", "tags": {"RPM": rpm, "STIR_TIME": stir, "TEMP": temp}}, headers=token()), "수집"))
    return out


def scan_input(c: TestClient, result_id: int, lot_no: str, qty: float):
    return c.post(P["POP-03"], data={"work_result_id": result_id, "barcode": lot_no, "qty": qty})


def end_batch(c: TestClient, result_id: int, good: int, defect: int = 0) -> dict:
    return ok(c.post(f"{P['POP-02']}/{result_id}/end", data={"good_qty": good, "defect_qty": defect}), "조리 완료")


def final_inspection(c: TestClient, lot_no: str, judgement: str, *, foreign: str = "N", sensory: float = 86.0, temp: float = 78.5) -> dict:
    insp = ok(c.post(P["QUA-02"], data={"insp_type": "최종", "lot_no": lot_no, "i_appearance": "양호", "i_taste": "양호", "i_measure_temp": temp,
                                        "i_sensory_score": sensory, "i_foreign_yn": foreign, "i_insp_comment": "(예시) 검식"}), "검식 등록")
    data = {"judgement": judgement}
    if judgement == "불합격":
        dc = conn.q1("select id from bas_defect_code order by id limit 1")
        assert dc, "불량코드 시드가 없다 (seed_dev1)"
        data.update({"defect_code_id": dc["id"], "defect_qty": "1"})
    judged = ok(c.post(f"{P['QUA-02']}/{insp['id']}/judge", data=data), "검식 판정")
    return {**insp, **judged}


def new_shipment(c: TestClient, order_no: str | None = None) -> dict:
    data = {"partner_code": CUSTOMER, "ship_date": date.today().isoformat()}
    if order_no:
        data["order_no"] = order_no
    return ok(c.post(P["SHP-01"], data=data), "출고 등록")


def scan_ship(c: TestClient, shipment_no: str, lot_no: str):
    return c.post(P["SHP-02"], data={"shipment_no": shipment_no, "barcode": lot_no})


def approve(c: TestClient, shipment_id: int):
    return c.post(f"{P['SHP-01']}/{shipment_id}/approve")


def hook_rejected(r) -> bool:
    return r.status_code == 422 and r.json().get("code") == "hook_rejected"
