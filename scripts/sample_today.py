"""오늘 날짜 샘플 — AI Agent 추천 질문(오늘의 재고량 · 출하량 · 생산량 · 입고량 · 불량률 · 작업지시 현황)이 답할 거리를 만든다 (예시).

    MES_PG_DSN=postgresql:///mes_demo_db uv run python scripts/sample_today.py      # 또는 make sample-today

`scripts/sample.py` 가 넣은 SMP- 기준정보를 쓰고, 실제 화면이 부르는 API 를 역할별 로그인으로 호출한다(채번 · 계보 · 권한 · 훅이 운영과 같다).
하루에 한 번만 들어간다 — 오늘 표식(note `(예시) 오늘 데이터`)이 있으면 멈춘다. 날이 바뀌면 다시 돌리면 그날 데이터가 생긴다.
  입고 12 (+ 합격 판정) → 작업지시 10 → 생산실적 10 (투입 · 측정값 · 종료 → 생산 LOT) → 공정 검사 (합격 9 · 불합격 1) → 출하 6 (LOT 스캔 · 승인 4)
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date

if not os.environ.get("MES_PG_DSN"):
    sys.exit("MES_PG_DSN 을 지정한다 — 예: MES_PG_DSN=postgresql:///mes_demo_db (코어 DB 에 섞지 않는다)")

from fastapi.testclient import TestClient  # noqa: E402

from mescore.app.main import app  # noqa: E402
from mescore.app.settings import get_settings  # noqa: E402
from mescore.db import conn  # noqa: E402

TODAY = date.today()
MARK = "(예시) 오늘 데이터"
random.seed(TODAY.toordinal())


def login(login_id: str, device: str | None = None) -> TestClient:
    c = TestClient(app, base_url="https://testserver", raise_server_exceptions=True)   # 운영(prod) 세션 쿠키는 Secure
    data = {"login_id": login_id, "password": get_settings().seed_password}
    if device:
        data["device"] = device
    r = c.post("/login", data=data)
    if r.status_code != 200:
        sys.exit(f"{login_id} 로그인 실패 {r.status_code} — .env 의 MES_SEED_PASSWORD 확인")
    return c


def ok(r, what: str) -> dict:
    if r.status_code != 200:
        raise SystemExit(f"[실패] {what} → {r.status_code} {r.text[:400]}")
    return r.json()


def col(sql: str, params=None, key: str = "id") -> list:
    return [r[key] for r in conn.q(sql, params)]


def main() -> None:
    if not conn.q1("select 1 as hit from bas_item where item_code like 'SMP-%' limit 1"):
        sys.exit("SMP- 기준정보가 없다 — scripts/sample.py 를 먼저 돌린다")
    if conn.q1("select 1 as hit from mat_receipt where receipt_date = current_date and note = %s limit 1", (MARK,)):
        sys.exit(f"{TODAY} 오늘 데이터가 이미 있다 — 하루에 한 번만 넣는다")
    admin, prod, qa, field = login("admin"), login("prod"), login("qa"), login("field", "pop")
    raws = col("select id from bas_item where item_code like 'SMP-RAW-%' order by item_code")
    prods = col("select id from bas_item where item_code like 'SMP-PRD-%' order by item_code")
    sups = col("select id from bas_partner where partner_code like 'SMP-SUP-%' order by partner_code")
    custs = col("select partner_code from bas_partner where partner_code like 'SMP-CUST-%' order by partner_code", key="partner_code")
    equip = conn.q("select id, process_id from bas_equipment where equip_code like 'SMP-EQ-%' and process_id is not null order by equip_code")

    print("· 입고 12 + 입고검사 합격")
    mats = []
    for _ in range(12):
        m = ok(prod.post("/mat/receipts", data={"item_id": random.choice(raws), "partner_id": random.choice(sups),
                                               "qty": str(random.choice([200, 300, 500])), "unit": "kg", "note": MARK}), "입고")
        ok(qa.post("/mat/inspections", data={"lot_no": m["lot_no"], "judgement": "합격"}), "입고검사")
        mats.append(m)

    print("· 작업지시 10 → 생산실적 10 → 공정 검사")
    lots = []
    for k in range(10):
        e = random.choice(equip)
        wo = ok(prod.post("/job/work-orders", data={"item_id": random.choice(prods), "process_id": e["process_id"], "equipment_id": e["id"],
                                                    "plan_qty": str(random.randint(100, 300)), "plan_date": TODAY.isoformat(), "note": MARK}), "작업지시")
        s = ok(field.post("/pop/result/start", data={"work_order_id": wo["id"], "equipment_id": e["id"]}), "작업 시작")
        for m in random.sample(mats, 2):
            ok(field.post("/pop/inputs", data={"work_result_id": s["id"], "barcode": m["lot_no"], "qty": str(random.randint(5, 20))}), "투입 스캔")
        end = ok(field.post(f"/pop/result/{s['id']}/end", data={"good_qty": str(random.randint(80, 240)), "defect_qty": str(random.randint(0, 8)),
                                                                 "m_temp_c": str(round(random.uniform(62, 78), 1)), "m_weight_kg": str(round(random.uniform(10, 60), 2)),
                                                                 "m_memo": ""}), "작업 종료")
        insp = ok(qa.post("/qua/inspections", data={"insp_type": "공정", "lot_no": end["lot_no"], "i_visual": "양호 (예시)",
                                                    "i_thickness": str(round(random.uniform(0.85, 1.15), 2))}), "검사 결과")
        if k < 9:
            ok(qa.post(f"/qua/inspections/{insp['id']}/judge", data={"judgement": "합격"}), "판정")
            lots.append(end["lot_no"])
        else:
            defect = col("select id from bas_defect_code where defect_code like 'SMP-DF-%' limit 1")[0]
            ok(qa.post(f"/qua/inspections/{insp['id']}/judge", data={"judgement": "불합격", "defect_code_id": [str(defect)], "qty": ["2"]}), "판정")

    print("· 출하 6 (오늘 출하일 · LOT 스캔 · 승인 4)")
    for k in range(6):
        sh = ok(prod.post("/shp/shipments", data={"partner_code": random.choice(custs), "ship_date": TODAY.isoformat(), "note": MARK}), "출하 등록")
        for lot_no in lots[k::6][:2]:
            ok(prod.post("/shp/scan", data={"shipment_no": sh["shipment_no"], "barcode": lot_no}), "출하 LOT 스캔")
        if k < 4:
            ok(admin.post(f"/shp/shipments/{sh['id']}/approve"), "출하 승인")

    print(f"\n완료 — {TODAY} 오늘 데이터")
    for label, sql in (("입고", "select count(*) as n from mat_receipt where receipt_date = current_date"),
                       ("생산실적(종료)", "select count(*) as n from pop_work_result where ended_at >= current_date"),
                       ("출하", "select count(*) as n from shp_shipment where ship_date = current_date"),
                       ("작업지시", "select count(*) as n from job_work_order where plan_date = current_date")):
        print(f"  {label:14s} {conn.q1(sql)['n']:>5}")


if __name__ == "__main__":
    main()
