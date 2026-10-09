"""MES AI Agent 화면 · API — `/agent` (질문) · `/agent/about` (에이전트 구성 · 데이터 범위). 어떤 MES 테이블에도 쓰지 않는다.

대화는 로그인 세션마다 서버 메모리에 최근 10개만 둔다(재기동하면 비워진다 · 저장 테이블 없음). 질문은 접근 로그(view)에 남긴다.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from mescore.app import rbac, templating
from mescore.app.util import audit

from . import llm, rag, schema, sqlguard
from .pipeline import ask

router = APIRouter()
MENU = {"code": "agent", "name": "MES AI Agent", "icon": "AI", "items": [("/agent", "질문하기"), ("/agent/about", "에이전트 구성")]}
_HISTORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
EXAMPLES = ("오늘 계획된 작업지시는 몇 건이고 상태별로 몇 건이야?", "검사 불합격이 가장 많은 품목 5개를 알려줘", "재고 상태인 생산 LOT 수량을 품목별로 합계 내줘",
            "고장이 아직 조치되지 않은 설비 목록", "출하 승인 전인 출하 건과 거래처", "수주 생산은 어떤 화면 순서로 진행해?")


def _key(request: Request, user: rbac.User) -> str:
    return f"{user.login_id}:{request.cookies.get('mes_session', '')[:16]}"


def _wants_html(request: Request) -> bool:
    return "text/html" in (request.headers.get("accept") or "")


@router.get("/agent", include_in_schema=False)
def agent_page(request: Request, user: rbac.User = Depends(rbac.require_login)) -> HTMLResponse:
    return templating.render(request, "agent/index.html", {
        "history": list(reversed(_HISTORY[_key(request, user)])), "result": None, "examples": EXAMPLES,
        "configured": llm.configured(), "model": llm.model(), "n_tables": len(schema.allowed(user)),
        "screen_name": "질문하기", "menu_name": "MES AI Agent",
    })


@router.post("/agent/ask", include_in_schema=False)
def agent_ask(request: Request, question: str = Form(""), user: rbac.User = Depends(rbac.require_login)):
    hist = _HISTORY[_key(request, user)]
    res = ask(question, user, list(hist))
    audit.write_log(kind=audit.VIEW, login_id=user.login_id, user_id=user.id, screen_id="AGENT",
                    detail={"path": "/agent/ask", "question": res.question[:300], "intent": res.intent, "status": res.status,
                            "sql": (res.sql or "")[:500], "rows": (res.data or {}).get("row_count")},
                    ip=audit.client_ip(request), device=audit.device_of(request))
    if res.status == 200 and res.answer:
        hist.append({"q": res.question, "a": res.answer, "sql": res.sql, "rows": (res.data or {}).get("row_count")})
    body = asdict(res)
    if not _wants_html(request):
        return JSONResponse(body, status_code=res.status)
    return templating.render(request, "agent/index.html", {
        "history": list(reversed(hist)), "result": body, "examples": EXAMPLES, "configured": llm.configured(), "model": llm.model(),
        "n_tables": len(schema.allowed(user)), "question": res.question, "screen_name": "질문하기", "menu_name": "MES AI Agent",
    }, status_code=res.status)


@router.post("/agent/reset", include_in_schema=False)
def agent_reset(request: Request, user: rbac.User = Depends(rbac.require_login)):
    _HISTORY[_key(request, user)].clear()
    return JSONResponse({"ok": True}) if not _wants_html(request) else agent_page(request, user)


@router.get("/agent/about", include_in_schema=False)
def agent_about(request: Request, user: rbac.User = Depends(rbac.require_login)) -> HTMLResponse:
    allowed = schema.allowed(user)
    blocked = sorted(set(schema.relations()) - set(allowed))
    idx = rag.index()
    sources: dict[str, int] = {}
    for c in idx.chunks:
        sources[c.source] = sources.get(c.source, 0) + 1
    return templating.render(request, "agent/about.html", {
        "configured": llm.configured(), "model": llm.model(), "allowed": allowed, "blocked": blocked,
        "never": sorted(schema.NEVER), "sources": sorted(sources.items()), "n_chunks": len(idx.chunks),
        "max_rows": sqlguard.MAX_ROWS, "timeout_ms": sqlguard.TIMEOUT_MS, "screen_name": "에이전트 구성", "menu_name": "MES AI Agent",
    })
