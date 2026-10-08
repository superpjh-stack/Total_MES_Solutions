"""S8 권한 — 역할 6 × 메뉴 12 = 72칸 · 외부업체 pop 403 · 작업자 trc 403 · 영양사 qua 입력 · 출고 담당 shp 입력 · 생산관리 sys 403 (gates.yaml S8 · scenarios.md §3)."""

from __future__ import annotations

from datetime import date

import pytest

from mescore.app import rbac
from mescore.db import conn

from _helpers import CUSTOMER, HTML, P, client, ok


@pytest.mark.fn("F-SYS-08")
def test_matrix():
    roles = {r["role_code"] for r in conn.q("select role_code from sys_role where use_yn = 'Y'")}
    assert {"ADMIN", "PRODUCTION", "NUTRITIONIST", "WORKER", "SHIPPING", "VENDOR"} <= roles
    assert conn.q1("select count(*) as n from sys_permission p join sys_role r on r.id = p.role_id where r.role_code in ('ADMIN','PRODUCTION','NUTRITIONIST','WORKER','SHIPPING','VENDOR')")["n"] == 72
    assert rbac.cell("ADMIN", "shp").level == "입력" and "승인" in rbac.cell("ADMIN", "shp").scopes and "입고검사" in rbac.cell("WORKER", "mat").scopes
    vendor, worker, nutri, shipping, prod, admin = client("vendor"), client("worker"), client("nutritionist"), client("shipping"), client("production"), client("admin")
    assert vendor.get("/pop/work").status_code == 403                                     # VENDOR pop 없음
    assert worker.get(P["TRC-02"]).status_code == 403                                     # WORKER trc 없음
    assert worker.get(P["KPI-01"]).status_code == 403
    assert prod.get("/sys/users").status_code == 403                                      # PRODUCTION sys 없음
    assert prod.get("/ifc/collect").status_code == 403
    assert shipping.get(P["QUA-02"]).status_code == 403                                   # SHIPPING qua 없음
    r = nutri.post(P["QUA-04"], data={"content": "(예시) 검식 이슈 — 권한 테스트", "occurred_at": date.today().isoformat()})
    assert r.status_code == 200, r.text                                                   # NUTRITIONIST qua 입력
    r = shipping.post(P["SHP-01"], data={"partner_code": CUSTOMER, "ship_date": date.today().isoformat()})
    assert r.status_code == 200, r.text                                                   # SHIPPING shp 입력
    assert ok(admin.post(f"{P['SHP-01']}/{r.json()['id']}/cancel"), "정리")["status"] == "취소"
    assert admin.post(P["QUA-04"], data={"content": "x"}).status_code == 403              # ADMIN qua 조회 — 정본 '품질관리: 조회'
    assert nutri.post(P["JOB-01"], data={"item_id": "1", "process_id": "1", "plan_qty": "1"}).status_code == 403   # 영양사 조리 지시 403
    assert worker.post(P["ORD-01"], data={"partner_code": CUSTOMER}).status_code == 403    # 작업자 수주 403
    assert vendor.get("/sys/logs", headers=HTML).status_code == 200                       # 외부업체 시스템 조회 — 정본 '로그 조회'
    # 메뉴 노출 — 외부업체 메인(HTML)에 조리 실적(pop) · 설비 수집(ifc) 링크가 없다
    home = vendor.get("/", headers=HTML).text
    assert 'href="/pop/work"' not in home and 'href="/ifc/collect"' not in home and 'href="/sys/logs"' in home
