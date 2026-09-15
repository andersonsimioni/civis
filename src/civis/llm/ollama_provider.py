"""
Ollama provider — speaks Ollama's /api/chat over HTTP.

Ollama's message format is close to OpenAI's: a list of role+content pairs
in, a single assistant message out. Token counts (prompt_eval_count,
eval_count) come back in the response envelope, so M4 telemetry is
"free" — no separate counter step needed.

The httpx client is injectable so tests can plug a MockTransport instead
of a real socket.
"""

import time

import httpx

from civis.config.models import ModelEntry, ProviderKind
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse

# Ollama's /api/chat endpoint. /v1/chat/completions also exists (OpenAI-
# compat mode) but /api/chat gives us richer telemetry (eval durations).
CHAT_ENDPOINT = "/api/chat"


class OllamaProvider(LLMProvider):
    """Concrete provider hitting a local Ollama server via /api/chat."""

    def __init__(
        self,
        entry: ModelEntry,
        client: httpx.Client | None = None,
    ) -> None:
        if entry.provider != ProviderKind.OLLAMA:
            raise ValueError(
                f"OllamaProvider requires an OLLAMA entry, got {entry.provider}."
            )
        self._entry = entry
        # Injectable client for tests. The default client uses the entry's
        # base_url and timeout; production code paths never pass `client`.
        self._client = client or httpx.Client(
            base_url=entry.base_url,
            timeout=entry.request_timeout_s,
        )

    @property
    def name(self) -> str:
        return f"ollama:{self._entry.model_id}"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        payload = {
            "model": self._entry.model_id,
            "messages": [m.model_dump() for m in messages],
            # Non-streaming keeps the MVP simple. Streaming is a week-6 concern
            # (UI needs the token feed to display "..." while the model thinks).
            "stream": False,
        }

        start = time.perf_counter()
        response = self._client.post(CHAT_ENDPOINT, json=payload)
        response.raise_for_status()
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        data = response.json()
        return LLMResponse(
            content=data["message"]["content"],
            # Ollama may omit counters on very short exchanges — default to 0
            # so downstream telemetry never sees KeyError.
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            latency_ms=elapsed_ms,
            provider_name=self.name,
        )
