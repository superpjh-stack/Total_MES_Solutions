"""MES AI Agent 화면 · API — `/agent` (질문) · `/agent/about` (에이전트 구성 · 데이터 범위). 어떤 MES 테이블에도 쓰지 않는다.

대화는 로그인 세션마다 서버 메모리에 최근 10개만 둔다(재기동하면 비워진다 · 저장 테이블 없음). 질문은 접근 로그(view)에 남긴다.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from mescore.app import rbac, templating
from mescore.app.util import audit

from . import llm, metrics, rag, schema, sqlguard, wake
from .pipeline import ask

router = APIRouter()
MENU = {"code": "agent", "name": "MES AI Agent", "icon": "AI", "items": [("/agent", "질문하기"), ("/agent/about", "에이전트 구성")]}
_HISTORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
#: 추천 질의 — 앞 6개는 정형 지표(LLM 없이 답함), 뒤 3개는 LLM SQL · RAG
SUGGEST = ("오늘의 재고량?", "오늘의 출하량?", "오늘의 생산량?", "오늘 입고량은?", "이번 주 불량률은?", "오늘 작업지시 현황",
           "검사 불합격이 가장 많은 품목 5개", "고장이 아직 조치되지 않은 설비 목록", "수주 생산은 어떤 화면 순서로 진행해?")
VOICE_JS = Path(__file__).parent / "static" / "voice.js"


def _key(request: Request, user: rbac.User) -> str:
    return f"{user.login_id}:{request.cookies.get('mes_session', '')[:16]}"


def _wants_html(request: Request) -> bool:
    return "text/html" in (request.headers.get("accept") or "")


def _page_ctx(user: rbac.User) -> dict:
    return {"examples": [f"{wake.name()}, {q}" for q in SUGGEST], "n_metric": len(metrics.CATALOG), "wake_name": wake.name(),
            "wake_pattern": wake.pattern(), "configured": llm.configured(), "model": llm.model(), "n_tables": len(schema.allowed(user)),
            "screen_name": "질문하기", "menu_name": "MES AI Agent"}


@router.get("/agent", include_in_schema=False)
def agent_page(request: Request, user: rbac.User = Depends(rbac.require_login)) -> HTMLResponse:
    return templating.render(request, "agent/index.html", {
        "history": list(reversed(_HISTORY[_key(request, user)])), "result": None, **_page_ctx(user),
    })


@router.get("/agent/voice.js", include_in_schema=False)
def agent_voice_js(user: rbac.User = Depends(rbac.require_login)) -> FileResponse:
    return FileResponse(VOICE_JS, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.post("/agent/ask", include_in_schema=False)
def agent_ask(request: Request, question: str = Form(""), voice: str = Form(""), user: rbac.User = Depends(rbac.require_login)):
    hist = _HISTORY[_key(request, user)]
    res = ask(question, user, list(hist))
    audit.write_log(kind=audit.VIEW, login_id=user.login_id, user_id=user.id, screen_id="AGENT",
                    detail={"path": "/agent/ask", "question": res.heard[:300], "route": res.route, "status": res.status, "voice": bool(voice),
                            "sql": (res.sql or "")[:500], "rows": (res.data or {}).get("row_count")},
                    ip=audit.client_ip(request), device=audit.device_of(request))
    if res.status == 200 and res.answer and res.route != "wake":
        hist.append({"q": res.question, "a": res.answer, "sql": res.sql, "rows": (res.data or {}).get("row_count"), "route": res.route})
    body = asdict(res)
    if not _wants_html(request):
        return JSONResponse(body, status_code=res.status)
    return templating.render(request, "agent/index.html", {
        "history": list(reversed(hist)), "result": body, "question": res.heard, "voice_mode": bool(voice), **_page_ctx(user),
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
        "wake_words": wake.words(), "metric_list": [(m.label, ", ".join(m.tables), m.uses_period) for m in metrics.CATALOG],
    })
