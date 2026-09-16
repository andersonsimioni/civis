"""
Pre-flight check for Ollama-based sessions.

Runs before the launcher opens the menu so the user gets a clear,
actionable error instead of a crash inside the chat when Ollama is
missing or the models are not pulled. This is the "make it round"
piece — 90% of first-run failures are one of the two conditions
this script surfaces.

Exit codes:
    0 — Ollama is up AND both required models are present.
    1 — Ollama is not reachable at localhost:11434.
    2 — Ollama is up but one or both models are missing AND the user
        declined to pull them (or --non-interactive was passed).
    3 — Ollama is up but pulling a missing model failed.

Usage from a shell:
    python scripts/preflight_ollama.py --interactive
    python scripts/preflight_ollama.py --non-interactive   # CI-safe
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Iterable

import httpx

OLLAMA_BASE_URL = "http://localhost:11434"
TAGS_ENDPOINT = f"{OLLAMA_BASE_URL}/api/tags"

# The two models the default Ollama-dual config expects. Kept in sync with
# civis.cli.wiring._DEFAULT_PERSONA_MODEL_ID / _DEFAULT_JUDGE_MODEL_ID.
REQUIRED_MODELS: tuple[str, ...] = (
    "qwen2.5:7b-instruct-q4_K_M",
    "llama3.1:8b-instruct-q4_K_M",
)


def _print_err(msg: str) -> None:
    print(msg, file=sys.stderr)


def check_ollama_running() -> bool:
    """Return True iff Ollama responds on the tags endpoint."""
    try:
        response = httpx.get(TAGS_ENDPOINT, timeout=3.0)
        response.raise_for_status()
        return True
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        return False


def installed_models() -> set[str]:
    """Return the set of model tags currently available in the local Ollama."""
    response = httpx.get(TAGS_ENDPOINT, timeout=3.0)
    response.raise_for_status()
    payload = response.json()
    # `models` is a list of {"name": "qwen2.5:7b-...", ...}
    return {entry["name"] for entry in payload.get("models", [])}


def missing_models(required: Iterable[str], installed: Iterable[str]) -> list[str]:
    installed_set = set(installed)
    return [m for m in required if m not in installed_set]


def _ollama_cli_available() -> bool:
    return shutil.which("ollama") is not None


def pull_model(model_tag: str) -> bool:
    """Run `ollama pull <tag>` and stream progress to the user's terminal."""
    if not _ollama_cli_available():
        _print_err(
            "[preflight] `ollama` command not found on PATH. Install Ollama "
            "Desktop or add its binary to PATH, then re-run."
        )
        return False
    print(f"[preflight] rodando: ollama pull {model_tag}")
    result = subprocess.run(["ollama", "pull", model_tag], check=False)
    return result.returncode == 0


def prompt_yes(question: str, default_yes: bool = True) -> bool:
    """Ask a yes/no question. Empty answer -> `default_yes`."""
    suffix = " [S/n] " if default_yes else " [s/N] "
    try:
        raw = input(question + suffix).strip().lower()
    except EOFError:
        return default_yes
    if not raw:
        return default_yes
    return raw in {"s", "sim", "y", "yes"}


def run_preflight(interactive: bool) -> int:
    """
    Full preflight sequence. Returns a process exit code (see module docstring).
    """
    print("[preflight] verificando Ollama em localhost:11434 ...")
    if not check_ollama_running():
        _print_err("")
        _print_err("[ERRO] Ollama não está respondendo em http://localhost:11434.")
        _print_err("")
        _print_err("Como resolver:")
        _print_err("  1. Abra o Ollama Desktop (Windows/Mac), OU")
        _print_err("  2. Rode `ollama serve` em outro terminal (Linux).")
        _print_err("")
        _print_err("Depois rode o launcher de novo.")
        return 1

    print("[preflight] Ollama OK. verificando modelos ...")
    try:
        installed = installed_models()
    except Exception as exc:  # noqa: BLE001 - surface network issues clearly
        _print_err(f"[ERRO] falha ao listar modelos do Ollama: {exc}")
        return 1

    missing = missing_models(REQUIRED_MODELS, installed)
    if not missing:
        print("[preflight] modelos OK:")
        for tag in REQUIRED_MODELS:
            print(f"           - {tag}")
        return 0

    _print_err("")
    _print_err("[AVISO] os seguintes modelos ainda não estão puxados:")
    for tag in missing:
        _print_err(f"        - {tag}")
    _print_err("")
    _print_err("Sem eles, as sessões vão falhar no primeiro turno.")
    _print_err("Puxar cada modelo é um download de ~4 GB.")
    _print_err("")

    if not interactive:
        _print_err(
            "[preflight] --non-interactive: não vou puxar automaticamente. "
            "Rode `ollama pull <modelo>` para cada um e tente novamente."
        )
        return 2

    if not prompt_yes("Puxar os modelos que faltam agora?"):
        _print_err(
            "[preflight] ok, seguindo sem puxar. As sessões falharão até você "
            "rodar `ollama pull` manualmente."
        )
        return 2

    for tag in missing:
        ok = pull_model(tag)
        if not ok:
            _print_err(f"[ERRO] falha ao puxar {tag}. Tente manual: ollama pull {tag}")
            return 3

    print("[preflight] tudo pronto.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-flight for Ollama sessions.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt the user to pull missing models (default).",
    )
    mode.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail fast without prompting when models are missing.",
    )
    args = parser.parse_args(argv)

    # Default to interactive if neither flag was given — safer for humans.
    interactive = not args.non_interactive

    return run_preflight(interactive=interactive)


if __name__ == "__main__":
    sys.exit(main())
