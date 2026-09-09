"""
Config catalog + roles tests.

Two things being verified here:

    1. The Pydantic contracts enforce the invariants that keep goal O3
       intact (persona != judge, roles point to real catalog entries,
       each provider has its required fields).

    2. Round-trip persistence: a config written to TOML and read back
       must be byte-equivalent semantically.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from civis.config.models import (
    CivisConfig,
    ModelEntry,
    ProviderKind,
    RoleAssignments,
)
from civis.config.store import load, save

# ---- fixtures --------------------------------------------------------------

def _make_config() -> CivisConfig:
    """Minimal valid config used across most tests."""
    return CivisConfig(
        models={
            "qwen7b_local": ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id="qwen2.5:7b-instruct-q4_K_M",
                base_url="http://localhost:11434",
            ),
            "llama8b_local": ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id="llama3.1:8b-instruct-q4_K_M",
                base_url="http://localhost:11434",
            ),
        },
        roles=RoleAssignments(persona="qwen7b_local", judge="llama8b_local"),
    )


# ---- provider requirements -------------------------------------------------

def test_ollama_entry_requires_base_url():
    with pytest.raises(ValidationError, match="base_url"):
        ModelEntry(
            provider=ProviderKind.OLLAMA,
            model_id="qwen2.5:7b",
        )


def test_openai_compat_requires_base_url_and_api_key_env():
    with pytest.raises(ValidationError, match="base_url"):
        ModelEntry(
            provider=ProviderKind.OPENAI_COMPAT,
            model_id="gpt-4o",
            api_key_env="OPENAI_API_KEY",
        )
    with pytest.raises(ValidationError, match="api_key_env"):
        ModelEntry(
            provider=ProviderKind.OPENAI_COMPAT,
            model_id="gpt-4o",
            base_url="https://api.openai.com/v1",
        )


def test_anthropic_requires_api_key_env():
    with pytest.raises(ValidationError, match="api_key_env"):
        ModelEntry(
            provider=ProviderKind.ANTHROPIC,
            model_id="claude-sonnet-4-6",
        )


# ---- role invariants -------------------------------------------------------

def test_role_pointing_to_missing_model_raises():
    with pytest.raises(ValidationError, match="not in the model catalog"):
        CivisConfig(
            models={
                "qwen7b_local": ModelEntry(
                    provider=ProviderKind.OLLAMA,
                    model_id="qwen2.5:7b",
                    base_url="http://localhost:11434",
                ),
            },
            roles=RoleAssignments(persona="qwen7b_local", judge="nonexistent"),
        )


def test_persona_and_judge_must_be_distinct_entries():
    """Goal O3: no self-evaluation."""
    with pytest.raises(ValidationError, match="distinct catalog entries"):
        CivisConfig(
            models={
                "qwen7b_local": ModelEntry(
                    provider=ProviderKind.OLLAMA,
                    model_id="qwen2.5:7b",
                    base_url="http://localhost:11434",
                ),
            },
            roles=RoleAssignments(persona="qwen7b_local", judge="qwen7b_local"),
        )


# ---- persistence round-trip ------------------------------------------------

def test_save_then_load_roundtrips(tmp_path: Path):
    config = _make_config()
    target = tmp_path / "config.toml"

    written_path = save(config, path=target)
    assert written_path == target
    assert target.exists()

    reloaded = load(path=target)
    assert reloaded == config


def test_load_missing_file_returns_none(tmp_path: Path):
    absent = tmp_path / "does_not_exist.toml"
    assert load(path=absent) is None


def test_save_creates_parent_directory(tmp_path: Path):
    """The wizard runs before ~/.config/civis/ exists — save must mkdir."""
    nested = tmp_path / "civis" / "config.toml"
    config = _make_config()
    save(config, path=nested)
    assert nested.exists()
