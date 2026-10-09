"""멀티에이전트 파이프라인 — 호출어 → 오케스트레이터 → (정형 지표 | 스키마 탐색 → SQL 작성 ⇄ SQL 실행 | 문서 검색) → 답변.

각 단계는 trace 한 줄을 남겨 화면이 "누가 무엇을 했는지" 그대로 보인다. 근거(조회 행 · 문서)가 없으면 답변 에이전트는 '판단 불가' 라고 말한다.
「로뎀」 이라고 부르지 않은 질문은 답하지 않는다(wake). 음성으로 읽을 짧은 문장은 `speech` 에 둔다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import psycopg

from mescore.app import rbac

from . import llm, metrics, orchestrator, rag, schema, sqlguard, wake

MAX_SQL_TRIES = 3
ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["data", "docs", "both", "chat"]},
        "restated": {"type": "string"},
        "tables": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["intent", "restated", "tables", "reason"],
    "additionalProperties": False,
}
SQL_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string"}, "explanation": {"type": "string"}},
    "required": ["sql", "explanation"],
    "additionalProperties": False,
}

ROUTER_SYSTEM = """너는 MES(제조 실행 시스템) AI 에이전트 팀의 라우터다. 사용자의 질문을 보고 어느 에이전트가 일할지 정한다.
- intent: data = MES DB 의 데이터를 조회해야 답할 수 있는 질문(건수 · 목록 · 합계 · 추이 · 특정 번호의 상태 등)
          docs = 기능 · 화면 사용법 · 업무 절차 · 규칙 · 설계 결정처럼 문서로 답하는 질문
          both = 둘 다 필요 · chat = 인사 등 MES 와 무관
