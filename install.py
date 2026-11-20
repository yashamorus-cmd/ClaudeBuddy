#!/usr/bin/env python3
"""Встановлення бадді однією командою.

    python3 install.py                 — ярлик у меню програм, автозапуск, хуки Claude Code, запуск
    python3 install.py --no-autostart  — без автозапуску
    python3 install.py --no-hooks      — без хуків Claude Code
    python3 install.py --uninstall     — прибрати все й зупинити бадді

Твої налаштування (~/.config/claude-buddy) не видаляються навіть при --uninstall.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
APP_FILE = DATA_HOME / "applications" / "claude-buddy.desktop"
AUTOSTART_FILE = CONFIG_HOME / "autostart" / "claude-buddy.desktop"
APT_HINT = "sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0"


def desktop_entry(autostart: bool) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Claude Buddy",
        "Comment=Маленький помаранчевий друг на робочому столі",
        f'Exec="{sys.executable}" "{HERE / "buddy.py"}"',
        "Icon=face-smile",
        "Terminal=false",
    ]
    if autostart:
        lines += ["X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-Delay=5"]
    else:
        lines += ["Categories=Utility;", "Keywords=buddy;бадді;claude;"]
    return "\n".join(lines) + "\n"


def is_autostart() -> bool:
    return AUTOSTART_FILE.exists()


def set_autostart(enabled: bool) -> None:
    if enabled:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(desktop_entry(autostart=True), encoding="utf-8")
    else:
        AUTOSTART_FILE.unlink(missing_ok=True)


def missing_dependencies() -> str | None:
    """Перевіряє GTK у тому самому Python, яким бадді запускатиметься."""
    check = ("import gi; gi.require_version('Gtk', '3.0'); gi.require_version('PangoCairo', '1.0'); "
             "from gi.repository import Gtk, PangoCairo; import cairo")
    result = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True)
    return None if result.returncode == 0 else (result.stderr.strip().splitlines() or ["?"])[-1]


def install(autostart: bool = True, hooks: bool = True) -> int:
    problem = missing_dependencies()
    if problem:
        print(f"✗ Бракує GTK для Python ({problem}).\n  Встанови: {APT_HINT}")
        return 1
    APP_FILE.parent.mkdir(parents=True, exist_ok=True)
    APP_FILE.write_text(desktop_entry(autostart=False), encoding="utf-8")
    print(f"✓ Ярлик у меню програм: {APP_FILE}")
    set_autostart(autostart)
    print(f"✓ Автозапуск {'увімкнено' if autostart else 'вимкнено'}")
    if hooks:
        import buddy_hook
        buddy_hook.update_settings(buddy_hook.install)
        print(f"✓ Хуки Claude Code додано в {buddy_hook.SETTINGS} (запрацюють у новій сесії)")
    # Якщо бадді вже працює, новий запуск просто змусить його помахати.
    subprocess.Popen([sys.executable, str(HERE / "buddy.py")], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("✓ Бадді запущено. Правий клік по ньому — меню.")
    return 0


def uninstall() -> int:
    import buddy_hook
    import claude_link
    APP_FILE.unlink(missing_ok=True)
    set_autostart(False)
    buddy_hook.update_settings(buddy_hook.uninstall)
    claude_link.send({"event": "quit"})  # попросимо бадді, що працює, попрощатися
    print("✓ Ярлик, автозапуск і хуки прибрано. Налаштування лишились у ~/.config/claude-buddy")
    return 0


def main(args: list[str]) -> int:
    unknown = set(args) - {"--no-autostart", "--no-hooks", "--uninstall"}
    if unknown:
        print(__doc__)
        return 2
    if "--uninstall" in args:
        return uninstall()
    return install(autostart="--no-autostart" not in args, hooks="--no-hooks" not in args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
