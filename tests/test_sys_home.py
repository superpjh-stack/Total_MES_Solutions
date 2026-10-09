"""메인 카드 "오늘 건수" · 로그인 권한 표 요약 · 사용자 ↔ 작업자 연결 (개발1 · CMN-01/02 · F-SYS-01/02). JSON 으로 판정.

오늘 건수는 `stats` 공개 함수 값과 같아야 한다(라우터는 SQL 을 쓰지 않는다). 비밀번호 값은 테스트 안의 임시 값뿐.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from mescore.app import nav, rbac, stats
from mescore.app.main import app
from mescore.app.routers import home
from mescore.app.settings import get_settings
from mescore.db import conn

SFX = uuid.uuid4().hex[:6].lower()
JSON = {"accept": "application/json"}


def _client(login_id: str, password: str | None = None) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/login", data={"login_id": login_id, "password": password or get_settings().seed_password}, headers=JSON)
    assert r.status_code == 200, f"{login_id} 로그인 실패 — make db-seed"
    return c


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    conn.x("delete from sys_session where user_id in (select id from sys_user where login_id like %s)", (f"h_{SFX}%",))
    conn.x("update sys_access_log set user_id = null where user_id in (select id from sys_user where login_id like %s)", (f"h_{SFX}%",))
    conn.x("delete from sys_user where login_id like %s", (f"h_{SFX}%",))
    conn.x("delete from bas_worker where worker_code like %s", (f"WK-H{SFX.upper()}%",))


def test_main_cards_today_come_from_stats():
    r = _client("admin").get("/", headers=JSON)
    assert r.status_code == 200
    cards = {(c["menu"]["code"] if isinstance(c["menu"], dict) else c["menu"]): c for c in r.json()["cards"]}
    if not hasattr(stats, "today_counts"):
        pytest.skip("stats.today_counts 없음 (개발3 회전 4 공표 전) — 카드는 전부 미수집")
    counts = stats.today_counts()
    for code, c in cards.items():
        if code in counts:
            assert isinstance(c["today"], int) and c["today_label"] == home.TODAY_LABELS[code], code
            assert c["today_source"] == stats.TODAY_COUNT_SOURCES[code]
        else:
            assert c["today"] is None   # 팩 모듈 — 출처 없으면 지어내지 않는다 → 화면 미수집
    assert set(home.TODAY_LABELS) == set(stats.TODAY_COUNT_SOURCES)


def test_login_page_has_role_summary_without_secrets():
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/login", headers=JSON)
    assert r.status_code == 200
    body = r.json()
    summary = body["role_summary"]
    assert [s["code"] for s in summary] == [x.code for x in rbac.roles()]
    admin = next(s for s in summary if s["code"] == "ADMIN")
    assert {w["code"] for w in admin["write_menus"]} == {m.code for m in nav.MENUS if rbac.cell("ADMIN", m.code).level == rbac.LEVEL_WRITE}
    for s in summary:
        assert s["read_count"] == sum(1 for m in nav.MENUS if rbac.cell(s["code"], m.code).can_read)
        assert all(ch["device"] in nav.DEVICE_CHANNEL for ch in s["channels"])
    text = r.text
    assert get_settings().seed_password not in text and "password_hash" not in text
    assert c.get("/login").status_code == 200   # HTML 도 그대로 그린다


@pytest.mark.fn("F-SYS-01")
def test_user_worker_link_for_pop_default():
    admin = _client("admin")
    wk = conn.q1("""insert into bas_worker (worker_code, worker_name, created_by) values (%s, '작업자 (예시)', 'test') returning id""",
                 (f"WK-H{SFX.upper()}",))["id"]
    pw = f"tmp-{uuid.uuid4().hex}"
    r = admin.post("/sys/users", data={"login_id": f"h_{SFX}", "user_name": "연결 (예시)", "role_id": rbac.role("FIELD").id,
                                       "worker_id": wk, "password": pw}, headers=JSON)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert conn.q1("select worker_id from sys_user where id = %s", (uid,))["worker_id"] == wk
    assert conn.q1("select w.worker_code from sys_user u join bas_worker w on w.id = u.worker_id where u.id = %s", (uid,))["worker_code"] == f"WK-H{SFX.upper()}"
    # 연결 해제(F-SYS-02) — 빈 값이면 NULL
    r = admin.post(f"/sys/users/{uid}", data={"worker_id": ""}, headers=JSON)
    assert r.status_code == 200, r.text
    assert conn.q1("select worker_id from sys_user where id = %s", (uid,))["worker_id"] is None


def test_seed_links_field_account_to_example_worker():
    row = conn.q1("""select w.worker_code from sys_user u join bas_worker w on w.id = u.worker_id where u.login_id = 'field'""")
    if row is None:
        pytest.skip("seed_dev1 미실행 또는 화면에서 연결을 바꿨다")
    assert row["worker_code"]


# ── D-605 · DEF-QA1-001 · DEF-QA3-001 — 개발용 무비밀번호 로그인은 MES_ENV=dev 명시 + 루프백에서만 ──

def _env(monkeypatch, value: str | None):
    from mescore.app import settings as st

    if value is None:
        monkeypatch.delenv("MES_ENV", raising=False)
    else:
        monkeypatch.setenv("MES_ENV", value)
    st.reset_cache()


@pytest.fixture
def env_restore():
    from mescore.app import settings as st

    yield
    st.reset_cache()


LOOP = ("127.0.0.1", 50000)


@pytest.mark.parametrize("env", ["prod", "", "staging"])
def test_login_as_is_404_outside_dev(monkeypatch, env_restore, env):
    _env(monkeypatch, env)
    c = TestClient(app, raise_server_exceptions=False, client=LOOP)
    r = c.post("/login/as", data={"role": "ADMIN"}, headers=JSON)
    assert r.status_code == 404
    assert c.get("/sys/users", headers=JSON).status_code in (401, 303)
    assert c.get("/login", headers=JSON).json()["dev_login"] is False


def test_login_as_is_404_in_dev_from_non_loopback(monkeypatch, env_restore):
    _env(monkeypatch, "dev")
    for client in [("testclient", 50000), ("10.0.0.7", 50000), ("192.168.1.20", 50000)]:
        c = TestClient(app, raise_server_exceptions=False, client=client)
        assert c.post("/login/as", data={"role": "ADMIN"}, headers=JSON).status_code == 404, client
    # 루프백이어도 프록시 전달 헤더가 있으면 바깥 요청이다
    c = TestClient(app, raise_server_exceptions=False, client=LOOP)
    r = c.post("/login/as", data={"role": "ADMIN"}, headers={**JSON, "x-forwarded-for": "203.0.113.5"})
    assert r.status_code == 404


def test_login_as_works_in_dev_from_loopback(monkeypatch, env_restore):
    _env(monkeypatch, "dev")
    if not get_settings().seed_password:
        pytest.skip("MES_SEED_PASSWORD 없음")
    c = TestClient(app, raise_server_exceptions=False, client=LOOP)
    assert c.get("/login", headers=JSON).json()["dev_login"] is True
    r = c.post("/login/as", data={"role": "ADMIN"}, headers=JSON)
    assert r.status_code == 200 and r.json()["role_code"] == "ADMIN"
