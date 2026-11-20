"""Тести логіки бадді. Запуск із папки проєкту: python3 -m unittest

Кожен тест працює з тимчасовою папкою налаштувань, тож твій справжній прогрес
і налаштування не чіпаються.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Дані тестів — у тимчасовій папці, а не в ~/.config/claude-buddy.
_TMP = tempfile.mkdtemp(prefix="claude-buddy-tests-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_TMP, "cache")
