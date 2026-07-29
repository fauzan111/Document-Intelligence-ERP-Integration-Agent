"""Provider-agnostic LLM client.

Enterprises in the EU care about vendor lock-in during procurement, so the
foundation never imports a provider SDK directly outside this module. Swap
providers via the ``LLM_PROVIDER`` env var; the rest of the codebase depends
only on :class:`LLMClient`.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import Settings, get_settings


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    # Hash of the prompt so audit logs can prove *what* was sent without
    # storing (potentially sensitive / PII) raw inputs verbatim.
    prompt_sha256: str


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, *, system: str, prompt: str, max_tokens: int) -> LLMResponse: ...


class AnthropicProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> LLMResponse:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if block.type == "text")
        return LLMResponse(
            text=text,
            model=self._model,
            provider="anthropic",
            prompt_sha256=_sha256(system + prompt),
        )


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            model=self._model,
            provider="openai",
            prompt_sha256=_sha256(system + prompt),
        )


class LLMClient:
    """The only LLM entry point the rest of the app should use."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._provider = self._build_provider(self._settings)

    @staticmethod
    def _build_provider(settings: Settings) -> LLMProvider:
        if settings.llm_provider == "anthropic":
            return AnthropicProvider(settings)
        if settings.llm_provider == "openai":
            return OpenAIProvider(settings)
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

    def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> LLMResponse:
        return self._provider.complete(system=system, prompt=prompt, max_tokens=max_tokens)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
