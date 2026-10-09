"""메인(IA) 하위 메뉴 — 기능표 · 업무 프로세스 (D-45). 읽기 전용 안내 화면."""

from __future__ import annotations

from mescore.app import contracts, guide, nav
from mescore.db import conn

from _dev2_helpers import HTML, client


def test_process_steps_point_to_real_screens():
    ids = {s.screen_id for s in nav.SCREENS}
    for p in guide.processes():
        assert p.steps, p.code
        for st in p.steps:
            assert st.screen_id in ids, f"{p.code} 의 단계가 없는 화면 {st.screen_id} 를 가리킨다"
            assert st.role in ("ADMIN", "PROD", "QA", "FIELD")


def test_function_table_lists_every_screen_function_and_writes_nothing():
    c = client("admin")
    before = conn.q1("select count(*)::int as n from sys_access_log where kind = 'change'")["n"]
    body = c.get("/main/functions").json()
    got = {r["id"] for g in body["groups"] for r in g["rows"]}
    want = {f.id for f in contracts.all_functions() if not f.is_batch}
    assert got == want and len(body["batch"]) == 4
    assert conn.q1("select count(*)::int as n from sys_access_log where kind = 'change'")["n"] == before
    assert c.get("/main/functions", params={"module": "pop"}).json()["n_rows"] == 8


def test_process_pages_render_and_dim_screens_the_role_cannot_open():
    field = client("field")
    assert field.get("/main/processes", headers=HTML).status_code == 200
    p10 = field.get("/main/processes", params={"code": "P10"}).json()["current"]
    bas = [s for s in p10["steps"] if s["screen_id"].startswith("BAS-")]
    assert bas and not any(s["open"] for s in bas)            # 현장 역할은 기준정보 권한 없음
    html = client("admin").get("/main/processes?code=P01", headers=HTML).text
    assert 'class="main-tabs"' in html and "/main/functions" in html
    assert client().get("/main/processes").status_code in (401, 303)
