"""문서 RAG — 계약 · 스키마 · 결정 · 업무 프로세스 · 도메인 카탈로그를 조각으로 나눠 BM25 로 찾는다(외부 벡터 DB 없음).

토큰 = 영숫자 단어 + 한글 글자 2-gram (조사 · 띄어쓰기에 덜 민감). 색인은 기동 뒤 첫 질문 때 한 번 만든다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

import yaml

from mescore.app import guide
from mescore.app.settings import ROOT

SOURCES = ("contracts/function-list.md", "contracts/db-schema.md", "contracts/screen-map.md", "contracts/interfaces.md",
           "contracts/api-contract.md", "contracts/pack-contract.md", "decisions.md", "spec.md")
CHUNK = 900


@dataclass(frozen=True)
class Chunk:
    source: str
    title: str
    text: str


#: 질문 말투에 흔히 붙는 2글자 조각 — 검색 점수에서 뺀다 ("~은 어떤 순서로 진행해?" 의 '진행' · '어떤' 이 문서 점수를 먹지 않게)
STOP = {"어떤", "어떻", "떻게", "무엇", "엇이", "알려", "려줘", "해줘", "진행", "행해", "하는", "있는", "에서", "으로", "인가", "인지", "해야",
        "나요", "까요", "니까", "습니", "니다", "해서", "하고", "하면", "되나", "되는", "보여", "여줘", "는지", "할까", "얼마", "어디", "언제"}


def _tokens(text: str) -> list[str]:
    text = text.lower()
    out = re.findall(r"[a-z0-9_]{2,}", text)
    for run in re.findall(r"[가-힣]+", text):
        out.extend(g for g in (run[i:i + 2] for i in range(max(len(run) - 1, 1))) if g not in STOP)
    return out


def _md_chunks(path: str) -> list[Chunk]:
    f = ROOT / path
    if not f.exists():
        return []
    out, heads, buf = [], [], []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            for i in range(0, len(body), CHUNK):
                out.append(Chunk(path, " › ".join(heads) or path, body[i:i + CHUNK]))
        buf.clear()

    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush()
            level = len(m.group(1))
            heads[:] = heads[: level - 1] + [m.group(2).strip()]
        elif line.startswith("| F-") or line.startswith("| B-MIG-"):
            flush()
            out.append(Chunk(path, " › ".join(heads), line[:CHUNK]))            # 기능표는 한 줄 = 한 조각
        else:
            buf.append(line)
            if sum(len(x) for x in buf) > CHUNK:
                flush()
    flush()
    return out


def _guide_chunks() -> list[Chunk]:
    out = []
    for p in guide.processes():
        steps = " → ".join(f"{s.screen_id} {s.action}" for s in p.steps)
        out.append(Chunk("app/guide.py", f"업무 프로세스 {p.code} {p.name}", f"{p.when}. {p.goal}. 단계: {steps}. 확인: {' / '.join(p.checks)}"))
    return out


def _domain_chunks() -> list[Chunk]:
    out = []
    for f in sorted((ROOT / "domains").glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        rel = str(f.relative_to(ROOT))
        out.append(Chunk(rel, f"도메인 {d.get('name')}", f"{d.get('summary', '')} 공정: {' → '.join(d.get('flow') or [])}. LOT: {d.get('lot_model', '')}. 관리점: {' / '.join(d.get('controls') or [])}"))
        for p in d.get("processes") or []:
            steps = " → ".join(f"{s.get('screen')} {s.get('action')}" for s in p.get("steps") or [])
            out.append(Chunk(rel, f"{d.get('name')} {p.get('code')} {p.get('name')}", f"{p.get('when', '')}. {p.get('goal', '')}. 단계: {steps}"))
    return out


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.docs = [Counter(_tokens(c.title) * 3 + _tokens(c.text)) for c in chunks]      # 제목이 맞으면 더 무겁게
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 1
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query: str, k: int = 5) -> list[tuple[float, Chunk]]:
        q = Counter(_tokens(query))
        scored = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                f = d.get(t)
                if f:
                    s += self.idf.get(t, 0) * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self.lens[i] / self.avg))
            if s > 0:
                scored.append((s, self.chunks[i]))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]


@lru_cache(maxsize=1)
def index() -> Index:
    chunks: list[Chunk] = []
    for s in SOURCES:
        chunks.extend(_md_chunks(s))
    chunks.extend(_guide_chunks())
    chunks.extend(_domain_chunks())
    return Index(chunks)


def search(query: str, k: int = 5) -> list[dict]:
    return [{"source": c.source, "title": c.title, "text": c.text, "score": round(s, 2)} for s, c in index().search(query, k)]
