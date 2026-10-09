"""MES AI Agent (선택 모듈 mesagent · D-47) — 가짜 Claude 응답기로 파이프라인 · SQL 관문 · 권한 · 화면을 네트워크 없이 확인한다."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from mescore.db import conn
from mesagent import llm, schema, sqlguard
from mesagent.pipeline import ask

from _dev2_helpers import HTML


class FakeClaude:
    """시스템 프롬프트 첫머리로 역할을 가른다. sqls 를 차례로 내놓아 자기수정을 시험한다."""

    def __init__(self, intent="data", tables=("job_work_order",), sqls=("select status as 상태, count(*) as 건수 from job_work_order group by status",)):
        self.intent, self.tables, self.sqls, self.calls = intent, list(tables), list(sqls), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        sys_text = kw["system"][0]["text"]
        self.calls.append(sys_text[:20])
        assert kw["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in kw["betas"]
        if sys_text.startswith("너는 MES(제조 실행 시스템) AI 에이전트 팀의 라우터"):
            out = json.dumps({"intent": self.intent, "restated": "작업지시 상태별 건수", "tables": self.tables, "reason": "건수 질문"})
        elif sys_text.startswith("너는 PostgreSQL"):
            out = json.dumps({"sql": self.sqls.pop(0) if len(self.sqls) > 1 else self.sqls[0], "explanation": "상태별 건수"})
        else:
            out = "작업지시는 상태별로 위 표와 같다."
        return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5", content=[SimpleNamespace(type="text", text=out)])


@pytest.fixture
def fake():
    def _use(**kw):
        f = FakeClaude(**kw)
        llm.set_client(f)
        return f
    yield _use
    llm.set_client(None)
    llm._client_forced = False


def _user_via_client(login_id):
    from mescore.app import rbac
    r = conn.q1("""select u.id, u.login_id, u.user_name, r.role_code, r.role_name from sys_user u join sys_role r on r.id = u.role_id where u.login_id = %s""", (login_id,))
    return SimpleNamespace(id=r["id"], login_id=r["login_id"], user_name=r["user_name"], role_code=r["role_code"], role_name=r["role_name"])


@pytest.mark.parametrize("sql,why", [
    ("delete from bas_item", "SELECT"), ("select 1 from bas_item; delete from bas_item", "한 문장"),
    ("select * from pg_catalog.pg_user", "카탈로그"), ("select login_id, password_hash from sys_user", "읽을 수 없는"),
    ("with x as (update bas_item set spec = 'a' returning id) select * from x", "키워드"), ("select pg_sleep(10) from bas_item", "키워드"),
    ("select 1", "참조하지"),
])
def test_guard_rejects_unsafe_sql(sql, why):
    known = set(schema.relations())
    allowed = set(schema.allowed(_user_via_client("admin")))
    with pytest.raises(sqlguard.SqlRejected, match=why):
        sqlguard.check(sql, known, allowed)


def test_run_is_read_only_and_capped():
    before = conn.q1("select count(*)::int as n from bas_item")["n"]
    out = sqlguard.run("select item_code from bas_item")
    assert out["row_count"] <= sqlguard.MAX_ROWS and out["columns"] == ["item_code"]
    assert conn.q1("select count(*)::int as n from bas_item")["n"] == before
    with pytest.raises(Exception):
        sqlguard.run("select 1 from bas_item where 1/0 = 1")


def test_role_cannot_query_modules_it_cannot_read():
    field = set(schema.allowed(_user_via_client("field")))
    assert "bas_item" not in field and "pop_work_result" in field            # 현장: 기준정보 없음 · 생산실적 입력
    assert not set(schema.NEVER) & set(schema.allowed(_user_via_client("admin")))


def test_pipeline_data_question_runs_sql_and_answers(fake):
    f = fake()
    res = ask("작업지시 상태별 건수", _user_via_client("admin"))
    assert res.status == 200 and res.intent == "data" and res.data["row_count"] >= 1
    assert res.sql.lower().startswith("select") and res.answer
    agents = [s["agent"] for s in res.trace]
    assert agents[:1] == ["문서 검색"] and "라우터" in agents and "SQL 작성" in agents and "SQL 실행" in agents and agents[-1] == "답변"
    assert len(f.calls) == 3                                                   # 라우터 · SQL · 답변


def test_sql_agent_self_corrects_after_db_error(fake):
    f = fake(sqls=("select no_such_column from job_work_order", "select count(*) as 건수 from job_work_order"))
    res = ask("작업지시 몇 건", _user_via_client("admin"))
    assert res.status == 200 and res.data["row_count"] == 1
    statuses = [(s["agent"], s["status"]) for s in res.trace if s["agent"] == "SQL 실행"]
    assert statuses == [("SQL 실행", "retry"), ("SQL 실행", "ok")]


def test_without_llm_returns_501_with_docs():
    llm.set_client(None)
    try:
        res = ask("수주 생산은 어떤 순서로 해?", _user_via_client("admin"))
        assert res.status == 501 and "LLM 미구성" in res.error and res.docs
        assert any(d["title"].startswith("업무 프로세스 P01") for d in res.docs)          # 상위 5 안
    finally:
        llm._client_forced = False


@pytest.fixture
def agent_app(monkeypatch):
    """`MES_ADDONS=agent` 로 앱을 새로 만든다 — 게이트는 코어 판정을 위해 선택 모듈을 끄고 돌린다(D-47)."""
    from mescore.app import settings
    from mescore.app.main import create_app
    monkeypatch.setenv("MES_ADDONS", "agent")
    settings.reset_cache()
    app = create_app()
    yield app
    monkeypatch.undo()
    settings.reset_cache()


def _login(app, login_id=None):
    from fastapi.testclient import TestClient
    from mescore.app.settings import get_settings
    c = TestClient(app, raise_server_exceptions=False)
    if login_id:
        assert c.post("/login", data={"login_id": login_id, "password": get_settings().seed_password}).json()["ok"]
    return c


def test_agent_pages_and_menu(fake, agent_app):
    fake(intent="docs", tables=())
    c = _login(agent_app, "admin")
    html = c.get("/agent", headers=HTML).text
    assert "MES AI Agent" in html and 'href="/agent/about"' in html and "메인 (IA)" not in html.split("<main", 1)[0][-400:]
    assert c.get("/agent/about", headers=HTML).status_code == 200
    r = c.post("/agent/ask", data={"question": "수주 생산 순서"})
    assert r.status_code == 200 and r.json()["intent"] == "docs" and r.json()["answer"]
    assert _login(agent_app).get("/agent").status_code in (401, 303)


def test_core_without_addon_has_no_agent_routes():
    """선택 모듈을 끄면 메뉴 · 라우트가 없다 — 코어 단독 판정(G-C12)의 전제."""
    import os
    from mescore.app import settings
    from mescore.app.main import create_app
    old = os.environ.get("MES_ADDONS")
    os.environ["MES_ADDONS"] = ""
    settings.reset_cache()
    try:
        app = create_app()
        assert not any(getattr(r, "path", "").startswith("/agent") for r in app.routes)
        assert not getattr(app.state, "addon_menus", [])
    finally:
        if old is None:
            os.environ.pop("MES_ADDONS", None)
        else:
            os.environ["MES_ADDONS"] = old
        settings.reset_cache()
