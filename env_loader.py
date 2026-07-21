"""Minimal read-only .env loader used instead of mutable dotenv helpers."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Union

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_value(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value[0] in ("'", '"'):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value.strip(value[0])
        return parsed if isinstance(parsed, str) else str(parsed)
    # Inlinekommentar kräver whitespace före #, så nycklar med # bevaras.
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def load_env_file(
    path: Union[str, Path],
    *,
    override: bool = False,
) -> bool:
    """
    Läs KEY=VALUE från en vanlig .env-fil till os.environ.

    Funktionen är avsiktligt read-only: den följer inga skriv-/rename-flöden och
    exponerar därför inte set_key-sårbarheten som fanns i python-dotenv.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return False

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            continue
        if override or key not in os.environ:
            os.environ[key] = _parse_value(raw_value)
    return True
