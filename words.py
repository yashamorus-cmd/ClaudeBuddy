"""Англійські слова: «Слово дня», вікторина, уроки й розумне повторення.

Самі слова лежать у wordlist.tsv (по рядку на слово, від простих A1 до складніших B1):
    слово <TAB> переклад <TAB> приклад <TAB> переклад прикладу <TAB> тема <TAB> рівень
Щоб додати слово — допиши рядок у той файл.

Повторення працює за «коробками Лейтнера»: кожне слово лежить у коробці 0..6.
Відповів правильно — слово переїжджає в наступну коробку й повернеться пізніше
(через 1, 2, 4, 7… днів). Помилився — назад у коробку 0, і бадді спитає його скоро.
Слово з коробки KNOWN_BOX і вище вважається вивченим.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass
from pathlib import Path

WORDLIST = Path(__file__).resolve().parent / "wordlist.tsv"

TOPICS = {
    "general": "Повсякденні",
    "people": "Люди й сім'я",
    "home": "Дім",
    "food": "Їжа",
    "time": "Час і числа",
    "body": "Тіло й здоров'я",
    "describe": "Прикметники й прислівники",
    "verbs": "Дієслова",
    "travel": "Подорожі",
    "city": "Місто й транспорт",
    "shopping": "Покупки й гроші",
    "nature": "Природа й погода",
    "hobby": "Спорт і хобі",
    "work": "Робота й навчання",
    "feelings": "Почуття й характер",
    "it": "IT і програмування",
    "media": "Медіа й суспільство",
    "phrasal": "Фразові дієслова",
    "linking": "Зв'язки й абстрактні слова",
}
LEVELS = ("A1", "A2", "B1")


@dataclass(frozen=True)
class Word:
    en: str
    uk: str
    example_en: str
    example_uk: str
    topic: str = "general"
    level: str = "A1"


def load_words(path: Path = WORDLIST) -> list[Word]:
    """Читає словник; биті рядки й повтори пропускає, а не падає."""
    result: list[Word] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        fields = [f.strip() for f in line.split("\t")]
        if len(fields) != 6 or not all(fields):
            continue
        en, uk, example_en, example_uk, topic, level = fields
        if en in seen or topic not in TOPICS or level not in LEVELS:
            continue
        seen.add(en)
        result.append(Word(en, uk, example_en, example_uk, topic, level))
    return result


WORDS: list[Word] = load_words()

BY_EN = {w.en: w for w in WORDS}
BOX_DAYS = [0, 1, 2, 4, 7, 14, 30]  # через скільки днів повторити слово з коробки N
KNOWN_BOX = 3


def pool(topics: dict[str, bool] | None = None) -> list[Word]:
    """Слова увімкнених тем; якщо вимкнено все — усі слова, щоб було з чого вчити."""
    if not topics:
        return list(WORDS)
    chosen = [w for w in WORDS if topics.get(w.topic, False)]
    return chosen or list(WORDS)


# --- розумне повторення ---------------------------------------------------------
def _entry(book: dict, word: Word) -> dict | None:
    entry = book.get(word.en)
    return entry if isinstance(entry, dict) else None


def box(book: dict, word: Word) -> int:
    entry = _entry(book, word)
    try:
        return max(0, min(len(BOX_DAYS) - 1, int(entry["box"]))) if entry else 0
    except (KeyError, TypeError, ValueError):
        return 0


def due(book: dict, word: Word) -> dt.date | None:
    """Коли повторити; None — слово ще жодного разу не траплялося."""
    entry = _entry(book, word)
    if not entry:
        return None
    try:
        return dt.date.fromisoformat(entry["due"])
    except (KeyError, TypeError, ValueError):
        return None


def review(book: dict, word: Word, correct: bool, day: dt.date) -> None:
    """Записує відповідь у «зошит» book: переносить слово в іншу коробку."""
    entry = _entry(book, word) or {"box": 0, "wrong": 0}
    level = box(book, word)
    if correct:
        level = min(level + 1, len(BOX_DAYS) - 1)
    else:
        level = 0
        entry["wrong"] = int(entry.get("wrong", 0)) + 1
    entry["box"] = level
    entry["due"] = (day + dt.timedelta(days=BOX_DAYS[level])).isoformat()
    book[word.en] = entry


def mark_seen(book: dict, word: Word, day: dt.date) -> None:
    """Слово дня показали: воно потрапляє в зошит, але ще не вивчене."""
    if _entry(book, word) is None:
        book[word.en] = {"box": 1, "wrong": 0, "due": (day + dt.timedelta(days=1)).isoformat()}


def known_count(book: dict, words: list[Word] | None = None) -> int:
    return sum(1 for w in (words or WORDS) if box(book, w) >= KNOWN_BOX)


def word_of_day(day: dt.date, words: list[Word], book: dict) -> Word:
    """Слово, якого ти ще не знаєш; якщо знаєш усі — просто по колу."""
    fresh = [w for w in words if box(book, w) < KNOWN_BOX] or words
    return fresh[day.toordinal() % len(fresh)]


def is_seen(book: dict, word: Word) -> bool:
    return _entry(book, word) is not None


def mark_known(book: dict, word: Word, day: dt.date) -> None:
    """«Я вже знаю це слово» на уроці: одразу у коробку вивчених, повторимо через тиждень."""
    entry = _entry(book, word) or {"wrong": 0}
    entry["box"] = KNOWN_BOX
    entry["due"] = (day + dt.timedelta(days=BOX_DAYS[KNOWN_BOX])).isoformat()
    book[word.en] = entry


def due_words(words: list[Word], book: dict, day: dt.date) -> list[Word]:
    """Знайомі слова, яких час повторити: найпростроченіші й найслабші — першими."""
    ready = [w for w in words if is_seen(book, w) and (due(book, w) or day) <= day]
    return sorted(ready, key=lambda w: (due(book, w) or day, box(book, w)))


def pick_quiz_word(words: list[Word], book: dict, day: dt.date, rng: random.Random) -> Word:
    """Для вікторини в меню: спершу знайомі слова, яких час повторити, особливо ті,
    в яких ти помилявся; якщо таких немає — знайомі; якщо й таких немає — перші нові."""
    ready = due_words(words, book, day)
    if not ready:
        ready = [w for w in words if is_seen(book, w)] or words[:50]
    weights = []
    for w in ready:
        entry = _entry(book, w)
        if entry and int(entry.get("wrong", 0)) > 0 and box(book, w) < KNOWN_BOX:
            weights.append(4.0)  # уже плутав — повторимо частіше
        else:
            weights.append(1.0)
    return rng.choices(ready, weights=weights, k=1)[0]


@dataclass(frozen=True)
class Question:
    word: Word
    options: tuple[str, ...]  # варіанти, серед яких один правильний
    direction: str = "en"  # "en": бачиш англійське, обираєш переклад; "uk": навпаки

    @property
    def prompt(self) -> str:
        return self.word.en if self.direction == "en" else self.word.uk

    @property
    def correct(self) -> str:
        return self.word.uk if self.direction == "en" else self.word.en


def make_question(word: Word, words: list[Word], rng: random.Random, direction: str = "en") -> Question:
    """Три хибні варіанти — бажано тієї ж теми й рівня: так вгадати важче, а вчиш більше."""
    def answer(w: Word) -> str:
        return w.uk if direction == "en" else w.en

    right = answer(word)
    # Слово з таким самим перекладом (suggest / offer — «пропонувати») теж було б правильним,
    # тож хибними варіантами його не показуємо.
    def fits(w: Word) -> bool:
        return answer(w) != right and w.uk != word.uk

    for candidates in (
        [w for w in words if w.topic == word.topic and w.level == word.level],
        [w for w in words if w.level == word.level],
        words,
        WORDS,
    ):
        wrong = sorted({answer(w) for w in candidates if fits(w)})
        if len(wrong) >= 3:
            break
    options = [right, *rng.sample(wrong, 3)]
    rng.shuffle(options)
    return Question(word, tuple(options), direction)


def random_question(words: list[Word] | None = None, book: dict | None = None,
                    day: dt.date | None = None, rng: random.Random | None = None) -> Question:
    rng = rng or random.Random()
    words = words or list(WORDS)
    word = pick_quiz_word(words, book or {}, day or dt.date.today(), rng)
    return make_question(word, words, rng, "en")
