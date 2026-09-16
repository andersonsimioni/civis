"""
Abstract LLM provider interface.

Concrete providers land in week 2:
    - claude.py   Primary provider, via the Anthropic API.
    - ollama.py   Local fallback, Llama 3.1 8B, for smoke-test resilience.

Design rule (goal O3): the judge and the persona must NEVER share a provider.
Provider selection happens outside this interface (in the session orchestrator),
so this module only defines the contract.

Streaming (fase D++): providers may override ``stream()`` to emit tokens as
they arrive. The base class ships a default implementation that wraps
``complete()`` in a single final chunk — this keeps every existing subclass
(mocks, judges, adversarial recorders) working without touching them. Only
the three real providers (Ollama, Anthropic, OpenAI-compat) override for
native SSE / JSON-lines streaming.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, Field

MessageRole = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    """One message in a chat-style conversation with an LLM."""

    role: MessageRole
    content: str


class LLMResponse(BaseModel):
    """Text response from an LLM plus basic telemetry (used for M4 metrics)."""

    content: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    provider_name: str


class LLMStreamChunk(BaseModel):
    """
    One chunk emitted by ``LLMProvider.stream()``.

    - ``content_delta``: newly-arrived text since the previous chunk (may be
      empty on the final sentinel chunk).
    - ``is_final``: True on the last chunk of the stream. When True,
      ``final_response`` MUST be populated with the aggregated response and
      full telemetry (input/output tokens, latency, provider_name) — this is
      how the orchestrator reconstructs a ``TurnResult`` after the stream
      drains.
    - ``final_response``: only meaningful when ``is_final`` is True.
    """

    content_delta: str
    is_final: bool
    final_response: LLMResponse | None = None


class LLMProvider(ABC):
    """
    Abstract provider. Concrete implementations own their auth, retry policy,
    and telemetry emission.
    """

    @abstractmethod
    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        """Send messages and return a completion. Blocking; retries are internal."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider name (e.g. 'claude-3-5-sonnet', 'ollama-llama3.1-8b')."""

    def stream(self, messages: list[LLMMessage]) -> Iterator[LLMStreamChunk]:
        """
        Yield the response one chunk at a time.

        Default implementation: call ``complete()``, emit the full text as a
        single non-final chunk (so ``st.write_stream`` still sees content),
        then emit a final sentinel chunk carrying the full ``LLMResponse``.
        This lets every scripted mock / test double keep working without
        implementing SSE parsing — real providers override for native
        token-by-token streaming.

        Callers must fully drain the iterator; the final chunk is where the
        aggregated ``LLMResponse`` (with telemetry) shows up.
        """
        response = self.complete(messages)
        # Emit the whole content as one partial chunk so downstream widgets
        # (Streamlit's st.write_stream) get something to render before the
        # sentinel. An empty content on the partial chunk is legal but ugly;
        # gate on truthiness to avoid a stray empty yield.
        if response.content:
            yield LLMStreamChunk(
                content_delta=response.content,
                is_final=False,
            )
        yield LLMStreamChunk(
            content_delta="",
            is_final=True,
            final_response=response,
        )
