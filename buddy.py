#!/usr/bin/env python3
"""Claude Buddy: a little orange pixel creature that lives on the desktop.

Left click        -> it jumps and enjoys being petted (wakes it up if asleep).
Double click      -> it says the next phrase right away.
Drag with mouse   -> carry it somewhere else.
Right click       -> menu: feed, games, word of the day, pomodoro, skins, pet,
                     weather, settings, restart, quit.

It also reacts to Claude Code (see buddy_hook.py), dances to music, falls asleep
when you are away, reminds you about breaks, commits and your own reminders, levels up
with achievements, and restarts by itself when its own code changes.
"""

import datetime as dt
import json
import math
import os
import random
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

import claude_link
import gitwatch
import install
import lesson
import progress
import reminders
import skins
import sounds
import sysinfo
import tamagotchi
import weather
import words

# GNOME on Wayland does not let normal windows place themselves anywhere on
# screen. Under XWayland (X11 compatibility) an override-redirect window can,
# so the backend must be chosen before Gtk is imported.
os.environ.setdefault("GDK_BACKEND", "x11")

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402

import music  # noqa: E402  (uses D-Bus from gi, so it comes after the backend choice)
from lesson_window import LessonWindow  # noqa: E402
from settings_window import SettingsWindow  # noqa: E402

HERE = Path(__file__).resolve().parent
LOG_PATH = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "claude-buddy" / "log.txt"

# --- Look ---------------------------------------------------------------
ORANGE = (0.851, 0.467, 0.341)  # #D97757
ORANGE_DARK = (0.72, 0.36, 0.25)
INK = (0.13, 0.12, 0.11)
BUBBLE_BG = (1.0, 0.98, 0.95)
FONT = "Sans 12"

# Pixel-art sprite, same shape as the mascot on Claude Code's start screen.
# "#" body, "o" eye, "L"/"R" the two leg pairs that take turns while walking.
SPRITE = [
    "...############...",
    "...##o######o##...",
    ".################.",
    "...############...",
    "....L.R....L.R....",
]
PX_W, PX_H = 3.5, 7  # one sprite pixel on screen (terminal cells are tall)
FINE_H = PX_H / 2  # accessories use square pixels for finer detail (see skins.py)
BODY_HALF_W = len(SPRITE[0]) * PX_W / 2
BODY_HALF_H = len(SPRITE) * PX_H / 2
BODY_R = int(BODY_HALF_W)  # rough radius, used for margins

# The window is bigger than the character so the speech bubble fits above it
# and a pet fits on either side.
WIN_W, WIN_H = 220, 190
CX, CY = WIN_W // 2, WIN_H - 30  # character centre inside the window
PET_GAP = 8  # px between the buddy and its pet

APPLE = (
    "..G..",
    ".RRR.",
    "RRRRR",
    "RRRRR",
    ".RRR.",
)
APPLE_PALETTE = {"R": (0.85, 0.15, 0.18), "G": (0.25, 0.60, 0.25)}

# --- Behaviour ------------------------------------------------------------
FPS = 30
WALK_SPEED = 90  # px per second
CHASE_SPEED = 170
CHASE_CHANCE = 0.3
DRAG_THRESHOLD = 5  # px the mouse must move with the button held to count as a drag

# How often it talks on its own (seconds between phrases), chosen in the menu.
TALK_INTERVALS = {"often": (30, 90), "normal": (60, 180), "rare": (300, 600), "never": None}
TALK_LABELS = {"often": "Часто", "normal": "Нормально", "rare": "Рідко", "never": "Ніколи"}

# Under Wayland the buddy only sees the cursor while it is over X11 windows; elsewhere
# it gets the last known spot. So it only trusts a position that changed recently.
POINTER_FRESH_S = 3.0  # cursor moved this recently -> OK to start chasing
POINTER_LOST_S = 6.0  # no movement this long during a chase -> give up

# Sleep: nobody touched the keyboard or mouse for this long -> it dozes off.
SLEEP_IDLE_S = 10 * 60
SLEEP_IDLE_NIGHT_S = 3 * 60
NIGHT_HOURS = (23, 7)  # from 23:00 to 07:00
WAKE_IDLE_S = 3  # activity this recent wakes it up

POMODORO_WORK_S = 25 * 60
POMODORO_BREAK_S = 5 * 60
POMODORO_LONG_BREAK_S = 15 * 60  # after every 4th tomato

GAME_S = 20  # «Catch me» lasts this long
GAME_SPEED = 420
MIN_SATIETY_TO_PLAY = 15
PET_AMOUNT = 3  # mood for a pat

WEATHER_REFRESH_S = 30 * 60
CODE_CHECK_S = 2  # how often to look for changes in its own code
MUSIC_CHECK_S = 3
DANCE_BPM = 108

GIT_CHECK_S = 15 * 60  # how often to look for forgotten commits
GIT_STALE_S = 2 * 3600  # changes older than this deserve a reminder
GIT_REPEAT_S = 2 * 3600  # the same project at most this often
GIT_GAP_S = 20 * 60  # any commit reminder at most this often
GIT_DEFAULT_ROOTS = ["~/PycharmProjects", "~/Projects", "~/projects", "~/code", "~/src"]

SYSTEM_CHECK_S = 30
CPU_HOT_C = 85
RAM_FULL_PCT = 92
DISK_LOW_GB = 5
WORK_NO_BREAK_S = 3 * 3600  # this long without a break -> suggest one
BREAK_IDLE_S = 5 * 60  # away this long = you had a break

TOOL_BUBBLE_GAP_S = 4  # "Editing file…" bubbles at most this often

LESSON_NUDGE_FROM_HOUR = 10  # remind about the lesson not earlier than this
LESSON_NUDGE_EVERY_S = 3 * 3600
LESSON_NUDGES_PER_DAY = 3

BUDDY_PHRASES = [
    "Не забудь попити води! 💧",
    "Як там код? Компілюється?",
    "Зроби перерву, розімнись 🙆",
    "Я тут, якщо що 🧡",
    "Коміт уже зробив?",
    "Ти молодець!",
    "Що будуємо сьогодні?",
    "Помилка — це просто підказка",
    "Хм, цікаве вікно…",
    "Тиць-тиць по клавіатурі ⌨️",
    "Ctrl+S! Збережи файл 💾",
    "Може, час на чай? ☕",
    "Я в тебе вірю!",
]

# English expressions with a translation, so the buddy also teaches a bit.
ENGLISH_PHRASES = [
    "Keep calm and code on 😎\n(Спокійно, пиши код далі)",
    "Practice makes perfect\n(Повторення — мати навчання)",
    "Better late than never\n(Краще пізно, ніж ніколи)",
    "Every cloud has a silver lining\n(Нема лиха без добра)",
    "Easy peasy lemon squeezy 🍋\n(Простіше простого)",
    "Break a leg!\n(Ні пуху ні пера!)",
    "It's a piece of cake 🍰\n(Це дуже легко)",
    "Don't give up!\n(Не здавайся!)",
    "Take it easy\n(Не напружуйся)",
    "Rome wasn't built in a day\n(Не все робиться одразу)",
    "Time flies ⏳\n(Час летить)",
    "Hang in there!\n(Тримайся!)",
    "Hello, world! 👋\n(Привіт, світе!)",
    "It works on my machine 🤷\n(А в мене працює)",
    "You've got this!\n(Ти впораєшся!)",
    "Slow and steady wins the race 🐢\n(Тихіше їдеш — далі будеш)",
    "Actions speak louder than words\n(Вчинки важать більше за слова)",
    "Two heads are better than one\n(Одна голова добре, а дві краще)",
    "The early bird catches the worm 🐦\n(Хто рано встає, тому Бог дає)",
    "No pain, no gain 💪\n(Без зусиль немає результату)",
    "Good job! 👍\n(Гарна робота!)",
    "Learn something new every day\n(Щодня дізнавайся щось нове)",
    "Stay hungry, stay foolish\n(Стів Джобс)",
    "Talk is cheap. Show me the code.\n(Лінус Торвальдс)",
    "First, solve the problem.\nThen, write the code.\n(Джон Джонсон)",
]

UKRAINIAN_QUOTES = [
    "«Борітеся — поборете!»\n— Тарас Шевченко",
    "«І чужому научайтесь,\nй свого не цурайтесь»\n— Тарас Шевченко",
    "«Contra spem spero!»\n(Без надії сподіваюсь)\n— Леся Українка",
    "«Світ ловив мене,\nта не спіймав»\n— Григорій Сковорода",
    "«Всякому місту —\nзвичай і права»\n— Григорій Сковорода",
    "«Життя іде\nі все без коректур»\n— Ліна Костенко",
    "«Де згода в сімействі,\nде мир і тишина…»\n— Іван Котляревський",
    "Вік живи — вік учись",
    "Без труда нема плода 🍎",
    "Де хотіння, там і вміння",
    "Не святі горшки ліплять",
    "Сім разів відміряй —\nодин раз відріж ✂️",
    "Терпи, козаче, —\nотаманом будеш",
    "Не кажи «гоп»,\nпоки не перескочиш",
    "Діло майстра величає 🛠️",
    "Очі бояться, а руки роблять",
    "Хто шукає, той знаходить 🔍",
    "Крапля камінь точить 💧",
    "Друзі пізнаються в біді",
    "Наука в ліс не веде,\nа з лісу виводить 🌲",
]



TOPICS = {
    "tips": ("Поради", BUDDY_PHRASES),
    "english": ("Англійські вислови", ENGLISH_PHRASES),
    "quotes": ("Українські цитати", UKRAINIAN_QUOTES),
}
CLICK_PHRASES = ["Ой!", "Лоскотно!", "Хі-хі!", "Агов!", "Я тут!", "Мур 🧡"]
CATCH_PHRASES = ["Спіймав курсор!", "Ось ти де!", "Попався!"]
LOST_PHRASES = ["Загубив курсор 🤔", "Куди ж він подівся?", "Агов, курсоре?"]
HELD_PHRASES = ["Ей, постав мене! 😳", "Ми летимо?!", "Обережно, я крихкий!"]
DROP_PHRASES = ["Дякую!", "Тут затишно", "О, нове місце!"]
SKIN_PHRASES = ["Як я тобі? 😎", "Стильно, правда?", "Новий образ!", "Мені личить?", "Красунчик!"]
UNDRESS_PHRASES = ["Так легше 😌", "Повернувся до класики", "Мінімалізм!"]
HUNGRY_PHRASES = ["Бурчить у животику… 🍎", "Може, перекусимо?", "I'm hungry!\n(Я голодний!)",
                  "Я б з'їв яблучко 🥺"]
