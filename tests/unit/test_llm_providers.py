"""
LLM provider tests.

Every real provider is exercised via httpx.MockTransport so tests never
need a live API endpoint. We assert on the wire format the provider
sends (request-shaping), on the parsing of a canned response, and on
the telemetry (token counts, latency, provider name). The factory is
checked for correct dispatch by ProviderKind.
"""

import json

import httpx
import pytest

from civis.config.models import ModelEntry, ProviderKind
from civis.llm.anthropic_provider import AnthropicProvider
from civis.llm.factory import build_provider
from civis.llm.ollama_provider import OllamaProvider
from civis.llm.openai_compat_provider import OpenAICompatProvider
from civis.llm.provider import LLMMessage, LLMProvider, LLMResponse, LLMStreamChunk

# ---- fixtures --------------------------------------------------------------

def _ollama_entry() -> ModelEntry:
    return ModelEntry(
        provider=ProviderKind.OLLAMA,
        model_id="qwen2.5:7b-instruct-q4_K_M",
        base_url="http://localhost:11434",
    )


def _openai_compat_entry() -> ModelEntry:
    return ModelEntry(
        provider=ProviderKind.OPENAI_COMPAT,
        model_id="gpt-4o",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    )


def _anthropic_entry() -> ModelEntry:
    return ModelEntry(
        provider=ProviderKind.ANTHROPIC,
        model_id="claude-sonnet-4-6",
        api_key_env="ANTHROPIC_API_KEY",
    )


# ---- Ollama provider -------------------------------------------------------

def test_ollama_provider_posts_to_api_chat_and_maps_response():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # Record what the provider actually sent so we can assert on it.
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b-instruct-q4_K_M",
                "message": {"role": "assistant", "content": "Olá!"},
                "prompt_eval_count": 42,
                "eval_count": 15,
                "done": True,
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://localhost:11434",
    )
    provider = OllamaProvider(_ollama_entry(), client=client)

    response = provider.complete([
        LLMMessage(role="system", content="Você é uma cidadã confusa."),
        LLMMessage(role="user", content="Bom dia!"),
    ])

    assert captured["path"] == "/api/chat"
    assert captured["body"]["model"] == "qwen2.5:7b-instruct-q4_K_M"
    assert captured["body"]["stream"] is False
    assert len(captured["body"]["messages"]) == 2

    assert response.content == "Olá!"
    assert response.input_tokens == 42
    assert response.output_tokens == 15
    assert response.latency_ms >= 0
    assert response.provider_name == "ollama:qwen2.5:7b-instruct-q4_K_M"


def test_ollama_provider_tolerates_missing_token_counts():
    """
    Very short exchanges sometimes omit prompt_eval_count. The provider must
    default to 0 rather than KeyError, so telemetry pipelines never crash on
    a degenerate response.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "ok"}, "done": True},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://localhost:11434",
    )
    provider = OllamaProvider(_ollama_entry(), client=client)

    response = provider.complete([LLMMessage(role="user", content="oi")])

    assert response.input_tokens == 0
    assert response.output_tokens == 0


def test_ollama_provider_rejects_wrong_entry_kind():
    with pytest.raises(ValueError, match="OLLAMA"):
        OllamaProvider(_openai_compat_entry())


# ---- OpenAI-compat provider -----------------------------------------------

def test_openai_compat_provider_posts_to_chat_completions_and_maps_response():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-abc123",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 3,
                    "total_tokens": 15,
                },
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
        headers={"Authorization": "Bearer sk-test-abc"},
    )
    provider = OpenAICompatProvider(_openai_compat_entry(), client=client)

    response = provider.complete([
        LLMMessage(role="system", content="You are helpful."),
        LLMMessage(role="user", content="Hi"),
    ])

    assert captured["path"] == "/v1/chat/completions"
    assert captured["body"]["model"] == "gpt-4o"
    assert captured["body"]["stream"] is False
    assert len(captured["body"]["messages"]) == 2
    # The injected client carries the Bearer header — in production the
    # provider builds this itself from api_key_env.
    assert captured["auth"] == "Bearer sk-test-abc"

    assert response.content == "Hello!"
    assert response.input_tokens == 12
    assert response.output_tokens == 3
    assert response.latency_ms >= 0
    assert response.provider_name == "openai_compat:gpt-4o"


def test_openai_compat_provider_tolerates_missing_usage_block():
    """Ollama's /v1 endpoint often omits the usage block entirely."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}}
                ],
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    )
    provider = OpenAICompatProvider(_openai_compat_entry(), client=client)

    response = provider.complete([LLMMessage(role="user", content="oi")])

    assert response.content == "ok"
    assert response.input_tokens == 0
    assert response.output_tokens == 0


