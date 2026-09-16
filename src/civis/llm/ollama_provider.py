"""
Ollama provider — speaks Ollama's /api/chat over HTTP.

Ollama's message format is close to OpenAI's: a list of role+content pairs
in, a single assistant message out. Token counts (prompt_eval_count,
eval_count) come back in the response envelope, so M4 telemetry is
"free" — no separate counter step needed.

The httpx client is injectable so tests can plug a MockTransport instead
of a real socket.

Streaming (fase D++): stream() posts with stream=true and consumes the
response as JSON-lines (one complete JSON object per line). Each line
carries either a partial delta (done=false) or the sentinel with full
telemetry (done=true). We aggregate the deltas and build one LLMResponse
on the sentinel — same fields as complete() so downstream consumers
(TurnResult, telemetry sidecar) don't care which entry point was used.
"""

import json
import time
from collections.abc import Iterator

import httpx

from civis.config.models import ModelEntry, ProviderKind
from civis.llm.provider import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMStreamChunk,
)

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
            # Non-streaming keeps complete() simple and blocking — that's what
            # the judge, run_study_v2 and the adversarial battery expect.
            # The streaming path lives in stream() and never touches this.
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

    def stream(self, messages: list[LLMMessage]) -> Iterator[LLMStreamChunk]:
        """
        Native token streaming via Ollama's JSON-lines format.

        Ollama responds with one JSON object per line while stream=true.
        Non-final lines have shape:
            {"message": {"content": "<piece>"}, "done": false}
        The sentinel line has:
            {"message": {"content": ""}, "done": true,
             "prompt_eval_count": <int>, "eval_count": <int>, ...}
        We yield one LLMStreamChunk per non-empty piece plus one final
        LLMStreamChunk carrying an aggregated LLMResponse with telemetry.
        """
        payload = {
            "model": self._entry.model_id,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        }

        # Collected content pieces — joined once on the sentinel to build
        # the final LLMResponse. Empty string is a legal delta (Ollama may
        # emit an empty content on the sentinel) but we skip yielding it
        # to avoid a stray no-op chunk for the UI.
        content_parts: list[str] = []
        input_tokens = 0
        output_tokens = 0

        start = time.perf_counter()
        with self._client.stream(
            "POST", CHAT_ENDPOINT, json=payload
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                # iter_lines strips the newline; empty lines can slip in
                # between chunks on some proxies — skip them defensively.
                if not line:
                    continue
                data = json.loads(line)
                delta = data.get("message", {}).get("content", "") or ""
                done = bool(data.get("done", False))

                if delta:
                    content_parts.append(delta)
                    yield LLMStreamChunk(
                        content_delta=delta,
                        is_final=False,
                    )

                if done:
                    # Capture telemetry from the sentinel. Missing counters
                    # default to 0 (matches complete()'s tolerance).
                    input_tokens = data.get("prompt_eval_count", 0)
                    output_tokens = data.get("eval_count", 0)
                    # Do not break here — iter_lines will return next; but
                    # in practice done=true is the last line and the loop
                    # exits naturally.
                    break

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        final_response = LLMResponse(
            content="".join(content_parts),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
            provider_name=self.name,
        )
        yield LLMStreamChunk(
            content_delta="",
            is_final=True,
            final_response=final_response,
        )
