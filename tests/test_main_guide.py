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


def test_domain_catalog_data_is_consistent():
    from mescore.app import domains
    assert {d["code"] for d in domains.all_domains()} >= {"kimchi", "foodservice", "printfilm", "metal", "alloy", "towel"}
    assert domains.problems() == []


def test_domain_pages_render_core_pack_and_proposed_steps():
    c = client("admin")
    assert c.get("/main/domains", headers=HTML).status_code == 200
    assert c.get("/main/domains", params={"d": "nope"}).status_code == 404
    k = c.get("/main/domains", params={"d": "kimchi", "p": "K01"}).json()["domain"]["current"]
    assert k["n_core"] > 0 and k["n_pack"] > 0                       # 코어 화면 + 김치 팩 화면이 섞인다
    a = c.get("/main/domains", params={"d": "alloy", "p": "A02"}).json()["domain"]["current"]
    assert [(x["screen_id"], x["kind"]) for x in a["steps"]][:2] == [("X-CHG-01", "proposed"), ("MAT-04", "core")]   # 합금: 제안 화면 + 코어 화면
    w = c.get("/main/domains", params={"d": "towel", "p": "T01"}).json()["domain"]["current"]
    assert ("X-DSN-01", "proposed") in [(x["screen_id"], x["kind"]) for x in w["steps"]] and len(w["steps"]) == 10   # 타월: 시안 승인은 제안 화면
    m = c.get("/main/domains", params={"d": "metal", "p": "M02"}).json()["domain"]["current"]
    assert m["n_proposed"] == 1 and m["steps"][0]["kind"] == "proposed" and not m["steps"][0]["open"]


def test_promo_tab_plays_the_video_for_logged_in_users_only():
    from mescore.app.routers import home
    c = client("admin")
    html = c.get("/main/promo", headers=HTML).text
    assert 'href="/main/promo"' in html and "<video" in html          # 메인 탭 · 사이드바에 「홍보」 · 재생기 (D-54)
    v = c.get("/main/promo/video", headers={"range": "bytes=0-1023"})
    assert v.status_code == 206 and v.headers["content-type"] == "video/mp4" and len(v.content) == 1024
    assert v.headers["content-range"].endswith(f"/{home.PROMO_VIDEO.stat().st_size}")
    assert c.get("/main/promo/poster").headers["content-type"] == "image/jpeg"
    assert client().get("/main/promo/video").status_code in (401, 303)
