"""
Anthropic Claude provider — speaks the /v1/messages API over HTTP.

Anthropic's wire format differs from OpenAI's in three material ways:
    - System prompts travel in a top-level "system" field, not as a message.
    - Messages carry only "user" and "assistant" roles.
    - The response envelope names token counters "input_tokens" / "output_tokens"
      inside a nested "usage" object.

We stay on raw httpx (no SDK dependency) to mirror the Ollama provider's
pattern and keep the dependency surface small. The httpx client is
injectable so tests can plug a MockTransport in place of a real socket.

Streaming (fase D++): stream() posts with stream=true and reads Server-Sent
Events line-by-line. Each event has an ``event: <type>`` line and a
``data: {...}`` line; we care about ``content_block_delta`` (partial text)
and ``message_delta`` (final usage). The reference doc:
https://docs.anthropic.com/en/api/messages-streaming
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

# Anthropic's Messages endpoint. Version header is required and pinned so a
# breaking change in the API surface fails loudly rather than silently.
API_BASE_URL = "https://api.anthropic.com"
MESSAGES_ENDPOINT = "/v1/messages"
API_VERSION_HEADER = "2023-06-01"

# Default max output tokens. Required by the Anthropic API; kept generous
# so verdicts with full rationale + citations don't get truncated.
DEFAULT_MAX_OUTPUT_TOKENS = 4096


class AnthropicProvider(LLMProvider):
    """Concrete provider hitting the Anthropic Messages API over HTTP."""

    def __init__(
        self,
        entry: ModelEntry,
        client: httpx.Client | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> None:
        if entry.provider != ProviderKind.ANTHROPIC:
            raise ValueError(
                f"AnthropicProvider requires an ANTHROPIC entry, got {entry.provider}."
            )
        self._entry = entry
        self._max_output_tokens = max_output_tokens
        # Injectable client for tests. Production callers omit `client`;
        # in that case we resolve the API key from the env var declared on
        # the catalog entry and attach the required auth headers up front.
        if client is not None:
            self._client = client
        else:
            api_key = self._resolve_api_key()
            self._client = httpx.Client(
                base_url=entry.base_url or API_BASE_URL,
                timeout=entry.request_timeout_s,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": API_VERSION_HEADER,
                    "content-type": "application/json",
                },
            )

    @property
    def name(self) -> str:
        return f"anthropic:{self._entry.model_id}"

    def complete(self, messages: list[LLMMessage]) -> LLMResponse:
        # Anthropic wants system prompts in a top-level field. We collect all
        # system messages (joined with two newlines) and strip them from the
        # message list. Keeps callers free to pass system+user+assistant
        # in the natural order without knowing this API quirk.
        system_prompt, chat_messages = self._split_system_prompt(messages)

        payload: dict = {
            "model": self._entry.model_id,
            "max_tokens": self._max_output_tokens,
            "messages": [m.model_dump() for m in chat_messages],
        }
        if system_prompt:
            payload["system"] = system_prompt

        start = time.perf_counter()
        response = self._client.post(MESSAGES_ENDPOINT, json=payload)
        response.raise_for_status()
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        data = response.json()
        return LLMResponse(
            content=self._extract_text(data),
            # Usage is nested under "usage" in Anthropic's response envelope.
            # Missing counters default to 0 so telemetry never crashes on a
            # degenerate response (matches OllamaProvider behavior).
            input_tokens=data.get("usage", {}).get("input_tokens", 0),
            output_tokens=data.get("usage", {}).get("output_tokens", 0),
            latency_ms=elapsed_ms,
            provider_name=self.name,
        )

    def stream(self, messages: list[LLMMessage]) -> Iterator[LLMStreamChunk]:
        """
        Native SSE streaming for Anthropic Messages.

        Wire format is Server-Sent Events: pairs of ``event: <type>`` /
        ``data: <json>`` lines separated by blank lines. We only need to
        parse the ``data:`` payloads because each one carries its own
        ``type`` field; the ``event:`` line is redundant with it.

        Types we care about:
            - content_block_delta: delta.text is a new text piece.
            - message_delta: usage carries final input/output_tokens.
            - message_stop: closes the stream (no payload we need).

        Other event types (message_start, content_block_start,
        content_block_stop, ping) are ignored — they carry structural
        markers we don't need to reconstruct the response.
        """
        system_prompt, chat_messages = self._split_system_prompt(messages)
        payload: dict = {
            "model": self._entry.model_id,
            "max_tokens": self._max_output_tokens,
            "messages": [m.model_dump() for m in chat_messages],
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        content_parts: list[str] = []
        input_tokens = 0
        output_tokens = 0

        start = time.perf_counter()
        with self._client.stream(
            "POST", MESSAGES_ENDPOINT, json=payload
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                # SSE separates events with blank lines and prefixes payload
                # with ``data: ``. We only parse data lines; event/ping/etc.
                # lines are ignored (the ``type`` inside the JSON tells us
                # everything we need).
                if not line or not line.startswith("data:"):
                    continue
                raw = line[len("data:"):].strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    # Defensive: some SSE proxies inject keep-alive comments.
                    # Silently skip malformed data lines rather than aborting
                    # the stream — the sentinel below still runs.
                    continue

                etype = event.get("type", "")
                if etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        piece = delta.get("text", "") or ""
                        if piece:
                            content_parts.append(piece)
                            yield LLMStreamChunk(
                                content_delta=piece,
                                is_final=False,
                            )
                elif etype == "message_delta":
                    usage = event.get("usage", {})
                    # Anthropic streams usage in the message_delta event.
                    # Non-streaming complete() also reads input/output_tokens
                    # from a "usage" block, but the streaming envelope
                    # sometimes only carries output_tokens here — keep both
                    # optional so we don't KeyError on partial updates.
                    if "input_tokens" in usage:
                        input_tokens = usage["input_tokens"]
                    if "output_tokens" in usage:
                        output_tokens = usage["output_tokens"]
                elif etype == "message_start":
                    # Some deployments push initial usage.input_tokens here
                    # (input is known before generation starts). Grab it if
                    # present so we don't lose it when message_delta only
                    # updates output_tokens.
                    message = event.get("message", {})
                    usage = message.get("usage", {})
                    if "input_tokens" in usage:
                        input_tokens = usage["input_tokens"]
                # message_stop / others: no-op; loop exits when iter_lines
                # drains.

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
        """
        Read the API key from the env var declared on the catalog entry.
        Fails loudly if the env var is unset — we prefer a clear crash at
        provider construction over a mysterious 401 mid-session.
        """
        env_name = self._entry.api_key_env
        if not env_name:
            raise ValueError(
                "Anthropic catalog entry is missing 'api_key_env'; "
                "the Pydantic validator should have caught this earlier."
            )
        api_key = os.environ.get(env_name)
        if not api_key:
            raise RuntimeError(
                f"Environment variable '{env_name}' is unset. "
                f"Export it before running (e.g. `export {env_name}=sk-ant-...`)."
            )
        return api_key

    @staticmethod
    def _split_system_prompt(
        messages: list[LLMMessage],
    ) -> tuple[str | None, list[LLMMessage]]:
        """Return (joined_system_prompt_or_None, non_system_messages)."""
        system_parts = [m.content for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]
        system_prompt = "\n\n".join(system_parts) if system_parts else None
        return system_prompt, non_system

    @staticmethod
    def _extract_text(data: dict) -> str:
        """
        Anthropic returns a "content" list of blocks. Text blocks have
        type='text' and a 'text' field. We concatenate all text blocks in
        order — non-text blocks (tool_use etc.) are not used in this MVP,
        so ignoring them is safe.
        """
        blocks = data.get("content", [])
        return "".join(
            block.get("text", "")
            for block in blocks
            if block.get("type") == "text"
        )
