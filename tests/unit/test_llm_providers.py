"""
LLM provider tests.

The Ollama provider is exercised via httpx.MockTransport so tests never
need a real Ollama server running. Stub providers are checked for the
expected NotImplementedError shape so integration code can rely on it.
The factory is checked for correct dispatch by ProviderKind.
"""

import json

import httpx
import pytest

from civis.config.models import ModelEntry, ProviderKind
from civis.llm.anthropic_provider import AnthropicProvider
from civis.llm.factory import build_provider
from civis.llm.ollama_provider import OllamaProvider
from civis.llm.openai_compat_provider import OpenAICompatProvider
from civis.llm.provider import LLMMessage

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


# ---- Stubs (week-3 providers) ---------------------------------------------

def test_openai_compat_stub_construction_ok_but_complete_raises():
    provider = OpenAICompatProvider(_openai_compat_entry())
    assert provider.name == "openai_compat:gpt-4o"
    with pytest.raises(NotImplementedError, match="week 3"):
        provider.complete([LLMMessage(role="user", content="oi")])


def test_openai_compat_stub_rejects_wrong_entry_kind():
    with pytest.raises(ValueError, match="OPENAI_COMPAT"):
        OpenAICompatProvider(_ollama_entry())


def test_anthropic_stub_construction_ok_but_complete_raises():
    provider = AnthropicProvider(_anthropic_entry())
    assert provider.name == "anthropic:claude-sonnet-4-6"
    with pytest.raises(NotImplementedError, match="week 3"):
        provider.complete([LLMMessage(role="user", content="oi")])


def test_anthropic_stub_rejects_wrong_entry_kind():
    with pytest.raises(ValueError, match="ANTHROPIC"):
        AnthropicProvider(_ollama_entry())


# ---- Factory dispatch ------------------------------------------------------

def test_factory_dispatches_ollama():
    assert isinstance(build_provider(_ollama_entry()), OllamaProvider)


def test_factory_dispatches_openai_compat():
    assert isinstance(build_provider(_openai_compat_entry()), OpenAICompatProvider)


def test_factory_dispatches_anthropic():
    assert isinstance(build_provider(_anthropic_entry()), AnthropicProvider)