- restated: 모호한 표현을 풀어 쓴 질문 한 문장(기간이 없으면 그대로 둔다)
- tables: data/both 이면 아래 '읽을 수 있는 테이블' 중 필요한 이름만(최대 6). 목록에 없는 이름은 쓰지 않는다
- reason: 판단 이유 한 문장
읽을 수 있는 테이블:
{tables}"""

SQL_SYSTEM = """너는 PostgreSQL 17 전문가인 SQL 작성 에이전트다. MES 데이터를 조회하는 SELECT 한 문장을 쓴다.
규칙:
- SELECT 또는 WITH 로 시작하는 한 문장만. 세미콜론 · 주석 · 쓰기 · DDL · 시스템 카탈로그 금지
- 아래 스키마에 있는 테이블 · 컬럼만 쓴다. 없으면 추측하지 말고 가장 가까운 것을 쓰고 explanation 에 밝힌다
- 사람이 읽을 컬럼(코드 · 이름 · 번호 · 수량 · 상태 · 날짜)을 고르고 의미 있는 별칭을 한국어로 붙인다
- 목록은 최근 순(order by ... desc)으로 50행 이내(limit 50). 집계는 group by 와 함께
- 오늘 = current_date, 이번 주 = date_trunc('week', current_date)
- 상태 값은 한국어 문자열이다(예: '대기' '진행' '마감' '취소' · '합격' '불합격' · '재고' '소진' '출하')
- LOT 상태는 v_lot_state, 잔량은 v_lot_stock, 작업지시 진행 여부는 v_work_order_progress 뷰를 쓴다
- explanation: 이 SQL 이 무엇을 세는지 한 문장
스키마:
{schema}"""

ANSWER_SYSTEM = """너는 MES AI 에이전트 팀의 답변 에이전트다. 주어진 근거만으로 한국어로 짧고 정확하게 답한다.
- 근거 = 'SQL 조회 결과' 와 '문서 조각' 뿐이다. 근거에 없는 숫자 · 사실은 만들지 않는다
- 조회 결과가 0행이면 "조회된 데이터가 없다" 고 말하고 조건을 짧게 밝힌다. 근거가 전혀 없으면 "판단 불가" 라고 말한다
- 숫자는 결과 그대로 쓰고 단위를 붙인다. 결과가 잘렸으면(상한) 그 사실을 밝힌다
- 문서를 근거로 쓰면 끝에 '근거:' 로 문서 제목을 적는다. 화면 ID(예: JOB-01)가 있으면 그대로 적어 사용자가 찾아가게 한다
- 첫 문장에 답을 쓴다. 표가 필요하면 5행 이내로 요약하고, 전체 행은 화면의 결과 표가 보여 준다고 말한다"""


@dataclass
class Result:
    question: str
    status: int = 200
    intent: str = ""
    answer: str = ""
    sql: str | None = None
    sql_explanation: str = ""
    data: dict | None = None
    docs: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    model: str = ""
    error: str = ""
    heard: str = ""                       # 들은 그대로(호출어 포함)
    route: str = ""                       # 오케스트레이터가 고른 길: metric | sql | rag | both | chat | ignored | wake
    ignored: bool = False                 # 호출어가 없어 답하지 않음
    speech: str = ""                      # 음성으로 읽을 짧은 답
    tables: list[dict] = field(default_factory=list)   # [{title sql data}] — 정형 지표는 여러 개

    def step(self, agent: str, title: str, status: str, detail: str = "", t0: float | None = None) -> None:
        self.trace.append({"agent": agent, "title": title, "status": status, "detail": detail,
                           "ms": round((time.perf_counter() - t0) * 1000) if t0 else None})


def _history_messages(history: list[dict]) -> list[dict]:
    out = []
    for h in history[-3:]:
        out.append({"role": "user", "content": h["q"]})
        out.append({"role": "assistant", "content": h["a"][:1500]})
    return out


ROUTE_LABEL = {"metric": "정형 지표 SQL", "sql": "DB · SQL 조회", "rag": "RAG 문서 조회", "both": "SQL + RAG", "chat": "일반 대화"}
INTENT_OF = {"sql": "data", "rag": "docs", "metric": "metric", "both": "both", "chat": "chat"}


def _pretty(sql: str) -> str:
    return re.sub(r"\n\s+", "\n  ", sql.strip())


def to_speech(text: str, limit: int = 260) -> str:
    """화면 답에서 읽을 부분만 — 표 · 기호 · 근거 줄을 빼고 앞 문장 몇 개."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip() and not ln.lstrip().startswith(("|", "근거", "```", "-", "*", "#"))]
    t = re.sub(r"[`*_#>|]", "", " ".join(lines))
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= limit:
        return t
    cut = max(t.rfind(". ", 0, limit), t.rfind("다 ", 0, limit), t.rfind("요 ", 0, limit))
    return t[: cut + 1].strip() if cut > 40 else t[:limit].strip() + " …"


def _run_metrics(res: Result, plan: orchestrator.Plan, allowed: list[str], known: set[str]) -> None:
    says = []
    for m in plan.metrics:
        t0 = time.perf_counter()
        p = plan.period
        missing = [t for t in m.tables if t not in allowed]
        if missing:
            says.append(f"{m.label}은 지금 역할로 볼 수 없는 데이터입니다.")
            res.step("정형 지표", m.label, "fail", f"권한 없는 테이블: {', '.join(missing)}", t0)
            continue
        summary = sqlguard.run(sqlguard.check(m.summary(p), known, set(allowed)))
        detail_sql = sqlguard.check(m.detail(p), known, set(allowed))
        detail = sqlguard.run(detail_sql)
        says.append(m.say(p, summary["rows"]))
        title = f"{m.label} · {p.label if m.uses_period else '현재'}"
        res.tables.append({"title": title, "sql": _pretty(detail_sql), "data": detail, "summary": summary["rows"]})
        res.step("정형 지표", title, "ok", f"요약 + 상세 {detail['row_count']}행 · {summary['ms'] + detail['ms']}ms · 읽기 전용", t0)
    if res.tables:
        res.sql, res.data = res.tables[0]["sql"], res.tables[0]["data"]
        res.sql_explanation = res.tables[0]["title"]
    res.answer = " ".join(says)
    res.speech = res.answer