def test_openai_compat_provider_tolerates_empty_choices():
    """Malformed response with no choices — return empty content, don't crash."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    )
    provider = OpenAICompatProvider(_openai_compat_entry(), client=client)
    response = provider.complete([LLMMessage(role="user", content="oi")])
    assert response.content == ""


def test_openai_compat_provider_rejects_wrong_entry_kind():
    with pytest.raises(ValueError, match="OPENAI_COMPAT"):
        OpenAICompatProvider(_ollama_entry())


def test_openai_compat_provider_reads_api_key_from_env(monkeypatch):
    """Auto-built client resolves the key from the env var declared on the entry."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-xyz")
    # Constructing without an injected client must succeed once the env var
    # is set. We can't cheaply exercise the outbound request here without a
    # mock transport, so this test just proves construction works.
    provider = OpenAICompatProvider(_openai_compat_entry())
    assert provider.name == "openai_compat:gpt-4o"


def test_openai_compat_provider_fails_loudly_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAICompatProvider(_openai_compat_entry())


# ---- Anthropic provider ---------------------------------------------------

def test_anthropic_provider_posts_to_messages_and_maps_response():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        captured["version_header"] = request.headers.get("anthropic-version")
        captured["api_key_header"] = request.headers.get("x-api-key")
        return httpx.Response(
            200,
            json={
                "id": "msg_abc",
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Bom dia. "},
                    {"type": "text", "text": "Em que posso ajudar?"},
                ],
                "model": "claude-sonnet-4-6",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 25, "output_tokens": 8},
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
        headers={
            "x-api-key": "sk-ant-test",
            "anthropic-version": "2023-06-01",
        },
    )
    provider = AnthropicProvider(_anthropic_entry(), client=client)

    response = provider.complete([
        LLMMessage(role="system", content="Você é uma cidadã confusa."),
        LLMMessage(role="system", content="Fale em pt-BR."),
        LLMMessage(role="user", content="Bom dia!"),
    ])

    assert captured["path"] == "/v1/messages"
    assert captured["body"]["model"] == "claude-sonnet-4-6"
    # System messages must be lifted out of the message list and joined.
    assert captured["body"]["system"] == "Você é uma cidadã confusa.\n\nFale em pt-BR."
    assert len(captured["body"]["messages"]) == 1
    assert captured["body"]["messages"][0]["role"] == "user"
    assert "max_tokens" in captured["body"]
    # Headers carried through the injected client.
    assert captured["api_key_header"] == "sk-ant-test"
    assert captured["version_header"] == "2023-06-01"

    # Multiple text blocks are concatenated in order.
    assert response.content == "Bom dia. Em que posso ajudar?"
    assert response.input_tokens == 25
    assert response.output_tokens == 8
    assert response.latency_ms >= 0
    assert response.provider_name == "anthropic:claude-sonnet-4-6"


def test_anthropic_provider_omits_system_when_no_system_message():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    provider = AnthropicProvider(_anthropic_entry(), client=client)
    provider.complete([LLMMessage(role="user", content="oi")])

    assert "system" not in captured["body"]


def test_anthropic_provider_tolerates_missing_usage_block():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "ok"}]},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    provider = AnthropicProvider(_anthropic_entry(), client=client)
    response = provider.complete([LLMMessage(role="user", content="oi")])

    assert response.input_tokens == 0
    assert response.output_tokens == 0
    assert response.content == "ok"


