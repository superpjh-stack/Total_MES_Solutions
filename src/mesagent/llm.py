"""Claude 호출 — Anthropic SDK (D-47). 키가 없으면 `LlmUnavailable`, 호출이 실패하면 `LlmError` — 조용한 대체 답 없음.

모델은 `MES_AGENT_MODEL`(기본 claude-opus-5-5). 서버 쪽 거절 대체(fallbacks="default")를 켠다 — 거절되면 같은 요청을 다른 모델이 이어 받는다.
구조화 출력은 `output_config.format`(json_schema), 깊이는 `output_config.effort`. 시스템 프롬프트는 역할마다 고정이라 캐시한다.
테스트는 `set_client(fake)` 로 가짜 클라이언트를 끼운다(네트워크 없음).
"""

from __future__ import annotations

import json
import os
from typing import Any

FALLBACK_BETA = "server-side-fallback-2026-07-01"
_client: Any = None
_client_forced = False


class LlmUnavailable(RuntimeError):
    """키 · 인증 정보가 없다 → 501."""


class LlmError(RuntimeError):
    """호출 실패 · 거절 · 형식 오류 → 502."""


def model() -> str:
    return os.environ.get("MES_AGENT_MODEL") or "claude-opus-5-5"


def configured() -> bool:
    if _client_forced:
        return _client is not None
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_PROFILE"))


def set_client(client: Any) -> None:
    """테스트 · 다른 공급 경로용. None 을 주면 '미구성' 으로 고정."""
    global _client, _client_forced
    _client, _client_forced = client, True


def _get() -> Any:
    global _client
    if _client_forced:
        if _client is None:
            raise LlmUnavailable("LLM 미구성")
        return _client
    if not configured():
        raise LlmUnavailable("LLM 미구성 — .env 에 ANTHROPIC_API_KEY 를 넣는다")
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(max_retries=2, timeout=120.0)
    return _client


def _call(*, system: str, messages: list[dict], max_tokens: int, effort: str, schema: dict | None) -> tuple[str, str]:
    import anthropic

    client = _get()
    output_config: dict = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    try:
        resp = client.beta.messages.create(
            model=model(),
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config=output_config,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as exc:
        raise LlmError(f"인증 실패 — API 키 확인 ({exc.status_code})") from exc
    except anthropic.RateLimitError as exc:
        raise LlmError("요청 한도 초과 — 잠시 뒤 다시") from exc
    except anthropic.APIStatusError as exc:
        raise LlmError(f"LLM 호출 실패 ({exc.status_code})") from exc
    except anthropic.APIConnectionError as exc:
        raise LlmError("LLM 서버에 연결하지 못했다") from exc
    if resp.stop_reason == "refusal":
        raise LlmError("모델이 이 요청을 거절했다")
    if resp.stop_reason == "max_tokens":
        raise LlmError("응답이 길이 한도에서 잘렸다")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return text, getattr(resp, "model", model())


def json_call(*, system: str, user: str, schema: dict, effort: str = "low", max_tokens: int = 8000, history: list[dict] | None = None) -> tuple[dict, str]:
    text, used = _call(system=system, messages=[*(history or []), {"role": "user", "content": user}], max_tokens=max_tokens, effort=effort, schema=schema)
    try:
        return json.loads(text), used
    except json.JSONDecodeError as exc:
        raise LlmError("구조화 출력이 JSON 이 아니다") from exc


def text_call(*, system: str, user: str, effort: str = "low", max_tokens: int = 8000, history: list[dict] | None = None) -> tuple[str, str]:
    return _call(system=system, messages=[*(history or []), {"role": "user", "content": user}], max_tokens=max_tokens, effort=effort, schema=None)
