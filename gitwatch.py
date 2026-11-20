"""Нагадування про коміти: шукає git-проєкти, де зміни давно лежать незакомічені.

«Давно» рахуємо від найстарішої незакоміченої зміни (час зміни файлу), але не раніше
за останній коміт. Видалені файли часу зміни не мають, тому їх пропускаємо.
Тут лише блокуючі функції (запускають git) — бадді викликає їх в окремому потоці.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SKIP_DIRS = {"node_modules", "venv", ".venv", "build", "dist", "__pycache__", "target", ".gradle"}
GIT_TIMEOUT_S = 10


def find_repos(roots: list[Path], max_depth: int = 3) -> list[Path]:
    """Усі папки з .git на глибині до max_depth (вкладені репозиторії теж)."""
    repos: list[Path] = []

    def walk(folder: Path, depth: int) -> None:
        if (folder / ".git").exists():
            repos.append(folder)
        if depth >= max_depth:
            return
        try:
            children = sorted(folder.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_dir() and not child.is_symlink() and not child.name.startswith(".") \
                    and child.name not in SKIP_DIRS:
                walk(child, depth + 1)

    for root in roots:
        if root.is_dir():
            walk(root, 0)
    return repos


def parse_status(output: str) -> list[tuple[str, str]]:
    """Вивід `git status --porcelain -z` -> [(код, шлях)]."""
    entries = []
    parts = output.split("\0")
    i = 0
    while i < len(parts):
        item = parts[i]
        i += 1
        if len(item) < 4:
            continue
        code, path = item[:2], item[3:]
        if code[0] in "RC":  # перейменування: далі йде старий шлях, він нам не потрібен
            i += 1
        entries.append((code, path))
    return entries


def _git(repo: Path, *args: str) -> str:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")  # не заважаємо твоїм git-командам
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                            timeout=GIT_TIMEOUT_S, env=env)
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "git failed")
    return result.stdout


def uncommitted_since(repo: Path) -> float | None:
    """Відколи (Unix-час) у репозиторії лежать незакомічені зміни; None — усе закомічено."""
    entries = parse_status(_git(repo, "status", "--porcelain", "-z", "--untracked-files=normal"))
    if not entries:
        return None
    mtimes = []
    for code, path in entries[:2000]:
        if "D" in code:
            continue
        try:
            mtimes.append((repo / path).stat().st_mtime)
        except OSError:
            continue
    try:
        last_commit = float(_git(repo, "log", "-1", "--format=%ct").strip() or 0)
    except (OSError, ValueError):
        last_commit = 0.0
    if not mtimes:
        return last_commit or None  # лише видалення: вважаємо від останнього коміту
    return max(min(mtimes), last_commit)


def stale_repos(roots: list[Path], now: float, older_than_s: float) -> list[tuple[Path, float]]:
    """[(репозиторій, скільки секунд без коміту)] — від найдавнішого."""
    found = []
    for repo in find_repos(roots):
        try:
            since = uncommitted_since(repo)
        except (OSError, subprocess.SubprocessError):
            continue
        if since is not None and now - since >= older_than_s:
            found.append((repo, now - since))
    return sorted(found, key=lambda item: -item[1])
