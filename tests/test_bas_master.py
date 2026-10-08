"""bas 기준정보 (F-BAS-01~36 · 개발1) — 기능 한 줄 = 엔드포인트 하나 = 테스트 하나. JSON 으로 판정 (TestClient 기본 Accept · D-18).

공통 시드(`make db-seed`)가 들어 있어야 한다. 코드는 실행마다 다른 접미사를 붙여 서로 부딪히지 않고, 만든 행은 삭제 기능으로 지운다.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from mescore.app import nav
from mescore.app.main import app
from mescore.app.settings import get_settings
from mescore.db import conn

SFX = uuid.uuid4().hex[:6].upper()
HTML = {"accept": "text/html"}


def _client(login_id: str = "admin") -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/login", data={"login_id": login_id, "password": get_settings().seed_password})
    assert r.status_code == 200, f"{login_id} 로그인 실패 {r.status_code} — make db-seed"
    return c


@pytest.fixture(scope="module")
def admin() -> TestClient:
    return _client("admin")


@pytest.fixture(scope="module")
def prod() -> TestClient:
    return _client("prod")       # bas 칸 = 조회 → 쓰기 403


def _process_id(admin: TestClient) -> int:
    return admin.get(nav.path_of("BAS-03")).json()["rows"][0]["id"]


# ── BAS-01 품목 ──────────────────────────────────────────────────────────
@pytest.mark.fn("F-BAS-01")
def test_item_create_dup_and_required(admin, prod):
    code = f"T-ITM-{SFX}"
    r = admin.post("/bas/items", data={"item_code": code, "item_name": "테스트 품목", "item_type": "제품", "unit": "EA"})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["item_code"] == code
    r = admin.post("/bas/items", data={"item_code": code, "item_name": "테스트 품목", "item_type": "제품"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error" and r.json()["fields"][0]["name"] == "item_code"
    r = admin.post("/bas/items", data={"item_code": f"T-ITM2-{SFX}", "item_type": "제품"})
    assert r.status_code == 422 and r.json()["fields"][0]["name"] == "item_name"
    r = admin.post("/bas/items", data={"item_code": f"T-ITM3-{SFX}", "item_name": "x", "item_type": "없는구분"})
    assert r.status_code == 422 and r.json()["fields"][0]["name"] == "item_type"
    assert prod.post("/bas/items", data={"item_code": f"T-ITM4-{SFX}", "item_name": "x", "item_type": "제품"}).status_code == 403
    assert conn.q1("select count(*) as n from sys_access_log where kind = 'change' and fn_id = 'F-BAS-01' and target = %s", (f"bas_item:{code}",))["n"] == 1


@pytest.mark.fn("F-BAS-02")
def test_item_update_keeps_code(admin):
    row = admin.get(f"/bas/items?q=T-ITM-{SFX}").json()["rows"][0]
    r = admin.post(f"/bas/items/{row['id']}", data={"item_name": "테스트 품목 (수정)", "use_yn": "N"})
    assert r.status_code == 200 and set(r.json()["changed"]) == {"item_name", "use_yn"}
    assert admin.post(f"/bas/items/{row['id']}", data={"item_code": "OTHER"}).status_code == 422
    assert admin.post("/bas/items/999999999", data={"item_name": "x"}).status_code == 404
    admin.post(f"/bas/items/{row['id']}", data={"use_yn": "Y"})


@pytest.mark.fn("F-BAS-04")
def test_item_list_filters_and_html(admin, prod):
    j = admin.get(f"/bas/items?q=T-ITM-{SFX}").json()
    assert j["screen_id"] == "BAS-01" and j["template"] == "bas/items.html" and len(j["rows"]) == 1 and j["rows"][0]["item_name"].startswith("테스트 품목")
    assert admin.get("/bas/items?item_type=원재료").json()["rows"] and all(r["item_type"] == "원재료" for r in admin.get("/bas/items?item_type=원재료").json()["rows"])
    assert admin.get("/bas/items?q=없는-코드-ZZZ").json()["rows"] == []
    h = admin.get("/bas/items?q=없는-코드-ZZZ", headers=HTML)
    assert h.status_code == 200 and "미수집" in h.text
    assert prod.get("/bas/items").status_code == 200


@pytest.mark.fn("F-BAS-03")
def test_item_delete_refuses_when_referenced(admin):
    item = admin.get(f"/bas/items?q=T-ITM-{SFX}").json()["rows"][0]
    raw = admin.get("/bas/items?item_type=원재료").json()["rows"][0]
    bom = admin.post("/bas/bom", data={"item_id": item["id"], "version": "D", "component_item_id": [raw["id"]], "qty": ["1"]}).json()
    r = admin.post(f"/bas/items/{item['id']}/delete")
    assert r.status_code == 422 and "bas_bom" in r.json()["fields"][0]["reason"]
    assert admin.post(f"/bas/bom/{bom['id']}/delete").status_code == 200
    assert admin.post(f"/bas/items/{item['id']}/delete").status_code == 200
    assert admin.post(f"/bas/items/{item['id']}/delete").status_code == 404


# ── BAS-02 BOM ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def bom_item(admin):
    code = f"T-BOM-{SFX}"
    r = admin.post("/bas/items", data={"item_code": code, "item_name": "BOM 상위", "item_type": "제품", "unit": "EA"})
    yield r.json()
    conn.x("delete from job_lot where work_order_id in (select id from job_work_order where item_id = %s)", (r.json()["id"],))
    conn.x("delete from job_work_order where item_id = %s", (r.json()["id"],))
    conn.x("delete from bas_bom_dtl where bom_id in (select id from bas_bom where item_id = %s)", (r.json()["id"],))
    conn.x("delete from bas_bom where item_id = %s", (r.json()["id"],))
    admin.post(f"/bas/items/{r.json()['id']}/delete")


@pytest.mark.fn("F-BAS-05")
def test_bom_create_lines_in_one_tx(admin, bom_item, prod):
    raws = admin.get("/bas/items?item_type=원재료").json()["rows"][:2]
    r = admin.post("/bas/bom", data={"item_id": bom_item["id"], "version": "1", "component_item_id": [raws[0]["id"], raws[1]["id"]],
                                     "qty": ["2.5", "1"], "unit": ["kg", "kg"], "loss_rate": ["1", ""]})
    assert r.status_code == 200 and r.json()["lines"] == 2
    assert admin.post("/bas/bom", data={"item_id": bom_item["id"], "version": "1", "component_item_id": [raws[0]["id"]], "qty": ["1"]}).status_code == 422
    r = admin.post("/bas/bom", data={"item_id": bom_item["id"], "version": "2", "component_item_id": [bom_item["id"]], "qty": ["1"]})
    assert r.status_code == 422 and "자기 자신" in r.json()["message"]
    r = admin.post("/bas/bom", data={"item_id": bom_item["id"], "version": "3", "component_item_id": [raws[0]["id"]], "qty": ["0"]})
    assert r.status_code == 422 and r.json()["fields"][0]["name"] == "qty"
    assert conn.q1("select count(*) as n from bas_bom where item_id = %s", (bom_item["id"],))["n"] == 1       # 실패한 것은 헤더도 남지 않았다
    assert prod.post("/bas/bom", data={"item_id": bom_item["id"], "version": "9", "component_item_id": [raws[0]["id"]], "qty": ["1"]}).status_code == 403


@pytest.mark.fn("F-BAS-08")
def test_bom_list_tree(admin, bom_item):
    j = admin.get(f"/bas/bom?item_id={bom_item['id']}").json()
    assert j["screen_id"] == "BAS-02" and len(j["trees"]) == 1 and j["trees"][0]["boms"][0]["version"] == "1" and len(j["trees"][0]["boms"][0]["lines"]) == 2
    assert admin.get(f"/bas/bom?item_id={bom_item['id']}", headers=HTML).status_code == 200
    assert admin.get("/bas/bom?item_id=abc").status_code == 422


@pytest.mark.fn("F-BAS-06")
def test_bom_update_lines_and_version_rule(admin, bom_item):
    bom = admin.get(f"/bas/bom?item_id={bom_item['id']}").json()["rows"][0]
    raw = admin.get("/bas/items?item_type=원재료").json()["rows"][0]
    r = admin.post(f"/bas/bom/{bom['id']}", data={"component_item_id": [raw["id"]], "qty": ["5"], "unit": ["kg"]})
    assert r.status_code == 200 and r.json()["lines"] == 1
    assert admin.get(f"/bas/bom?item_id={bom_item['id']}").json()["rows"][0]["line_count"] == 1
    r = admin.post(f"/bas/bom/{bom['id']}", data={"item_id": raw["id"]})
    assert r.status_code == 422
    # 지시가 참조하는 버전은 구성품을 못 바꾼다 → 새 버전으로만
    prc = _process_id(admin)
    wo = admin.post("/job/work-orders", data={"item_id": bom_item["id"], "process_id": prc, "plan_qty": "10", "bom_id": bom["id"]}).json()
    r = admin.post(f"/bas/bom/{bom['id']}", data={"component_item_id": [raw["id"]], "qty": ["6"]})
    assert r.status_code == 422 and "새 버전" in r.json()["message"]
    assert admin.post(f"/bas/bom/{bom['id']}", data={"use_yn": "N"}).status_code == 200      # 헤더 값은 바꿀 수 있다
    admin.post(f"/bas/bom/{bom['id']}", data={"use_yn": "Y"})
    assert admin.post(f"/job/work-orders/{wo['id']}/cancel").status_code == 200
    assert admin.post("/bas/bom/999999999", data={"use_yn": "N"}).status_code == 404


@pytest.mark.fn("F-BAS-07")
def test_bom_delete_refuses_when_work_order_refers(admin, bom_item):
    bom = admin.get(f"/bas/bom?item_id={bom_item['id']}").json()["rows"][0]
    prc = _process_id(admin)
    wo = admin.post("/job/work-orders", data={"item_id": bom_item["id"], "process_id": prc, "plan_qty": "10", "bom_id": bom["id"]}).json()
    assert admin.post(f"/bas/bom/{bom['id']}/delete").status_code == 422
    assert admin.post(f"/job/work-orders/{wo['id']}/cancel").status_code == 200
    assert admin.post(f"/bas/bom/{bom['id']}/delete").status_code == 422                                     # 취소된 지시도 참조다
    conn.x("delete from job_lot where work_order_id in (select id from job_work_order where bom_id = %s)", (bom["id"],))
    conn.x("delete from job_work_order where bom_id = %s", (bom["id"],))     # 테스트 정리 — 지시가 사라지면 삭제된다
    assert admin.post(f"/bas/bom/{bom['id']}/delete").status_code == 200
    assert admin.post(f"/bas/bom/{bom['id']}/delete").status_code == 404
    assert conn.q1("select count(*) as n from bas_bom_dtl where bom_id = %s", (bom["id"],))["n"] == 0


# ── BAS-03 공정 ──────────────────────────────────────────────────────────
@pytest.mark.fn("F-BAS-09")
def test_process_create(admin, prod):
    code = f"T-PRC-{SFX}"
    r = admin.post("/bas/processes", data={"process_code": code, "process_name": "테스트 공정", "seq": "99"})
    assert r.status_code == 200 and r.json()["process_code"] == code
    assert admin.post("/bas/processes", data={"process_code": code, "process_name": "x"}).status_code == 422
    assert admin.post("/bas/processes", data={"process_code": f"T-PRC2-{SFX}", "process_name": "x", "seq": "-1"}).status_code == 422
    assert prod.post("/bas/processes", data={"process_code": f"T-PRC3-{SFX}", "process_name": "x"}).status_code == 403


@pytest.mark.fn("F-BAS-10")
def test_process_update(admin):
    row = admin.get(f"/bas/processes?q=T-PRC-{SFX}").json()["rows"][0]
    r = admin.post(f"/bas/processes/{row['id']}", data={"process_name": "테스트 공정 2", "seq": "98", "use_yn": "N"})
    assert r.status_code == 200 and set(r.json()["changed"]) == {"process_name", "seq", "use_yn"}
    assert admin.post(f"/bas/processes/{row['id']}", data={"process_code": "X"}).status_code == 422
    admin.post(f"/bas/processes/{row['id']}", data={"use_yn": "Y"})


@pytest.mark.fn("F-BAS-12")
def test_process_list_counts(admin):
    j = admin.get("/bas/processes").json()
    assert j["screen_id"] == "BAS-03" and j["rows"] and {"param_count", "equipment_count"} <= set(j["rows"][0])
    seqs = [r["seq"] for r in j["rows"]]
    assert seqs == sorted(seqs)
    assert admin.get("/bas/processes", headers=HTML).status_code == 200


@pytest.mark.fn("F-BAS-11")
def test_process_delete_refuses_when_param_refers(admin):
    row = admin.get(f"/bas/processes?q=T-PRC-{SFX}").json()["rows"][0]
    p = admin.post("/bas/process-params", data={"process_id": row["id"], "param_key": "t_del", "label": "x"}).json()
    r = admin.post(f"/bas/processes/{row['id']}/delete")
    assert r.status_code == 422 and "bas_process_param" in r.json()["fields"][0]["reason"]
    assert admin.post(f"/bas/process-params/{p['id']}/delete").status_code == 200
    assert admin.post(f"/bas/processes/{row['id']}/delete").status_code == 200
    assert admin.post(f"/bas/processes/{row['id']}/delete").status_code == 404


# ── BAS-04 공정 측정값 정의 (G-C24 출발점) ───────────────────────────────
@pytest.mark.fn("F-BAS-13")
def test_process_param_create_all_columns(admin, prod):
    prc = _process_id(admin)
    key = f"t_{SFX.lower()}"
    r = admin.post("/bas/process-params", data={"process_id": prc, "param_key": key, "label": "테스트 측정값", "unit": "℃", "value_type": "number",
                                                "min_value": "60", "max_value": "80", "required_yn": "Y", "source": "collect", "collect_tag": "", "agg": "avg", "seq": "5"})
    assert r.status_code == 200
    row = conn.q1("select * from bas_process_param where process_id = %s and param_key = %s", (prc, key))
    assert (row["label"], row["unit"], row["value_type"], float(row["min_value"]), float(row["max_value"]), row["required_yn"], row["source"], row["collect_tag"], row["agg"], row["seq"]) == \
           ("테스트 측정값", "℃", "number", 60.0, 80.0, "Y", "collect", key, "avg", 5)
    assert admin.post("/bas/process-params", data={"process_id": prc, "param_key": key, "label": "x"}).status_code == 422            # (공정, 키) 중복
    assert admin.post("/bas/process-params", data={"process_id": prc, "param_key": "bad key", "label": "x"}).status_code == 422
    assert admin.post("/bas/process-params", data={"process_id": prc, "param_key": "t_rng", "label": "x", "min_value": "9", "max_value": "1"}).status_code == 422
    assert admin.post("/bas/process-params", data={"process_id": prc, "param_key": "t_sel", "label": "x", "value_type": "select"}).status_code == 422
    r = admin.post("/bas/process-params", data={"process_id": prc, "param_key": f"t_sel_{SFX.lower()}", "label": "x", "value_type": "select", "choices": "a, b"})
    assert r.status_code == 200 and conn.q1("select choices from bas_process_param where id = %s", (r.json()["id"],))["choices"] == ["a", "b"]
    admin.post(f"/bas/process-params/{r.json()['id']}/delete")
    assert prod.post("/bas/process-params", data={"process_id": prc, "param_key": "t_x", "label": "x"}).status_code == 403


@pytest.mark.fn("F-BAS-14")
def test_process_param_update_keeps_key(admin):
    prc = _process_id(admin)
    key = f"t_{SFX.lower()}"
    row = conn.q1("select id from bas_process_param where process_id = %s and param_key = %s", (prc, key))
    r = admin.post(f"/bas/process-params/{row['id']}", data={"min_value": "50", "required_yn": "N", "source": "manual"})
    assert r.status_code == 200 and set(r.json()["changed"]) == {"min_value", "required_yn", "source"}
    assert admin.post(f"/bas/process-params/{row['id']}", data={"param_key": "renamed"}).status_code == 422
    assert admin.post(f"/bas/process-params/{row['id']}", data={"max_value": "10"}).status_code == 422       # 상한 < 하한(50)


@pytest.mark.fn("F-BAS-16")
def test_process_param_list_grouped(admin):
    j = admin.get("/bas/process-params").json()
    assert j["screen_id"] == "BAS-04" and j["master"]["group_by"] == "process_name" and j["groups"]
    collect = admin.get("/bas/process-params?source=collect").json()["rows"]
    assert all(r["source"] == "collect" and r["collect_tag"] for r in collect)
    assert admin.get("/bas/process-params", headers=HTML).status_code == 200


@pytest.mark.fn("F-BAS-15")
def test_process_param_delete_refuses_when_measured(admin):
    prc = _process_id(admin)
    key = f"t_{SFX.lower()}"
    row = conn.q1("select id from bas_process_param where process_id = %s and param_key = %s", (prc, key))
    item = admin.get("/bas/items").json()["rows"][0]
    wo = admin.post("/job/work-orders", data={"item_id": item["id"], "process_id": prc, "plan_qty": "1"}).json()
    res = conn.q1("insert into pop_work_result (work_order_id, process_id, created_by) values (%s, %s, 'test') returning id", (wo["id"], prc))
    conn.x("insert into pop_measure (work_result_id, param_id, param_key, value_num, created_by) values (%s, %s, %s, 1, 'test')", (res["id"], row["id"], key))
    r = admin.post(f"/bas/process-params/{row['id']}/delete")
    assert r.status_code == 422 and "pop_measure" in r.json()["fields"][0]["reason"]
    conn.x("delete from pop_measure where work_result_id = %s", (res["id"],))
    conn.x("delete from pop_work_result where id = %s", (res["id"],))
    conn.x("delete from job_lot where work_order_id = %s", (wo["id"],))
    conn.x("delete from job_work_order where id = %s", (wo["id"],))
    assert admin.post(f"/bas/process-params/{row['id']}/delete").status_code == 200
    assert admin.post(f"/bas/process-params/{row['id']}/delete").status_code == 404


# ── BAS-05 설비 ──────────────────────────────────────────────────────────
@pytest.mark.fn("F-BAS-17")
def test_equipment_create(admin, prod):
    code = f"T-EQ-{SFX}"
    r = admin.post("/bas/equipment", data={"equip_code": code, "equip_name": "테스트 설비", "process_id": _process_id(admin), "collect_yn": "Y"})
    assert r.status_code == 200
    assert admin.post("/bas/equipment", data={"equip_code": code, "equip_name": "x"}).status_code == 422
    assert admin.post("/bas/equipment", data={"equip_code": f"T-EQ2-{SFX}", "equip_name": "x", "process_id": "999999999"}).status_code == 422
    assert prod.post("/bas/equipment", data={"equip_code": f"T-EQ3-{SFX}", "equip_name": "x"}).status_code == 403


@pytest.mark.fn("F-BAS-18")
def test_equipment_update(admin):
    row = admin.get(f"/bas/equipment?q=T-EQ-{SFX}").json()["rows"][0]
    assert admin.post(f"/bas/equipment/{row['id']}", data={"equip_name": "테스트 설비 2", "collect_yn": "N"}).status_code == 200
    assert admin.post(f"/bas/equipment/{row['id']}", data={"equip_code": "X"}).status_code == 422


@pytest.mark.fn("F-BAS-20")
def test_equipment_list_by_process(admin):
    j = admin.get(f"/bas/equipment?process_id={_process_id(admin)}").json()
    assert j["screen_id"] == "BAS-05" and j["rows"] and "last_collect_at" in j["rows"][0] and "process_name" in j["rows"][0]
    assert admin.get("/bas/equipment", headers=HTML).status_code == 200


@pytest.mark.fn("F-BAS-19")
def test_equipment_delete_refuses_when_result_refers(admin):
    row = admin.get(f"/bas/equipment?q=T-EQ-{SFX}").json()["rows"][0]
    prc = _process_id(admin)
    item = admin.get("/bas/items").json()["rows"][0]
    wo = admin.post("/job/work-orders", data={"item_id": item["id"], "process_id": prc, "plan_qty": "1", "equipment_id": row["id"]}).json()
    assert admin.post(f"/bas/equipment/{row['id']}/delete").status_code == 422
    conn.x("delete from job_lot where work_order_id = %s", (wo["id"],))
    conn.x("delete from job_work_order where id = %s", (wo["id"],))
    assert admin.post(f"/bas/equipment/{row['id']}/delete").status_code == 200


# ── BAS-06 거래처 ────────────────────────────────────────────────────────
@pytest.mark.fn("F-BAS-21")
def test_partner_create(admin, prod):
    code = f"T-PT-{SFX}"
    assert admin.post("/bas/partners", data={"partner_code": code, "partner_name": "테스트 거래처", "partner_type": "고객", "contact": "02-000"}).status_code == 200
    assert admin.post("/bas/partners", data={"partner_code": code, "partner_name": "x", "partner_type": "고객"}).status_code == 422
    assert admin.post("/bas/partners", data={"partner_code": f"T-PT2-{SFX}", "partner_name": "x", "partner_type": "없음"}).status_code == 422
    assert prod.post("/bas/partners", data={"partner_code": f"T-PT3-{SFX}", "partner_name": "x", "partner_type": "고객"}).status_code == 403


@pytest.mark.fn("F-BAS-22")
def test_partner_update(admin):
    row = admin.get(f"/bas/partners?q=T-PT-{SFX}").json()["rows"][0]
    assert admin.post(f"/bas/partners/{row['id']}", data={"partner_type": "공급", "contact": ""}).status_code == 200
    assert admin.post(f"/bas/partners/{row['id']}", data={"partner_code": "X"}).status_code == 422


@pytest.mark.fn("F-BAS-24")
def test_partner_list(admin):
    j = admin.get("/bas/partners?partner_type=공급")
    assert j.status_code == 200 and j.json()["screen_id"] == "BAS-06" and all(r["partner_type"] == "공급" for r in j.json()["rows"])
    assert admin.get(f"/bas/partners?q=T-PT-{SFX}").json()["rows"][0]["partner_name"] == "테스트 거래처"


@pytest.mark.fn("F-BAS-23")
def test_partner_delete_refuses_when_order_refers(admin):
    row = admin.get(f"/bas/partners?q=T-PT-{SFX}").json()["rows"][0]
    o = conn.q1("insert into ord_order (order_no, partner_id, order_date, created_by) values (%s, %s, current_date, 'test') returning id", (f"T-ORD-{SFX}", row["id"]))
    assert admin.post(f"/bas/partners/{row['id']}/delete").status_code == 422
    conn.x("delete from ord_order where id = %s", (o["id"],))
    assert admin.post(f"/bas/partners/{row['id']}/delete").status_code == 200


# ── BAS-07 작업자 ────────────────────────────────────────────────────────
@pytest.mark.fn("F-BAS-25")
def test_worker_create(admin, prod):
    code = f"T-WK-{SFX}"
    assert admin.post("/bas/workers", data={"worker_code": code, "worker_name": "테스트 작업자", "process_id": _process_id(admin)}).status_code == 200
    assert admin.post("/bas/workers", data={"worker_code": code, "worker_name": "x"}).status_code == 422
    assert admin.post("/bas/workers", data={"worker_code": f"T-WK2-{SFX}", "worker_name": "x", "user_id": "999999999"}).status_code == 422
    assert prod.post("/bas/workers", data={"worker_code": f"T-WK3-{SFX}", "worker_name": "x"}).status_code == 403


@pytest.mark.fn("F-BAS-26")
def test_worker_update_links_user(admin):
    row = admin.get(f"/bas/workers?q=T-WK-{SFX}").json()["rows"][0]
    uid = conn.q1("select id from sys_user where login_id = 'field'")["id"]
    assert admin.post(f"/bas/workers/{row['id']}", data={"user_id": uid}).status_code == 200
    assert admin.get(f"/bas/workers?q=T-WK-{SFX}").json()["rows"][0]["login_id"] == "field"


@pytest.mark.fn("F-BAS-28")
def test_worker_list_by_process(admin):
    j = admin.get(f"/bas/workers?process_id={_process_id(admin)}").json()
    assert j["screen_id"] == "BAS-07" and j["rows"] and all(r["process_id"] == _process_id(admin) for r in j["rows"])


@pytest.mark.fn("F-BAS-27")
def test_worker_delete_refuses_when_result_refers(admin):
    row = admin.get(f"/bas/workers?q=T-WK-{SFX}").json()["rows"][0]
    prc = _process_id(admin)
    item = admin.get("/bas/items").json()["rows"][0]
    wo = admin.post("/job/work-orders", data={"item_id": item["id"], "process_id": prc, "plan_qty": "1"}).json()
    res = conn.q1("insert into pop_work_result (work_order_id, process_id, worker_id, created_by) values (%s, %s, %s, 'test') returning id", (wo["id"], prc, row["id"]))
    r = admin.post(f"/bas/workers/{row['id']}/delete")
    assert r.status_code == 422 and "pop_work_result" in r.json()["fields"][0]["reason"]
    conn.x("delete from pop_work_result where id = %s", (res["id"],))
    conn.x("delete from job_lot where work_order_id = %s", (wo["id"],))
    conn.x("delete from job_work_order where id = %s", (wo["id"],))
    assert admin.post(f"/bas/workers/{row['id']}/delete").status_code == 200


# ── BAS-08 불량코드 ──────────────────────────────────────────────────────
@pytest.mark.fn("F-BAS-29")
def test_defect_code_create(admin, prod):
    code = f"T-DF-{SFX}"
    assert admin.post("/bas/defect-codes", data={"defect_code": code, "defect_name": "테스트 불량"}).status_code == 200
    assert admin.post("/bas/defect-codes", data={"defect_code": code, "defect_name": "x"}).status_code == 422
    assert prod.post("/bas/defect-codes", data={"defect_code": f"T-DF2-{SFX}", "defect_name": "x"}).status_code == 403


@pytest.mark.fn("F-BAS-30")
def test_defect_code_update(admin):
    row = admin.get(f"/bas/defect-codes?q=T-DF-{SFX}").json()["rows"][0]
    assert admin.post(f"/bas/defect-codes/{row['id']}", data={"process_id": _process_id(admin), "defect_name": "테스트 불량 2"}).status_code == 200
    assert admin.get(f"/bas/defect-codes?q=T-DF-{SFX}").json()["rows"][0]["process_name"]


@pytest.mark.fn("F-BAS-32")
def test_defect_code_list(admin):
    j = admin.get("/bas/defect-codes").json()
    assert j["screen_id"] == "BAS-08" and j["rows"]
    assert admin.get("/bas/defect-codes", headers=HTML).status_code == 200


@pytest.mark.fn("F-BAS-31")
def test_defect_code_delete_refuses_when_scrap_refers(admin):
    row = admin.get(f"/bas/defect-codes?q=T-DF-{SFX}").json()["rows"][0]
    prc = _process_id(admin)
    item = admin.get("/bas/items").json()["rows"][0]
    wo = admin.post("/job/work-orders", data={"item_id": item["id"], "process_id": prc, "plan_qty": "1"}).json()
    res = conn.q1("insert into pop_work_result (work_order_id, process_id, created_by) values (%s, %s, 'test') returning id", (wo["id"], prc))
    conn.x("insert into pop_scrap (work_result_id, defect_code_id, qty, created_by) values (%s, %s, 1, 'test')", (res["id"], row["id"]))
    assert admin.post(f"/bas/defect-codes/{row['id']}/delete").status_code == 422
    conn.x("delete from pop_scrap where work_result_id = %s", (res["id"],))
    conn.x("delete from pop_work_result where id = %s", (res["id"],))
    conn.x("delete from job_lot where work_order_id = %s", (wo["id"],))
    conn.x("delete from job_work_order where id = %s", (wo["id"],))
    assert admin.post(f"/bas/defect-codes/{row['id']}/delete").status_code == 200


# ── BAS-09 공통코드 ──────────────────────────────────────────────────────
@pytest.mark.fn("F-BAS-33")
def test_code_create_group_code_unique(admin, prod):
    grp = f"T_GRP_{SFX}"
    assert admin.post("/bas/codes", data={"group_code": grp, "code": "A", "code_name": "가", "seq": "1"}).status_code == 200
    assert admin.post("/bas/codes", data={"group_code": grp, "code": "A", "code_name": "가"}).status_code == 422
    assert admin.post("/bas/codes", data={"group_code": grp, "code": "B", "code_name": "나", "seq": "2"}).status_code == 200
    r = admin.post("/bas/codes", data={"group_code": "ITEM_TYPE", "code": f"T{SFX}", "code_name": "테스트 구분"})   # 코어 예약 그룹 — 코드 추가는 된다
    assert r.status_code == 200 and conn.q1("select is_core from bas_code where id = %s", (r.json()["id"],))["is_core"] == "N"
    assert prod.post("/bas/codes", data={"group_code": grp, "code": "C", "code_name": "x"}).status_code == 403


@pytest.mark.fn("F-BAS-34")
def test_code_update(admin):
    row = admin.get(f"/bas/codes?group_code=T_GRP_{SFX}").json()["rows"][0]
    assert admin.post(f"/bas/codes/{row['id']}", data={"code_name": "가 (수정)", "seq": "9", "use_yn": "N"}).status_code == 200
    assert admin.post(f"/bas/codes/{row['id']}", data={"code": "Z"}).status_code == 422


@pytest.mark.fn("F-BAS-36")
def test_code_list_by_group(admin):
    j = admin.get("/bas/codes?group_code=ITEM_TYPE").json()
    assert j["screen_id"] == "BAS-09" and {r["code"] for r in j["rows"]} >= {"제품", "반제품", "원재료", "부자재"}
    assert admin.get(f"/bas/codes?group_code=T_GRP_{SFX}").json()["rows"][0]["seq"] == 2    # use_yn=N 인 A(seq 9) 뒤
    assert admin.get("/bas/codes", headers=HTML).status_code == 200


@pytest.mark.fn("F-BAS-35")
def test_code_delete_core_refused(admin):
    core = conn.q1("select id from bas_code where group_code = 'ITEM_TYPE' and is_core = 'Y' limit 1")
    r = admin.post(f"/bas/codes/{core['id']}/delete")
    assert r.status_code == 422 and "코어" in r.json()["message"]
    for row in admin.get(f"/bas/codes?group_code=T_GRP_{SFX}").json()["rows"]:
        assert admin.post(f"/bas/codes/{row['id']}/delete").status_code == 200
    mine = conn.q1("select id from bas_code where group_code = 'ITEM_TYPE' and code = %s", (f"T{SFX}",))
    assert admin.post(f"/bas/codes/{mine['id']}/delete").status_code == 200
    assert admin.get(f"/bas/codes?group_code=T_GRP_{SFX}").json()["rows"] == []
