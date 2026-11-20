"""Нагадування: «нагадай о 15:00 подзвонити». Зберігаються в reminders.json,
тож не губляться, навіть якщо бадді перезапуститься чи вимкнеться комп'ютер.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import storage

FILE = "reminders.json"


@dataclass(frozen=True)
class Reminder:
    text: str
    at: float  # коли нагадати (Unix-час)

    def when(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.at)


def next_time(hour: int, minute: int, now: dt.datetime) -> dt.datetime:
    """Найближчий такий час: сьогодні, а якщо вже минув — завтра."""
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += dt.timedelta(days=1)
    return candidate


def load() -> list[Reminder]:
    items = []
    for item in storage.load_json(FILE, []):
        try:
            items.append(Reminder(str(item["text"])[:200], float(item["at"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(items, key=lambda r: r.at)


def save(items: list[Reminder]) -> None:
    storage.save_json(FILE, [{"text": r.text, "at": r.at} for r in sorted(items, key=lambda r: r.at)])


def split_due(items: list[Reminder], now: float) -> tuple[list[Reminder], list[Reminder]]:
    """(ті, що вже пора показати; ті, що ще чекають)."""
    due = [r for r in items if r.at <= now]
    waiting = [r for r in items if r.at > now]
    return due, waiting
