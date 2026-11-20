"""Вікно налаштувань бадді: усе, що не влазить у меню, розкладено по вкладках.

Вікно лише показує стан і передає твій вибір бадді (методи set_* у buddy.py) —
сама логіка й збереження залишаються там.
"""

from __future__ import annotations

import datetime as dt
import json

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

import buddy_hook  # noqa: E402
import lesson  # noqa: E402
import progress  # noqa: E402
import skins  # noqa: E402
import sysinfo  # noqa: E402
import words  # noqa: E402

TALK_LABELS = {"often": "Часто", "normal": "Нормально", "rare": "Рідко", "never": "Ніколи"}
TOPIC_LABELS = {"tips": "Поради", "english": "Англійські вислови", "quotes": "Українські цитати"}


def hooks_installed() -> bool:
    try:
        return buddy_hook.MARK in json.dumps(json.loads(buddy_hook.SETTINGS.read_text()).get("hooks", {}))
    except (OSError, ValueError, AttributeError):
        return False


class SettingsWindow(Gtk.Window):
    PAGES = ["Загальне", "Claude і код", "Навчання", "Свята й погода", "Прогрес", "Комп'ютер"]

    def __init__(self, buddy) -> None:
        super().__init__(title="Claude Buddy — налаштування")
        self.buddy = buddy
        self.set_default_size(480, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.cpu = sysinfo.CpuLoad()
        self.achievements_shown: tuple = ()

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.add(self.notebook)
        self.build_general()
        self.build_claude()
        self.build_learning()
        self.build_holidays()
        self.build_progress()
        self.build_computer()

        self.refresh()
        self.timer = GLib.timeout_add_seconds(2, self.refresh)
        self.connect("destroy", self.on_destroy)

    def on_destroy(self, _widget: Gtk.Widget) -> None:
        GLib.source_remove(self.timer)
        self.buddy.settings_window = None

    def show_page(self, name: str) -> None:
        if name in self.PAGES:
            self.notebook.set_current_page(self.PAGES.index(name))

    # --- building blocks ----------------------------------------------------
    def page(self, title: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(16)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(box)
        self.notebook.append_page(scrolled, Gtk.Label(label=title))
        return box

    @staticmethod
    def heading(box: Gtk.Box, text: str) -> None:
        label = Gtk.Label(xalign=0)
        label.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
        label.set_margin_top(6)
        box.add(label)

    @staticmethod
    def hint(box: Gtk.Box, text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.set_line_wrap(True)
        label.get_style_context().add_class("dim-label")
        box.add(label)
        return label

    @staticmethod
    def text(box: Gtk.Box, text: str = "") -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0)
        label.set_line_wrap(True)
        label.set_selectable(True)
        box.add(label)
        return label

    @staticmethod
    def switch(box: Gtk.Box, label: str, active: bool, on_change) -> Gtk.Switch:
        row = Gtk.Box(spacing=12)
        name = Gtk.Label(label=label, xalign=0)
        name.set_line_wrap(True)
        row.pack_start(name, True, True, 0)
        widget = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
        # Підключаємо після set_active, щоб початкове значення не вважалось твоєю зміною.
        widget.connect("notify::active", lambda w, _param: on_change(w.get_active()))
        row.pack_end(widget, False, False, 0)
        box.add(row)
        return widget

    @staticmethod
    def check(box: Gtk.Box, label: str, active: bool, on_change) -> Gtk.CheckButton:
        widget = Gtk.CheckButton(label=label)
        widget.set_active(active)
        widget.connect("toggled", lambda w: on_change(w.get_active()))
        box.add(widget)
        return widget

    @staticmethod
    def button(box: Gtk.Box, label: str, on_click) -> Gtk.Button:
        widget = Gtk.Button(label=label)
        widget.set_halign(Gtk.Align.START)
        widget.connect("clicked", lambda _w: on_click())
        box.add(widget)
        return widget

    # --- pages --------------------------------------------------------------
    def build_general(self) -> None:
        b, cfg = self.buddy, self.buddy.config
        box = self.page("Загальне")
        self.heading(box, "Розмови")
        row = Gtk.Box(spacing=12)
        row.pack_start(Gtk.Label(label="Як часто говорить", xalign=0), True, True, 0)
        combo = Gtk.ComboBoxText()
        for key, label in TALK_LABELS.items():
            combo.append(key, label)
        combo.set_active_id(cfg["talk"])
        combo.connect("changed", lambda c: b.set_talk(c.get_active_id()))
        row.pack_end(combo, False, False, 0)
        box.add(row)
        self.hint(box, "Про що говорить:")
        for key, label in TOPIC_LABELS.items():
            self.check(box, label, cfg["topics"][key], lambda on, k=key: b.set_topic(k, on))

        self.heading(box, "Поведінка")
        self.switch(box, "🔕 Не заважати (без фраз, погоні за курсором і нагадувань)", cfg["dnd"], b.set_dnd)
        self.switch(box, "🔊 Звуки", cfg["sounds"], b.set_sounds)
        self.switch(box, "🚀 Запускати при вході в систему", b.is_autostart(), b.set_autostart)

    def build_claude(self) -> None:
        b, cfg = self.buddy, self.buddy.config
        box = self.page("Claude і код")
        self.heading(box, "Claude Code")
        self.switch(box, "«Готово!» і запити дозволу", cfg["claude"], b.set_claude)
        self.switch(box, "Показувати, що робить Claude (тести, коміти, файли)", cfg["claude_tools"],
                    b.set_claude_tools)
        self.hooks_label = self.hint(box, "")
        self.hooks_button = self.button(box, "Встановити хуки Claude Code", self.install_hooks)

        self.heading(box, "Коміти")
        self.switch(box, "Нагадувати про незакомічені зміни (понад 2 години)", cfg["git_reminders"],
                    b.set_git_reminders)
        self.hint(box, "Папки з проєктами (через кому):")
        entry = Gtk.Entry()
        entry.set_text(", ".join(cfg["git_roots"]))
        entry.set_placeholder_text("~/PycharmProjects, ~/Projects")
        entry.connect("activate", lambda e: b.set_git_roots(e.get_text()))
        entry.connect("focus-out-event", lambda e, _ev: b.set_git_roots(e.get_text()) and False)
        box.add(entry)
        self.hint(box, "Порожньо — бадді шукає в ~/PycharmProjects, ~/Projects, ~/code, ~/src.")

    def build_learning(self) -> None:
        b, cfg = self.buddy, self.buddy.config
        box = self.page("Навчання")
        self.heading(box, "Мета")
        self.goal_label = self.text(box)
        self.button(box, "📚 Відкрити урок", b.open_lesson)
        self.button(box, "Змінити дату мети…", b.ask_goal_date)
        self.switch(box, "Нагадувати про урок протягом дня", cfg["lesson_nudges"], b.set_lesson_nudges)
        self.switch(box, "Вимовляти нові слова вголос", cfg["lesson_autospeak"], b.set_lesson_autospeak)
        self.heading(box, "Англійська")
        self.words_label = self.text(box)
        self.hint(box, "Теми для уроків, слова дня й вікторини:")
        for key, label in words.TOPICS.items():
            count = sum(1 for w in words.WORDS if w.topic == key)
            self.check(box, f"{label} ({count})", cfg["word_topics"].get(key, True),
                       lambda on, k=key: b.set_word_topic(k, on))
        self.hint(box, "Слова, у яких ти помиляєшся, бадді питає частіше. Слово вважається вивченим, "
                       f"коли ти правильно відповів на нього {words.KNOWN_BOX} рази з перервами.")

    def build_holidays(self) -> None:
        b, cfg = self.buddy, self.buddy.config
        box = self.page("Свята й погода")
        self.heading(box, "Свята")
        self.switch(box, "Сезонні скіни на свята", cfg["seasonal"], b.set_seasonal)
        self.season_label = self.hint(box, "")
        self.birthday_label = self.text(box)
        self.button(box, "Змінити день народження…", b.ask_birthday)
        self.heading(box, "Погода")
        self.weather_label = self.text(box)
        self.button(box, "Вказати місто…", b.ask_city)
        self.button(box, "Вимкнути погоду", b.disable_weather)
        self.hint(box, "Погода — з Open-Meteo: надсилається лише назва міста й координати.")

    def build_progress(self) -> None:
        box = self.page("Прогрес")
        self.level_label = self.text(box)
        self.level_bar = Gtk.ProgressBar()
        box.add(self.level_bar)
        self.today_label = self.text(box)
        self.heading(box, "Досягнення")
        self.achievements_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add(self.achievements_box)

    def build_computer(self) -> None:
        box = self.page("Комп'ютер")
        self.heading(box, "Зараз")
        self.computer_label = self.text(box)
        self.hint(box, "Бадді попередить, якщо процесор перегріється (від 85°), закінчується пам'ять "
                       "чи місце на диску, або якщо ти понад 3 години без перерви.")

    # --- live data ----------------------------------------------------------
    def install_hooks(self) -> None:
        try:
            buddy_hook.update_settings(buddy_hook.install)
            self.buddy.say("Хуки встановлено! 🤖\nЗапрацюють у новій сесії Claude", 4)
        except (OSError, SystemExit) as e:
            self.buddy.say(f"Не вийшло: {e}", 4)
        self.refresh()

    def refresh(self) -> bool:
        b = self.buddy
        installed = hooks_installed()
        self.hooks_label.set_text("✓ Хуки Claude Code встановлено." if installed
                                  else "Хуки Claude Code не встановлено — без них бадді не знає, що робить Claude.")
        self.hooks_button.set_visible(not installed)

        p = b.tracker.p
        pool = b.word_pool()
        self.words_label.set_text(f"Вивчено {words.known_count(p.word_book, pool)} з {len(pool)} слів "
                                  f"(усього в словнику {len(words.WORDS)}).")
        plan = b.lesson_plan()
        lesson_state = "✅ пройдено" if plan.done else f"{len(plan.new)} нових, {len(plan.reviews)} повторити"
        self.goal_label.set_text(
            f"🎯 Мета — словник із {plan.total} слів до {plan.goal:%d.%m.%Y} (лишилось {max(0, plan.days_left)} дн.)\n"
            f"Познайомився: {plan.seen} · вивчено: {plan.known}\n"
            f"Сьогоднішній урок: {lesson_state}\n{lesson.status_text(plan)}")

        season = b.season
        self.season_label.set_text(f"Зараз: {season.name}" if season else "Зараз свят немає.")
        birthday = skins.parse_birthday(b.config["birthday"])
        self.birthday_label.set_text(f"🎂 День народження: {birthday[1]:02d}.{birthday[0]:02d}"
                                     if birthday else "🎂 День народження не вказано.")
        city = b.config["city"]
        if city and b.weather_now:
            w = b.weather_now
            self.weather_label.set_text(f"🌦 {city['name']}: {w.temp:+.0f}°, {w.label}")
        elif city:
            self.weather_label.set_text(f"🌦 {city['name']}: оновлюю…")
        else:
            self.weather_label.set_text("🌦 Місто не вказано.")

        level = p.level
        start, end = progress.xp_for(level), progress.xp_for(level + 1)
        self.level_label.set_text(f"🏆 Рівень {level} · {p.xp} XP (до наступного: {end - p.xp})\n"
                                  f"🔥 Днів поспіль: {p.day_streak}")
        self.level_bar.set_fraction((p.xp - start) / max(1, end - start))
        today = p.today(dt.date.today())
        self.today_label.set_text(
            "Сьогодні: "
            f"🍅 {today.get('pomodoro', 0)} · ✅ {today.get('claude', 0)} відповідей Claude · "
            f"🎯 {today.get('quiz', 0)} правильних · 🍎 {today.get('feed', 0)} · "
            f"💃 {today.get('dance_min', 0)} хв танців")
        shown = tuple(p.unlocked)
        if shown != self.achievements_shown:  # перебудовуємо список лише коли щось змінилось
            self.achievements_shown = shown
            for child in self.achievements_box.get_children():
                child.destroy()
            for a in progress.ACHIEVEMENTS:
                done = a.id in p.unlocked
                reward = ""
                if a.reward:
                    slot, acc_id = a.reward
                    reward = f" → 🎁 {skins.SLOTS[slot][1][acc_id].name}"
                label = Gtk.Label(label=f"{'✅' if done else '🔒'} {a.name} — {a.description}{reward}", xalign=0)
                label.set_line_wrap(True)
                if not done:
                    label.get_style_context().add_class("dim-label")
                self.achievements_box.add(label)
            self.achievements_box.show_all()

        lines = []
        cpu = self.cpu.percent()
        if cpu is not None:
            lines.append(f"🖥 Процесор: {cpu:.0f}%")
        temp = sysinfo.cpu_temp()
        if temp is not None:
            lines.append(f"🌡 Температура: {temp:.0f}°")
        ram = sysinfo.memory_used()
        if ram is not None:
            lines.append(f"🧠 Пам'ять: зайнято {ram:.0f}%")
        disk = sysinfo.disk_free()
        if disk is not None:
            lines.append(f"💽 Диск: вільно {disk[0]:.0f} ГБ ({disk[1]:.0f}%)")
        worked = b.worked_seconds()
        if worked is not None:
            lines.append(f"⏱ Без перерви: {int(worked // 3600)} год {int(worked % 3600 // 60)} хв")
        if b.track:
            lines.append(f"🎵 Грає: {b.track.label()}")
        self.computer_label.set_text("\n".join(lines) or "Немає даних")
        return True
