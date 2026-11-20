#!/usr/bin/env python3
"""Хук Claude Code: каже бадді, що Claude закінчив роботу або чекає на тебе.

Підключення — у ~/.claude/settings.json (див. README, розділ «Claude Code»):
    python3 /шлях/до/buddy_hook.py stop     — хук Stop (Claude закінчив відповідь)
    python3 /шлях/до/buddy_hook.py notify   — хук Notification (потрібен дозвіл / чекає)

Завжди завершується з кодом 0 і за частку секунди, тож ніколи не заважає Claude.
"""

import json
import sys


def main() -> None:
    kind = sys.argv[1] if len(sys.argv) > 1 else "stop"
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    from claude_link import send  # лежить поруч із цим файлом

    send({
        "event": kind,
        "message": str(payload.get("message", ""))[:300],
        "cwd": str(payload.get("cwd", "")),
    })


if __name__ == "__main__":
    try:
        main()
    except Exception:  # хук не має права зламати Claude Code
        pass
    sys.exit(0)
