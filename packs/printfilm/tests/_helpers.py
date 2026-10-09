"""printfilm 팩 테스트 공용 — 로그인 클라이언트 · 시드 조회 · 수주 → Job → 입고 · 입고검사 → POP(인쇄 롤) 을 **API 로** 만드는 픽스처 (개발2).

실행: `MES_PACK=printfilm uv run pytest -q packs/printfilm/tests` (DB mes_printfilm_db · `MES_PACK=printfilm make db-reset` 뒤).
계정은 코어 시드(admin · prod · field)와, 팩 역할 QC 의 `qc`(코어 seed_core USERS 가 역할 코드 QA 만 알아 만들지 않는다 — F-SYS-01 로 만든다).
테스트가 만든 LOT · Job · 출하는 DB 에 남는다(채번 소비 · 코드 `T-…`).
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from mescore.app import nav, packs
from mescore.app.settings import get_settings
from mescore.db import conn

HTML = {"accept": "text/html"}
PACK = "printfilm"

if (os.environ.get("MES_PACK") or "") != PACK or packs.current().name != PACK:
    pytest.skip(f"MES_PACK={PACK} 로 실행해야 한다 (지금 {os.environ.get('MES_PACK')!r} / {packs.current().name!r})", allow_module_level=True)

P = {s: nav.path_of(s) for s in ("ORD-01", "JOB-01", "JOB-03", "MAT-01", "MAT-02", "MAT-03", "POP-02", "POP-03", "POP-04", "QUA-02", "SHP-01", "SHP-02", "SHP-04",
                                  "TRC-01", "TRC-02", "SYS-01", "KPI-03", "X-PRT-01", "X-PRT-02", "X-PRT-03", "X-CLR-01", "X-RLL-01", "X-RLL-02", "X-RLL-03")}
_clients: dict[str, TestClient] = {}


def _password() -> str:
    pw = get_settings().seed_password
    assert pw, "MES_SEED_PASSWORD 미설정 — .env"
    return pw


def ensure_qc_user() -> None:
    """팩 역할 QC 의 계정 `qc` — 없으면 관리자가 F-SYS-01 로 만든다 (비밀번호는 시드 비밀번호 · 문서에 적지 않는다)."""
    if conn.q1("select 1 from sys_user where login_id = 'qc' and status = '사용'"):
        return
    role = conn.q1("select id from sys_role where role_code = 'QC'")
    assert role, "역할 QC 가 없다 — pack.yaml: roles · make db-seed"
    r = client("admin").post(P["SYS-01"], data={"login_id": "qc", "user_name": "품질 담당 (예시)", "role_id": role["id"], "password": _password()})
    assert r.status_code == 200, r.text


def client(login_id: str | None = None, device: str | None = None, fresh: bool = False) -> TestClient:
    from mescore.app.main import app

    key = f"{login_id}:{device}"
    if not fresh and key in _clients:
        return _clients[key]
    c = TestClient(app, raise_server_exceptions=False)
    if login_id:
        if login_id == "qc":
            ensure_qc_user()
        data = {"login_id": login_id, "password": _password()}
        if device:
            data["device"] = device
        r = c.post("/login", data=data)
        assert r.status_code == 200 and r.json()["ok"], f"{login_id} 로그인 실패 {r.status_code} — MES_PACK=printfilm make db-seed · .env"
    if not fresh:
        _clients[key] = c
    return c


def uniq(prefix: str = "T") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def one(sql: str, params=()) -> dict:
    r = conn.q1(sql, params)
    assert r, f"없음: {sql} {params}"
    return r


def item_id(code: str) -> int:
    return one("select id from bas_item where item_code = %s", (code,))["id"]


def process_id(code: str = "EX-PR-10") -> int:
    return one("select id from bas_process where process_code = %s", (code,))["id"]


def equipment_id(code: str = "EX-EQ-01") -> int:
    return one("select id from bas_equipment where equip_code = %s", (code,))["id"]


def partner_id(code: str) -> int:
    return one("select id from bas_partner where partner_code = %s", (code,))["id"]


def defect_code_id(code: str = "EX-DF-01") -> int:
    return one("select id from bas_defect_code where defect_code = %s", (code,))["id"]


# ── 흐름 픽스처 (전부 API) ───────────────────────────────────────────────
def new_order(item_code: str = "EX-FG-01", qty: float = 1000) -> dict:
    """수주 1 · 상세 1 (D-506 — Job 은 수주 상세 필수). 돌려주는 dict 에 order_dtl_id."""
    r = client("prod").post(P["ORD-01"], data={"partner_code": "EX-CU-01", "due_date": date.today().isoformat(), "item_code": [item_code], "qty": [str(qty)], "unit": ["m"]})
    assert r.status_code == 200, r.text
    body = r.json()
    dtl = one("select id from ord_order_dtl where order_id = %s order by line_no limit 1", (body["id"],))
    return {**body, "order_dtl_id": dtl["id"]}


def new_job(item_code: str = "EX-FG-01", process_code: str = "EX-PR-10", equip_code: str = "EX-EQ-01", qty: float = 500, *, plate: str | None = "EX-PL-01",
            anilox: str | None = "EX-AN-01", ink: str | None = "EX-INK-01", order_dtl_id: int | None = None, expect: int = 200) -> dict:
    """Job 등록 (F-JOB-01 · 훅 validate_job_work_order · after_save → ext). expect ≠ 200 이면 응답 JSON 을 그대로 돌려준다."""
    dtl = order_dtl_id if order_dtl_id is not None else new_order(item_code)["order_dtl_id"]
    data = {"item_id": item_id(item_code), "process_id": process_id(process_code), "equipment_id": equipment_id(equip_code), "plan_qty": str(qty),
            "unit": "m", "plan_date": date.today().isoformat(), "order_dtl_id": dtl}
    for k, v in (("attr_plate_code", plate), ("attr_anilox_code", anilox), ("attr_ink_code", ink)):
        if v:
            data[k] = v
    r = client("prod").post(P["JOB-01"], data=data)
    assert r.status_code == expect, r.text
    body = r.json()
    if expect == 200:
        body["order_dtl_id"] = dtl
    return body


def receive(item_code: str = "EX-RM-01", qty: float = 100, *, passed: bool = True) -> dict:
    """입고(F-MAT-01 · 현장) → 입고검사 합격(F-MAT-04 · 품질 · 범위 입고검사)."""
    r = client("field").post(P["MAT-01"], data={"item_id": item_id(item_code), "qty": str(qty), "partner_id": partner_id("EX-SU-01"), "attr_supplier_lot_no": uniq("SUP")})
    assert r.status_code == 200, r.text
    body = r.json()
    if passed:
        j = client("qc").post(P["MAT-02"], data={"lot_no": body["lot_no"], "judgement": "합격", "i_insp_note": "(예시)"})
        assert j.status_code == 200, j.text
    return body


def run_print(job: dict, inputs: list[tuple[str, float]], good: float, *, length_m: float = 1000, width_mm: float = 1000, delta_e: float | None = None) -> dict:
    """POP 시작(F-POP-02) → 투입 스캔(F-POP-06) → 종료(F-POP-03 · 훅 on_result_closed → ROLL). 돌려주는 dict 에 result_id · lot_id · lot_no."""
    c = client("field")
    s = c.post(f"{P['POP-02']}/start", data={"work_order_id": job["id"]})
    assert s.status_code == 200, s.text
    rid = s.json()["id"]
    for lot_no, qty in inputs:
        r = c.post(P["POP-03"], data={"work_result_id": rid, "barcode": lot_no, "qty": str(qty)})
        assert r.status_code == 200, r.text
    data = {"good_qty": str(good), "attr_length_m": str(length_m), "attr_width_mm": str(width_mm)}
    if delta_e is not None:
        data["m_delta_e"] = str(delta_e)
    e = c.post(f"{P['POP-02']}/{rid}/end", data=data)
    assert e.status_code == 200, e.text
    return {**e.json(), "result_id": rid}


def splice(nos: list[str], *, equip_code: str = "EX-EQ-02", length_m: float = 2000, work_order_no: str | None = None, expect: int = 200) -> dict:
    data = {"roll_no": nos, "equipment_id": equipment_id(equip_code), "length_m": str(length_m)}
    if work_order_no:
        data["work_order_no"] = work_order_no
    r = client("field").post(f"{P['X-RLL-01']}/splice", data=data)
    assert r.status_code == expect, r.text
    return r.json()


def slit(no: str, count: int = 3, widths: str = "300,300,400", *, equip_code: str = "EX-EQ-03", expect: int = 200) -> dict:
    r = client("field").post(P["X-RLL-02"], data={"roll_no": no, "count": str(count), "widths_mm": widths, "equipment_id": equipment_id(equip_code), "length_m": "2000"})
    assert r.status_code == expect, r.text
    return r.json()


def inspect_register(lot_no: str, *, delta_e: float | None = 1.2, position: str | None = None) -> int:
    """최종 검사 등록만 (F-QUA-04 · 판정 전 judgement NULL) → 검사 id."""
    data = {"insp_type": "최종", "lot_no": lot_no}
    if delta_e is not None:
        data["i_delta_e"] = str(delta_e)
    if position:
        data["i_defect_position"] = position
    r = client("qc").post(P["QUA-02"], data=data)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def judge(inspection_id: int, judgement: str = "합격", *, defect: str | None = None) -> dict:
    """판정 (F-QUA-05). 불합격이면 불량코드 1줄."""
    jd = {"judgement": judgement}
    if judgement == "불합격":
        jd.update({"defect_code_id": [str(defect_code_id(defect or "EX-DF-04"))], "defect_qty": ["1"]})
    j = client("qc").post(f"{P['QUA-02']}/{inspection_id}/judge", data=jd)
    assert j.status_code == 200, j.text
    return {**j.json(), "inspection_id": inspection_id}


def inspect(lot_no: str, judgement: str = "합격", *, delta_e: float | None = 1.2, defect: str | None = None, position: str | None = None) -> dict:
    """최종 검사 등록 → 판정 한 번에."""
    return judge(inspect_register(lot_no, delta_e=delta_e, position=position), judgement, defect=defect)


def new_shipment() -> dict:
    r = client("field").post(P["SHP-01"], data={"partner_code": "EX-CU-01", "ship_date": date.today().isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def scan(shipment_no: str, lot_no: str, *, expect: int = 200):
    r = client("field").post(P["SHP-02"], data={"shipment_no": shipment_no, "barcode": lot_no})
    assert r.status_code == expect, r.text
    return r.json()


def approve(shipment_id: int, *, expect: int = 200):
    r = client("admin").post(f"{P['SHP-01']}/{shipment_id}/approve")
    assert r.status_code == expect, r.text
    return r.json()


def genealogy_by_relation(lot_ids: list[int]) -> tuple[dict[str, int], dict[str, int], int]:
    rows = conn.q("select relation, relation_base from lot_genealogy where parent_lot_id = any(%(i)s) or child_lot_id = any(%(i)s)", {"i": lot_ids})
    rel: dict[str, int] = {}
    base: dict[str, int] = {}
    for r in rows:
        rel[r["relation"]] = rel.get(r["relation"], 0) + 1
        base[r["relation_base"]] = base.get(r["relation_base"], 0) + 1
    return rel, base, len(rows)


def s1_upto_slitting() -> dict:
    """gates.yaml S1 의 1~8 — 원재료 LOT 2 → Job → 인쇄 Roll 2 → splice → 슬리팅 3. 돌려준다: m1 m2 job r1 r2 f s1 s2 s3."""
    m1, m2 = receive("EX-RM-01", 100), receive("EX-RM-02", 100)
    job = new_job()
    r1 = run_print(job, [(m1["lot_no"], 50)], 500, delta_e=1.0)
    r2 = run_print(job, [(m1["lot_no"], 50), (m2["lot_no"], 50)], 500, delta_e=1.5)
    fz = splice([r1["lot_no"], r2["lot_no"]])
    sp = slit(fz["lot_no"], 3, "300,300,400")
    s1, s2, s3 = sp["lots"]
    return {"m1": m1, "m2": m2, "job": job, "r1": r1, "r2": r2, "f": fz, "s1": s1, "s2": s2, "s3": s3}
