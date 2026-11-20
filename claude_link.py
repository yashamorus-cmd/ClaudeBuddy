"""Зв'язок із Claude Code: хук (buddy_hook.py) шле подію, бадді на неї реагує.

Події летять через локальний Unix-сокет у твоїй тимчасовій папці (доступ лише
в тебе). Якщо бадді не запущений, хук просто нічого не робить.
Тут немає GTK, щоб хук запускався миттєво й не затримував Claude.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

MAX_MESSAGE = 4096


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and Path(runtime).is_dir():
        return Path(runtime) / "claude-buddy.sock"
    return Path("/tmp") / f"claude-buddy-{os.getuid()}.sock"


def send(event: dict) -> bool:
    """Надсилає подію бадді. Ніколи не кидає виняток: бадді може бути вимкнений."""
    try:
        data = json.dumps(event, ensure_ascii=False).encode()[:MAX_MESSAGE]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.3)
            sock.sendto(data, str(socket_path()))
        return True
    except OSError:
        return False


# Команда Bash -> що сказати. Перевіряються по черзі, перша збіжна перемагає.
COMMAND_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("git push",), "Відправляю на GitHub 🚀"),
    (("git commit",), "Комічу 💾"),
    (("pytest", "unittest", "npm test", "npm run test", "vitest", "jest", "gradle test",
      "go test", "cargo test", "bun test"), "Запускаю тести 🧪"),
    (("eslint", "ruff", "pyflakes", "flake8", "npm run lint", "tsc --noemit"), "Перевіряю код 🔍"),
    (("npm run build", "vite build", "assemble", "gradle build", "cargo build", "make ",
      "tsc", "docker build"), "Збираю проєкт 🔨"),
    (("npm install", "npm i ", "pip install", "apt install", "pnpm add", "yarn add",
      "bun add", "uv add"), "Встановлюю пакети 📦"),
    (("curl ", "wget "), "Ходжу в інтернет 🌐"),
]

FILE_TOOLS = {"Edit": "Редагую", "MultiEdit": "Редагую", "Write": "Пишу", "NotebookEdit": "Редагую"}


def describe_tool(tool: str, detail: str) -> str | None:
    """Що Claude зараз робить, людською мовою; None — нічого цікавого, мовчимо."""
    if tool == "Bash":
        command = f" {detail.lower()} "
        for patterns, text in COMMAND_PATTERNS:
            if any(p in command for p in patterns):
                return text
        return None
    if tool in FILE_TOOLS:
        name = Path(detail).name if detail else "файл"
        return f"{FILE_TOOLS[tool]} {name} ✏️"
    return None


def describe_failure(tool: str) -> str:
    return "Ой, команда впала 😬" if tool == "Bash" else "Ой, щось не вийшло 😬"


def tool_detail(tool: str, tool_input: object) -> str:
    """З усього, що Claude передає інструменту, бадді потрібна лише команда або ім'я файлу."""
    if not isinstance(tool_input, dict):
        return ""
    if tool == "Bash":
        return str(tool_input.get("command", ""))[:300]
    return str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")[:300]


class Listener:
    """Бік бадді: слухає сокет. fileno() віддаємо GLib, щоб не блокувати екран."""

    def __init__(self) -> None:
        self.path = socket_path()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.path.unlink()  # залишився від попереднього запуску
        except FileNotFoundError:
            pass
        old_umask = os.umask(0o177)  # сокет одразу з правами 600: писати можеш лише ти
        try:
            self.sock.bind(str(self.path))
        finally:
            os.umask(old_umask)
        self.sock.setblocking(False)

    def fileno(self) -> int:
        return self.sock.fileno()

    def read_all(self) -> list[dict]:
        events = []
        while True:
            try:
                data = self.sock.recv(MAX_MESSAGE)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                event = json.loads(data.decode())
            except (UnicodeDecodeError, ValueError):
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def close(self) -> None:
        self.sock.close()
        try:
            self.path.unlink()
        except OSError:
            pass
