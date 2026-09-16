"""
CIVIS package init.

Loads a local ``.env`` file (repo root) on import so API keys written by
the setup wizard are available to every provider without the user having
to run ``setx`` and reopen the shell. Real environment variables always
win — ``override=False`` prevents the file from stomping on values the
user set explicitly.

Silent no-op if python-dotenv is missing or the file is absent, which
keeps the fallback (real env vars only) working in CI.
"""

from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a runtime dep in pyproject
    load_dotenv = None  # type: ignore[assignment]

# Walk up from this file to find the repo root (pyproject.toml sibling).
# Works whether the package is imported from a checkout or an installed
# wheel — in the wheel case the .env just won't exist and we do nothing.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"

if load_dotenv is not None and _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)
