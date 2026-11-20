"""Де бадді зберігає свої дані і як записує їх безпечно.

Усе лежить у ~/.config/claude-buddy/. Запис атомарний: спершу у тимчасовий файл,
потім заміна, тож збій посеред запису ніколи не залишить зіпсований файл.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude-buddy"


def cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "claude-buddy"


def load_json(name: str, default):
    """Читає файл; якщо його немає, він зіпсований або іншого типу — повертає default."""
    try:
        data = json.loads((config_dir() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def save_json(name: str, data) -> None:
    path = config_dir() / name
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # не змогли зберегти — не привід падати
