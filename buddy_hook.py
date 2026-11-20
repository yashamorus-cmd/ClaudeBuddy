#!/usr/bin/env python3
"""Хук Claude Code: розповідає бадді, що робить Claude.

Події (перший аргумент):
    stop    — хук Stop: Claude закінчив відповідь
    notify  — хук Notification: Claude чекає на дозвіл або на тебе
    tool    — хук PreToolUse: Claude запускає команду чи редагує файл
    fail    — хук PostToolUseFailure: команда завершилась помилкою

Встановити / прибрати всі хуки в ~/.claude/settings.json:
    python3 buddy_hook.py --install
    python3 buddy_hook.py --uninstall

Під час роботи хук завжди завершується з кодом 0 і за частку секунди,
тож ніколи не заважає Claude.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS = Path.home() / ".claude" / "settings.json"
MARK = "buddy_hook.py"  # так ми впізнаємо свої хуки серед чужих

# Подія Claude Code -> (matcher, аргумент для цього скрипта)
HOOKS = {
    "Stop": (None, "stop"),
    "Notification": (None, "notify"),
    "PreToolUse": ("Bash|Edit|MultiEdit|Write|NotebookEdit", "tool"),
    "PostToolUseFailure": ("Bash", "fail"),
}


def hook_command(arg: str) -> str:
    return f"python3 {HERE / 'buddy_hook.py'} {arg} 2>/dev/null || true"


def install(settings: dict) -> dict:
    """Додає хуки бадді, замінюючи старі версії своїх; чужі хуки не чіпає."""
    settings = uninstall(settings)
    hooks = settings.setdefault("hooks", {})
    for event, (matcher, arg) in HOOKS.items():
        entry = {"hooks": [{"type": "command", "command": hook_command(arg), "timeout": 5}]}
        if matcher:
            entry = {"matcher": matcher, **entry}
        hooks.setdefault(event, []).append(entry)
    return settings


def uninstall(settings: dict) -> dict:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    for event in list(hooks):
        entries = []
        for entry in hooks[event] if isinstance(hooks[event], list) else []:
            inner = [h for h in entry.get("hooks", []) if MARK not in str(h.get("command", ""))]
            if inner:
                entries.append({**entry, "hooks": inner})
        if entries:
            hooks[event] = entries
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]
    return settings


def update_settings(change, path: Path = SETTINGS) -> None:
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        settings = {}
    if not isinstance(settings, dict):
        raise SystemExit(f"{path}: очікував JSON-об'єкт")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(change(settings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def send_event(kind: str) -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    sys.path.insert(0, str(HERE))
    from claude_link import send, tool_detail  # лежить поруч із цим файлом

    tool = str(payload.get("tool_name", ""))
    send({
        "event": kind,
        "message": str(payload.get("message", ""))[:300],
        "cwd": str(payload.get("cwd", "")),
        "tool": tool,
        "detail": tool_detail(tool, payload.get("tool_input")),
    })


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "stop"
    if arg == "--install":
        update_settings(install)
        print(f"Хуки бадді додано в {SETTINGS}")
        return
    if arg == "--uninstall":
        update_settings(uninstall)
        print(f"Хуки бадді прибрано з {SETTINGS}")
        return
    try:
        send_event(arg)
    except Exception:  # хук не має права зламати Claude Code
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
