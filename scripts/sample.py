"""테스트용 샘플 데이터 — 업무 테이블마다 100건 안팎 (예시).

    MES_PG_DSN=postgresql:///mes_demo_db uv run python scripts/sample.py

실제 화면이 부르는 API 를 역할별 로그인으로 그대로 호출한다. 그래서 채번 · 계보 · 권한 · 검증 · 훅이 운영과 똑같이 적용된다.
코드는 전부 `SMP-` 로 시작하고 이름에 `(예시)` 가 붙는다 — 회사 실데이터가 아니다. 이미 `SMP-` 데이터가 있으면 멈춘다(두 번 넣지 않는다).
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta

if not os.environ.get("MES_PG_DSN"):
    sys.exit("MES_PG_DSN 을 지정한다 — 예: MES_PG_DSN=postgresql:///mes_demo_db (코어 DB 에 섞지 않는다)")

from fastapi.testclient import TestClient  # noqa: E402

from mescore.app.main import app  # noqa: E402
from mescore.app.settings import get_settings  # noqa: E402
from mescore.db import conn  # noqa: E402

random.seed(20261009)
TODAY = date.today()
N = 100


def login(login_id: str, device: str | None = None) -> TestClient:
    c = TestClient(app, raise_server_exceptions=True)
    data = {"login_id": login_id, "password": get_settings().seed_password}
    if device:
        data["device"] = device
    r = c.post("/login", data=data)
    if r.status_code != 200:
        sys.exit(f"{login_id} 로그인 실패 {r.status_code} — make db-seed 를 먼저 · .env 의 MES_SEED_PASSWORD 확인")
    return c


def ok(r, what: str) -> dict:
    if r.status_code != 200:
        raise SystemExit(f"[실패] {what} → {r.status_code} {r.text[:400]}")
    return r.json()


def ids(sql: str, params=None) -> list[int]:
    return [r["id"] for r in conn.q(sql, params)]


def step(title: str) -> None:
    print(f"· {title}", flush=True)


def main() -> None:
    if conn.q1("select 1 as hit from bas_item where item_code like 'SMP-%' limit 1"):
        sys.exit("이미 SMP- 샘플이 있다 — 다시 넣으려면 make db-reset 뒤에 돌린다")
    admin, prod, qa, field = login("admin"), login("prod"), login("qa"), login("field", "pop")

    # ── 기준정보 ──────────────────────────────────────────────
    step("공정 10 · 공정 측정값 30")
    procs = []
    for i, name in enumerate(["원료 계량", "혼합", "가공", "성형", "건조", "검사 준비", "포장", "라벨링", "적재", "출하 준비"], 1):
        procs.append(ok(admin.post("/bas/processes", data={"process_code": f"SMP-PRC-{i:02d}", "process_name": f"{name} (예시)", "seq": i * 10}), "공정")["id"])
    for pid in procs:
        ok(admin.post("/bas/process-params", data={"process_id": pid, "param_key": "temp_c", "label": "온도 (예시)", "unit": "℃",
                                                    "value_type": "number", "min_value": "60", "max_value": "80", "required_yn": "Y", "seq": 1}), "측정값")
        ok(admin.post("/bas/process-params", data={"process_id": pid, "param_key": "weight_kg", "label": "중량 (예시)", "unit": "kg",
                                                    "value_type": "number", "required_yn": "Y", "seq": 2}), "측정값")
        ok(admin.post("/bas/process-params", data={"process_id": pid, "param_key": "memo", "label": "특이사항 (예시)",
                                                    "value_type": "text", "required_yn": "N", "seq": 3}), "측정값")

    step("품목 100 (원재료 50 · 제품 50)")
    raws, prods = [], []
    for i in range(1, 51):
        raws.append(ok(admin.post("/bas/items", data={"item_code": f"SMP-RAW-{i:03d}", "item_name": f"원재료 {i:03d} (예시)", "item_type": "원재료",
                                                        "spec": f"{random.choice([10, 20, 25])}kg 포대", "unit": "kg"}), "품목")["id"])
    for i in range(1, 51):
        prods.append(ok(admin.post("/bas/items", data={"item_code": f"SMP-PRD-{i:03d}", "item_name": f"제품 {i:03d} (예시)", "item_type": "제품",
                                                         "spec": f"{random.choice([500, 1000, 2000])}g", "unit": "EA"}), "품목")["id"])
    raw_code = {iid: f"SMP-RAW-{n:03d}" for n, iid in enumerate(raws, 1)}
    prd_code = {iid: f"SMP-PRD-{n:03d}" for n, iid in enumerate(prods, 1)}

    step("BOM 50 (제품마다 원재료 2~3)")
    for p in prods:
        comps = random.sample(raws, random.choice([2, 3]))
        ok(admin.post("/bas/bom", data={"item_id": p, "version": "1", "component_item_id": [str(c) for c in comps],
                                         "qty": [str(round(random.uniform(0.1, 2.0), 3)) for _ in comps], "unit": ["kg"] * len(comps)}), "BOM")

    step("거래처 100 (고객 50 · 공급 50)")
    for i in range(1, 51):
        ok(admin.post("/bas/partners", data={"partner_code": f"SMP-CUST-{i:03d}", "partner_name": f"고객사 {i:03d} (예시)", "partner_type": "고객",
                                              "contact": f"02-000-{i:04d}"}), "거래처")
    for i in range(1, 51):
        ok(admin.post("/bas/partners", data={"partner_code": f"SMP-SUP-{i:03d}", "partner_name": f"공급사 {i:03d} (예시)", "partner_type": "공급",
                                              "contact": f"031-000-{i:04d}"}), "거래처")
    sups = ids("select id from bas_partner where partner_code like 'SMP-SUP-%' order by partner_code")

    step("설비 100 (공정마다 10 · 수집 설비 20)")
    equip_of: dict[int, list[int]] = {p: [] for p in procs}
    for i in range(1, 101):
        pid = procs[(i - 1) % len(procs)]
        e = ok(admin.post("/bas/equipment", data={"equip_code": f"SMP-EQ-{i:03d}", "equip_name": f"설비 {i:03d} (예시)", "process_id": pid,
                                                   "collect_yn": "Y" if i % 5 == 0 else "N"}), "설비")
        equip_of[pid].append(e["id"])

    step("작업자 100 · 불량코드 100")
    for i in range(1, 101):
        ok(admin.post("/bas/workers", data={"worker_code": f"SMP-WK-{i:03d}", "worker_name": f"작업자 {i:03d} (예시)", "process_id": procs[(i - 1) % 10]}), "작업자")
        ok(admin.post("/bas/defect-codes", data={"defect_code": f"SMP-DF-{i:03d}", "defect_name": f"불량유형 {i:03d} (예시)", "process_id": procs[(i - 1) % 10]}), "불량코드")
    defects = ids("select id from bas_defect_code where defect_code like 'SMP-DF-%'")

    step("검사 계획 (공정 검사 항목 — 공정마다 2)")
    for pid in procs:
        ok(qa.post("/qua/plans", data={"insp_type": "공정", "process_id": pid, "item_key": ["visual", "thickness"], "label": ["외관 (예시)", "두께 (예시)"],
                                        "value_type": ["text", "number"], "min_value": ["", "0.8"], "max_value": ["", "1.2"]}), "검사 계획")

    # ── 수주 · 계획 · 작업지시 ─────────────────────────────────
    step("수주 100 (상세 1~3줄)")
    orders = []
    custs = [f"SMP-CUST-{i:03d}" for i in range(1, 51)]
    for i in range(N):
        od = TODAY - timedelta(days=random.randint(0, 40))
        picks = random.sample(prods, random.randint(1, 3))
        o = ok(prod.post("/ord/orders", data={"partner_code": random.choice(custs), "order_date": od.isoformat(),
                                               "due_date": (od + timedelta(days=random.randint(5, 25))).isoformat(),
                                               "item_code": [prd_code[p] for p in picks], "qty": [str(random.randint(50, 500)) for _ in picks],
                                               "unit": ["EA"] * len(picks), "note": "(예시)"}), "수주")
        orders.append(o)

    step("생산계획 100 (수주 상세 연결 · 85건 확정)")
    plans = []
    for o in orders:
        d = conn.q1("select line_no, item_id, qty from ord_order_dtl d join ord_order h on h.id = d.order_id where h.order_no = %s order by line_no limit 1", (o["order_no"],))
        p = ok(prod.post("/ord/plans", data={"order_no": o["order_no"], "line_no": str(d["line_no"]),
                                              "plan_date": (TODAY - timedelta(days=random.randint(0, 20))).isoformat(), "plan_qty": str(d["qty"]), "unit": "EA"}), "생산계획")
        plans.append(p)
    confirmed = random.sample(plans, 85)
    for p in confirmed:
        ok(prod.post(f"/ord/plans/{p['id']}/confirm"), "계획 확정")

    step("작업지시 100 (확정 계획 85 + 계획 없는 지시 15)")
    wos = []
    for p in confirmed:
        item = conn.q1("select item_id, plan_qty from ord_plan where id = %s", (p["id"],))
        pid = random.choice(procs)
        wos.append(ok(prod.post("/job/work-orders", data={"plan_id": p["id"], "item_id": item["item_id"], "process_id": pid,
                                                           "equipment_id": random.choice(equip_of[pid]), "plan_qty": str(item["plan_qty"])}), "작업지시"))
    for _ in range(15):
        pid = random.choice(procs)
        wos.append(ok(prod.post("/job/work-orders", data={"item_id": random.choice(prods), "process_id": pid, "equipment_id": random.choice(equip_of[pid]),
                                                           "plan_qty": str(random.randint(50, 300)), "plan_date": TODAY.isoformat()}), "작업지시"))

    # ── 자재 입고 · 입고검사 ──────────────────────────────────
    step("입고 100 · 입고검사 (합격 90 · 불합격 5 · 미검사 5)")
    mats = []
    for i in range(N):
        r = ok(prod.post("/mat/receipts", data={"item_id": random.choice(raws), "partner_id": random.choice(sups), "qty": str(random.choice([300, 500, 800])),
                                                 "unit": "kg", "note": "(예시)"}), "입고")
        mats.append(r)
    for i, m in enumerate(mats):
        if i < 90:
            ok(qa.post("/mat/inspections", data={"lot_no": m["lot_no"], "judgement": "합격"}), "입고검사")
        elif i < 95:
            ok(qa.post("/mat/inspections", data={"lot_no": m["lot_no"], "judgement": "불합격", "note": "(예시) 이물"}), "입고검사")
    passed = mats[:90]

    # ── 생산실적 (POP) ─────────────────────────────────────────
    step("생산실적 100 (시작 · 투입 스캔 · 측정값 · 종료 → 생산 LOT 100)")
    products = []
    for k, wo in enumerate(wos):
        wo_row = conn.q1("select process_id, equipment_id from job_work_order where id = %s", (wo["id"],))
        s = ok(field.post("/pop/result/start", data={"work_order_id": wo["id"], "equipment_id": wo_row["equipment_id"] or ""}), "작업 시작")
        for m in random.sample(passed, random.choice([1, 2])):
            ok(field.post("/pop/inputs", data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": str(random.randint(5, 25))}), "투입 스캔")
        temp = round(random.uniform(55, 85), 1)                     # 일부는 범위(60~80) 밖 — 이탈 표시 확인용
        e = ok(field.post(f"/pop/result/{s['id']}/end", data={"good_qty": str(random.randint(40, 200)), "defect_qty": str(random.randint(0, 6)),
                                                               "m_temp_c": str(temp), "m_weight_kg": str(round(random.uniform(10, 60), 2)),
                                                               "m_memo": "(예시)" if k % 7 == 0 else ""}), "작업 종료")
        products.append(e)
        if k % 10 == 0:
            ok(field.post(f"/pop/result/{s['id']}/scrap", data={"qty": "1", "defect_code_id": random.choice(defects)}), "폐기")

    # ── 품질 ──────────────────────────────────────────────────
    step("공정 검사 100 (합격 85 · 조건부 5 · 불합격 10)")
    for k, p in enumerate(products):
        th = round(random.uniform(0.7, 1.3), 2)
        insp = ok(qa.post("/qua/inspections", data={"insp_type": "공정", "lot_no": p["lot_no"], "i_visual": "양호 (예시)", "i_thickness": str(th)}), "검사 결과")
        if k < 85:
            ok(qa.post(f"/qua/inspections/{insp['id']}/judge", data={"judgement": "합격"}), "판정")
        elif k < 90:
            ok(qa.post(f"/qua/inspections/{insp['id']}/judge", data={"judgement": "조건부"}), "판정")
        else:
            ok(qa.post(f"/qua/inspections/{insp['id']}/judge", data={"judgement": "불합격", "defect_code_id": [str(random.choice(defects))], "qty": ["3"]}), "판정")

    step("이상 100 (조치 60 · 종결 30)")
    for k in range(N):
        iss = ok(qa.post("/qua/issues", data={"content": f"공정 이상 {k + 1:03d} (예시)", "process_id": random.choice(procs), "cause": "원인 조사 중 (예시)"}), "이상")
        if k < 60:
            ok(qa.post(f"/qua/issues/{iss['id']}/action", data={"action": "조치 완료 (예시)"}), "시정 조치")
            if k < 30:
                ok(qa.post(f"/qua/issues/{iss['id']}/close"), "종결")

    # ── 설비 ──────────────────────────────────────────────────
    step("설비 가동 기록 100 · 점검 100 · 고장 100 (조치 70)")
    all_eq = ids("select id from bas_equipment where equip_code like 'SMP-EQ-%' order by equip_code")
    for k, eid in enumerate(all_eq):
        ok(field.post("/eqp/status", data={"equipment_id": eid, "state": random.choice(["가동", "정지", "점검"])}), "가동 기록")
        ok(field.post("/eqp/checks", data={"equipment_id": eid, "item": random.choice(["윤활", "벨트 장력", "센서 청소"]) + " (예시)",
                                             "result": random.choice(["양호", "양호", "주의"])}), "점검")
    for k in range(N):
        f = ok(field.post("/eqp/faults", data={"equipment_id": random.choice(all_eq), "symptom": f"고장 증상 {k + 1:03d} (예시)"}), "고장")
        if k < 70:
            ok(field.post(f"/eqp/faults/{f['id']}/fix", data={"fix_action": "부품 교체 (예시)", "next_state": "가동"}), "고장 조치")

    # ── 출하 ──────────────────────────────────────────────────
    step("출하 100 (LOT 스캔 · 승인 70 · 성적서 50)")
    sellable = [p for p in products if conn.q1("select s.state, l.insp_status from v_lot_state s join lot l on l.id = s.lot_id where l.lot_no = %s",
                                                (p["lot_no"],)) in ({"state": "재고", "insp_status": "합격"}, {"state": "재고", "insp_status": "조건부"})]
    shipments = []
    for k in range(N):
        o = orders[k]
        cust = conn.q1("select p.partner_code from ord_order h join bas_partner p on p.id = h.partner_id where h.order_no = %s", (o["order_no"],))["partner_code"]
        sh = ok(prod.post("/shp/shipments", data={"partner_code": cust, "ship_date": (TODAY + timedelta(days=random.randint(-10, 10))).isoformat(),
                                                   "order_no": o["order_no"], "note": "(예시)"}), "출하 등록")
        shipments.append(sh)
        if k < len(sellable):
            ok(prod.post("/shp/scan", data={"shipment_no": sh["shipment_no"], "barcode": sellable[k]["lot_no"]}), "출하 LOT 스캔")
    approved = 0
    for k, sh in enumerate(shipments):
        if k < len(sellable) and approved < 70:
            ok(admin.post(f"/shp/shipments/{sh['id']}/approve"), "출하 승인")
            approved += 1
            if approved <= 50:
                ok(prod.post("/shp/documents", data={"shipment_id": str(sh["id"])}), "성적서 발행")

    # ── 결과 ──────────────────────────────────────────────────
    print("\n완료 — 테이블별 행 수 (샘플 + 시드)")
    for t in ("bas_item", "bas_partner", "bas_process", "bas_process_param", "bas_equipment", "bas_worker", "bas_defect_code", "bas_bom",
              "ord_order", "ord_order_dtl", "ord_plan", "job_work_order", "mat_receipt", "lot", "lot_genealogy", "pop_work_result", "pop_input",
              "pop_measure", "pop_scrap", "qua_insp_plan", "qua_inspection", "qua_defect", "qua_issue", "eqp_run_log", "eqp_check", "eqp_fault",
              "shp_shipment", "shp_document", "ifc_outbox"):
        print(f"  {t:20s} {conn.q1(f'select count(*)::int as n from {t}')['n']:>6}")


if __name__ == "__main__":
    main()
