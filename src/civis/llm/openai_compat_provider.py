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
"""

import os
import time

import httpx

from civis.config.models import ModelEntry, ProviderKind
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse

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
        # keeps the MVP simple; streaming is a UI concern (fase D).
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
