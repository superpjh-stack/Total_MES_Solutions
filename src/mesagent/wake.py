"""호출어 — 「로뎀」 이라고 불러야 답한다. 부르지 않은 질문은 듣기만 하고 답하지 않는다(음성 · 글 모두).

음성 인식은 「로뎀」 을 로댐 · 노뎀 · 로덤 · 로템 으로 받아 적기도 해서 그 변형도 호출로 본다.
`MES_AGENT_WAKE` (쉼표) 로 호출어를 바꾼다 — 바꾸면 그 낱말 그대로만 본다.
"""

from __future__ import annotations

import os
import re

DEFAULT = ("로뎀", "로댐", "노뎀", "로덤", "로템", "rodem")
FILLER = r"(?:(?:음|어|저기요?|헤이|hey|야|자)[\s,.!~]*)*"
SUFFIX = r"(?:아|야|님|씨|이)?"


def words() -> tuple[str, ...]:
    env = [w.strip() for w in (os.environ.get("MES_AGENT_WAKE") or "").split(",") if w.strip()]
    return tuple(env) or DEFAULT


def name() -> str:
    return words()[0]


def pattern() -> str:
    """JS 와 같은 문장(음성 화면이 그대로 쓴다)."""
    alt = "|".join(re.escape(w) for w in sorted(words(), key=len, reverse=True))
    return rf"^\s*{FILLER}({alt}){SUFFIX}(?=$|[\s,.!?~])[\s,.!?~]*"


def parse(text: str) -> tuple[bool, str]:
    """(호출했나, 호출어를 뺀 질문)."""
    m = re.match(pattern(), text or "", re.I)
    if not m:
        return False, (text or "").strip()
    return True, text[m.end():].strip()
