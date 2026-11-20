"""Тамагочі: ситість і настрій бадді, а також усе, що він пам'ятає між запусками.

Показники падають з часом — і поки бадді вимкнений теж: повернувся після вихідних,
а він зголоднів. Зберігається в ~/.config/claude-buddy/state.json (налаштування,
які ти обираєш у меню, лежать окремо, у config.json).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATE_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude-buddy" / "state.json"

MAX = 100.0
SATIETY_STEP_S = 6 * 60  # ситість -1 кожні 6 хв: з повної до нуля ~10 год
MOOD_STEP_S = 9 * 60  # настрій -1 кожні 9 хв: ~15 год
HUNGRY = 30  # нижче — бадді голодний
SAD = 30  # нижче — бадді сумує
FULL = 95  # вище — більше не їсть
FEED_AMOUNT = 25


@dataclass
class Needs:
    satiety: float = 80.0
    mood: float = 80.0
    updated: float = 0.0  # коли востаннє рахували падіння (секунди Unix)

    def decay(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        if self.updated <= 0 or now < self.updated:  # перший запуск або годинник перевели назад
            self.updated = now
            return
        elapsed = now - self.updated
        self.satiety = max(0.0, self.satiety - elapsed / SATIETY_STEP_S)
        self.mood = max(0.0, self.mood - elapsed / MOOD_STEP_S)
        self.updated = now

    def feed(self) -> bool:
        """Годує; False — якщо бадді вже ситий і не хоче."""
        self.decay()
        if self.satiety >= FULL:
            return False
        self.satiety = min(MAX, self.satiety + FEED_AMOUNT)
        return True

    def cheer(self, amount: float) -> None:
        self.decay()
        self.mood = min(MAX, self.mood + amount)

    def tire(self, amount: float) -> None:
        self.decay()
        self.satiety = max(0.0, self.satiety - amount)

    @property
    def hungry(self) -> bool:
        return self.satiety < HUNGRY

    @property
    def sad(self) -> bool:
        return self.mood < SAD

    @property
    def wellbeing(self) -> float:
        """Найгірший показник: голодний бадді не радіє, навіть якщо пограли."""
        return min(self.satiety, self.mood)


@dataclass
class State:
    needs: Needs = field(default_factory=Needs)
    best_catch: int = 0  # рекорд у грі «Спіймай мене»
    word_day: str = ""  # коли востаннє казав слово дня (ISO-дата)
    learned_day: str = ""  # коли востаннє отримав бонус за вивчене слово
    pos: list[float] | None = None  # де стояв на екрані


def load() -> State:
    state = State()
    try:
        data = json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        state.needs.decay()
        return state
    needs = data.get("needs") or {}
    try:
        state.needs = Needs(
            satiety=min(MAX, max(0.0, float(needs.get("satiety", 80)))),
            mood=min(MAX, max(0.0, float(needs.get("mood", 80)))),
            updated=float(needs.get("updated", 0)),
        )
        state.best_catch = max(0, int(data.get("best_catch", 0)))
    except (TypeError, ValueError):
        pass
    state.word_day = str(data.get("word_day", ""))
    state.learned_day = str(data.get("learned_day", ""))
    pos = data.get("pos")
    if isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, (int, float)) for v in pos):
        state.pos = [float(pos[0]), float(pos[1])]
    state.needs.decay()
    return state


def save(state: State) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2))
        tmp.replace(STATE_PATH)  # атомарно: збій ніколи не залишить пів файлу
    except OSError:
        pass