def test_anthropic_provider_ignores_non_text_content_blocks():
    """Tool-use blocks in the response are silently skipped in the MVP."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "tool_use", "id": "tool_1", "name": "search"},
                    {"type": "text", "text": "world"},
                ],
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    provider = AnthropicProvider(_anthropic_entry(), client=client)
    response = provider.complete([LLMMessage(role="user", content="hi")])
    assert response.content == "Hello world"


def test_anthropic_provider_rejects_wrong_entry_kind():
    with pytest.raises(ValueError, match="ANTHROPIC"):
        AnthropicProvider(_ollama_entry())


def test_anthropic_provider_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-live-xyz")
    provider = AnthropicProvider(_anthropic_entry())
    assert provider.name == "anthropic:claude-sonnet-4-6"


def test_anthropic_provider_fails_loudly_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(_anthropic_entry())


# ---- Factory dispatch ------------------------------------------------------

def test_factory_dispatches_ollama():
    assert isinstance(build_provider(_ollama_entry()), OllamaProvider)


def test_factory_dispatches_openai_compat(monkeypatch):
    # Factory builds the real provider now, which resolves the API key at
    # construction — provide one via the env so the test doesn't crash.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert isinstance(build_provider(_openai_compat_entry()), OpenAICompatProvider)


def test_factory_dispatches_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert isinstance(build_provider(_anthropic_entry()), AnthropicProvider)


# ---------------------------------------------------------------------------
# Streaming (Fase D++)
# ---------------------------------------------------------------------------
#
# Every native streaming path is exercised by feeding the MockTransport
# a canned wire-format body (Ollama JSON-lines, Anthropic SSE, OpenAI-
# compat SSE) and asserting that stream() yields the expected token
# sequence plus a final LLMStreamChunk with populated telemetry. The
# default ABC implementation is covered via a tiny stub provider so we
# prove that mock/adversarial subclasses which never override stream()
# still emit chunks the orchestrator can consume.


def _ollama_stream_body() -> bytes:
    """Three partial chunks + one done=true sentinel with telemetry."""
    lines = [
        '{"model":"m","message":{"role":"assistant","content":"Ol"},"done":false}',
        '{"model":"m","message":{"role":"assistant","content":"á"},"done":false}',
        '{"model":"m","message":{"role":"assistant","content":", moço"},"done":false}',
        (
            '{"model":"m","message":{"role":"assistant","content":""},'
            '"done":true,"prompt_eval_count":17,"eval_count":4}'
        ),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_ollama_stream_yields_partial_tokens_then_final_chunk():
    """
    stream() must emit one LLMStreamChunk per non-empty content delta and
    exactly one final chunk carrying the aggregated LLMResponse. The
    partial chunks arrive in the order the server sent them — the UI
    concatenates them left-to-right to render token-by-token.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        # The provider must ask for streaming; otherwise Ollama returns a
        # single blob and our SSE-style consumer would parse a whole
        # response as one JSON line.
        assert payload["stream"] is True
        return httpx.Response(200, content=_ollama_stream_body())

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://localhost:11434",
    )
    provider = OllamaProvider(_ollama_entry(), client=client)

    chunks = list(provider.stream([LLMMessage(role="user", content="oi")]))
    partials = [c for c in chunks if not c.is_final]
    finals = [c for c in chunks if c.is_final]

    assert [c.content_delta for c in partials] == ["Ol", "á", ", moço"]
    assert len(finals) == 1


def test_ollama_stream_final_chunk_has_full_response_and_telemetry():
    """
    The final LLMStreamChunk exposes the aggregated content and the
    telemetry captured from the done=true sentinel (prompt_eval_count and
    eval_count map directly to input/output_tokens).
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ollama_stream_body())

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://localhost:11434",
    )
    provider = OllamaProvider(_ollama_entry(), client=client)

    chunks = list(provider.stream([LLMMessage(role="user", content="oi")]))
    final = chunks[-1]

    assert final.is_final is True
    assert final.final_response is not None
    assert final.final_response.content == "Olá, moço"
    assert final.final_response.input_tokens == 17
    assert final.final_response.output_tokens == 4
    assert final.final_response.provider_name == provider.name
    assert final.final_response.latency_ms >= 0


def _anthropic_stream_body() -> bytes:
    """A realistic SSE body with content_block_delta + message_delta.usage."""
    events = [
        'event: message_start',
        'data: {"type":"message_start","message":{"id":"m1","usage":{"input_tokens":12}}}',
        '',
        'event: content_block_start',
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
        '',
        'event: content_block_delta',
        (
            'data: {"type":"content_block_delta","index":0,'
            '"delta":{"type":"text_delta","text":"Bom "}}'
        ),
        '',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"dia"}}',
        '',
        'event: content_block_delta',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"!"}}',
        '',
        'event: message_delta',
        (
            'data: {"type":"message_delta",'
            '"delta":{"stop_reason":"end_turn"},'
            '"usage":{"output_tokens":3}}'
        ),
        '',
        'event: message_stop',
        'data: {"type":"message_stop"}',
        '',
    ]
    return ("\n".join(events) + "\n").encode("utf-8")


def test_anthropic_stream_parses_sse_content_block_deltas():
    """Every text_delta becomes one partial LLMStreamChunk, in wire order."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        # System messages must still be lifted out of the message list.
        assert payload.get("system") is None or isinstance(payload["system"], str)
        return httpx.Response(200, content=_anthropic_stream_body())

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    provider = AnthropicProvider(_anthropic_entry(), client=client)

    chunks = list(provider.stream([LLMMessage(role="user", content="oi")]))
    partials = [c.content_delta for c in chunks if not c.is_final]
    assert partials == ["Bom ", "dia", "!"]


