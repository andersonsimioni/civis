"""
CLI wiring tests: config load / default and role -> provider resolution.
"""

from pathlib import Path

import pytest

from civis.cli.wiring import (
    DEFAULT_JUDGE_KEY,
    DEFAULT_PERSONA_KEY,
    build_default_config,
    build_provider_from_config,
    load_or_default_config,
)
from civis.config.models import (
    CivisConfig,
    ModelEntry,
    ProviderKind,
    RoleAssignments,
)
from civis.config.store import save
from civis.llm.ollama_provider import OllamaProvider


def test_default_config_has_two_distinct_ollama_entries():
    config = build_default_config()
    assert set(config.models.keys()) == {DEFAULT_PERSONA_KEY, DEFAULT_JUDGE_KEY}
    persona_entry = config.models[DEFAULT_PERSONA_KEY]
    judge_entry = config.models[DEFAULT_JUDGE_KEY]
    assert persona_entry.provider == ProviderKind.OLLAMA
    assert judge_entry.provider == ProviderKind.OLLAMA
    # The O3 invariant requires distinct catalog KEYS (not models). We
    # follow the stronger rule anyway — two distinct model ids.
    assert persona_entry.model_id != judge_entry.model_id


def test_default_config_passes_civis_config_invariants():
    """
    CivisConfig has two validators: roles reference existing entries, and
    persona != judge. If the default config ever violates them, the CLI
    fall-back path would crash — this test guards against that regression.
    """
    config = build_default_config()
    assert config.roles.persona in config.models
    assert config.roles.judge in config.models
    assert config.roles.persona != config.roles.judge


def test_build_provider_from_config_resolves_persona_role():
    config = build_default_config()
    provider = build_provider_from_config(config, DEFAULT_PERSONA_KEY)
    assert isinstance(provider, OllamaProvider)
    assert provider.name.startswith("ollama:")


def test_build_provider_raises_for_unknown_role():
    config = build_default_config()
    with pytest.raises(KeyError, match="not defined"):
        build_provider_from_config(config, "nonexistent_role")


def test_load_or_default_returns_default_when_no_config(monkeypatch, tmp_path: Path):
    """When the user has no config.toml, we fall back to the default and
    label the source as 'default_ollama' so the CLI can print a notice."""
    monkeypatch.setattr(
        "civis.cli.wiring.load_config",
        lambda: None,
    )
    config, source = load_or_default_config()
    assert isinstance(config, CivisConfig)
    assert source == "default_ollama"


def test_load_or_default_returns_user_config_when_present(monkeypatch, tmp_path: Path):
    """When a config.toml exists, load and label as 'user_config'."""
    target = tmp_path / "config.toml"
    saved_config = CivisConfig(
        models={
            "a": ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id="test:a",
                base_url="http://localhost:11434",
            ),
            "b": ModelEntry(
                provider=ProviderKind.OLLAMA,
                model_id="test:b",
                base_url="http://localhost:11434",
            ),
        },
        roles=RoleAssignments(persona="a", judge="b"),
    )
    save(saved_config, path=target)

    # Monkeypatch load_config in the wiring namespace to point at our tmp path.
    from civis.config.store import load as real_load

    monkeypatch.setattr("civis.cli.wiring.load_config", lambda: real_load(path=target))

    config, source = load_or_default_config()
    assert source == "user_config"
    assert config == saved_config
