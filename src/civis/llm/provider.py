"""
Abstract LLM provider interface.

Concrete providers land in week 2:
    - claude.py   Primary provider, via the Anthropic API.
    - ollama.py   Local fallback, Llama 3.1 8B, for smoke-test resilience.

Design rule (goal O3): the judge and the persona must NEVER share a provider.
Provider selection happens outside this interface (in the session orchestrator),
so this module only defines the contract.
"""

from abc import ABC, abstractmethod
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
