"""LLM provider adapters (provider-agnostic interface)."""

from .base import LLMAdapter, LLMError
from .openai_adapter import OpenAIAdapter

_REGISTRY: dict[str, type[LLMAdapter]] = {
    "openai": OpenAIAdapter,
}


def get_adapter(provider: str, api_key: str, **kw) -> LLMAdapter:
    try:
        cls = _REGISTRY[provider]
    except KeyError:
        raise LLMError(
            f"Unsupported provider {provider!r}. Available: {sorted(_REGISTRY)}"
        ) from None
    return cls(api_key=api_key, **kw)


def register_adapter(provider: str, cls: type[LLMAdapter]) -> None:
    """Register an adapter (used by tests to plug a mock, and by future providers)."""
    _REGISTRY[provider] = cls