SAD_PHRASES = ["Мені сумно… пограймося? 🥺", "Погладь мене, будь ласка", "Нудно… 😔"]
FED_PHRASES = ["Ням-ням! 😋", "Смачно! Дякую 🧡", "Yummy!\n(Смакота!)", "Ох, наївся 😌"]
FULL_PHRASES = ["Я вже наївся 😅", "Більше не влізе!", "Maybe later, I'm full\n(Може, пізніше, я ситий)"]
TOO_HUNGRY_PHRASES = ["Я надто голодний, щоб гратися 🥺\nПогодуй мене спершу", "Сил нема… 🍎 Спершу поїсти!"]
WAKE_PHRASES = ["О, ти повернувся! 👋", "Я трішки задрімав 😴", "Ой, привіт! Я не спав, чесно 😅"]
NIGHT_PHRASES = ["Вже пізно, час спати 🌙", "Завтра доробимо? 😴", "Нічка надворі 🌙\nНе засиджуйся"]
DONE_PHRASES = ["Готово! ✅", "Claude закінчив! ✅", "Зроблено! 🎉"]

# --- Settings (what you choose in the menu) ---------------------------------
CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude-buddy" / "config.json"
DEFAULT_CONFIG = {
    "head": None,
    "face": None,
    "body": None,
    "pet": None,
    "seasonal": True,
    "talk": "normal",
    "topics": {key: True for key in TOPICS},
    "dnd": False,
    "claude": True,
    "birthday": None,  # "MM-DD"
    "city": None,  # {"name", "lat", "lon"}
    "sounds": True,
    "claude_tools": True,  # show what Claude is doing (tests, commits, files)
    "git_reminders": True,
    "git_roots": [],  # empty -> GIT_DEFAULT_ROOTS
    "word_topics": {key: True for key in words.TOPICS},
    "goal_date": lesson.DEFAULT_GOAL.isoformat(),  # learn all the words by this day
    "lesson_autospeak": True,  # say every new word aloud on its card
    "lesson_nudges": True,
}


def load_config() -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    try:
        saved = json.loads(CONFIG_PATH.read_text())
    except (OSError, ValueError):
        return config
    if not isinstance(saved, dict):
        return config
    # Anything unknown or broken falls back to the default instead of crashing.
    for slot, (_title, items) in skins.SLOTS.items():
        if saved.get(slot) in items:  # ignore accessories that no longer exist
            config[slot] = saved[slot]
    if saved.get("pet") in skins.PETS:
        config["pet"] = saved["pet"]
    for key in ("seasonal", "dnd", "claude", "sounds", "claude_tools", "git_reminders",
                "lesson_autospeak", "lesson_nudges"):
        if isinstance(saved.get(key), bool):
            config[key] = saved[key]
    roots = saved.get("git_roots")
    if isinstance(roots, list):
        config["git_roots"] = [str(r) for r in roots if isinstance(r, str) and r.strip()]
    if isinstance(saved.get("goal_date"), str):
        config["goal_date"] = lesson.parse_goal(saved["goal_date"]).isoformat()
    word_topics = saved.get("word_topics")
    if isinstance(word_topics, dict):
        for key in words.TOPICS:
            if isinstance(word_topics.get(key), bool):
                config["word_topics"][key] = word_topics[key]
    if saved.get("talk") in TALK_INTERVALS:
        config["talk"] = saved["talk"]
    topics = saved.get("topics")
    if isinstance(topics, dict):
        for key in TOPICS:
            if isinstance(topics.get(key), bool):
                config["topics"][key] = topics[key]
    if skins.parse_birthday(saved.get("birthday")):
        config["birthday"] = saved["birthday"]
    city = saved.get("city")
    if isinstance(city, dict):
        try:
            config["city"] = {"name": str(city["name"]), "lat": float(city["lat"]), "lon": float(city["lon"])}
        except (KeyError, TypeError, ValueError):
            pass
    return config


def save_config(config: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2))
        tmp.replace(CONFIG_PATH)  # atomic: a crash never leaves a half-written file
    except OSError:
        pass  # not being able to save a hat is no reason to crash


def log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")
    except OSError:
        pass


def today() -> dt.date:
    # BUDDY_DATE=2026-12-25 lets you preview seasonal skins on any day.
    override = os.environ.get("BUDDY_DATE")
    if override:
        try:
            return dt.date.fromisoformat(override)
        except ValueError:
            pass
    return dt.date.today()


def is_night(now: dt.datetime) -> bool:
    start, end = NIGHT_HOURS
    return now.hour >= start or now.hour < end