def _extractive(res: Result) -> None:
    """LLM 없이 문서 조각을 그대로 보여 주는 답."""
    if not res.docs:
        res.answer = "문서에서 관련 내용을 찾지 못했습니다."
    else:
        top = res.docs[0]
        body = re.sub(r"\s+", " ", top["text"]).strip()
        res.answer = f"문서에서 찾은 내용입니다 — {top['title']}: {body[:400]}{'…' if len(body) > 400 else ''}\n근거: " + " · ".join(d["title"][:40] for d in res.docs[:3])
    res.speech = f"문서에서 찾은 내용입니다. {res.docs[0]['title']}." if res.docs else res.answer


def ask(question: str, user: rbac.User, history: list[dict] | None = None) -> Result:
    heard = (question or "").strip()
    res = Result(question=heard, heard=heard)
    if not heard:
        res.status, res.error = 422, "질문이 비었다"
        return res

    # ⓪ 호출어 — 부르지 않으면 답하지 않는다
    called, q = wake.parse(heard)
    if not called:
        res.ignored, res.route, res.intent = True, "ignored", "ignored"
        res.step("호출어", f"「{wake.name()}」 호출 없음 — 답하지 않는다", "skip", f"예) {wake.name()}, 오늘의 재고량?")
        return res
    res.question = q
    res.step("호출어", f"「{wake.name()}」 호출 확인", "ok")
    if not q:
        res.route = res.intent = "wake"
        res.answer = res.speech = "네, 말씀하세요."
        return res

    allowed = schema.allowed(user)
    known = set(schema.relations())
    hist = _history_messages(history or [])
    try:
        # ① 오케스트레이터 — 정형 지표 SQL · LLM SQL · RAG 중 어디로 갈지
        t0 = time.perf_counter()
        plan = orchestrator.by_rule(q)
        if plan is None and llm.configured():
            r, res.model = llm.json_call(system=ROUTER_SYSTEM.format(tables=schema.table_list_text(allowed)), user=q, schema=ROUTER_SCHEMA,
                                         effort="low", max_tokens=4000, history=hist)
            plan = orchestrator.from_router(r, allowed)
        elif plan is None:
            plan = orchestrator.fallback(q)
        res.route, res.intent = plan.route, INTENT_OF[plan.route]
        extra = f" · 테이블 {', '.join(plan.tables)}" if plan.tables else ""
        res.step("오케스트레이터", f"경로 → {ROUTE_LABEL[plan.route]}{extra}", "ok", f"{plan.by} — {plan.reason}", t0)

        if plan.route == "metric":
            _run_metrics(res, plan, allowed, known)
            return res

        # ⑤ 문서 검색 — rag · both · chat, 그리고 SQL 이 실패했을 때의 근거
        t0 = time.perf_counter()
        res.docs = rag.search(q, k=5)
        if plan.route != "sql":
            res.step("문서 검색", f"RAG 조각 {len(res.docs)}개", "ok", " · ".join(d["title"][:40] for d in res.docs[:3]), t0)

        if not llm.configured():
            if plan.route == "sql":
                res.status = 501
                res.error = "LLM 미구성 (D-47) — 자유 형식 데이터 질문은 SQL 작성 에이전트(LLM)가 필요하다. .env 에 ANTHROPIC_API_KEY 를 넣는다. 정형 지표(오늘의 재고량 · 출하량 · 생산량 · 입고량 · 불량률 · 작업지시 현황)는 지금도 답한다"
                res.speech = "이 질문은 언어 모델이 있어야 답할 수 있습니다. 오늘의 재고량, 출하량, 생산량 같은 질문은 지금도 답할 수 있어요."
                res.step("SQL 작성", "건너뜀 — LLM 미구성", "skip")
                return res
            _extractive(res)
            res.step("답변", "문서 발췌(LLM 미구성)", "ok")
            return res

        restated = plan.restated or q
        if plan.route in ("sql", "both"):
            # ② 스키마 탐색 — 라우터가 고른 테이블 + 설명 검색으로 보탠 테이블
            t0 = time.perf_counter()
            picked = list(plan.tables)
            if len(picked) < 3:
                for t in allowed:
                    if t not in picked and any(w in (schema.descriptions().get(t, "") + t) for w in restated.split() if len(w) >= 2):
                        picked.append(t)
                    if len(picked) >= 6:
                        break
            if not picked:
                picked = [t for t in ("job_work_order", "pop_work_result", "lot") if t in allowed]
            detail = schema.detail_text(picked)
            res.step("스키마 탐색", f"테이블 {len(picked)} · 컬럼 · 외래키", "ok", ", ".join(picked), t0)

            # ③ SQL 작성 ⇄ ④ 실행 (자기수정)
            feedback = ""
            for attempt in range(1, MAX_SQL_TRIES + 1):
                t0 = time.perf_counter()
                draft, _ = llm.json_call(system=SQL_SYSTEM.format(schema=detail), user=restated + feedback, schema=SQL_SCHEMA, effort="medium", max_tokens=6000)
                sql = draft["sql"].strip()
                res.step("SQL 작성", f"시도 {attempt}", "ok", draft.get("explanation", ""), t0)
                t0 = time.perf_counter()
                try:
                    safe = sqlguard.check(sql, known, set(allowed))
                    res.data = sqlguard.run(safe)
                    res.sql, res.sql_explanation = safe, draft.get("explanation", "")
                    res.tables = [{"title": res.sql_explanation or "조회 결과", "sql": safe, "data": res.data}]
                    res.step("SQL 실행", f"{res.data['row_count']}행{' (상한에서 잘림)' if res.data['truncated'] else ''}", "ok", f"{res.data['ms']}ms · 읽기 전용", t0)
                    break
                except sqlguard.SqlRejected as exc:
                    res.step("SQL 실행", "검사에서 막힘", "retry", str(exc), t0)
                    feedback = f"\n\n[이전 SQL 이 검사에서 막혔다 — 고쳐서 다시 써라]\nSQL: {sql}\n사유: {exc}"
                except psycopg.Error as exc:
                    msg = str(exc).strip().splitlines()[0][:300]
                    res.step("SQL 실행", "DB 오류", "retry", msg, t0)
                    feedback = f"\n\n[이전 SQL 이 DB 에서 실패했다 — 고쳐서 다시 써라]\nSQL: {sql}\n오류: {msg}"
            if res.data is None:
                res.step("SQL 실행", f"{MAX_SQL_TRIES}회 모두 실패", "fail")

        # ⑥ 답변
        t0 = time.perf_counter()
        evidence = []
        if res.data is not None:
            preview = res.data["rows"][:40]
            evidence.append(f"[SQL 조회 결과] {res.sql_explanation}\nSQL: {res.sql}\n행 수: {res.data['row_count']}{' (상한 ' + str(sqlguard.MAX_ROWS) + '행에서 잘림)' if res.data['truncated'] else ''}\n열: {res.data['columns']}\n행(앞 40): {preview}")
        elif plan.route in ("sql", "both"):
            evidence.append("[SQL 조회 결과] 조회 실패 — 데이터를 가져오지 못했다")
        if plan.route in ("rag", "both", "chat") or res.data is None:
            evidence.append("[문서 조각]\n" + "\n\n".join(f"({d['title']} · {d['source']})\n{d['text']}" for d in res.docs))
        res.answer, m = llm.text_call(system=ANSWER_SYSTEM, user=f"질문: {q}\n\n" + "\n\n".join(evidence), effort="low", max_tokens=4000, history=hist)
        res.model = res.model or m
        res.speech = to_speech(res.answer)
        res.step("답변", "근거로 답 작성", "ok", f"모델 {res.model}", t0)
    except llm.LlmUnavailable as exc:
        res.status, res.error = 501, f"{exc} (D-47)"
    except llm.LlmError as exc:
        res.status, res.error = 502, str(exc)
        res.step("오류", "LLM 호출 실패", "fail", str(exc))
    return res
