"""Прогрес: досвід (XP), рівні, досягнення, статистика й «зошит» зі словами.

Бадді отримує досвід за те, що ви робите разом: помодоро, слова, ігри, задачі Claude.
Рівень росте з досвідом, а досягнення відкривають нові скіни (skins.LOCKED).
Зберігається в ~/.config/claude-buddy/progress.json.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Callable

import storage
import words

FILE = "progress.json"
KEEP_DAYS = 30  # скільки днів статистики пам'ятати

# Скільки досвіду дає кожна подія.
XP = {
    "pomodoro": 20,
    "word": 10,
    "quiz": 5,
    "catch": 1,
    "claude": 2,
    "feed": 1,
    "pet": 0,
    "dance_min": 1,
    "reminder": 3,
    "night": 0,
    "lesson": 30,
    "lesson_answer": 1,
}


def level_for(xp: int) -> int:
    """Рівень 2 — 25 XP, 3 — 100, 4 — 225, 5 — 400… (кожен наступний довший)."""
    return 1 + math.isqrt(max(0, xp) // 25)


def xp_for(level: int) -> int:
    """Скільки досвіду потрібно, щоб досягти рівня."""
    return 25 * (level - 1) ** 2


@dataclass
class Progress:
    xp: int = 0
    totals: dict[str, int] = field(default_factory=dict)  # подія -> скільки разів за весь час
    daily: dict[str, dict[str, int]] = field(default_factory=dict)  # ISO-дата -> подія -> скільки
    best: dict[str, int] = field(default_factory=dict)  # рекорди: catch, quiz_streak
    unlocked: list[str] = field(default_factory=list)  # отримані досягнення
    quiz_streak: int = 0
    day_streak: int = 0
    last_day: str = ""
    word_book: dict[str, dict] = field(default_factory=dict)  # див. words.review
    word_of_day: dict[str, str] = field(default_factory=dict)  # {"day": ISO, "en": слово}
    lesson: dict = field(default_factory=dict)  # {"day": ISO, "new": [слова], "done": bool}

    @property
    def level(self) -> int:
        return level_for(self.xp)

    def today(self, day: dt.date) -> dict[str, int]:
        return self.daily.get(day.isoformat(), {})

    def known_words(self) -> int:
        return words.known_count(self.word_book)


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    description: str
    check: Callable[[Progress], bool]
    reward: tuple[str, str] | None = None  # (слот, аксесуар), який відкривається


def _total(key: str, n: int) -> Callable[[Progress], bool]:
    return lambda p: p.totals.get(key, 0) >= n


ACHIEVEMENTS: list[Achievement] = [
    Achievement("first_task", "Перша спільна задача", "Claude закінчив першу відповідь", _total("claude", 1)),
    Achievement("claude_50", "Напарник Claude", "50 відповідей Claude", _total("claude", 50), ("head", "halo")),
    Achievement("first_pomo", "Перша помідорка", "Завершити одне помодоро", _total("pomodoro", 1)),
    Achievement("pomo_25", "Майстер фокусу", "25 помодоро", _total("pomodoro", 25), ("head", "tomato_hat")),
    Achievement("words_10", "Перші 10 слів", "Вивчити 10 слів у вікторині", lambda p: p.known_words() >= 10),
    Achievement("words_40", "Ходячий словник", "Вивчити 40 слів", lambda p: p.known_words() >= 40,
                ("head", "grad_cap")),
    Achievement("quiz_streak_5", "Без помилок", "5 правильних відповідей поспіль",
                lambda p: p.best.get("quiz_streak", 0) >= 5, ("face", "star_glasses")),
    Achievement("catch_15", "Спритні руки", "Спіймати бадді 15 разів за гру",
                lambda p: p.best.get("catch", 0) >= 15, ("head", "sweatband")),
    Achievement("dance_30", "Танцюрист", "30 хвилин танців під музику", _total("dance_min", 30), ("body", "disco")),
    Achievement("feed_50", "Турботливий", "Погодувати бадді 50 разів", _total("feed", 50)),
    Achievement("days_7", "Тиждень разом", "7 днів поспіль з бадді", lambda p: p.day_streak >= 7),
    Achievement("level_5", "П'ятий рівень", "Дійти до 5-го рівня", lambda p: p.level >= 5, ("body", "royal_cape")),
    Achievement("night_owl", "Нічна сова", "Працювати після 2-ї ночі", _total("night", 1)),
    Achievement("reminders_10", "Нічого не забуваю", "10 спрацьованих нагадувань", _total("reminder", 10)),
    Achievement("lesson_1", "Перший урок", "Пройти перший урок англійської", _total("lesson", 1)),
    Achievement("lesson_30", "Місяць навчання", "Пройти 30 уроків", _total("lesson", 30)),
    Achievement("words_500", "Пів тисячі", "Вивчити 500 слів", lambda p: p.known_words() >= 500),
    Achievement("words_1500", "Мета: 1500 слів!", "Вивчити 1500 слів", lambda p: p.known_words() >= 1500,
                ("head", "laurel")),
]
BY_ID = {a.id: a for a in ACHIEVEMENTS}


@dataclass
class Gains:
    """Що змінилося після події — щоб бадді міг про це сказати."""
    xp: int = 0
    level_up: int | None = None  # новий рівень, якщо він змінився
    unlocked: list[Achievement] = field(default_factory=list)


class Tracker:
    """Записує події й зберігає прогрес."""

    def __init__(self, progress: Progress | None = None, autosave: bool = True) -> None:
        self.p = progress or load()
        self.autosave = autosave

    def add(self, event: str, amount: int = 1, day: dt.date | None = None) -> Gains:
        day = day or dt.date.today()
        old_level = self.p.level
        self._touch_day(day)
        self.p.totals[event] = self.p.totals.get(event, 0) + amount
        today = self.p.daily.setdefault(day.isoformat(), {})
        today[event] = today.get(event, 0) + amount
        gained = XP.get(event, 0) * amount
        self.p.xp += gained
        return self._finish(old_level, gained)

    def record_best(self, key: str, value: int) -> Gains:
        old_level = self.p.level
        if value > self.p.best.get(key, 0):
            self.p.best[key] = value
        return self._finish(old_level, 0)

    def quiz_answer(self, word: words.Word, correct: bool, day: dt.date | None = None,
                    event: str = "quiz") -> Gains:
        day = day or dt.date.today()
        words.review(self.p.word_book, word, correct, day)
        if correct:
            self.p.quiz_streak += 1
            best = self.record_best("quiz_streak", self.p.quiz_streak)
            gains = self.add(event, day=day)
            gains.unlocked = best.unlocked + gains.unlocked  # інакше рекордне досягнення загубилось би
            return gains
        self.p.quiz_streak = 0
        return self._finish(self.p.level, 0)

    def finish_lesson(self, day: dt.date | None = None) -> Gains:
        """Урок пройдено: досвід — лише раз на день, навіть якщо пройдеш ще раз."""
        day = day or dt.date.today()
        if self.p.lesson.get("day") == day.isoformat() and self.p.lesson.get("done"):
            return self._finish(self.p.level, 0)
        self.p.lesson = {**self.p.lesson, "day": day.isoformat(), "done": True}
        return self.add("lesson", day=day)

    def word_of_day(self, day: dt.date, pool: list[words.Word]) -> words.Word:
        """Одне слово на весь день, навіть якщо за день щось вивчиш."""
        saved = self.p.word_of_day
        if saved.get("day") == day.isoformat() and saved.get("en") in words.BY_EN:
            word = words.BY_EN[saved["en"]]
            if word in pool:
                return word
        word = words.word_of_day(day, pool, self.p.word_book)
        self.p.word_of_day = {"day": day.isoformat(), "en": word.en}
        self.save()
        return word

    def _touch_day(self, day: dt.date) -> None:
        """Рахує, скільки днів поспіль ти з бадді."""
        today = day.isoformat()
        if self.p.last_day == today:
            return
        yesterday = (day - dt.timedelta(days=1)).isoformat()
        self.p.day_streak = self.p.day_streak + 1 if self.p.last_day == yesterday else 1
        self.p.last_day = today
        # Стара статистика не потрібна — файл не росте безкінечно.
        cutoff = (day - dt.timedelta(days=KEEP_DAYS)).isoformat()
        self.p.daily = {d: v for d, v in self.p.daily.items() if d >= cutoff}

    def _finish(self, old_level: int, gained: int) -> Gains:
        gains = Gains(xp=gained)
        if self.p.level > old_level:
            gains.level_up = self.p.level
        for achievement in ACHIEVEMENTS:
            if achievement.id not in self.p.unlocked and achievement.check(self.p):
                self.p.unlocked.append(achievement.id)
                gains.unlocked.append(achievement)
        if self.autosave:
            self.save()
        return gains

    def is_unlocked(self, achievement_id: str) -> bool:
        return achievement_id in self.p.unlocked

    def save(self) -> None:
        if self.autosave:
            save(self.p)


def load() -> Progress:
    data = storage.load_json(FILE, {})
    p = Progress()
    try:
        p.xp = max(0, int(data.get("xp", 0)))
        p.quiz_streak = max(0, int(data.get("quiz_streak", 0)))
        p.day_streak = max(0, int(data.get("day_streak", 0)))
    except (TypeError, ValueError):
        pass
    p.last_day = str(data.get("last_day", ""))
    for name in ("totals", "best"):
        value = data.get(name)
        if isinstance(value, dict):
            setattr(p, name, {str(k): int(v) for k, v in value.items() if isinstance(v, int)})
    daily = data.get("daily")
    if isinstance(daily, dict):
        p.daily = {str(d): {str(k): int(v) for k, v in day.items() if isinstance(v, int)}
                   for d, day in daily.items() if isinstance(day, dict)}
    unlocked = data.get("unlocked")
    if isinstance(unlocked, list):
        p.unlocked = [a for a in unlocked if a in BY_ID]
    book = data.get("word_book")
    if isinstance(book, dict):
        p.word_book = {k: v for k, v in book.items() if isinstance(v, dict)}
    wod = data.get("word_of_day")
    if isinstance(wod, dict):
        p.word_of_day = {str(k): str(v) for k, v in wod.items()}
    lesson = data.get("lesson")
    if isinstance(lesson, dict) and isinstance(lesson.get("new", []), list):
        p.lesson = {"day": str(lesson.get("day", "")), "new": [str(w) for w in lesson.get("new", [])],
                    "done": bool(lesson.get("done", False))}
    return p


def save(p: Progress) -> None:
    storage.save_json(FILE, {
        "xp": p.xp,
        "totals": p.totals,
        "daily": p.daily,
        "best": p.best,
        "unlocked": p.unlocked,
        "quiz_streak": p.quiz_streak,
        "day_streak": p.day_streak,
        "last_day": p.last_day,
        "word_book": p.word_book,
        "word_of_day": p.word_of_day,
        "lesson": p.lesson,
    })
