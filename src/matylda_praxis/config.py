"""Small local configuration loader for optional provider adapters."""

from __future__ import annotations

import os
from pathlib import Path


LOCAL_ENV_NAMES = frozenset({"OPENAI_API_KEY", "OPENAI_MODEL"})


def load_local_env(path: str | Path = ".env.local") -> tuple[str, ...]:
    """Load known provider settings without overriding the process environment."""
    target = Path(path)
    if not target.is_file():
        return ()
    loaded: list[str] = []
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in LOCAL_ENV_NAMES or name in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value:
            os.environ[name] = value
            loaded.append(name)
    return tuple(loaded)
