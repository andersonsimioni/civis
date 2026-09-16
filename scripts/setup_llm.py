"""
Interactive LLM setup wizard.

Walks the user through picking a persona provider, a judge provider, and
any required env vars. Writes a valid config.toml to the OS-appropriate
user config path (%APPDATA%/civis on Windows, $XDG_CONFIG_HOME/civis
elsewhere). Enforces the O3 invariant client-side (persona != judge) so
we don't hand a broken file to CivisConfig at CLI boot.

Presets: Ollama-dual, all-Anthropic, all-DeepSeek, and mix-and-match
between Ollama, Anthropic, and any OpenAI-compatible endpoint (OpenAI,
DeepSeek, Groq, Together, Fireworks, xAI, custom URL).

Usage:
    python scripts/setup_llm.py               # interactive
    python scripts/setup_llm.py --show        # print current config path
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Provider presets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpenAICompatPreset:
    """One row of the OpenAI-compat provider menu."""

    label: str
    base_url: str
    api_key_env: str
    default_persona_model: str
    default_judge_model: str


# Popular OpenAI-compat services. Users can also pick "custom" and type
# their own base_url + env var.
OPENAI_COMPAT_PRESETS: list[OpenAICompatPreset] = [
    OpenAICompatPreset(
        label="OpenAI (api.openai.com)",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_persona_model="gpt-4o-mini",
        default_judge_model="gpt-4o",
    ),
    OpenAICompatPreset(
        label="DeepSeek (api.deepseek.com)",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        default_persona_model="deepseek-chat",
        default_judge_model="deepseek-reasoner",
    ),
    OpenAICompatPreset(
        label="Groq (api.groq.com, fastest inference)",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        default_persona_model="llama-3.3-70b-versatile",
        default_judge_model="llama-3.3-70b-versatile",
    ),
    OpenAICompatPreset(
        label="Together AI (api.together.xyz)",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        default_persona_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        default_judge_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
    ),
    OpenAICompatPreset(
        label="Fireworks (api.fireworks.ai)",
        base_url="https://api.fireworks.ai/inference/v1",
        api_key_env="FIREWORKS_API_KEY",
        default_persona_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
        default_judge_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
    ),
    OpenAICompatPreset(
        label="xAI Grok (api.x.ai)",
        base_url="https://api.x.ai/v1",
        api_key_env="XAI_API_KEY",
        default_persona_model="grok-2-1212",
        default_judge_model="grok-2-1212",
    ),
]

# Anthropic presets — just the model list, everything else is fixed.
ANTHROPIC_PERSONA_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6"]
ANTHROPIC_JUDGE_MODELS = ["claude-sonnet-4-6", "claude-opus-4-7"]
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"

# Ollama defaults — the two models the launcher preflight already pulls.
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_DEFAULT_PERSONA = "qwen2.5:7b-instruct-q4_K_M"
OLLAMA_DEFAULT_JUDGE = "llama3.1:8b-instruct-q4_K_M"


# ---------------------------------------------------------------------------
# Config path resolution
# ---------------------------------------------------------------------------

def resolve_config_path() -> Path:
    """OS-appropriate location of the user's CIVIS config.toml."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "civis" / "config.toml"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "civis" / "config.toml"
    return Path.home() / ".config" / "civis" / "config.toml"


# ---------------------------------------------------------------------------
# Prompt helpers (input with default)
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str | None = None) -> str:
    """Prompt for input; blank returns default (or empty string)."""
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def ask_choice(prompt: str, options: list[str], default_index: int = 0) -> int:
    """Numbered menu; returns 0-based index of the choice."""
    print(f"\n{prompt}")
    for i, opt in enumerate(options, start=1):
        marker = " (padrão)" if (i - 1) == default_index else ""
        print(f"  {i}. {opt}{marker}")
    while True:
        raw = input(f"Escolha [1-{len(options)}]: ").strip()
        if not raw:
            return default_index
        try:
            n = int(raw)
        except ValueError:
            print("Digite um número.")
            continue
        if 1 <= n <= len(options):
            return n - 1
        print(f"Fora da faixa. Escolha entre 1 e {len(options)}.")


# ---------------------------------------------------------------------------
# Entry building
# ---------------------------------------------------------------------------

@dataclass
class BuiltEntry:
    """The rendered TOML block for one catalog entry + its role usage."""

    catalog_key: str
    provider: str
    model_id: str
    base_url: str | None
    api_key_env: str | None
    timeout_s: float = 60.0


def build_ollama_entry(role: str) -> BuiltEntry:
    """Prompt for Ollama model id (default depends on role)."""
    default = OLLAMA_DEFAULT_PERSONA if role == "persona" else OLLAMA_DEFAULT_JUDGE
    model_id = ask(f"Model id ({role})", default=default)
    return BuiltEntry(
        catalog_key=f"{role}_ollama",
        provider="ollama",
        model_id=model_id,
        base_url=OLLAMA_BASE_URL,
        api_key_env=None,
    )


def build_anthropic_entry(role: str) -> BuiltEntry:
    """Prompt for Claude model id from a curated list."""
    models = ANTHROPIC_PERSONA_MODELS if role == "persona" else ANTHROPIC_JUDGE_MODELS
    idx = ask_choice(f"Modelo Claude ({role}):", models, default_index=0)
    return BuiltEntry(
        catalog_key=f"{role}_claude",
        provider="anthropic",
        model_id=models[idx],
        base_url=None,
        api_key_env=ANTHROPIC_API_KEY_ENV,
    )


