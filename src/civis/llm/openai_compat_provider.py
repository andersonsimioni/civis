"""
OpenAI-compatible provider — one adapter for services that speak
/v1/chat/completions: OpenAI, Groq, DeepSeek, Together, xAI, Fireworks,
Mistral, and Ollama's /v1 endpoint.

STUB in week 2. Full implementation lands in week 3 (once the Ollama
provider proves the shape of the abstraction). Left as NotImplementedError
so the catalog can hold OPENAI_COMPAT entries and the factory dispatch
compiles, but any actual completion call fails loudly with a clear message.
"""

from civis.config.models import ModelEntry, ProviderKind
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse


class OpenAICompatProvider(LLMProvider):
    """Stub for services speaking OpenAI Chat Completions. Filled in week 3."""

    def __init__(self, entry: ModelEntry) -> None:
        if entry.provider != ProviderKind.OPENAI_COMPAT:
            raise ValueError(
                f"OpenAICompatProvider requires an OPENAI_COMPAT entry, "
                f"got {entry.provider}."
            )
        self._entry = entry

    @property
    def name(self) -> str:
        return f"openai_compat:{self._entry.model_id}"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        raise NotImplementedError(
            "OpenAI-compatible provider lands in week 3. "
            "For now, configure an OLLAMA entry."
        )
