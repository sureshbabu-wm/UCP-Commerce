"""OpenAI adapter. Uses Chat Completions with JSON response format.

Provider-agnostic at the orchestration level: the only OpenAI-specific bit lives here.
"""

from __future__ import annotations

from .base import LLMAdapter, LLMError


class OpenAIAdapter(LLMAdapter):
    provider = "openai"

    @property
    def default_model(self) -> str:
        return "gpt-4o"

    def _complete(self, messages: list[dict]) -> str:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMError("openai package not installed; `pip install openai`") from e

        client = OpenAI(api_key=self.api_key)
        try:
            resp = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except Exception as e:  # openai.OpenAIError and friends
            from openai import OpenAIError

            if isinstance(e, OpenAIError):
                raise LLMError(f"OpenAI request failed: {e}") from e
            raise
        return resp.choices[0].message.content or ""
