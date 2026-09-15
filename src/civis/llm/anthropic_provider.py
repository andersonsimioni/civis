"""
Anthropic Claude provider — distinct wire format from OpenAI, so it gets
its own module rather than living inside the OpenAI-compat adapter.

STUB in week 2. Full implementation lands in week 3 alongside the
OpenAI-compat adapter. Same rationale: the catalog can carry ANTHROPIC
entries and the factory dispatch compiles, but calling complete() fails
loudly rather than silently returning a fake response.
"""

from civis.config.models import ModelEntry, ProviderKind
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    """Stub for Anthropic Claude via the official SDK. Filled in week 3."""

    def __init__(self, entry: ModelEntry) -> None:
        if entry.provider != ProviderKind.ANTHROPIC:
            raise ValueError(
                f"AnthropicProvider requires an ANTHROPIC entry, got {entry.provider}."
            )
        self._entry = entry

    @property
    def name(self) -> str:
        return f"anthropic:{self._entry.model_id}"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        raise NotImplementedError(
            "Anthropic provider lands in week 3. "
            "For now, configure an OLLAMA entry."
        )
