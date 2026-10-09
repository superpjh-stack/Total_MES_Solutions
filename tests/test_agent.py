"""MES AI Agent (선택 모듈 mesagent · D-47 · D-48) — 가짜 Claude 응답기로 호출어 · 오케스트레이터 · 정형 지표 · 파이프라인 · SQL 관문 · 권한 · 화면 · 음성 스크립트를 네트워크 없이 확인한다."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from mescore.db import conn
from datetime import date

from mesagent import llm, metrics, orchestrator, schema, sqlguard, wake
from mesagent.pipeline import ask, to_speech

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
    res = ask("로뎀, 작업지시 상태별 건수를 비교해줘", _user_via_client("admin"))
    assert res.status == 200 and res.route == "sql" and res.intent == "data" and res.data["row_count"] >= 1
    assert res.sql.lower().startswith("select") and res.answer and res.speech
    agents = [s["agent"] for s in res.trace]
    assert agents[:2] == ["호출어", "오케스트레이터"] and "SQL 작성" in agents and "SQL 실행" in agents and agents[-1] == "답변"
    assert "LLM 라우터" in res.trace[1]["detail"]
    assert len(f.calls) == 3                                                   # 라우터 · SQL · 답변


def test_sql_agent_self_corrects_after_db_error(fake):
    f = fake(sqls=("select no_such_column from job_work_order", "select count(*) as 건수 from job_work_order"))
    res = ask("로뎀 작업지시 번호 목록", _user_via_client("admin"))
    assert res.status == 200 and res.data["row_count"] == 1
    statuses = [(s["agent"], s["status"]) for s in res.trace if s["agent"] == "SQL 실행"]
    assert statuses == [("SQL 실행", "retry"), ("SQL 실행", "ok")]


# ── 호출어 ────────────────────────────────────────────────
@pytest.mark.parametrize("text,called,rest", [
    ("로뎀, 오늘의 재고량?", True, "오늘의 재고량?"), ("로뎀아 오늘 출하량", True, "오늘 출하량"), ("음 로뎀님, 생산량", True, "생산량"),
    ("로템 오늘 재고", True, "오늘 재고"), ("Rodem 재고", True, "재고"), ("로뎀", True, ""),
    ("오늘의 재고량?", False, "오늘의 재고량?"), ("재고 로뎀", False, "재고 로뎀"), ("로뎀즈 재고", False, "로뎀즈 재고"),
])
def test_wake_word(text, called, rest):
    assert wake.parse(text) == (called, rest)


def test_without_wake_word_agent_stays_silent(fake):
    f = fake()
    res = ask("오늘의 재고량?", _user_via_client("admin"))
    assert res.status == 200 and res.ignored and res.route == "ignored" and not res.answer and not res.speech and not res.tables
    assert f.calls == []                                                       # LLM 도 DB 도 부르지 않는다
    res = ask("로뎀", _user_via_client("admin"))
    assert res.route == "wake" and res.answer == "네, 말씀하세요."


# ── 오케스트레이터 · 정형 지표 ───────────────────────────────
@pytest.mark.parametrize("q,route", [
    ("오늘의 재고량?", "metric"), ("오늘의 출하량?", "metric"), ("오늘의 생산량?", "metric"), ("어제 입고량", "metric"),
    ("이번 주 불량률은?", "metric"), ("오늘 작업지시 현황", "metric"),
    ("수주 생산은 어떤 화면 순서로 진행해?", "rag"), ("LOT 를 나누려면 어떻게 해?", "rag"),
    ("검사 불합격이 가장 많은 품목 5개", "sql"), ("SMP-PRD-001 재고", "sql"),
])
def test_orchestrator_routes_without_llm(q, route):
    plan = orchestrator.by_rule(q) or orchestrator.fallback(q)
    expect_free = route == "sql" and metrics.match(q)
    assert plan.route == ("metric" if expect_free else route)                  # LLM 이 없으면 세부 조건 지표 질문도 지표로 답한다
    assert (orchestrator.by_rule(q) is not None) == (route == "metric")       # 규칙으로 바로 정해지는 것은 지표뿐


def test_period_parsing():
    t = date(2026, 10, 9)                                                      # 금요일
    assert (metrics.period("오늘", t).d0, metrics.period("오늘", t).d1) == (t, date(2026, 10, 10))
    assert metrics.period("어제 출하", t).d0 == date(2026, 10, 8)
    assert metrics.period("이번 주", t).d0 == date(2026, 10, 5)
    assert (metrics.period("지난주", t).d0, metrics.period("지난주", t).d1) == (date(2026, 9, 28), date(2026, 10, 5))
    assert (metrics.period("지난달", t).d0, metrics.period("지난달", t).d1) == (date(2026, 9, 1), date(2026, 10, 1))
    assert metrics.period("최근 7일", t).d0 == date(2026, 10, 3)


@pytest.mark.parametrize("q,key", [("오늘의 재고량?", "stock"), ("오늘의 출하량?", "shipment"), ("오늘의 생산량?", "production"),
                                   ("오늘 입고량은?", "receipt"), ("이번 주 불량률은?", "defect"), ("오늘 작업지시 현황", "work_order")])
def test_metric_questions_answer_without_llm(fake, q, key):
    f = fake()
    res = ask(f"로뎀, {q}", _user_via_client("admin"))
    assert res.status == 200 and res.route == "metric" and res.answer and res.speech == res.answer
    assert len(res.tables) == 1 and res.tables[0]["data"]["columns"] and res.tables[0]["sql"].lower().startswith(("select", "with"))
    assert f.calls == []                                                       # 숫자는 검증된 SQL 이 낸다 — LLM 을 부르지 않는다
    assert [s["agent"] for s in res.trace] == ["호출어", "오케스트레이터", "정형 지표"]


def test_metric_numbers_match_direct_sql(fake):
    fake()
    res = ask("로뎀 오늘의 생산량", _user_via_client("admin"))
    n = conn.q1("select count(*)::int as n, coalesce(sum(good_qty), 0) as g from pop_work_result where ended_at >= current_date and ended_at < current_date + 1")
    if n["n"]:
        assert metrics.num(n["g"]) in res.answer and f"실적 {n['n']:,}건" in res.answer
    else:
        assert "실적이 없습니다" in res.answer
    res = ask("로뎀 오늘 생산량과 출하량", _user_via_client("admin"))
    assert [t["title"].split(" · ")[0] for t in res.tables] == ["생산량", "출하량"]


def test_metric_respects_role():
    field = _user_via_client("field")
    res = ask("로뎀, 오늘의 재고량?", field)
    assert res.status == 200 and "볼 수 없는" in res.answer and not res.tables


def test_without_llm_docs_answer_from_rag_and_free_sql_is_501():
    llm.set_client(None)
    try:
        res = ask("로뎀, 수주 생산은 어떤 순서로 해?", _user_via_client("admin"))
        assert res.status == 200 and res.route == "rag" and res.docs and res.answer.startswith("문서에서 찾은 내용")
        assert any(d["title"].startswith("업무 프로세스 P01") for d in res.docs)          # 상위 5 안
        res = ask("로뎀, 검사 불합격이 가장 많은 품목 5개", _user_via_client("admin"))
        assert res.status == 501 and "LLM 미구성" in res.error and res.speech
    finally:
        llm._client_forced = False


def test_to_speech_strips_tables_and_sources():
    text = "오늘 생산량은 120 EA 입니다.\n| 품목 | 수량 |\n|---|---|\n근거: 업무 프로세스 P01"
    assert to_speech(text) == "오늘 생산량은 120 EA 입니다."


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
    assert "MES AI Agent" in html and 'href="/agent/about"' in html and 'src="/agent/voice.js"' in html and "data-mic" in html
    assert "로뎀, 오늘의 재고량?" in html and "로뎀, 오늘의 출하량?" in html and "로뎀, 오늘의 생산량?" in html
    assert c.get("/agent/about", headers=HTML).status_code == 200
    js = c.get("/agent/voice.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"] and "SpeechRecognition" in js.text and "speechSynthesis" in js.text
    r = c.post("/agent/ask", data={"question": "로뎀, 수주 생산 순서는 어떻게 돼?", "voice": "1"})
    assert r.status_code == 200 and r.json()["route"] == "rag" and r.json()["answer"] and r.json()["speech"]
    r = c.post("/agent/ask", data={"question": "수주 생산 순서는 어떻게 돼?"})
    assert r.status_code == 200 and r.json()["ignored"] and not r.json()["answer"]
    html = c.post("/agent/ask", data={"question": "로뎀 오늘의 재고량", "voice": "1"}, headers=HTML).text
    assert 'data-voice-mode="1"' in html and ('data-speech="지금 기준 재고' in html or 'data-speech="지금 재고' in html)
    assert _login(agent_app).get("/agent").status_code in (401, 303)
    assert _login(agent_app).get("/agent/voice.js").status_code in (401, 303)


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
