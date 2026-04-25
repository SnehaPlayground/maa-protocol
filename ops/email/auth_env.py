from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

ENV_CANDIDATES = (
    Path("/root/.config/sneha/env.sh"),
    Path("/root/.openclaw/workspace/.env"),
)


def load_env_file(path: Path) -> Dict[str, str]:
    env_updates: Dict[str, str] = {}
    if not path.exists():
        return env_updates

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        env_updates[key] = value
    return env_updates


def build_auth_env() -> Dict[str, str]:
    env = os.environ.copy()
    for path in ENV_CANDIDATES:
        env.update(load_env_file(path))
    return env
