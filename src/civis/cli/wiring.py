"""
Config + provider wiring for the CLI.

Kept in its own module so tests can build a default config or exercise
the fall-back path without instantiating the Typer command.

Behaviour:
    - If ~/.config/civis/config.toml (or the OS equivalent) exists,
      load it and validate. Roles resolve to catalog entries.
    - Otherwise, return a two-model Ollama default and print a notice
      so the user knows to run the setup wizard eventually (wk-6).
    - build_provider_from_config resolves a role name to a concrete
      LLMProvider via the factory.
"""

from civis.config.models import (
    CivisConfig,
    ModelEntry,
    ProviderKind,
    RoleAssignments,
)
from civis.config.store import load as load_config
from civis.llm.factory import build_provider
from civis.llm.provider import LLMProvider

# Catalog keys used by the default (no-config) fall-back. Kept as constants
# so tests and the CLI reference the same names.
DEFAULT_PERSONA_KEY = "persona"
DEFAULT_JUDGE_KEY = "judge"

# Default Ollama base URL used by the fall-back config. Overridable only by
# saving a real config.toml — we resist adding a second env-var knob here.
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

# Default model ids for the fall-back config. Two distinct Ollama models so
# the CivisConfig invariant (persona != judge) holds.
_DEFAULT_PERSONA_MODEL_ID = "qwen2.5:7b-instruct-q4_K_M"
_DEFAULT_JUDGE_MODEL_ID = "llama3.1:8b-instruct-q4_K_M"


def build_default_config() -> CivisConfig:
    """
    Build the two-model Ollama config used when no config.toml exists yet.
    Both entries point at localhost:11434 — the user needs Ollama running
    with both models pulled (`ollama pull qwen2.5:7b`, etc.).
    """
    return CivisConfig(
        models={
            DEFAULT_PERSONA_KEY: ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id=_DEFAULT_PERSONA_MODEL_ID,
                base_url=_DEFAULT_OLLAMA_BASE_URL,
            ),
            DEFAULT_JUDGE_KEY: ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id=_DEFAULT_JUDGE_MODEL_ID,
                base_url=_DEFAULT_OLLAMA_BASE_URL,
            ),
        },
        roles=RoleAssignments(persona=DEFAULT_PERSONA_KEY, judge=DEFAULT_JUDGE_KEY),
    )


def load_or_default_config() -> tuple[CivisConfig, str]:
    """
    Return (config, source_label). source_label is 'user_config' when the
    user's config.toml was found and validated, or 'default_ollama' when
    the fall-back was used.
    """
    loaded = load_config()
    if loaded is not None:
        return loaded, "user_config"
    return build_default_config(), "default_ollama"


def build_provider_from_config(config: CivisConfig, role_key: str) -> LLMProvider:
    """
    Resolve a role name to a concrete LLMProvider by looking up the catalog
    key assigned to that role and passing the ModelEntry to the factory.
    """
    role_map = config.roles.as_mapping()
    # role_key is a plain string; the mapping keys are RoleName enum values,
    # so we match on the enum's string value.
    catalog_key = None
    for role, target in role_map.items():
        if role.value == role_key:
            catalog_key = target
            break
    if catalog_key is None:
        raise KeyError(
            f"Role '{role_key}' is not defined in the config. "
            f"Known roles: {[r.value for r in role_map]}"
        )
    entry = config.models[catalog_key]
    return build_provider(entry)
