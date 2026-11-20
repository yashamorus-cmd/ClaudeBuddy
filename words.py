"""Англійські слова для «Слова дня» і вікторини.

Щоб додати слово — допиши рядок у WORDS: слово, переклад, приклад і переклад прикладу.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    en: str
    uk: str
    example_en: str
    example_uk: str


WORDS: list[Word] = [
    Word("apple", "яблуко", "I eat an apple every day.", "Я їм яблуко щодня."),
    Word("friend", "друг", "You are my best friend.", "Ти мій найкращий друг."),
    Word("happy", "щасливий", "I feel happy today.", "Я сьогодні щасливий."),
    Word("hungry", "голодний", "The buddy is hungry.", "Бадді голодний."),
    Word("water", "вода", "Don't forget to drink water.", "Не забудь пити воду."),
    Word("house", "будинок", "My house is near the park.", "Мій будинок біля парку."),
    Word("book", "книга", "This book is very interesting.", "Ця книга дуже цікава."),
    Word("morning", "ранок", "Good morning, everyone!", "Доброго ранку всім!"),
    Word("night", "ніч", "The night is dark and quiet.", "Ніч темна й тиха."),
    Word("tree", "дерево", "There is a big tree outside.", "Надворі росте велике дерево."),
    Word("sun", "сонце", "The sun is shining.", "Світить сонце."),
    Word("rain", "дощ", "Take an umbrella, it's raining.", "Візьми парасольку, йде дощ."),
    Word("snow", "сніг", "The snow is white and soft.", "Сніг білий і м'який."),
    Word("weather", "погода", "The weather is nice today.", "Сьогодні гарна погода."),
    Word("window", "вікно", "Open the window, please.", "Відчини вікно, будь ласка."),
    Word("kitchen", "кухня", "We cook in the kitchen.", "Ми готуємо на кухні."),
    Word("tired", "втомлений", "I'm tired after work.", "Я втомився після роботи."),
    Word("break", "перерва", "Let's take a short break.", "Зробімо коротку перерву."),
    Word("sleep", "спати", "Cats sleep a lot.", "Коти багато сплять."),
    Word("dream", "мрія / сон", "Follow your dream.", "Іди за своєю мрією."),
    Word("brave", "сміливий", "Be brave and try again.", "Будь сміливим і спробуй ще."),
    Word("kind", "добрий", "She is kind to everyone.", "Вона добра до всіх."),
    Word("clever", "розумний", "What a clever idea!", "Яка розумна ідея!"),
    Word("quiet", "тихий", "The library is quiet.", "У бібліотеці тихо."),
    Word("busy", "зайнятий", "I'm busy right now.", "Я зараз зайнятий."),
    Word("ready", "готовий", "Are you ready?", "Ти готовий?"),
    Word("easy", "легкий", "This task is easy.", "Це завдання легке."),
    Word("difficult", "складний", "The exam was difficult.", "Іспит був складний."),
    Word("future", "майбутнє", "The future is bright.", "Майбутнє світле."),
    Word("journey", "подорож", "Have a nice journey!", "Гарної подорожі!"),
    Word("mistake", "помилка", "Everyone makes mistakes.", "Усі помиляються."),
    Word("learn", "вчитися", "I learn English every day.", "Я щодня вчу англійську."),
    Word("remember", "пам'ятати", "Remember to save your work.", "Не забудь зберегти роботу."),
    Word("forget", "забувати", "Don't forget your keys.", "Не забудь ключі."),
    Word("try", "пробувати", "Try it one more time.", "Спробуй ще раз."),
    Word("build", "будувати", "Let's build something cool.", "Збудуймо щось класне."),
    Word("fix", "виправляти", "I need to fix this bug.", "Мені треба виправити цю помилку."),
    Word("save", "зберігати", "Press Ctrl+S to save.", "Натисни Ctrl+S, щоб зберегти."),
    Word("screen", "екран", "Look at the screen.", "Подивись на екран."),
    Word("keyboard", "клавіатура", "My keyboard is noisy.", "Моя клавіатура гучна."),
    Word("computer", "комп'ютер", "The computer is slow today.", "Комп'ютер сьогодні повільний."),
    Word("question", "питання", "Can I ask a question?", "Можна запитати?"),
    Word("answer", "відповідь", "That's the right answer!", "Це правильна відповідь!"),
    Word("idea", "ідея", "I have a great idea.", "У мене чудова ідея."),
    Word("team", "команда", "We are a good team.", "Ми гарна команда."),
    Word("weekend", "вихідні", "See you after the weekend.", "Побачимось після вихідних."),
    Word("holiday", "свято / відпустка", "Happy holidays!", "Щасливих свят!"),
    Word("together", "разом", "Let's do it together.", "Зробімо це разом."),
    Word("always", "завжди", "I always drink tea in the morning.", "Я завжди п'ю чай зранку."),
    Word("never", "ніколи", "Never give up!", "Ніколи не здавайся!"),
]


def word_of_day(day: dt.date) -> Word:
    """Одне слово на день, однакове весь день; наступного дня — наступне."""
    return WORDS[day.toordinal() % len(WORDS)]


@dataclass(frozen=True)
class Question:
    word: Word
    options: tuple[str, ...]  # переклади, серед яких один правильний

    @property
    def correct(self) -> str:
        return self.word.uk


def random_question(rng: random.Random | None = None) -> Question:
    rng = rng or random.Random()
    word = rng.choice(WORDS)
    others = rng.sample([w.uk for w in WORDS if w.uk != word.uk], 3)
    options = [word.uk, *others]
    rng.shuffle(options)
    return Question(word, tuple(options))
