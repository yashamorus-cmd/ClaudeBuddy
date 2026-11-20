"""Вікно щоденного уроку англійської.

Урок має три кроки:
1. Картки — знайомство з новими словами: слово, переклад, приклад, 🔊 вимова.
2. Вікторина — нові слова й ті, яких час повторити, в обидва боки
   (англійське → переклад і навпаки). Помилка — слово повернеться наприкінці уроку.
3. Підсумок — що зроблено і чи встигаєш до мети.

Клавіші: 1–4 — вибір відповіді, Enter або пробіл — «Далі».
"""

from __future__ import annotations

import random

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

import lesson  # noqa: E402
import sounds  # noqa: E402
import words  # noqa: E402

AUTO_NEXT_MS = 900  # після правильної відповіді — далі саме


def esc(text: str) -> str:
    return GLib.markup_escape_text(text)


class LessonWindow(Gtk.Window):
    def __init__(self, buddy) -> None:
        super().__init__(title="Урок англійської 📚")
        self.buddy = buddy
        self.rng = random.Random()
        self.set_default_size(560, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.connect("destroy", self.on_destroy)
        self.connect("key-press-event", self.on_key)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_border_width(18)
        self.add(outer)
        self.header = Gtk.Label(xalign=0)
        outer.pack_start(self.header, False, False, 0)
        self.bar = Gtk.ProgressBar()
        outer.pack_start(self.bar, False, False, 0)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.body.set_valign(Gtk.Align.CENTER)
        outer.pack_start(self.body, True, True, 0)
        self.footer = Gtk.Box(spacing=8)
        self.footer.set_halign(Gtk.Align.END)
        outer.pack_end(self.footer, False, False, 0)

        self.option_buttons: list[Gtk.Button] = []
        self.button_options: dict[Gtk.Button, str] = {}
        self.next_action = None  # що робить Enter
        self.auto_next: int | None = None
        self.start()

    def on_destroy(self, _widget: Gtk.Widget) -> None:
        self.cancel_auto_next()
        self.buddy.lesson_window = None

    # --- lesson flow ----------------------------------------------------------
    def start(self) -> None:
        self.plan = self.buddy.lesson_plan()
        book = self.buddy.tracker.p.word_book
        self.cards = [w for w in self.plan.new if not words.is_seen(book, w)]
        self.card_index = 0
        self.stats = {"new": 0, "known": 0, "right": 0, "wrong": 0}
        self.queue: list[tuple[words.Word, str]] = []
        self.retried: set[str] = set()
        self.answered = 0
        if self.plan.done and not self.cards:
            self.show_done(already=True)
        elif self.cards:
            self.show_card()
        else:
            self.start_quiz()

    def start_quiz(self) -> None:
        book = self.buddy.tracker.p.word_book
        fresh = [w for w in self.plan.new if words.box(book, w) < words.KNOWN_BOX]
        reviews = list(self.plan.reviews)
        self.rng.shuffle(fresh)
        self.rng.shuffle(reviews)
        # Нове слово спершу питаємо «англійське → переклад», знайоме — у випадковий бік.
        self.queue = [(w, "en") for w in fresh] + [(w, self.rng.choice(("en", "uk"))) for w in reviews]
        self.total_questions = len(self.queue)
        if not self.queue:
            self.finish()
            return
        self.next_question()

    def next_question(self) -> None:
        self.cancel_auto_next()
        if not self.queue:
            self.finish()
            return
        word, direction = self.queue.pop(0)
        self.show_question(word, direction)

    def finish(self) -> None:
        gains = self.buddy.tracker.finish_lesson(self.buddy.today())
        self.buddy.lesson_finished(gains, self.stats)
        self.plan = self.buddy.lesson_plan()
        self.show_done()

    # --- screens --------------------------------------------------------------
    def clear(self) -> None:
        self.cancel_auto_next()
        for box in (self.body, self.footer):
            for child in box.get_children():
                child.destroy()
        self.option_buttons = []
        self.button_options = {}
        self.next_action = None

    def set_header(self, text: str, fraction: float) -> None:
        self.header.set_markup(f"<b>{esc(text)}</b>")
        self.bar.set_fraction(max(0.0, min(1.0, fraction)))

    def label(self, markup: str, dim: bool = False, selectable: bool = False) -> Gtk.Label:
        widget = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        widget.set_markup(markup)
        widget.set_line_wrap(True)
        widget.set_selectable(selectable)
        if dim:
            widget.get_style_context().add_class("dim-label")
        self.body.pack_start(widget, False, False, 0)
        return widget

    def speak_button(self, text: str, caption: str = "🔊") -> None:
        if not sounds.can_speak():
            return
        button = Gtk.Button(label=caption)
        button.set_halign(Gtk.Align.CENTER)
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.connect("clicked", lambda _b: sounds.speak_english(text))
        self.body.pack_start(button, False, False, 0)

    def footer_button(self, text: str, action, default: bool = False) -> Gtk.Button:
        button = Gtk.Button(label=text)
        button.connect("clicked", lambda _b: action())
        if default:
            button.get_style_context().add_class("suggested-action")
            self.next_action = action
        self.footer.pack_start(button, False, False, 0)
        return button

    def show_card(self) -> None:
        self.clear()
        word = self.cards[self.card_index]
        topic = words.TOPICS.get(word.topic, word.topic)
        self.set_header(f"Нові слова: {self.card_index + 1} з {len(self.cards)}",
                        self.card_index / max(1, len(self.cards)))
        self.label(f"<span size='small'>{esc(word.level)} · {esc(topic)}</span>", dim=True)
        self.label(f"<span size='xx-large' weight='bold'>{esc(word.en)}</span>")
        self.speak_button(word.en)
        self.label(f"<span size='x-large'>{esc(word.uk)}</span>", selectable=True)
        self.label(f"<i>{esc(word.example_en)}</i>", selectable=True)
        self.speak_button(word.example_en, "🔊 речення")
        self.label(esc(word.example_uk), dim=True, selectable=True)
        self.footer_button("Я вже знаю це слово ✓", lambda: self.card_done(word, known=True))
        next_button = self.footer_button("Запам'ятав, далі ▶", lambda: self.card_done(word, known=False),
                                         default=True)
        self.show_all()
        next_button.grab_focus()
        if self.buddy.config.get("lesson_autospeak", True):
            sounds.speak_english(word.en)

    def card_done(self, word: words.Word, known: bool) -> None:
        day = self.buddy.today()
        book = self.buddy.tracker.p.word_book
        if known:
            words.mark_known(book, word, day)
            self.stats["known"] += 1
        else:
            words.mark_seen(book, word, day)
            self.stats["new"] += 1
        self.buddy.tracker.save()
        self.card_index += 1
        if self.card_index < len(self.cards):
            self.show_card()
        else:
            self.start_quiz()

    def show_question(self, word: words.Word, direction: str) -> None:
        self.clear()
        pool = self.buddy.word_pool()
        question = words.make_question(word, pool, self.rng, direction)
        done = self.total_questions - len(self.queue) - 1
        self.set_header(f"Вікторина: {done + 1} з {self.total_questions}", done / max(1, self.total_questions))
        ask = "Як перекласти?" if direction == "en" else "Як це англійською?"
        self.label(esc(ask), dim=True)
        self.label(f"<span size='xx-large' weight='bold'>{esc(question.prompt)}</span>")
        if direction == "en":
            self.speak_button(word.en)
        self.feedback = self.label("")
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        for i, option in enumerate(question.options):
            button = Gtk.Button(label=f"{i + 1}. {option}")
            button.get_child().set_line_wrap(True)
            button.connect("clicked", lambda _b, o=option: self.answer(question, o))
            grid.attach(button, i % 2, i // 2, 1, 1)
            self.option_buttons.append(button)
            self.button_options[button] = option
        self.body.pack_start(grid, False, False, 6)
        self.show_all()

    def answer(self, question: words.Question, chosen: str) -> None:
        if not self.option_buttons or self.next_action:
            return  # уже відповів на це питання
        word = question.word
        correct = chosen == question.correct
        gains = self.buddy.tracker.quiz_answer(word, correct, self.buddy.today(), event="lesson_answer")
        self.buddy.celebrate(gains)
        # Кнопки лишаються кольоровими (сірі «вимкнені» кнопки ховають кольори);
        # повторні натискання ігнорує перевірка на початку answer().
        for button in self.option_buttons:
            option = self.button_options[button]
            if option == question.correct:
                button.get_style_context().add_class("suggested-action")
            elif option == chosen:
                button.get_style_context().add_class("destructive-action")
        if correct:
            self.stats["right"] += 1
            self.feedback.set_markup("<b>✅ Правильно!</b>")
            if question.direction == "uk":
                sounds.speak_english(word.en)
            self.auto_next = GLib.timeout_add(AUTO_NEXT_MS, self.on_auto_next)
        else:
            self.stats["wrong"] += 1
            self.feedback.set_markup(
                f"<b>❌ {esc(word.en)} — {esc(word.uk)}</b>\n<i>{esc(word.example_en)}</i>\n{esc(word.example_uk)}")
            if word.en not in self.retried:  # спитаємо ще раз наприкінці уроку
                self.retried.add(word.en)
                self.queue.append((word, "en" if question.direction == "uk" else "uk"))
                self.total_questions += 1
        next_button = self.footer_button("Далі ▶", self.next_question, default=True)
        next_button.show()
        next_button.grab_focus()

    def on_auto_next(self) -> bool:
        self.auto_next = None
        self.next_question()
        return False

    def cancel_auto_next(self) -> None:
        if self.auto_next is not None:
            GLib.source_remove(self.auto_next)
            self.auto_next = None

    def show_done(self, already: bool = False) -> None:
        self.clear()
        plan = self.plan
        self.set_header("Урок на сьогодні зроблено! 🎉" if not already else "Сьогоднішній урок уже пройдено ✅", 1.0)
        if not already:
            asked = self.stats["right"] + self.stats["wrong"]
            self.label(f"<span size='large'>Нових слів: <b>{self.stats['new']}</b>"
                       f" · уже знав: <b>{self.stats['known']}</b>\n"
                       f"Правильних відповідей: <b>{self.stats['right']}</b> з {asked}</span>")
        self.label(f"Познайомився: <b>{plan.seen}</b> з {plan.total} слів · вивчено: <b>{plan.known}</b>")
        self.label(esc(lesson.status_text(plan)), dim=True)
        self.label(f"До {plan.goal:%d.%m.%Y}: {max(0, plan.days_left)} дн.", dim=True)
        self.footer_button("Ще 5 нових слів", self.more_words)
        self.footer_button("Закрити", self.destroy, default=True)
        self.show_all()

    def more_words(self) -> None:
        extra = self.buddy.lesson_extra()
        if not extra:
            self.label("Нових слів більше немає — ти познайомився з усіма! 🎉")
            self.show_all()
            return
        self.plan = self.buddy.lesson_plan()
        self.cards = extra
        self.card_index = 0
        self.stats = {"new": 0, "known": 0, "right": 0, "wrong": 0}
        self.show_card()

    # --- keyboard -------------------------------------------------------------
    def on_key(self, _widget: Gtk.Widget, event) -> bool:
        key = event.string
        if key in ("1", "2", "3", "4") and self.option_buttons and self.next_action is None:
            index = int(key) - 1
            if index < len(self.option_buttons):
                self.option_buttons[index].clicked()
                return True
        if event.keyval in (65293, 65421, 32) and self.next_action:  # Enter, Enter на цифровій, пробіл
            self.next_action()
            return True
        return False