def plural(n: int, one: str, few: str, many: str) -> str:
    """Українська множина: 1 раз, 2 рази, 5 разів."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def times_word(n: int) -> str:
    return plural(n, "раз", "рази", "разів")


def duration_text(seconds: float) -> str:
    """3 години, 2 дні."""
    hours = int(seconds // 3600)
    if hours >= 48:
        days = hours // 24
        return f"{days} {plural(days, 'день', 'дні', 'днів')}"
    return f"{hours} {plural(hours, 'годину', 'години', 'годин')}"


def newest_code_mtime() -> float:
    try:
        return max((p.stat().st_mtime for p in HERE.glob("*.py")), default=0.0)
    except OSError:
        return 0.0


def code_error() -> str | None:
    """Checks that every module at least compiles, so a half-saved file never kills the buddy."""
    for path in sorted(HERE.glob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (SyntaxError, ValueError, OSError) as e:
            return f"{path.name}: {e}"
    return None


# GTK names the double-click event differently in older versions.
DOUBLE_CLICK = getattr(Gdk.EventType, "DOUBLE_BUTTON_PRESS", Gdk.EventType._2BUTTON_PRESS)


class PhraseBag:
    """Hands out phrases in random order with no repeats until the whole list is used."""

    def __init__(self, phrases: list[str]) -> None:
        self.phrases = list(phrases)
        self.bag: list[str] = []
        self.last: str | None = None

    def next(self) -> str | None:
        if not self.phrases:
            return None
        if not self.bag:
            self.bag = random.sample(self.phrases, len(self.phrases))
            # Do not start a new round with the phrase that just ended the previous one.
            if len(self.bag) > 1 and self.bag[-1] == self.last:
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
        self.last = self.bag.pop()
        return self.last


class IdleMonitor:
    """How long nobody touched the keyboard or mouse. GNOME tells this even under Wayland."""

    def __init__(self) -> None:
        try:
            self.bus: Gio.DBusConnection | None = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self.bus = None

    def seconds(self) -> float | None:
        if self.bus is None:
            return None
        try:
            reply = self.bus.call_sync(
                "org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core",
                "org.gnome.Mutter.IdleMonitor", "GetIdletime", None,
                GLib.VariantType.new("(t)"), Gio.DBusCallFlags.NONE, 500, None,
            )
        except GLib.Error:
            self.bus = None  # not GNOME: the buddy just never falls asleep on its own
            return None
        return reply.unpack()[0] / 1000


class Buddy(Gtk.Window):
    def __init__(self, app: Gtk.Application) -> None:
        # POPUP = override-redirect: no frame, no taskbar entry, free placement.
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_application(app)
        self.set_app_paintable(True)
        self.set_default_size(WIN_W, WIN_H)
        self.set_keep_above(True)

        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)  # lets the background be transparent

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("realize", self.on_realize)
        self.connect("destroy", self.on_destroy)

        self.config = load_config()
        self.life = tamagotchi.load()
        self.needs = self.life.needs

        self.x, self.y = self.start_position()
        self.target = (self.x, self.y)
        self.facing = 1  # 1 = looking right, -1 = left (the pet walks behind)

        self.state = "rest"  # rest / walk / chase / held / sleep / game
        self.state_time = 2.0
        self.look = (0.0, 0.0)
        self.step_phase = 0.0
        self.wobble = 0.0
        self.jump_t = 0.0
        self.jumps_left = 0
        self.feed_t = 0.0  # apple falling into its mouth
        self.blink_t = random.uniform(2, 5)
        self.phrase = ""
        self.phrase_t = 0.0
        self.queue: list[tuple[str, float | None]] = []  # phrases waiting for the bubble to free up
        self.next_phrase_t = random.uniform(20, 40)  # the first one comes a bit sooner
        self.phrases = PhraseBag(self.topic_phrases())
        self.quitting = False
        self.restarting = False
        self.menu: Gtk.Menu | None = None
        self.timers: dict[str, float] = {}
        self.game: dict | None = None
        self.pomo: dict | None = None
        self.idle = IdleMonitor()
        self.night_key = ""
        self.was_hungry = self.needs.hungry
        self.weather_now: weather.Weather | None = None
        self.weather_busy = False
        self.code_loaded = newest_code_mtime()
        self.code_seen = self.code_loaded
        self.code_seen_at = time.monotonic()

        self.tracker = progress.Tracker()
        self.sound = sounds.Player()
        self.sound.prepare()
        self.music = music.MusicWatcher()
        self.track: music.Track | None = None
        self.announced_track: music.Track | None = None
        self.dance_t = 0.0  # seconds danced since the last full minute
        self.reminders = reminders.load()
        self.light_phrase = False  # the bubble shows a minor note that anything may replace
        self.last_light = 0.0
        self.settings_window: SettingsWindow | None = None
        self.lesson_window: LessonWindow | None = None
        self.lesson_nudges: dict[str, object] = {"day": "", "count": 0, "last": -math.inf}
        self.warned: dict[str, float] = {}  # warning -> when it was last said (monotonic)
        self.active_since: float | None = None  # when you sat down at the computer (Unix time)
        self.next_break_nag = 0.0
        self.owl_key = ""
        self.git_busy = False
        self.git_warned: dict[str, float] = {}
        self.git_last = -math.inf
        # Not right at start: first say hello, then nag about commits.
        self.timers["git"] = time.monotonic() + 120
        self.timers["lesson"] = time.monotonic() + 90

        self.outfit: dict[str, skins.Accessory] = {}
        self.season: skins.Season | None = None
        self.refresh_outfit()

        # Claude Code hooks talk to us through a local socket (see claude_link.py).
        self.claude: claude_link.Listener | None = None
        try:
            self.claude = claude_link.Listener()
            GLib.io_add_watch(self.claude.fileno(), GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN,
                              self.on_claude_event)
        except OSError as e:
            log(f"Claude Code link is off: {e}")
            self.claude = None

        if os.environ.pop("BUDDY_RESTARTED", None):
            self.say("Я оновився! ✨", 3)
        elif self.season and self.season.greeting:
            self.say(self.season.greeting, 4)
        self.maybe_word_of_day()

        # Last seen cursor position and when it last changed (see POINTER_FRESH_S).
        self.last_pointer = self.pointer()
        self.pointer_moved_at = 0.0

        # Left button held on the buddy: (offset_x, offset_y, start_x, start_y) or None.
        self.press: tuple[float, float, float, float] | None = None
        self.dragging = False

        self.move_window()
        GLib.timeout_add(1000 // FPS, self.tick)

    # --- Setup ------------------------------------------------------------
    def on_realize(self, _widget: Gtk.Widget) -> None:
        self.update_input_shape()

    def on_destroy(self, _widget: Gtk.Widget) -> None:
        self.save_life()
        if self.claude:
            self.claude.close()
            self.claude = None

    def update_input_shape(self) -> None:
        # Only the character (with its hat or flag) catches clicks; everything else
        # in the window passes clicks through to whatever is underneath.
        if not self.get_realized():
            return
        left = CX - BODY_HALF_W
        right = CX + BODY_HALF_W
        top = CY - BODY_HALF_H
        for acc in self.outfit.values():
            left = min(left, CX - BODY_HALF_W + acc.col * PX_W)
            right = max(right, CX - BODY_HALF_W + (acc.col + acc.width) * PX_W)
            top = min(top, CY - BODY_HALF_H + acc.row * FINE_H - acc.float_amp)
        top = int(top - 30)  # extra room above for the jump
        rect = cairo.RectangleInt(int(left), top, int(right - left) + 1, WIN_H - top)
        self.input_shape_combine_region(cairo.Region(rect))

    def start_position(self) -> tuple[float, float]:
        """After a restart — where it was; otherwise the saved spot or the bottom of the screen."""
        pos = None
        env = os.environ.pop("BUDDY_POS", None)
        if env:
            try:
                x, y = (float(v) for v in env.split(","))
                pos = (x, y)
            except ValueError:
                pass
        if pos is None and self.life.pos:
            pos = (self.life.pos[0], self.life.pos[1])
        if pos is None:
            display = Gdk.Display.get_default()
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            a = monitor.get_workarea()
            return a.x + a.width / 2, a.y + a.height - 80
        return self.clamp_to_area(pos)

    def every(self, key: str, period: float) -> bool:
        """True once per `period` seconds (and right away the first time)."""
        now = time.monotonic()
        if now >= self.timers.get(key, 0.0):
            self.timers[key] = now + period
            return True
        return False

    def save_life(self) -> None:
        self.life.pos = [self.x, self.y]
        tamagotchi.save(self.life)

    # --- Skins ------------------------------------------------------------
    def refresh_outfit(self) -> None:
        """Works out what the buddy wears: your choice, today's season and the weather."""
        outfit = {}
        for slot, (_title, items) in skins.SLOTS.items():
            if self.config.get(slot) in items and self.skin_unlocked(slot, self.config[slot]):
                outfit[slot] = items[self.config[slot]]
        if self.config["seasonal"]:
            self.season = skins.active_season(today(), skins.parse_birthday(self.config["birthday"]))
        else:
            self.season = None
        if self.season:
            outfit.update(self.season.outfit)  # the season wins only in the slots it uses
        if self.weather_now and self.weather_now.kind in ("rain", "storm"):
            outfit["weather"] = skins.WEATHER["umbrella"]
        self.outfit = outfit
        self.update_input_shape()

    def skin_unlocked(self, slot: str, acc_id: str) -> bool:
        achievement = skins.LOCKED.get(slot, {}).get(acc_id)
        return achievement is None or self.tracker.is_unlocked(achievement)

    def body_color(self) -> tuple[float, float, float]:
        base = (self.season and self.season.body_color) or ORANGE
        # A hungry or sad buddy looks paler, so you notice without opening the menu.
        worst = self.needs.wellbeing
        if worst >= tamagotchi.HUNGRY:
            return base
        k = (tamagotchi.HUNGRY - worst) / tamagotchi.HUNGRY * 0.55
        grey = sum(base) / 3
        return tuple(c + (grey - c) * k for c in base)

    def eye_color(self) -> tuple[float, float, float]:
        return (self.season and self.season.eye_color) or INK

    def accessories_top(self) -> float:
        """How far (px) the highest accessory sticks out above the head."""
        top = 0.0
        for acc in self.outfit.values():
            top = min(top, acc.row * FINE_H - acc.float_amp)
        return -top

    def set_accessory(self, slot: str, acc_id: str | None) -> None:
        if self.config.get(slot) == acc_id:
            return
        self.config[slot] = acc_id
        save_config(self.config)
        self.refresh_outfit()
        self.start_jump()
        self.say(random.choice(SKIN_PHRASES if acc_id else UNDRESS_PHRASES), 2.5)

    def set_pet(self, pet_id: str | None) -> None:
        if self.config["pet"] == pet_id:
            return
        self.config["pet"] = pet_id
        save_config(self.config)
        self.start_jump()
        pet = skins.PETS.get(pet_id) if pet_id else None
        self.say(f"{pet.name} тепер зі мною! {pet.sound}" if pet else "Бувай, друже 👋", 2.5)

    def set_seasonal(self, enabled: bool) -> None:
        if self.config["seasonal"] == enabled:
            return
        self.config["seasonal"] = enabled
        save_config(self.config)
        self.refresh_outfit()
        if enabled and self.season:
            self.say(self.season.greeting or random.choice(SKIN_PHRASES), 3)

    # --- Settings ---------------------------------------------------------
    def topic_phrases(self) -> list[str]:
        return [p for key, (_title, phrases) in TOPICS.items() if self.config["topics"][key] for p in phrases]

    def set_talk(self, talk: str) -> None:
        self.config["talk"] = talk
        save_config(self.config)
        interval = TALK_INTERVALS[talk]
        if interval:
            self.next_phrase_t = random.uniform(*interval)
        self.say("Добре, буду мовчати 🤐" if interval is None else "Добре! 👌", 2)

    def set_topic(self, key: str, enabled: bool) -> None:
        self.config["topics"][key] = enabled
        save_config(self.config)
        self.phrases = PhraseBag(self.topic_phrases())

    def set_claude(self, enabled: bool) -> None:
        self.config["claude"] = enabled
        save_config(self.config)
        self.say("Стежу за Claude 👀" if enabled else "Більше не слідкую за Claude", 2)

    def set_sounds(self, enabled: bool) -> None:
        self.config["sounds"] = enabled
        save_config(self.config)
        if enabled:
            self.sound.play("done")
        self.say("Звук увімкнено 🔊" if enabled else "Тиша 🔇", 2)

    def set_claude_tools(self, enabled: bool) -> None:
        self.config["claude_tools"] = enabled
        save_config(self.config)

    def set_git_reminders(self, enabled: bool) -> None:
        self.config["git_reminders"] = enabled
        save_config(self.config)

    def set_git_roots(self, text: str) -> None:
        roots = [part.strip() for part in text.split(",") if part.strip()]
        if roots != self.config["git_roots"]:
            self.config["git_roots"] = roots
            save_config(self.config)

    def set_word_topic(self, key: str, enabled: bool) -> None:
        self.config["word_topics"][key] = enabled
        save_config(self.config)

    def set_lesson_autospeak(self, enabled: bool) -> None:
        self.config["lesson_autospeak"] = enabled
        save_config(self.config)

    def set_lesson_nudges(self, enabled: bool) -> None:
        self.config["lesson_nudges"] = enabled
        save_config(self.config)

    def is_autostart(self) -> bool:
        return install.is_autostart()

    def set_autostart(self, enabled: bool) -> None:
        try:
            install.set_autostart(enabled)
        except OSError as e:
            self.say(f"Не вийшло: {e}", 3)
            return
        self.say("Буду з тобою з самого ранку! 🌅" if enabled else "Добре, запускай мене сам 🙂", 2.5)

    def open_settings(self, page: str | None = None) -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
            self.settings_window.show_all()
            self.settings_window.refresh()  # hides what should be hidden after show_all
        if page:
            self.settings_window.show_page(page)
        self.settings_window.present()

    def set_dnd(self, enabled: bool) -> None:
        self.config["dnd"] = enabled
        save_config(self.config)
        if enabled and self.state == "chase":
            self.set_state("rest", 3)
        self.say("Тихо-тихо 🤫" if enabled else "Я знову з тобою! 🧡", 2)

    # --- Menu -------------------------------------------------------------
    @staticmethod
    def menu_item(label: str, callback) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=label)
        item.connect("activate", lambda _w: callback())
        return item

    @staticmethod
    def submenu_item(label: str, submenu: Gtk.Menu) -> Gtk.MenuItem:
        item = Gtk.MenuItem(label=label)
        item.set_submenu(submenu)
        return item

    @staticmethod
    def check_item(label: str, active: bool, on_toggle) -> Gtk.CheckMenuItem:
        item = Gtk.CheckMenuItem(label=label)
        item.set_active(active)
        item.connect("toggled", lambda w: on_toggle(w.get_active()))
        return item

    @staticmethod
    def radio_menu(options: list[tuple], current, on_pick) -> Gtk.Menu:
        menu = Gtk.Menu()
        group: Gtk.RadioMenuItem | None = None
        for option in options:
            value, label = option[0], option[1]
            sensitive = option[2] if len(option) > 2 else True
            item = Gtk.RadioMenuItem.new_with_label_from_widget(group, label)
            group = group or item
            item.set_active(value == current)
            item.set_sensitive(sensitive)
            # "toggled" also fires for the item being switched off, hence get_active().
            item.connect("toggled", lambda w, v=value: w.get_active() and on_pick(v))
            menu.append(item)
        return menu

    def show_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()
        add = menu.append
        self.needs.decay()

        stats = Gtk.MenuItem(label=f"🍎 Ситість {self.needs.satiety:.0f}%  ·  💛 Настрій {self.needs.mood:.0f}%")
        stats.set_sensitive(False)
        add(stats)
        p = self.tracker.p
        next_xp = progress.xp_for(p.level + 1)
        add(self.menu_item(f"🏆 Рівень {p.level} · {p.xp}/{next_xp} XP", lambda: self.open_settings("Прогрес")))
        if self.track:
            playing = Gtk.MenuItem(label=f"🎵 {self.track.label()}"[:60])
            playing.set_sensitive(False)
            add(playing)
        if self.config["city"] and self.weather_now:
            w = self.weather_now
            forecast = Gtk.MenuItem(label=f"🌦 {self.config['city']['name']}: {w.temp:+.0f}°, {w.label}")
            forecast.set_sensitive(False)
            add(forecast)
        add(Gtk.SeparatorMenuItem())

        add(self.menu_item("Погодувати 🍎", self.feed))
        play = Gtk.Menu()
        question = words.random_question(self.word_pool(), p.word_book, today())
        quiz = Gtk.Menu()
        for option in question.options:
            quiz.append(self.menu_item(option, lambda o=option: self.answer_quiz(question, o)))
        play.append(self.submenu_item(f"🎯 Вікторина: як перекласти «{question.word.en}»?", quiz))
        record = f" (рекорд: {self.life.best_catch})" if self.life.best_catch else ""
        play.append(self.menu_item(f"🏃 Спіймай мене!{record}", self.start_game))
        add(self.submenu_item("Погратися ⚽", play))

        add(self.menu_item(self.lesson_label(), self.open_lesson))
        add(self.menu_item(f"📖 Слово дня: {self.todays_word().en}", self.tell_word))
        add(self.menu_item(self.pomodoro_label(), self.toggle_pomodoro))
        add(self.submenu_item(f"⏰ Нагадування ({len(self.reminders)})" if self.reminders else "⏰ Нагадування",
                              self.reminders_menu()))
        add(Gtk.SeparatorMenuItem())

        # Show which slots the season currently overrides, so the choice is not confusing.
        overridden = set(self.season.outfit) if self.season else set()
        for slot, (title, items) in skins.SLOTS.items():
            options = [(None, "Немає", True)]
            for acc_id, acc in items.items():
                if self.skin_unlocked(slot, acc_id):
                    options.append((acc_id, acc.name, True))
                else:
                    how = progress.BY_ID[skins.LOCKED[slot][acc_id]].description.lower()
                    options.append((acc_id, f"🔒 {acc.name} ({how})", False))
            sub = self.radio_menu(options, self.config.get(slot), lambda v, s=slot: self.set_accessory(s, v))
            add(self.submenu_item(title + (" (зараз сезонний)" if slot in overridden else ""), sub))
        pets = [(None, "Немає"), *((k, pet.name) for k, pet in skins.PETS.items())]
        add(self.submenu_item("Компаньйон 🐾", self.radio_menu(pets, self.config["pet"], self.set_pet)))
        add(Gtk.SeparatorMenuItem())

        add(self.check_item("🔕 Не заважати", self.config["dnd"], self.set_dnd))
        add(self.menu_item("⚙️ Налаштування…", self.open_settings))
        add(self.menu_item("🔄 Перезапустити", lambda: self.restart("Перезапускаюсь… 🔄")))
        add(self.menu_item("Вийти", self.quit_buddy))

        # Stand still while the menu is open, otherwise it would walk away from it.
        prev_state = (self.state, self.state_time)
        if self.state != "game":
            self.set_state("rest", math.inf)

        def on_closed(_menu: Gtk.Menu) -> None:
            if not self.quitting and self.state == "rest":
                previous = prev_state[0] if prev_state[0] not in ("held", "sleep", "game") else "rest"
                self.set_state(previous, min(prev_state[1], 5.0))
            self.menu = None

        menu.connect("deactivate", on_closed)
        menu.show_all()
        menu.attach_to_widget(self, None)
        self.menu = menu  # keep a reference so it is not garbage-collected while open
        menu.popup_at_pointer(event)

    # --- Dialogs ----------------------------------------------------------
    # Opened a moment after the menu closes: a dialog inside a closing menu misbehaves.
    @staticmethod
    def dialog(title: str) -> Gtk.Dialog:
        dialog = Gtk.Dialog(title=title)
        dialog.set_keep_above(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        return dialog

    def ask_city(self) -> None:
        GLib.idle_add(self.city_dialog)

    def city_dialog(self) -> bool:
        dialog = self.dialog("Погода для бадді")
        dialog.add_buttons("Скасувати", Gtk.ResponseType.CANCEL, "Зберегти", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.add(Gtk.Label(label="У якому місті ти живеш?"))
        entry = Gtk.Entry()
        entry.set_activates_default(True)
        entry.set_text(self.config["city"]["name"] if self.config["city"] else "")
        box.add(entry)
        note = Gtk.Label(label="Назву міста бадді надішле в Open-Meteo,\nщоб дізнаватися погоду.")
        note.get_style_context().add_class("dim-label")
        box.add(note)
        dialog.show_all()
        response = dialog.run()
        name = entry.get_text().strip()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and name:
            self.say("Шукаю місто… 🔎", 3)
            self.in_background(lambda: weather.find_city(name), self.on_city_found)
        return False

    def ask_birthday(self) -> None:
        GLib.idle_add(self.birthday_dialog)

    def birthday_dialog(self) -> bool:
        dialog = self.dialog("Твій день народження")
        dialog.add_buttons("Прибрати", 1, "Скасувати", Gtk.ResponseType.CANCEL, "Зберегти", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.add(Gtk.Label(label="Коли в тебе день народження?\nРік не важливий 🎂"))
        calendar = Gtk.Calendar()
        saved = skins.parse_birthday(self.config["birthday"])
        if saved:
            calendar.select_month(saved[0] - 1, 2000)  # 2000 is a leap year: 29 Feb fits
            calendar.select_day(saved[1])
        box.add(calendar)
        dialog.show_all()
        response = dialog.run()
        _year, month0, day = calendar.get_date()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.config["birthday"] = f"{month0 + 1:02d}-{day:02d}"
            save_config(self.config)
            old_season = self.season.name if self.season else None
            self.refresh_outfit()
            if self.season and self.season.name != old_season:
                self.attention(self.season.greeting, 5, jumps=3)
            else:
                self.say(f"Запам'ятав! 🎂 {day:02d}.{month0 + 1:02d}", 3)
        elif response == 1:
            self.config["birthday"] = None
            save_config(self.config)
            self.refresh_outfit()
            self.say("Добре, забув 🤐", 2)
        return False

    def in_background(self, work, done) -> None:
        """Runs slow work (network) in a thread and hands the result back to the GTK thread."""
        def run() -> None:
            try:
                result, error = work(), None
            except Exception as e:  # network errors come in many shapes
                result, error = None, e
            GLib.idle_add(done, result, error)

        threading.Thread(target=run, daemon=True).start()

    # --- Weather ----------------------------------------------------------
    def on_city_found(self, city: weather.City | None, error: Exception | None) -> bool:
        if error:
            log(f"city search failed: {error}")
            self.say("Не вдалося дістатися до сервера погоди 😕", 3)
        elif city is None:
            self.say("Не знайшов таке місто 🤔", 3)
        else:
            self.config["city"] = {"name": city.name, "lat": city.lat, "lon": city.lon}
            save_config(self.config)
            self.weather_now = None
            self.say(f"Тепер стежу за погодою: {city.name} 🌦", 3)
            self.fetch_weather()
        return False

    def fetch_weather(self) -> None:
        city = self.config["city"]
        if not city or self.weather_busy:
            return
        self.weather_busy = True
        place = weather.City(city["name"], city["lat"], city["lon"])
        self.in_background(lambda: weather.current(place), self.on_weather)

    def on_weather(self, now: weather.Weather | None, error: Exception | None) -> bool:
        self.weather_busy = False
        if error or now is None or not self.config["city"]:
            if error:
                log(f"weather failed: {error}")
            return False
        old = self.weather_now
        self.weather_now = now
        self.refresh_outfit()
        comment = self.weather_comment(now)
        if comment and (old is None or old.kind != now.kind) and not self.config["dnd"]:
            self.queue_say(comment, 5)
        return False

    @staticmethod
    def weather_comment(now: weather.Weather) -> str | None:
        if now.kind == "rain":
            return f"Надворі {now.label} ☔\nНе забудь парасольку!"
        if now.kind == "storm":
            return "Гроза ⛈️ Краще посидіти вдома"
        if now.kind == "snow":
            return "Сніг іде! ❄️ Одягнись тепліше"
        if now.temp <= -10:
            return f"Мороз {now.temp:.0f}° 🥶\nОдягнись тепліше!"
        if now.temp >= 30:
            return f"Спека {now.temp:+.0f}° 🥵\nПий більше води!"
        return None

    def disable_weather(self) -> None:
        self.config["city"] = None
        self.weather_now = None
        save_config(self.config)
        self.refresh_outfit()
        self.say("Добре, без погоди 🌤", 2)

    # --- Progress and sounds ----------------------------------------------
    def play_sound(self, name: str) -> None:
        if self.config["sounds"] and not self.config["dnd"]:
            self.sound.play(name)

    def celebrate(self, gains: progress.Gains) -> None:
        """Tells about a new level or achievement after anything that gave experience."""
        if gains.level_up:
            self.start_jump(3)
            self.play_sound("level")
            self.queue_say(f"Новий рівень {gains.level_up}! 🎉", 4)
        for achievement in gains.unlocked:
            text = f"🏆 Досягнення: {achievement.name}"
            if achievement.reward:
                slot, acc_id = achievement.reward
                text += f"\n🎁 Новий скін: {skins.SLOTS[slot][1][acc_id].name}"
            self.play_sound("achievement")
            self.queue_say(text, 5)

    def record(self, event: str, amount: int = 1) -> None:
        self.celebrate(self.tracker.add(event, amount, today()))

    # --- Tamagotchi -------------------------------------------------------
    def feed(self) -> None:
        self.wake_quietly()
        if not self.needs.feed():
            self.say(random.choice(FULL_PHRASES), 2.5)
            return
        self.feed_t = 0.6  # the apple falls, then it jumps for joy (see tick)
        self.was_hungry = self.needs.hungry
        self.save_life()
        self.say(random.choice(FED_PHRASES), 2.5)
        self.record("feed")

    # --- Words ------------------------------------------------------------
    def word_pool(self) -> list[words.Word]:
        return words.pool(self.config["word_topics"])

    def todays_word(self) -> words.Word:
        plan = self.lesson_plan()
        if plan.new:  # слово дня — перше з сьогоднішнього уроку
            return plan.new[0]
        return self.tracker.word_of_day(today(), self.word_pool())

    def word_text(self) -> str:
        w = self.todays_word()
        return f"📖 Слово дня: {w.en} — {w.uk}\n{w.example_en}\n({w.example_uk})"

    def tell_word(self) -> None:
        self.wake_quietly()
        self.say(self.word_text(), 9)
        words.mark_seen(self.tracker.p.word_book, self.todays_word(), today())
        day = today().isoformat()
        if self.life.learned_day != day:  # learning makes it happy, once a day
            self.life.learned_day = day
            self.needs.cheer(10)
            self.save_life()
            self.queue_say("Молодець, що вчишся! 💛", 2.5)
            self.record("word")
        else:
            self.tracker.save()

    def maybe_word_of_day(self) -> None:
        day = today().isoformat()
        if self.life.word_day != day:
            self.life.word_day = day
            self.save_life()
            self.queue_say(self.word_text(), 9)

    # --- Lessons ----------------------------------------------------------
    @staticmethod
    def today() -> dt.date:
        return today()

    def goal_date(self) -> dt.date:
        return lesson.parse_goal(self.config["goal_date"])

    def lesson_plan(self) -> lesson.Plan:
        p = self.tracker.p
        plan, state = lesson.today_plan(p.lesson, p.word_book, self.word_pool(), today(), self.goal_date())
        if state != p.lesson:
            p.lesson = state
            self.tracker.save()
        return plan

    def lesson_extra(self) -> list[words.Word]:
        p = self.tracker.p
        extra = lesson.add_extra(p.lesson, p.word_book, self.word_pool())
        self.tracker.save()
        return extra

    def lesson_label(self) -> str:
        plan = self.lesson_plan()
        if plan.done:
            return "📚 Урок зроблено ✅ (ще 5 слів?)"
        parts = []
        if plan.new:
            parts.append(f"{len(plan.new)} нових")
        if plan.reviews:
            parts.append(f"{len(plan.reviews)} повторити")
        return "📚 Урок: " + (", ".join(parts) if parts else "повторення")

    def open_lesson(self) -> None:
        self.wake_quietly()
        if self.lesson_window is None:
            self.lesson_window = LessonWindow(self)
            self.lesson_window.show_all()
        self.lesson_window.present()

    def lesson_finished(self, gains: progress.Gains, stats: dict) -> None:
        self.needs.cheer(10)
        self.save_life()
        self.play_sound("level")
        self.attention(f"Урок зроблено! 🎉\nНових слів: {stats['new']}, правильних: {stats['right']}", 5, jumps=3)
        self.celebrate(gains)

    def set_goal_date(self, day: dt.date) -> None:
        self.config["goal_date"] = day.isoformat()
        save_config(self.config)
        self.say(f"Нова мета: {day:%d.%m.%Y} 🎯", 3)

    def ask_goal_date(self) -> None:
        GLib.idle_add(self.goal_dialog)

    def goal_dialog(self) -> bool:
        dialog = self.dialog("Мета навчання")
        dialog.add_buttons("Скасувати", Gtk.ResponseType.CANCEL, "Зберегти", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.add(Gtk.Label(label="До якого дня вивчити всі слова?"))
        calendar = Gtk.Calendar()
        goal = self.goal_date()
        calendar.select_month(goal.month - 1, goal.year)
        calendar.select_day(goal.day)
        box.add(calendar)
        dialog.show_all()
        response = dialog.run()
        year, month0, day = calendar.get_date()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            chosen = dt.date(year, month0 + 1, day)
            if chosen <= today():
                self.say("Мета має бути в майбутньому 🙂", 3)
            else:
                self.set_goal_date(chosen)
        return False

    def check_lesson_nudge(self) -> None:
        """Нагадує про урок кілька разів на день, якщо він ще не пройдений."""
        if (not self.config["lesson_nudges"] or self.config["dnd"] or self.quitting
                or self.state in ("sleep", "game") or self.lesson_window is not None):
            return
        now = dt.datetime.now()
        if now.hour < LESSON_NUDGE_FROM_HOUR:
            return
        day = today().isoformat()
        if self.lesson_nudges["day"] != day:
            self.lesson_nudges = {"day": day, "count": 0, "last": -math.inf}
        if (self.lesson_nudges["count"] >= LESSON_NUDGES_PER_DAY
                or time.monotonic() - self.lesson_nudges["last"] < LESSON_NUDGE_EVERY_S):
            return
        idle = self.idle.seconds()
        if idle is not None and idle > 60:  # тебе немає за комп'ютером — нагадаємо пізніше
            return
        plan = self.lesson_plan()
        if plan.done or not (plan.new or plan.reviews):
            return
        self.lesson_nudges["count"] = int(self.lesson_nudges["count"]) + 1
        self.lesson_nudges["last"] = time.monotonic()
        self.queue_say(f"{self.lesson_label()} 📚\nПравий клік → Урок. До мети {plan.days_left} дн.!", 7)

    # --- Games ------------------------------------------------------------
    def answer_quiz(self, question: words.Question, chosen: str) -> None:
        self.wake_quietly()
        w = question.word
        correct = chosen == question.correct
        was_known = words.box(self.tracker.p.word_book, w) >= words.KNOWN_BOX
        gains = self.tracker.quiz_answer(w, correct, today())
        if correct:
            self.needs.cheer(15)
            self.needs.tire(3)
            self.start_jump(2)
            learned = not was_known and words.box(self.tracker.p.word_book, w) >= words.KNOWN_BOX
            streak = self.tracker.p.quiz_streak
            extra = "\n🎓 Слово вивчено!" if learned else (f"\n🔥 {streak} поспіль!" if streak >= 3 else "")
            self.say(f"Правильно! 🎉\n{w.en} — {w.uk}{extra}", 3.5)
        else:
            self.needs.cheer(5)  # playing is fun even when you miss
            self.say(f"Майже! 🙂\n{w.en} — {w.uk}\nЯ спитаю його ще раз", 4)
        self.save_life()
        self.celebrate(gains)

    def start_game(self) -> None:
        if self.game:
            return
        self.wake_quietly()
        if self.needs.satiety < MIN_SATIETY_TO_PLAY:
            self.say(random.choice(TOO_HUNGRY_PHRASES), 3)
            return
        self.game = {"score": 0}
        self.set_state("game", GAME_S)
        self.target = self.random_point(same_monitor=True)
        self.say("Спіймай мене! 🏃\nКлацай по мені", 2.5)

    def catch(self) -> None:
        self.game["score"] += 1
        self.start_jump()
        self.say(f"Ой! {self.game['score']} 🎯", 0.8)
        self.target = self.random_point(same_monitor=True)

    def end_game(self) -> None:
        score = self.game["score"] if self.game else 0
        self.game = None
        best = self.life.best_catch
        if score == 0:
            text = "Жодного разу не спіймав 😜\nСпробуй ще!"
        else:
            text = f"Ти спіймав мене {score} {times_word(score)}!"
            if score > best:
                self.life.best_catch = score
                text += "\nНовий рекорд! 🏆"
            else:
                text += f"\nРекорд: {best}"
        self.needs.cheer(min(5 + score * 2, 25))
        self.needs.tire(5)
        self.save_life()
        self.set_state("rest", 4)
        self.start_jump()
        self.say(text, 4)
        if score:
            self.celebrate(self.tracker.record_best("catch", score))
            self.record("catch", score)

    # --- Pomodoro ---------------------------------------------------------
    def pomodoro_label(self) -> str:
        if not self.pomo:
            return f"🍅 Помодоро: почати ({POMODORO_WORK_S // 60} хв)"
        minutes = math.ceil(max(0.0, self.pomo["ends"] - time.monotonic()) / 60)
        phase = "Робота" if self.pomo["phase"] == "work" else "Перерва"
        return f"🍅 {phase}: ще {minutes} хв — зупинити"

    def toggle_pomodoro(self) -> None:
        if self.pomo:
            self.pomo = None
            self.say("Помодоро зупинено 🍅", 2)
            return
        self.pomo = {"phase": "work", "ends": time.monotonic() + POMODORO_WORK_S, "count": 0}
        self.say(f"Погнали! {POMODORO_WORK_S // 60} хвилин фокусу 🍅", 3)

    def pomodoro_next(self) -> None:
        now = time.monotonic()
        if self.pomo["phase"] == "work":
            self.pomo["count"] += 1
            count = self.pomo["count"]
            rest_s = POMODORO_LONG_BREAK_S if count % 4 == 0 else POMODORO_BREAK_S
            self.pomo.update(phase="break", ends=now + rest_s)
            self.play_sound("break")
            self.attention(f"🍅 Помідорка №{count} готова!\nПерерва {rest_s // 60} хв ☕\n"
                           "Встань, розімнись, попий води", 10, jumps=2)
            self.go_to_center()
            self.record("pomodoro")
        else:
            self.pomo.update(phase="work", ends=now + POMODORO_WORK_S)
            self.play_sound("done")
            self.attention(f"Перерва скінчилась 💪\nНаступні {POMODORO_WORK_S // 60} хв — фокус!", 5)

    # --- Reminders --------------------------------------------------------
    def reminders_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()
        menu.append(self.menu_item("Додати…", self.ask_reminder))
        if self.reminders:
            menu.append(Gtk.SeparatorMenuItem())
        now = dt.datetime.now()
        for reminder in self.reminders:
            when = reminder.when()
            stamp = f"{when:%H:%M}" if when.date() == now.date() else f"{when:%d.%m %H:%M}"
            sub = Gtk.Menu()
            sub.append(self.menu_item("Видалити", lambda r=reminder: self.delete_reminder(r)))
            menu.append(self.submenu_item(f"{stamp} — {reminder.text[:40]}", sub))
        return menu

    def ask_reminder(self) -> None:
        GLib.idle_add(self.reminder_dialog)

    def reminder_dialog(self) -> bool:
        dialog = self.dialog("Нове нагадування")
        dialog.add_buttons("Скасувати", Gtk.ResponseType.CANCEL, "Зберегти", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.add(Gtk.Label(label="Про що нагадати?", xalign=0))
        entry = Gtk.Entry()
        entry.set_placeholder_text("Наприклад: подзвонити бабусі")
        entry.set_activates_default(True)
        box.add(entry)

        soon = dt.datetime.now() + dt.timedelta(minutes=30)
        at_row = Gtk.Box(spacing=6)
        at_radio = Gtk.RadioButton.new_with_label(None, "О котрій:")
        hour = Gtk.SpinButton.new_with_range(0, 23, 1)
        hour.set_value(soon.hour)
        minute = Gtk.SpinButton.new_with_range(0, 59, 1)
        minute.set_value(soon.minute)
        for widget in (at_radio, hour, Gtk.Label(label=":"), minute):
            at_row.pack_start(widget, False, False, 0)
        box.add(at_row)
        in_row = Gtk.Box(spacing=6)
        in_radio = Gtk.RadioButton.new_with_label_from_widget(at_radio, "Через (хвилин):")
        minutes = Gtk.SpinButton.new_with_range(1, 24 * 60, 5)
        minutes.set_value(30)
        in_row.pack_start(in_radio, False, False, 0)
        in_row.pack_start(minutes, False, False, 0)
        box.add(in_row)
        # Changing a number picks its option, so you do not have to click the circle too.
        hour.connect("value-changed", lambda _w: at_radio.set_active(True))
        minute.connect("value-changed", lambda _w: at_radio.set_active(True))
        minutes.connect("value-changed", lambda _w: in_radio.set_active(True))
        in_radio.set_active(True)

        dialog.show_all()
        response = dialog.run()
        text = entry.get_text().strip()
        now = dt.datetime.now()
        if in_radio.get_active():
            when = now + dt.timedelta(minutes=minutes.get_value_as_int())
        else:
            when = reminders.next_time(hour.get_value_as_int(), minute.get_value_as_int(), now)
        dialog.destroy()
        if response == Gtk.ResponseType.OK and text:
            self.reminders = sorted([*self.reminders, reminders.Reminder(text[:200], when.timestamp())],
                                    key=lambda r: r.at)
            reminders.save(self.reminders)
            day = "" if when.date() == now.date() else " завтра"
            self.say(f"Нагадаю{day} о {when:%H:%M} ⏰", 3)
        return False

    def delete_reminder(self, reminder: reminders.Reminder) -> None:
        self.reminders = [r for r in self.reminders if r != reminder]
        reminders.save(self.reminders)
        self.say("Видалив нагадування 🗑", 2)

    def check_reminders(self) -> None:
        now = time.time()
        due, waiting = reminders.split_due(self.reminders, now)
        if not due:
            return
        self.reminders = waiting
        reminders.save(waiting)
        for i, reminder in enumerate(due):
            late = "\n(трохи запізнився: я був вимкнений)" if now - reminder.at > 600 else ""
            if i == 0:
                self.attention(f"⏰ {reminder.text}{late}", 15, jumps=3)
            else:
                self.queue_say(f"⏰ {reminder.text}{late}", 10)
        self.play_sound("reminder")
        self.go_to_center()
        self.record("reminder", len(due))

    # --- Claude Code ------------------------------------------------------
    def on_claude_event(self, _fd: int, _condition: GLib.IOCondition) -> bool:
        if self.claude:
            for event in self.claude.read_all():
                self.handle_claude(event)
        return True  # keep listening

    def handle_claude(self, event: dict) -> None:
        kind = event.get("event")
        if kind == "quit":  # install.py --uninstall asks us to leave
            self.quit_buddy()
            return
        if self.quitting:
            return
        project = Path(str(event.get("cwd") or "")).name
        where = f"\n({project})" if project else ""
        tool = str(event.get("tool") or "")
        if kind == "stop" and self.config["claude"]:
            self.needs.cheer(2)  # finishing things together is nice
            self.play_sound("done")
            self.attention(random.choice(DONE_PHRASES) + where, 5)
            self.record("claude")
        elif kind == "notify" and self.config["claude"]:
            message = str(event.get("message") or "")
            lower = message.lower()
            if "permission" in lower:
                text = "Claude чекає на твій дозвіл 🙋"
            elif "waiting" in lower or "input" in lower:
                text = "Claude чекає на тебе ⌨️"
            else:
                text = message[:120] or "Claude кличе тебе 🔔"
            self.play_sound("attention")
            self.attention(text + where, 8, jumps=2)
        elif kind == "tool" and self.config["claude_tools"] and not self.config["dnd"]:
            text = claude_link.describe_tool(tool, str(event.get("detail") or ""))
            if text:
                self.say_light(text, 2.5)
        elif kind == "fail" and self.config["claude_tools"] and not self.config["dnd"]:
            self.say_light(claude_link.describe_failure(tool), 3, force=True)

    # --- Sleep and breaks -------------------------------------------------
    def check_sleep(self) -> None:
        idle = self.idle.seconds()
        if idle is None:
            return
        self.track_breaks(idle)
        now = dt.datetime.now()
        if self.state == "sleep":
            if idle < WAKE_IDLE_S:
                self.wake(random.choice(WAKE_PHRASES))
            return
        # With music on it dances instead of dozing off, even if you just listen.
        if self.state in ("rest", "walk") and self.menu is None and not self.quitting and not self.track:
            limit = SLEEP_IDLE_NIGHT_S if is_night(now) else SLEEP_IDLE_S
            if idle >= limit:
                self.fall_asleep()
                return
        if is_night(now) and idle < 60:
            night = (now - dt.timedelta(hours=NIGHT_HOURS[1])).date().isoformat()
            if 2 <= now.hour < 5 and night != self.owl_key:
                self.owl_key = night
                self.record("night")
            # Still at the computer late at night: say so once per night.
            if night != self.night_key and not self.config["dnd"]:
                self.night_key = night
                self.queue_say(random.choice(NIGHT_PHRASES), 4)

    def track_breaks(self, idle: float) -> None:
        """Counts how long you have been at the computer without a real break."""
        now = time.time()
        if idle >= BREAK_IDLE_S:
            self.active_since = None
            self.next_break_nag = 0.0
            return
        if self.active_since is None:
            self.active_since = now - idle
        worked = now - self.active_since
        if (worked >= WORK_NO_BREAK_S and now >= self.next_break_nag and not self.pomo
                and not self.config["dnd"] and self.state != "sleep"):
            self.next_break_nag = now + 3600
            self.queue_say(f"Ти вже {duration_text(worked)} без перерви 🙆\nВстань, розімнись!", 6)

    def worked_seconds(self) -> float | None:
        return time.time() - self.active_since if self.active_since else None

    def fall_asleep(self) -> None:
        self.set_state("sleep", math.inf)
        self.phrase = ""
        self.phrase_t = 0.0
        self.queue.clear()

    def wake(self, text: str | None = None) -> None:
        self.set_state("rest", random.uniform(2, 4))
        self.start_jump()
        if text:
            self.say(text, 2.5)

    def wake_quietly(self) -> None:
        if self.state == "sleep":
            self.set_state("rest", 3)

    # --- Music ------------------------------------------------------------
    def check_music(self) -> None:
        self.track = self.music.now_playing()
        if (self.track and self.track != self.announced_track and self.can_chat()
                and not self.phrase and not self.queue):
            self.announced_track = self.track
            artist = f"\n{self.track.artist}" if self.track.artist else ""
            self.say(f"🎵 {self.track.title}{artist}", 4)

    def dancing(self) -> bool:
        return self.track is not None and self.state == "rest" and not self.quitting

    # --- Commits and the computer -----------------------------------------
    def git_roots(self) -> list[Path]:
        roots = self.config["git_roots"] or GIT_DEFAULT_ROOTS
        return [Path(r).expanduser() for r in roots if Path(r).expanduser().is_dir()]

    def check_git(self) -> None:
        if self.git_busy or not self.config["git_reminders"] or self.config["dnd"]:
            return
        roots = self.git_roots()
        if not roots:
            return
        self.git_busy = True
        self.in_background(lambda: gitwatch.stale_repos(roots, time.time(), GIT_STALE_S), self.on_git)

    def on_git(self, stale: list | None, error: Exception | None) -> bool:
        self.git_busy = False
        if error:
            log(f"git check failed: {error}")
        if not stale or self.config["dnd"] or self.quitting:
            return False
        now = time.monotonic()
        if now - self.git_last < GIT_GAP_S:
            return False
        for repo, age in stale:
            if now - self.git_warned.get(str(repo), -math.inf) < GIT_REPEAT_S:
                continue
            self.git_warned[str(repo)] = now
            self.git_last = now
            self.queue_say(f"У {repo.name} зміни без коміту\nвже {duration_text(age)} 💾 Закомітиш?", 6)
            break
        return False

    def warn_once(self, key: str, every_s: float, text: str) -> None:
        now = time.monotonic()
        if now - self.warned.get(key, -math.inf) >= every_s:
            self.warned[key] = now
            self.queue_say(text, 5)

    def check_system(self) -> None:
        if self.config["dnd"] or self.quitting:
            return
        temp = sysinfo.cpu_temp()
        if temp is not None and temp >= CPU_HOT_C:
            self.warn_once("hot", 30 * 60, f"Процесор гарячий: {temp:.0f}° 🥵\nМоже, щось зависло?")
        ram = sysinfo.memory_used()
        if ram is not None and ram >= RAM_FULL_PCT:
            self.warn_once("ram", 30 * 60, f"Пам'ять майже заповнена: {ram:.0f}% 🧠\nЗакрий зайві вкладки")
        disk = sysinfo.disk_free()
        if disk is not None and (disk[0] < DISK_LOW_GB or disk[1] < 5):
            self.warn_once("disk", 6 * 3600, f"На диску лишилось {disk[0]:.1f} ГБ 💽\nЧас прибрати")

    # --- Restart ----------------------------------------------------------
    def check_code(self) -> None:
        """Code changed on disk -> restart with it, so updates show up without a re-login."""
        mtime = newest_code_mtime()
        now = time.monotonic()
        if mtime != self.code_seen:  # still being saved: wait until it stops changing
            self.code_seen, self.code_seen_at = mtime, now
            return
        if mtime <= self.code_loaded or now - self.code_seen_at < 2:
            return
        self.code_loaded = mtime
        error = code_error()
        if error:
            log(f"not restarting, code does not compile: {error}")
            self.say("Мій код зламався 🛠️\nЧекаю, поки виправлять", 5)
            return
        self.restart("Мене оновили! Перезапускаюсь 🔄")

    def restart(self, text: str) -> None:
        if self.restarting:
            return
        self.restarting = True
        self.quitting = True
        self.set_state("rest", math.inf)
        self.say(text, 3)
        self.save_life()
        env = dict(os.environ, BUDDY_POS=f"{self.x:.0f},{self.y:.0f}", BUDDY_RESTARTED="1")
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        # The new copy waits until this one has exited: only one buddy may run at a time.
        command = (f"sleep 1.5; exec {shlex.quote(sys.executable)} {shlex.quote(str(HERE / 'buddy.py'))}"
                   f" >>{shlex.quote(str(LOG_PATH))} 2>&1")
        subprocess.Popen(["sh", "-c", command], env=env, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        GLib.timeout_add(800, self.close_now)

    def close_now(self) -> bool:
        self.close()
        return False

    def quit_buddy(self) -> None:
        self.quitting = True
        self.set_state("rest", 999)
        self.say("Бувай! 👋", 2)
        GLib.timeout_add(1500, self.close_now)

    def hello_again(self) -> None:
        """Somebody launched a second copy: there can be only one, so this one waves."""
        if self.quitting:
            return
        self.wake_quietly()
        self.start_jump(2)
        self.say("Я тут! 👋\nЯ вже працюю", 3)

    # --- Positions on screen ----------------------------------------------
    def move_window(self) -> None:
        self.move(int(self.x - CX), int(self.y - CY))

    @staticmethod
    def workareas() -> list[Gdk.Rectangle]:
        display = Gdk.Display.get_default()
        return [display.get_monitor(i).get_workarea() for i in range(display.get_n_monitors())]

    def area_at(self, x: float, y: float) -> Gdk.Rectangle:
        """The monitor under the point, or the closest one if the point is between monitors."""
        areas = self.workareas()

        def distance(a: Gdk.Rectangle) -> float:
            dx = max(a.x - x, 0, x - (a.x + a.width))
            dy = max(a.y - y, 0, y - (a.y + a.height))
            return dx * dx + dy * dy

        return min(areas, key=distance)

    def random_point(self, same_monitor: bool = False) -> tuple[float, float]:
        a = self.area_at(self.x, self.y)
        areas = self.workareas()
        if not same_monitor and len(areas) > 1 and random.random() < 0.25:
            a = random.choice(areas)  # sometimes it goes to visit another monitor
        margin = BODY_R + 20
        return (
            random.uniform(a.x + margin, a.x + a.width - margin),
            random.uniform(a.y + 120, a.y + a.height - margin),
        )

    def clamp_to_area(self, point: tuple[float, float]) -> tuple[float, float]:
        a = self.area_at(*point)
        margin = BODY_R + 20
        return (
            min(max(point[0], a.x + margin), a.x + a.width - margin),
            min(max(point[1], a.y + 120), a.y + a.height - margin),
        )

    def go_to_center(self) -> None:
        if self.state in ("held", "game"):
            return
        a = self.area_at(self.x, self.y)
        self.target = (a.x + a.width / 2, a.y + a.height * 0.6)
        self.set_state("walk", 30.0)

    # --- Logic ------------------------------------------------------------
    def pointer(self) -> tuple[float, float]:
        seat = Gdk.Display.get_default().get_default_seat()
        _screen, px, py = seat.get_pointer().get_position()
        return float(px), float(py)

    def say(self, text: str, seconds: float | None = None) -> None:
        self.phrase = text
        self.light_phrase = False
        # Long quotes stay longer so there is time to read them.
        self.phrase_t = seconds if seconds is not None else max(4.0, len(text) / 10)

    def say_light(self, text: str, seconds: float, force: bool = False) -> None:
        """A minor note (what Claude is doing): never covers something important,
        never wakes the buddy, and does not flicker when Claude edits many files in a row."""
        now = time.monotonic()
        if self.state == "sleep" or (self.phrase and not self.light_phrase):
            return
        if not force and now - self.last_light < TOOL_BUBBLE_GAP_S:
            return
        self.last_light = now
        self.say(text, seconds)
        self.light_phrase = True

    def queue_say(self, text: str, seconds: float | None = None) -> None:
        """Says it once the current phrase is over, so it does not cut anything off."""
        if self.phrase:
            self.queue.append((text, seconds))
        else:
            self.say(text, seconds)

    def attention(self, text: str, seconds: float, jumps: int = 1) -> None:
        """Something important: wake up, jump and say it right away."""
        self.wake_quietly()
        if self.state != "held":
            self.start_jump(jumps)
        self.say(text, seconds)

    def start_jump(self, times: int = 1) -> None:
        self.jump_t = 0.6
        self.jumps_left = times - 1

    def set_state(self, state: str, seconds: float) -> None:
        self.state = state
        self.state_time = seconds

    def note_pointer(self, point: tuple[float, float]) -> None:
        if point != self.last_pointer:
            self.last_pointer = point
            self.pointer_moved_at = time.monotonic()

    def pointer_age(self) -> float:
        """Seconds since the cursor position last changed."""
        return time.monotonic() - self.pointer_moved_at

    def choose_next_action(self) -> None:
        if self.track and random.random() < 0.6:
            self.set_state("rest", random.uniform(6, 12))  # good song: keep dancing on the spot
            return
        # Chase only a cursor we can actually see right now, not a stale position.
        if (not self.config["dnd"] and random.random() < CHASE_CHANCE
                and self.pointer_age() < POINTER_FRESH_S):
            self.set_state("chase", 12.0)
        else:
            self.target = self.random_point()
            self.set_state("walk", 30.0)

    def step_towards(self, target: tuple[float, float], speed: float, dt: float) -> float:
        """Moves towards target and returns the distance that was left."""
        dx, dy = target[0] - self.x, target[1] - self.y
        dist = math.hypot(dx, dy)
        if dist > 1:
            self.look = (dx / dist, dy / dist)
            if abs(dx) > 1:
                self.facing = 1 if dx > 0 else -1
            step = min(dist, speed * dt)
            self.x += dx / dist * step
            self.y += dy / dist * step
            self.step_phase += dt * speed / 9
        return dist

    def can_chat(self) -> bool:
        return (not self.quitting and not self.config["dnd"]
                and TALK_INTERVALS[self.config["talk"]] is not None
                and self.state not in ("sleep", "game"))

    def random_phrase(self) -> str | None:
        if self.needs.hungry and random.random() < 0.5:
            return random.choice(HUNGRY_PHRASES)
        if self.needs.sad and random.random() < 0.5:
            return random.choice(SAD_PHRASES)
        return self.phrases.next()

    def periodic(self) -> None:
        """Slow checks that do not need to run 30 times a second."""
        if self.every("outfit", 60):
            # The buddy may run for days, so a season can start or end while it is on screen.
            old = self.season.name if self.season else None
            self.refresh_outfit()
            if self.season and self.season.name != old and self.season.greeting:
                self.say(self.season.greeting, 4)
        if self.every("needs", 60):
            self.needs.decay()
            if self.needs.hungry and not self.was_hungry and not self.config["dnd"]:
                self.queue_say("Я зголоднів 🥺\nПогодуй мене (правий клік)", 4)
            self.was_hungry = self.needs.hungry
            self.save_life()
        if self.every("idle", 5):
            self.check_sleep()
        if self.config["city"] and self.every("weather", WEATHER_REFRESH_S):
            self.fetch_weather()
        if not self.restarting and self.every("code", CODE_CHECK_S):
            self.check_code()
        if self.pomo and time.monotonic() >= self.pomo["ends"]:
            self.pomodoro_next()
        if self.every("reminders", 5):
            self.check_reminders()
        if self.every("music", MUSIC_CHECK_S):
            self.check_music()
        if self.every("git", GIT_CHECK_S):
            self.check_git()
        if self.every("system", SYSTEM_CHECK_S):
            self.check_system()
        if self.every("lesson", 5 * 60):
            self.check_lesson_nudge()

    def tick(self) -> bool:
        dt = 1 / FPS
        self.state_time -= dt
        self.wobble += dt
        self.note_pointer(self.pointer())
        # A hungry or sad buddy drags its feet.
        pace = 0.6 if (self.needs.hungry or self.needs.sad) else 1.0

        if self.state == "held":
            # Position follows the mouse in on_motion; here the legs just dangle.
            self.step_phase += dt * 14
        elif self.state in ("rest", "sleep"):
            self.look = (self.look[0] * 0.95, self.look[1] * 0.95)
            if self.state == "rest" and self.state_time <= 0 and not self.quitting:
                self.choose_next_action()
        elif self.state == "walk":
            if self.step_towards(self.target, WALK_SPEED * pace, dt) < 3 or self.state_time <= 0:
                self.set_state("rest", random.uniform(2, 6))
        elif self.state == "chase":
            px, py = self.last_pointer
            # Stop a bit below the cursor so the buddy does not cover it.
            if self.step_towards((px, py + 40), CHASE_SPEED * pace, dt) < 30:
                self.say(random.choice(CATCH_PHRASES), 2.5)
                self.set_state("rest", random.uniform(3, 6))
            elif self.pointer_age() > POINTER_LOST_S:
                # Probably over a Wayland window where the cursor is invisible to us.
                self.say(random.choice(LOST_PHRASES), 2.5)
                self.set_state("rest", random.uniform(3, 6))
            elif self.state_time <= 0:
                self.set_state("rest", random.uniform(2, 4))
        elif self.state == "game":
            if self.step_towards(self.target, GAME_SPEED, dt) < 5:
                self.target = self.random_point(same_monitor=True)
            if self.state_time <= 0:
                self.end_game()

        if self.jump_t > 0:
            self.jump_t = max(0.0, self.jump_t - dt)
            if self.jump_t == 0 and self.jumps_left > 0:
                self.jumps_left -= 1
                self.jump_t = 0.6
        if self.feed_t > 0:
            self.feed_t = max(0.0, self.feed_t - dt)
            if self.feed_t == 0:
                self.start_jump()
        if self.dancing():
            self.dance_t += dt
            if self.dance_t >= 60:
                self.dance_t -= 60
                self.record("dance_min")

        self.periodic()

        self.blink_t -= dt
        if self.blink_t < -0.15:
            self.blink_t = random.uniform(2, 6)

        if self.phrase_t > 0:
            self.phrase_t -= dt
            if self.phrase_t <= 0:
                self.phrase = ""
        elif self.queue:
            self.say(*self.queue.pop(0))
        elif self.can_chat():
            self.next_phrase_t -= dt
            if self.next_phrase_t <= 0:
                text = self.random_phrase()
                if text:
                    self.say(text)
                self.next_phrase_t = random.uniform(*TALK_INTERVALS[self.config["talk"]])

        self.move_window()
        self.queue_draw()
        return True  # keep the timer running

    # --- Mouse ------------------------------------------------------------
    # A click and the start of a drag look the same at first, so the decision is
    # made later: moving with the button held -> drag, releasing in place -> click.
    def on_press(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if self.quitting:
            return True
        if event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.press = None
            self.show_menu(event)
        elif event.button == 1 and self.state == "game":
            if event.type == Gdk.EventType.BUTTON_PRESS:
                self.catch()  # in the game a press counts right away, no dragging
        elif event.button == 1 and event.type == DOUBLE_CLICK:
            self.press = None
            self.wake_quietly()
            self.start_jump()
            self.say(self.phrases.next() or random.choice(CLICK_PHRASES))
        elif event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.press = (self.x - event.x_root, self.y - event.y_root, event.x_root, event.y_root)
        return True

    def on_motion(self, _widget: Gtk.Widget, event: Gdk.EventMotion) -> bool:
        # Over our own window the cursor position is always accurate, even on Wayland.
        self.note_pointer((event.x_root, event.y_root))
        if self.press is None:
            return False
        off_x, off_y, start_x, start_y = self.press
        if not self.dragging and math.hypot(event.x_root - start_x, event.y_root - start_y) > DRAG_THRESHOLD:
            self.dragging = True
            self.set_state("held", math.inf)
            self.say(random.choice(HELD_PHRASES), math.inf)
        if self.dragging:
            self.x, self.y = event.x_root + off_x, event.y_root + off_y
            self.move_window()
        return True

    def on_release(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.button != 1 or self.press is None:
            return False
        self.press = None
        if self.dragging:
            self.dragging = False
            # Dropped near an edge? Keep it fully on screen.
            self.x, self.y = self.clamp_to_area((self.x, self.y))
            self.say(random.choice(DROP_PHRASES), 2)
            self.set_state("rest", random.uniform(3, 6))
            self.save_life()
        elif self.state == "sleep":
            self.wake("Ой, я спав! 😳")
        else:
            # A click is a pat: it cheers the buddy up a little.
            self.needs.cheer(PET_AMOUNT)
            self.tracker.add("pet", day=today())
            self.start_jump()
            pet = skins.PETS.get(self.config["pet"]) if self.config["pet"] else None
            if pet and random.random() < 0.3:
                self.say(pet.sound, 1.5)
            else:
                self.say(random.choice(CLICK_PHRASES), 1.5)
        return True

    # --- Drawing ----------------------------------------------------------
    def on_draw(self, _widget: Gtk.Widget, cr: cairo.Context) -> bool:
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        held = self.state == "held"
        sleeping = self.state == "sleep"
        moving = held or self.state in ("walk", "chase", "game")  # held: legs dangle
        # Pixel art looks best with whole-pixel hops instead of smooth bobbing.
        bob = 2 if moving and not held and math.sin(self.step_phase) > 0 else 0
        dancing = self.dancing()
        sway = 0
        beat = self.wobble * DANCE_BPM / 60  # beats since start
        if sleeping:
            bob = 1 if math.sin(self.wobble * 1.6) > 0 else 0  # slow breathing
        elif dancing:
            bob = 3 if math.sin(beat * 2 * math.pi) > 0 else 0  # a hop on every beat
            sway = 2 if math.sin(beat * math.pi) > 0 else -2  # lean left, lean right
        elif self.phrase and not moving:
            bob = 1 if math.sin(self.wobble * 14) > 0 else 0  # "talking" wiggle
        jump = math.sin(math.pi * self.jump_t / 0.6) * 30 if self.jump_t > 0 else 0
        cy = CY - bob - jump

        self.draw_shadow(cr, jump)
        self.draw_pet(cr, moving and not held, dancing)
        cr.save()
        cr.translate(sway, 0)
        self.draw_sprite(cr, cy, moving, sleeping)
        # Clothes first, then face and hat on top, the seasonal extra and umbrella last.
        for slot in ("body", "face", "head", "extra", "weather"):
            if slot in self.outfit:
                self.draw_accessory(cr, self.outfit[slot], cy)
        cr.restore()
        if self.feed_t > 0:
            self.draw_apple(cr, cy)
        if sleeping:
            self.draw_zzz(cr, cy)
        if dancing:
            self.draw_notes(cr, cy)
        if self.phrase:
            self.draw_bubble(cr, cy - self.accessories_top())
        return False

    def draw_pixels(self, cr: cairo.Context, art, palette, left: float, top: float,
                    flip: bool = False) -> None:
        """Draws a small picture made of letters in square (fine) pixels."""
        width = len(art[0])
        for row, line in enumerate(art):
            for col, cell in enumerate(line):
                if cell == ".":
                    continue
                x = width - 1 - col if flip else col
                cr.set_source_rgb(*palette[cell])
                cr.rectangle(left + x * PX_W, top + row * FINE_H, PX_W + 0.5, FINE_H + 0.5)
                cr.fill()

    def draw_accessory(self, cr: cairo.Context, acc: skins.Accessory, cy: float) -> None:
        left = CX - BODY_HALF_W + acc.col * PX_W
        top = cy - BODY_HALF_H + acc.row * FINE_H
        if acc.float_amp:
            top += round(math.sin(self.wobble * 2.5) * acc.float_amp)  # whole pixels, like the rest
        self.draw_pixels(cr, acc.frame(self.wobble), acc.palette, left, top)

    def draw_pet(self, cr: cairo.Context, moving: bool, dancing: bool = False) -> None:
        pet = skins.PETS.get(self.config["pet"]) if self.config["pet"] else None
        if pet is None or self.state == "held":  # while you carry the buddy, the pet waits
            return
        frame = pet.frames[int(self.step_phase * 0.5) % len(pet.frames)] if moving else pet.frames[0]
        width = pet.width * PX_W
        height = pet.height * FINE_H
        ground = CY + BODY_HALF_H
        hop = 1 if moving and math.sin(self.step_phase * 1.3) > 0 else 0
        if dancing:  # the pet dances too, half a beat later
            hop = 2 if math.sin(self.wobble * DANCE_BPM / 60 * 2 * math.pi + math.pi) > 0 else 0
        # It walks behind the buddy and looks the same way.
        if self.facing >= 0:
            left, flip = CX - BODY_HALF_W - PET_GAP - width, False
        else:
            left, flip = CX + BODY_HALF_W + PET_GAP, True
        cr.save()
        cr.translate(left + width / 2, ground + 2)
        cr.scale(width * 0.45, 2.5)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.set_source_rgba(0, 0, 0, 0.15)
        cr.fill()
        self.draw_pixels(cr, frame, pet.palette, left, ground - height - hop, flip)

    def draw_apple(self, cr: cairo.Context, cy: float) -> None:
        fallen = 1 - self.feed_t / 0.6  # 0 -> 1 while it falls
        left = CX - len(APPLE[0]) * PX_W / 2
        top = cy - BODY_HALF_H - 55 + fallen * 45
        self.draw_pixels(cr, APPLE, APPLE_PALETTE, left, top)

    def draw_zzz(self, cr: cairo.Context, cy: float) -> None:
        layout = PangoCairo.create_layout(cr)
        for i in range(3):
            phase = (self.wobble * 0.35 + i / 3) % 1  # each Z floats up and fades out
            layout.set_font_description(Pango.FontDescription(f"Sans Bold {8 + phase * 6:.0f}"))
            layout.set_text("z" if phase < 0.5 else "Z", -1)
            cr.set_source_rgba(*INK, 1 - phase)
            cr.move_to(CX + BODY_HALF_W - 8 + phase * 22, cy - BODY_HALF_H - 10 - phase * 45)
            PangoCairo.show_layout(cr, layout)

    def draw_notes(self, cr: cairo.Context, cy: float) -> None:
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Sans Bold 11"))
        for i, note in enumerate(("♪", "♫")):
            phase = (self.wobble * 0.5 + i / 2) % 1  # each note floats up and fades out
            side = -1 if i == 0 else 1
            layout.set_text(note, -1)
            cr.set_source_rgba(*ORANGE_DARK, 1 - phase)
            cr.move_to(CX + side * (BODY_HALF_W + 4 + phase * 10) - 5, cy - BODY_HALF_H - phase * 35)
            PangoCairo.show_layout(cr, layout)

    def draw_shadow(self, cr: cairo.Context, jump: float) -> None:
        scale = 1 - jump / 100
        cr.save()
        cr.translate(CX, CY + BODY_HALF_H + 2)
        cr.scale(BODY_HALF_W * 0.8 * scale, 3 * scale)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.set_source_rgba(0, 0, 0, 0.18)
        cr.fill()

    def draw_sprite(self, cr: cairo.Context, cy: float, moving: bool, sleeping: bool = False) -> None:
        left = CX - BODY_HALF_W
        top = cy - BODY_HALF_H
        eyes_closed = self.blink_t < 0 or sleeping
        # While walking one pair of legs is lifted, then the other.
        lifted = ("L" if math.sin(self.step_phase * 0.5) > 0 else "R") if moving else ""
        body, eye = self.body_color(), self.eye_color()

        for row, line in enumerate(SPRITE):
            for col, cell in enumerate(line):
                if cell == ".":
                    continue
                x = left + col * PX_W
                y = top + row * PX_H
                h = PX_H
                if cell == "o":
                    cr.set_source_rgb(*body)
                    cr.rectangle(x, y, PX_W + 0.5, PX_H + 0.5)
                    cr.fill()
                    if eyes_closed:
                        y, h = y + PX_H * 0.7, PX_H * 0.3  # closed eye: thin line
                    cr.set_source_rgb(*eye)
                else:
                    if cell == lifted or (sleeping and cell in "LR"):
                        h = PX_H * 0.5  # asleep it sits down: legs tucked in
                    cr.set_source_rgb(*body)
                # +0.5 hides hairline gaps between neighbouring pixels.
                cr.rectangle(x, y, PX_W + 0.5, h + 0.5)
                cr.fill()

    def draw_bubble(self, cr: cairo.Context, cy: float) -> None:
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription(FONT))
        layout.set_width((WIN_W - 30) * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_text(self.phrase, -1)
        _ink, logical = layout.get_pixel_extents()

        pad = 8
        w = logical.width + pad * 2
        h = logical.height + pad * 2
        x = CX - w / 2
        y = max(2.0, cy - BODY_HALF_H - h - 14)
        r = 10

        cr.new_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.line_to(CX + 8, y + h)
        cr.line_to(CX, y + h + 10)  # tail pointing at the buddy
        cr.line_to(CX - 8, y + h)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()
        cr.set_source_rgb(*BUBBLE_BG)
        cr.fill_preserve()
        cr.set_source_rgb(*ORANGE_DARK)
        cr.set_line_width(2)
        cr.stroke()

        cr.set_source_rgb(*INK)
        cr.move_to(x + pad - logical.x, y + pad)
        PangoCairo.show_layout(cr, layout)


def main() -> None:
    # The application id makes it single-instance: a second launch only reaches
    # the running buddy (it waves), and does not start another one.
    app = Gtk.Application(application_id="ua.yasha.ClaudeBuddy")

    def on_activate(application: Gtk.Application) -> None:
        windows = application.get_windows()
        if windows:
            windows[0].hello_again()
        else:
            Buddy(application).show_all()

    app.connect("activate", on_activate)
    app.run(None)


if __name__ == "__main__":
    main()
