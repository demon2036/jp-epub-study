from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | str = ".env", *, override: bool = False) -> dict[str, str]:
    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if value and value[0] in ("'", '"') and value[-1] == value[0] and len(value) >= 2:
            value = value[1:-1]

        if not override and key in os.environ:
            continue

        os.environ[key] = value
        loaded[key] = value

    return loaded

