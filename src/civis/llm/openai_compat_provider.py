"""
OpenAI-compatible provider — speaks POST /v1/chat/completions.

One adapter covers every service that ships an OpenAI-compatible surface:
OpenAI, Groq, DeepSeek, Together, xAI, Fireworks, Mistral, and Ollama's
/v1 endpoint. The wire format is close enough that a single request/response
mapping works for all of them.

Auth: Bearer token in the Authorization header. The token is read from the
env var declared on the catalog entry (never stored in the file itself).
The httpx client is injectable so tests can plug MockTransport instead of
a real socket.

Streaming (fase D++): stream() posts with stream=true and reads SSE
``data: {...}`` lines. The stream terminates with a literal ``data: [DONE]``
sentinel per the OpenAI spec. To collect telemetry, we ask the server for
``stream_options.include_usage=true`` so the final chunk carries a full
``usage`` block. Providers that don't honour this option (some OSS
implementations) simply produce zeros in the final LLMResponse — content
is the same either way.
"""

import json
import os
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

# Standard OpenAI-compatible chat endpoint. Every hosted service that claims
# compatibility exposes exactly this path relative to their base URL.
CHAT_ENDPOINT = "/chat/completions"


class OpenAICompatProvider(LLMProvider):
    """Concrete provider hitting any OpenAI-compatible /v1/chat/completions."""

    def __init__(
        self,
        entry: ModelEntry,
        client: httpx.Client | None = None,
    ) -> None:
        if entry.provider != ProviderKind.OPENAI_COMPAT:
            raise ValueError(
                f"OpenAICompatProvider requires an OPENAI_COMPAT entry, "
                f"got {entry.provider}."
            )
        self._entry = entry
        # Injectable client for tests. In production we build a default
        # client that carries the Bearer token from the env var declared on
        # the catalog entry — resolving now (not on first request) means an
        # unset key crashes at startup, not mid-session.
        if client is not None:
            self._client = client
        else:
            api_key = self._resolve_api_key()
            self._client = httpx.Client(
                base_url=entry.base_url,
                timeout=entry.request_timeout_s,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )

    @property
    def name(self) -> str:
        return f"openai_compat:{self._entry.model_id}"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        # OpenAI-compatible wire format: model + messages list. Non-streaming
        # keeps complete() blocking, which is what the judge and adversarial
        # battery rely on. The streaming path lives in stream().
        payload = {
            "model": self._entry.model_id,
            "messages": [m.model_dump() for m in messages],
            "stream": False,
        }

        start = time.perf_counter()
        response = self._client.post(CHAT_ENDPOINT, json=payload)
        response.raise_for_status()
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        data = response.json()
        return LLMResponse(
            content=self._extract_text(data),
            # usage is optional in some OpenAI-compatible responses (Ollama's
            # /v1 omits it entirely). Defaulting to 0 keeps telemetry alive.
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
            latency_ms=elapsed_ms,
            provider_name=self.name,
        )

    def stream(self, messages: list[LLMMessage]) -> Iterator[LLMStreamChunk]:
        """
        Native SSE streaming for OpenAI-compatible chat completions.

        Wire format: repeated ``data: {json}`` lines terminated by a literal
        ``data: [DONE]`` sentinel. Each JSON chunk shape (per OpenAI spec):

            {"choices": [{"delta": {"content": "<piece>"}, ...}], ...}

        The final chunk carries an empty delta and (when
        stream_options.include_usage is honoured by the server) a top-level
        ``usage`` block with prompt_tokens / completion_tokens. Providers
        that ignore include_usage simply emit no usage — the final
        LLMResponse then reports zero tokens (content is still complete).
        """
        payload = {
            "model": self._entry.model_id,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
            # Ask compliant servers to attach the final usage block. Servers
            # that don't recognise this option just ignore it — no crash,
            # only zeros in telemetry.
            "stream_options": {"include_usage": True},
        }

        content_parts: list[str] = []
        input_tokens = 0
        output_tokens = 0

        start = time.perf_counter()
        with self._client.stream(
            "POST", CHAT_ENDPOINT, json=payload
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line[len("data:"):].strip()
                if not raw:
                    continue
                if raw == "[DONE]":
                    # OpenAI's explicit stream terminator; nothing to parse.
                    break
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    # Malformed line (rare on real servers; some proxies
                    # inject SSE keep-alives). Skip rather than abort.
                    continue

                # Content deltas live under choices[0].delta.content. The
                # very first chunk usually has an empty delta ({"role":
                # "assistant"}) — skip empty strings so the UI doesn't get
                # a no-op yield.
                choices = chunk.get("choices", []) or []
                if choices:
                    delta_obj = choices[0].get("delta", {}) or {}
                    piece = delta_obj.get("content") or ""
                    if piece:
                        content_parts.append(piece)
                        yield LLMStreamChunk(
                            content_delta=piece,
                            is_final=False,
                        )

                # The usage block appears on the terminal chunk when the
                # server honours stream_options.include_usage. Capture it
                # whenever we see it — never override a real value with 0.
                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    input_tokens = usage.get("prompt_tokens", input_tokens)
                    output_tokens = usage.get(
                        "completion_tokens", output_tokens
                    )

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

    # ---- helpers ----------------------------------------------------------

    def _resolve_api_key(self) -> str:
        """Read the API key from the env var declared on the catalog entry."""
        env_name = self._entry.api_key_env
        if not env_name:
            raise ValueError(
                "OPENAI_COMPAT entry is missing 'api_key_env'; "
                "the Pydantic validator should have caught this earlier."
            )
        api_key = os.environ.get(env_name)
        if not api_key:
            raise RuntimeError(
                f"Environment variable '{env_name}' is unset. "
                f"Export it before running (e.g. `export {env_name}=sk-...`)."
            )
        return api_key

    @staticmethod
    def _extract_text(data: dict) -> str:
        """
        Read the assistant message content from the first choice. Every
        OpenAI-compatible service returns choices[0].message.content;
        missing values default to '' so we never KeyError on a malformed
        response — the caller sees empty content and can retry.
        """
        choices = data.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return message.get("content", "") or ""
