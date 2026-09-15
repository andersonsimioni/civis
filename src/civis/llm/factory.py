"""
LLM provider factory.

Central dispatch point: given a ModelEntry from the catalog, return the
concrete LLMProvider instance that speaks the right protocol. Callers
(orchestrator, judge, wizard) never import the concrete classes — the
factory is the single seam.

Adding a new provider = one new dispatch branch plus the concrete module.
"""

from civis.config.models import ModelEntry, ProviderKind
from civis.llm.anthropic_provider import AnthropicProvider
from civis.llm.ollama_provider import OllamaProvider
from civis.llm.openai_compat_provider import OpenAICompatProvider
from civis.llm.provider import LLMProvider


def build_provider(entry: ModelEntry) -> LLMProvider:
    """Return the provider instance appropriate for the given catalog entry."""
    match entry.provider:
        case ProviderKind.OLLAMA:
            return OllamaProvider(entry)
        case ProviderKind.OPENAI_COMPAT:
            return OpenAICompatProvider(entry)
        case ProviderKind.ANTHROPIC:
            return AnthropicProvider(entry)
