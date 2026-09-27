"""Small, dependency-free environment file loader for local development."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path | None = None) -> Path | None:
    """Load ``.env`` values without replacing variables already in the shell."""
    env_path = Path(path) if path else Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return None

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or (not key.replace("_", "").isalnum()):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return env_path