def build_openai_compat_entry(role: str) -> BuiltEntry:
    """Full submenu: pick a preset (or custom), then model id + timeout."""
    labels = [p.label for p in OPENAI_COMPAT_PRESETS] + ["Custom (digite base_url)"]
    # Default index 1 = DeepSeek (Anderson's declared provider of choice).
    idx = ask_choice(f"Serviço OpenAI-compat ({role}):", labels, default_index=1)
    if idx < len(OPENAI_COMPAT_PRESETS):
        preset = OPENAI_COMPAT_PRESETS[idx]
        default_model = (
            preset.default_persona_model if role == "persona"
            else preset.default_judge_model
        )
        model_id = ask(f"Model id ({role})", default=default_model)
        base_url = preset.base_url
        api_key_env = preset.api_key_env
    else:
        base_url = ask("Base URL (ex.: https://exemplo.com/v1)")
        model_id = ask(f"Model id ({role})")
        api_key_env = ask("Nome da env var da API key", default="CUSTOM_API_KEY")
    # Reasoning models (deepseek-reasoner, o1-*) sometimes need more time.
    default_timeout = 90.0 if "reason" in model_id.lower() or "o1" in model_id.lower() else 60.0
    return BuiltEntry(
        catalog_key=f"{role}_{_short_provider_name(base_url)}",
        provider="openai_compat",
        model_id=model_id,
        base_url=base_url,
        api_key_env=api_key_env,
        timeout_s=default_timeout,
    )


def _short_provider_name(base_url: str) -> str:
    """Extract 'deepseek' from 'https://api.deepseek.com/v1' for catalog key."""
    from urllib.parse import urlparse

    host = urlparse(base_url).hostname or "custom"
    parts = host.split(".")
    if len(parts) >= 2:
        # api.deepseek.com -> deepseek; api.openai.com -> openai
        return parts[-2].replace("-", "_")
    return "custom"


def build_entry_for_role(role: str) -> BuiltEntry:
    """Top-level provider picker for one role."""
    provider_labels = [
        "Ollama (local, gratuito)",
        "Anthropic Claude (API paga)",
        "OpenAI-compatible (OpenAI, DeepSeek, Groq, Together, xAI…)",
    ]
    print(f"\n─── Provider da {role.upper()} ───")
    idx = ask_choice("Escolha o provider:", provider_labels, default_index=1)
    if idx == 0:
        return build_ollama_entry(role)
    if idx == 1:
        return build_anthropic_entry(role)
    return build_openai_compat_entry(role)


# ---------------------------------------------------------------------------
# TOML rendering
# ---------------------------------------------------------------------------

def render_toml(persona: BuiltEntry, judge: BuiltEntry) -> str:
    """Assemble the final config.toml text."""
    persona_key = persona.catalog_key
    judge_key = judge.catalog_key
    # Guarantee distinct catalog keys even if provider+model match. The
    # underlying invariant is on catalog KEYS, not on the model_id, so
    # this suffix is enough to satisfy Pydantic.
    if persona_key == judge_key:
        judge_key = judge_key + "_judge"

    lines: list[str] = [
        "# Generated by scripts/setup_llm.py",
        "# Edit by hand if you know what you're doing.",
        "",
    ]
    lines.extend(_render_entry(persona_key, persona))
    lines.append("")
    lines.extend(_render_entry(judge_key, judge))
    lines.append("")
    lines.append("[roles]")
    lines.append(f'persona = "{persona_key}"')
    lines.append(f'judge = "{judge_key}"')
    lines.append("")
    return "\n".join(lines)


def _render_entry(key: str, entry: BuiltEntry) -> list[str]:
    out = [f"[models.{key}]"]
    out.append(f'provider = "{entry.provider}"')
    out.append(f'model_id = "{entry.model_id}"')
    if entry.base_url:
        out.append(f'base_url = "{entry.base_url}"')
    if entry.api_key_env:
        out.append(f'api_key_env = "{entry.api_key_env}"')
    out.append(f"request_timeout_s = {entry.timeout_s}")
    return out


# ---------------------------------------------------------------------------
# Env var check
# ---------------------------------------------------------------------------

def check_env_var(name: str | None) -> tuple[bool, str]:
    """Return (is_set, hint) for an API key env var."""
    if not name:
        return True, ""
    if os.environ.get(name):
        return True, f"OK: {name} detectada."
    if platform.system() == "Windows":
        hint = f"AUSENTE. Rode: setx {name} sk-... (e abra novo cmd)"
    else:
        hint = f"AUSENTE. Rode: export {name}=sk-..."
    return False, hint


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CIVIS LLM setup wizard.")
    parser.add_argument("--show", action="store_true", help="Print target config path and exit.")
    args = parser.parse_args(argv)

    target = resolve_config_path()

    if args.show:
        print(target)
        return 0

    print("═" * 60)
    print("  CIVIS — Configuração de LLM")
    print("═" * 60)
    print(f"\nArquivo a gerar: {target}")

    persona = build_entry_for_role("persona")
    judge = build_entry_for_role("judge")

    print("\n─── Configuração escolhida ───")
    print(f"  persona: {persona.provider}:{persona.model_id}")
    print(f"  judge:   {judge.provider}:{judge.model_id}")

    if input("\nConfirmar e salvar? [S/n] ").strip().lower() in {"n", "nao", "não", "no"}:
        print("Abortado — nada foi escrito.")
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    toml_text = render_toml(persona, judge)
    target.write_text(toml_text, encoding="utf-8")
    print(f"\nSalvo em {target}")

    print("\n─── Env vars necessárias ───")
    for env_name in {persona.api_key_env, judge.api_key_env}:
        if not env_name:
            continue
        is_set, hint = check_env_var(env_name)
        prefix = "  [OK] " if is_set else "  [!!] "
        print(f"{prefix}{hint}")

    print("\nPronto. Abra o menu (opção 1) para testar a nova config.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
