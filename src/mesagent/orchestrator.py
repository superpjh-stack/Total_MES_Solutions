"""오케스트레이터 — 질문 하나를 어느 길로 풀지 정한다.

    metric  정형 지표 카탈로그(metrics) — 미리 검증한 SQL · LLM 없이도 답한다 (오늘의 재고량 · 출하량 · 생산량 …)
    sql     LLM 이 SQL 을 써서 MES DB 조회 (세부 조건 · 목록 · 순위 · 특정 번호)
    rag     문서 RAG 조회 (사용법 · 절차 · 규칙 · 결정)
    both    SQL + RAG
    chat    MES 와 무관

판단 순서: ① 규칙 — 지표 낱말 + 양/기간 신호가 있고 세부 조건이 없으면 metric
          ② LLM 라우터(구성돼 있으면) — data / docs / both / chat 과 필요한 테이블
          ③ 규칙 대체(LLM 미구성) — 문서 신호면 rag, 데이터 신호면 sql(→ 501), 지표 낱말이 있으면 metric
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import metrics

DATA_CUE = r"몇|얼마|합계|건수|수량|목록|현황|상태|오늘|어제|이번|최근|가장|상위|언제|누가|어느|번호|LOT|lot|재고|출하|입고|생산|불량|작업\s*지시|수주|설비|검사"


@dataclass
class Plan:
    route: str                                  # metric | sql | rag | both | chat
    by: str                                     # 규칙 | LLM 라우터 | 규칙(LLM 미구성)
    reason: str
    metrics: list = field(default_factory=list)
    period: metrics.Period | None = None
    tables: list[str] = field(default_factory=list)
    restated: str = ""


def by_rule(q: str) -> Plan | None:
    """규칙만으로 정해지는 경우(정형 지표). 아니면 None."""
    hits = metrics.match(q)
    if hits and not metrics.is_free(q):
        p = metrics.period(q)
        names = " · ".join(m.label for m in hits)
        return Plan("metric", "규칙", f"정형 지표({names}) · 기간 {p.label if any(m.uses_period for m in hits) else '현재'} — 검증된 SQL 로 바로 조회",
                    metrics=hits, period=p)
    return None


def fallback(q: str) -> Plan:
    """LLM 이 없을 때 규칙으로 고른다."""
    hits = metrics.match(q)
    if hits:
        p = metrics.period(q)
        return Plan("metric", "규칙(LLM 미구성)", "세부 조건은 LLM 이 있어야 풀 수 있어 정형 지표로 답한다", metrics=hits, period=p)
    if re.search(metrics.DOC_CUE, q):
        return Plan("rag", "규칙(LLM 미구성)", "사용법 · 절차 질문 — 문서에서 찾는다")
    if re.search(DATA_CUE, q):
        return Plan("sql", "규칙(LLM 미구성)", "자유 형식 데이터 질문 — SQL 작성에 LLM 이 필요하다")
    return Plan("rag", "규칙(LLM 미구성)", "분류 신호가 없어 문서에서 찾는다")


def from_router(r: dict, allowed: list[str]) -> Plan:
    route = {"data": "sql", "docs": "rag", "both": "both", "chat": "chat"}.get(r.get("intent"), "rag")
    return Plan(route, "LLM 라우터", r.get("reason", ""), tables=[t for t in r.get("tables", []) if t in allowed][:6], restated=r.get("restated") or "")
