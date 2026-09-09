"""
TOML persistence layer for CIVIS configuration.

Path resolution follows OS conventions via platformdirs:
    Linux/Mac : $XDG_CONFIG_HOME/civis/config.toml (usually ~/.config/civis/)
    Windows   : %APPDATA%\\civis\\config.toml

The file is human-editable; tomlkit is used on write so future edits can
preserve comments. On read, we validate through Pydantic — any structural
error is surfaced early (before any LLM call happens).
"""

from pathlib import Path

import tomlkit
from platformdirs import user_config_dir

from civis.config.models import CivisConfig

APP_NAME = "civis"
CONFIG_FILENAME = "config.toml"


def config_path() -> Path:
    """OS-appropriate path to the CIVIS config file. May not exist yet."""
    return Path(user_config_dir(APP_NAME)) / CONFIG_FILENAME


def load(path: Path | None = None) -> CivisConfig | None:
    """
    Load and validate the config file. Returns None if the file does not
    exist yet — callers use that signal to trigger the setup wizard.

    A malformed file (parse error or schema violation) raises so that the
    problem is loud, not silently ignored.
    """
    target = path or config_path()
    if not target.exists():
        return None

    raw_text = target.read_text(encoding="utf-8")
    parsed = tomlkit.parse(raw_text).unwrap()
    return CivisConfig.model_validate(parsed)


def save(config: CivisConfig, path: Path | None = None) -> Path:
    """
    Write the config to disk atomically-ish (write then rename would be
    stricter; not worth the complexity for a hand-editable dev config).

    Returns the path written to.
    """
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    # Build a plain dict first, then let tomlkit format it. This keeps the
    # code readable and matches how a human would author the file.
    payload: dict = {
        "models": {
            name: entry.model_dump(exclude_none=True)
            for name, entry in config.models.items()
        },
        "roles": config.roles.model_dump(),
    }

    target.write_text(tomlkit.dumps(payload), encoding="utf-8")
    return target