def test_anthropic_stream_extracts_usage_from_message_delta():
    """
    Anthropic streams usage across two events: message_start carries
    input_tokens (the prompt is known before the model generates) and
    message_delta closes with output_tokens. The final LLMStreamChunk
    must merge both.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_anthropic_stream_body())

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    provider = AnthropicProvider(_anthropic_entry(), client=client)

    chunks = list(provider.stream([LLMMessage(role="user", content="oi")]))
    final = chunks[-1]

    assert final.is_final is True
    assert final.final_response is not None
    assert final.final_response.content == "Bom dia!"
    assert final.final_response.input_tokens == 12
    assert final.final_response.output_tokens == 3
    assert final.final_response.provider_name == provider.name


def _openai_compat_stream_body() -> bytes:
    """OpenAI-compat SSE with content deltas, final usage, and [DONE]."""
    events = [
        'data: {"choices":[{"index":0,"delta":{"role":"assistant"}}]}',
        '',
        'data: {"choices":[{"index":0,"delta":{"content":"Hello"}}]}',
        '',
        'data: {"choices":[{"index":0,"delta":{"content":" world"}}]}',
        '',
        'data: {"choices":[{"index":0,"delta":{"content":"!"}}]}',
        '',
        (
            'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":7,"completion_tokens":3}}'
        ),
        '',
        'data: [DONE]',
        '',
    ]
    return ("\n".join(events) + "\n").encode("utf-8")


def test_openai_compat_stream_parses_data_lines_and_usage():
    """
    stream() must extract choices[0].delta.content for each non-empty
    piece and read the final usage block (prompt_tokens /
    completion_tokens) into the LLMResponse. The literal [DONE] sentinel
    ends the loop without parse errors.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        # include_usage is what asks compliant servers to emit the usage
        # block on the terminal chunk — required to keep telemetry alive.
        assert payload["stream_options"]["include_usage"] is True
        return httpx.Response(200, content=_openai_compat_stream_body())

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.openai.com/v1",
    )
    provider = OpenAICompatProvider(_openai_compat_entry(), client=client)

    chunks = list(provider.stream([LLMMessage(role="user", content="oi")]))
    partials = [c.content_delta for c in chunks if not c.is_final]
    final = chunks[-1]

    assert partials == ["Hello", " world", "!"]
    assert final.is_final is True
    assert final.final_response is not None
    assert final.final_response.content == "Hello world!"
    assert final.final_response.input_tokens == 7
    assert final.final_response.output_tokens == 3


def test_default_stream_impl_wraps_complete_in_single_partial_chunk():
    """
    Subclasses that don't override stream() (mocks, adversarial recorders,
    scripted judges) must still emit at least one partial chunk plus one
    final chunk carrying the full LLMResponse. This is what lets the
    orchestrator's streaming path work uniformly across every provider.
    """
    class _StubProvider(LLMProvider):
        @property
        def name(self) -> str:
            return "stub:test"

        def complete(self, messages: list[LLMMessage]) -> LLMResponse:
            return LLMResponse(
                content="fixed reply",
                input_tokens=3,
                output_tokens=5,
                latency_ms=42,
                provider_name=self.name,
            )

    provider = _StubProvider()
    chunks: list[LLMStreamChunk] = list(
        provider.stream([LLMMessage(role="user", content="oi")])
    )

    # Exactly one partial (the whole content) + one final sentinel.
    assert [c.content_delta for c in chunks if not c.is_final] == ["fixed reply"]
    finals = [c for c in chunks if c.is_final]
    assert len(finals) == 1
    assert finals[0].final_response is not None
    assert finals[0].final_response.content == "fixed reply"
    assert finals[0].final_response.input_tokens == 3
    assert finals[0].final_response.output_tokens == 5
