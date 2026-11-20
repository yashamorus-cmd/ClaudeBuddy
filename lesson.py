"""Щоденний урок англійської: скільки нових слів сьогодні, щоб встигнути до мети,
і які знайомі слова час повторити.

Мета — познайомитися з усіма словами до дати мети (за замовчуванням 31 травня 2027).
Нові слова закінчуються за BUFFER_DAYS днів до неї, щоб лишився час усе повторити.
План на день фіксується зранку (при першому відкритті), тож протягом дня не «пливе».
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import words

DEFAULT_GOAL = dt.date(2027, 5, 31)
BUFFER_DAYS = 14  # нові слова закінчуємо за два тижні до мети — далі лише повторення
REVIEW_LIMIT = 30  # більше повторень за раз — уже втомлює
MIN_NEW, MAX_NEW = 3, 40
EXTRA_NEW = 5  # «Ще 5 нових слів» після уроку


def parse_goal(value: object) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return DEFAULT_GOAL


def days_for_new_words(today: dt.date, goal: dt.date) -> int:
    """Скільки днів лишилось на нові слова (включно з сьогоднішнім)."""
    return (goal - dt.timedelta(days=BUFFER_DAYS) - today).days + 1


def daily_target(unseen: int, today: dt.date, goal: dt.date) -> int:
    """Нових слів на сьогодні: рівномірно розподіляємо ті, що лишились, на дні до мети."""
    if unseen <= 0:
        return 0
    days = days_for_new_words(today, goal)
    if days <= 0:  # уже запізнюємось — учимо по максимуму
        return min(MAX_NEW, unseen)
    return min(unseen, max(MIN_NEW, min(MAX_NEW, math.ceil(unseen / days))))


@dataclass
class Plan:
    day: dt.date
    goal: dt.date
    new: list[words.Word]  # нові слова сьогоднішнього уроку
    reviews: list[words.Word]  # знайомі слова, яких час повторити
    done: bool
    total: int  # слів у словнику (з увімкнених тем)
    seen: int  # з якими вже познайомився
    known: int  # вивчені (KNOWN_BOX і вище)

    @property
    def days_left(self) -> int:
        return (self.goal - self.day).days


def today_plan(lesson_state: dict, book: dict, pool: list[words.Word], today: dt.date,
               goal: dt.date) -> tuple[Plan, dict]:
    """План уроку й оновлений стан уроку (його треба зберегти в прогресі)."""
    if lesson_state.get("day") != today.isoformat():
        unseen = [w for w in pool if not words.is_seen(book, w)]
        target = daily_target(len(unseen), today, goal)
        lesson_state = {"day": today.isoformat(), "new": [w.en for w in unseen[:target]], "done": False}
    new = [words.BY_EN[en] for en in lesson_state.get("new", []) if en in words.BY_EN]
    new_set = {w.en for w in new}
    reviews = [w for w in words.due_words(pool, book, today) if w.en not in new_set][:REVIEW_LIMIT]
    plan = Plan(
        day=today,
        goal=goal,
        new=new,
        reviews=reviews,
        done=bool(lesson_state.get("done")),
        total=len(pool),
        seen=sum(1 for w in pool if words.is_seen(book, w)),
        known=words.known_count(book, pool),
    )
    return plan, lesson_state


def add_extra(lesson_state: dict, book: dict, pool: list[words.Word], count: int = EXTRA_NEW) -> list[words.Word]:
    """Додає до сьогоднішнього уроку ще кілька нових слів (для тих, хто хоче більше)."""
    planned = set(lesson_state.get("new", []))
    extra = [w for w in pool if not words.is_seen(book, w) and w.en not in planned][:count]
    lesson_state["new"] = [*lesson_state.get("new", []), *(w.en for w in extra)]
    return extra


def status_text(plan: Plan) -> str:
    """Коротко: де ти зараз відносно мети."""
    left = plan.total - plan.seen
    if left <= 0:
        return f"🎉 Усі {plan.total} слів уже знайомі! Лишилось повторювати."
    days = days_for_new_words(plan.day, plan.goal)
    if days <= 0:
        return f"⏰ До мети мало часу: лишилось {left} нових слів — учимо по максимуму."
    per_day = math.ceil(left / days)
    noun = "нове слово" if per_day % 10 == 1 and per_day % 100 != 11 else (
        "нові слова" if 2 <= per_day % 10 <= 4 and not 12 <= per_day % 100 <= 14 else "нових слів")
    return f"Щоб встигнути до {plan.goal:%d.%m.%Y}, треба ~{per_day} {noun} на день."
