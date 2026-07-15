"""LLM client abstraction.

`LLMClient` is a tiny protocol so the generation service can be tested
without ever making a network call (see tests/test_llm_validation.py, which
injects a FakeLLMClient). `OpenAICompatibleClient` talks to any
OpenAI-chat-completions-compatible endpoint — Groq, OpenRouter, and OpenAI
itself all satisfy this, which is why swapping providers is just an env var
change (LLM_BASE_URL / LLM_MODEL / LLM_API_KEY), not a code change.
"""
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.exceptions import LLMGenerationError


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = base_url or settings.llm_base_url
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout_seconds

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMGenerationError(
                "No LLM API key configured (set LLM_API_KEY in .env). "
                "See .env.example for provider setup."
            )
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMGenerationError(f"LLM provider request failed: {exc}") from exc

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMGenerationError(f"Unexpected LLM response shape: {data}") from exc


def get_default_client() -> LLMClient:
    return OpenAICompatibleClient()
