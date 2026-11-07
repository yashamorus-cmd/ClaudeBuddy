#!/usr/bin/env python3
"""Claude Buddy: a little orange pixel creature that lives on the desktop.

Left click        -> it jumps in place.
Double click      -> it says the next phrase right away.
Drag with mouse   -> carry it somewhere else.
Right click       -> it says goodbye and quits.
"""

import math
import os
import random
import time

# GNOME on Wayland does not let normal windows place themselves anywhere on
# screen. Under XWayland (X11 compatibility) an override-redirect window can,
# so the backend must be chosen before Gtk is imported.
os.environ.setdefault("GDK_BACKEND", "x11")

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

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
BODY_HALF_W = len(SPRITE[0]) * PX_W / 2
BODY_HALF_H = len(SPRITE) * PX_H / 2
BODY_R = int(BODY_HALF_W)  # rough radius, used for margins

# The window is bigger than the character so the speech bubble fits above it.
WIN_W, WIN_H = 220, 160
CX, CY = WIN_W // 2, WIN_H - 30  # character centre inside the window

# --- Behaviour ------------------------------------------------------------
FPS = 30
WALK_SPEED = 90  # px per second
CHASE_SPEED = 170
CHASE_CHANCE = 0.3
PHRASE_INTERVAL = (60, 180)  # seconds between phrases said on its own
DRAG_THRESHOLD = 5  # px the mouse must move with the button held to count as a drag

# Under Wayland the buddy only sees the cursor while it is over X11 windows; elsewhere
# it gets the last known spot. So it only trusts a position that changed recently.
POINTER_FRESH_S = 3.0  # cursor moved this recently -> OK to start chasing
POINTER_LOST_S = 6.0  # no movement this long during a chase -> give up

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

PHRASES = BUDDY_PHRASES + ENGLISH_PHRASES + UKRAINIAN_QUOTES
CLICK_PHRASES = ["Ой!", "Лоскотно!", "Хі-хі!", "Агов!", "Я тут!"]
CATCH_PHRASES = ["Спіймав курсор!", "Ось ти де!", "Попався!"]
LOST_PHRASES = ["Загубив курсор 🤔", "Куди ж він подівся?", "Агов, курсоре?"]
HELD_PHRASES = ["Ей, постав мене! 😳", "Ми летимо?!", "Обережно, я крихкий!"]
DROP_PHRASES = ["Дякую!", "Тут затишно", "О, нове місце!"]

# GTK names the double-click event differently in older versions.
DOUBLE_CLICK = getattr(Gdk.EventType, "DOUBLE_BUTTON_PRESS", Gdk.EventType._2BUTTON_PRESS)


class PhraseBag:
    """Hands out phrases in random order with no repeats until the whole list is used."""

    def __init__(self, phrases: list[str]) -> None:
        self.phrases = list(phrases)
        self.bag: list[str] = []
        self.last: str | None = None

    def next(self) -> str:
        if not self.bag:
            self.bag = random.sample(self.phrases, len(self.phrases))
            # Do not start a new round with the phrase that just ended the previous one.
            if len(self.bag) > 1 and self.bag[-1] == self.last:
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
        self.last = self.bag.pop()
        return self.last


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

        area = Gdk.Display.get_default().get_monitor(0).get_workarea()
        self.area = area
        self.x = area.x + area.width / 2
        self.y = area.y + area.height - 80
        self.target = (self.x, self.y)

        self.state = "rest"
        self.state_time = 2.0
        self.look = (0.0, 0.0)
        self.step_phase = 0.0
        self.wobble = 0.0
        self.jump_t = 0.0
        self.blink_t = random.uniform(2, 5)
        self.phrase = ""
        self.phrase_t = 0.0
        self.next_phrase_t = random.uniform(20, 40)  # the first one comes a bit sooner
        self.phrases = PhraseBag(PHRASES)
        self.quitting = False

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
        # Only the character itself catches clicks; everything else in the
        # window passes clicks through to whatever is underneath.
        top = int(CY - BODY_HALF_H - 30)  # extra room above for the jump
        rect = cairo.RectangleInt(int(CX - BODY_HALF_W), top, int(BODY_HALF_W * 2), WIN_H - top)
        self.input_shape_combine_region(cairo.Region(rect))

    def move_window(self) -> None:
        self.move(int(self.x - CX), int(self.y - CY))

    # --- Logic ------------------------------------------------------------
    def pointer(self) -> tuple[float, float]:
        seat = Gdk.Display.get_default().get_default_seat()
        _screen, px, py = seat.get_pointer().get_position()
        return float(px), float(py)

    def random_point(self) -> tuple[float, float]:
        a = self.area
        margin = BODY_R + 20
        return (
            random.uniform(a.x + margin, a.x + a.width - margin),
            random.uniform(a.y + 120, a.y + a.height - margin),
        )

    def clamp_to_area(self, point: tuple[float, float]) -> tuple[float, float]:
        a = self.area
        margin = BODY_R + 20
        return (
            min(max(point[0], a.x + margin), a.x + a.width - margin),
            min(max(point[1], a.y + 120), a.y + a.height - margin),
        )

    def say(self, text: str, seconds: float | None = None) -> None:
        self.phrase = text
        # Long quotes stay longer so there is time to read them.
        self.phrase_t = seconds if seconds is not None else max(4.0, len(text) / 10)

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
        # Chase only a cursor we can actually see right now, not a stale position.
        if random.random() < CHASE_CHANCE and self.pointer_age() < POINTER_FRESH_S:
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
            step = min(dist, speed * dt)
            self.x += dx / dist * step
            self.y += dy / dist * step
            self.step_phase += dt * speed / 9
        return dist

    def tick(self) -> bool:
        dt = 1 / FPS
        self.state_time -= dt
        self.wobble += dt
        self.note_pointer(self.pointer())

        if self.state == "held":
            # Position follows the mouse in on_motion; here the legs just dangle.
            self.step_phase += dt * 14
        elif self.state == "rest":
            self.look = (self.look[0] * 0.95, self.look[1] * 0.95)
            if self.state_time <= 0 and not self.quitting:
                self.choose_next_action()
        elif self.state == "walk":
            if self.step_towards(self.target, WALK_SPEED, dt) < 3 or self.state_time <= 0:
                self.set_state("rest", random.uniform(2, 6))
        elif self.state == "chase":
            px, py = self.last_pointer
            # Stop a bit below the cursor so the buddy does not cover it.
            if self.step_towards((px, py + 40), CHASE_SPEED, dt) < 30:
                self.say(random.choice(CATCH_PHRASES), 2.5)
                self.set_state("rest", random.uniform(3, 6))
            elif self.pointer_age() > POINTER_LOST_S:
                # Probably over a Wayland window where the cursor is invisible to us.
                self.say(random.choice(LOST_PHRASES), 2.5)
                self.set_state("rest", random.uniform(3, 6))
            elif self.state_time <= 0:
                self.set_state("rest", random.uniform(2, 4))

        if self.jump_t > 0:
            self.jump_t = max(0.0, self.jump_t - dt)

        self.blink_t -= dt
        if self.blink_t < -0.15:
            self.blink_t = random.uniform(2, 6)

        if self.phrase_t > 0:
            self.phrase_t -= dt
            if self.phrase_t <= 0:
                self.phrase = ""
        elif not self.quitting:
            self.next_phrase_t -= dt
            if self.next_phrase_t <= 0:
                self.say(self.phrases.next())
                self.next_phrase_t = random.uniform(*PHRASE_INTERVAL)

        self.move_window()
        self.queue_draw()
        return True  # keep the timer running

    # --- Mouse ------------------------------------------------------------
    # A click and the start of a drag look the same at first, so the decision is
    # made later: moving with the button held -> drag, releasing in place -> click.
    def on_press(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if self.quitting:
            return True
        if event.button == 3:
            self.quitting = True
            self.set_state("rest", 999)
            self.say("Бувай! 👋", 2)
            GLib.timeout_add(1500, self.close)
        elif event.button == 1 and event.type == DOUBLE_CLICK:
            self.press = None
            self.jump_t = 0.6
            self.say(self.phrases.next())
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
        else:
            self.jump_t = 0.6
            self.say(random.choice(CLICK_PHRASES), 1.5)
        return True

    # --- Drawing ----------------------------------------------------------
    def on_draw(self, _widget: Gtk.Widget, cr: cairo.Context) -> bool:
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        held = self.state == "held"
        moving = held or self.state in ("walk", "chase")  # held: legs dangle
        # Pixel art looks best with whole-pixel hops instead of smooth bobbing.
        bob = 2 if moving and not held and math.sin(self.step_phase) > 0 else 0
        if self.phrase and not moving:
            bob = 1 if math.sin(self.wobble * 14) > 0 else 0  # "talking" wiggle
        jump = math.sin(math.pi * self.jump_t / 0.6) * 30 if self.jump_t > 0 else 0
        cy = CY - bob - jump

        self.draw_shadow(cr, jump)
        self.draw_sprite(cr, cy, moving)
        if self.phrase:
            self.draw_bubble(cr, cy)
        return False

    def draw_shadow(self, cr: cairo.Context, jump: float) -> None:
        scale = 1 - jump / 100
        cr.save()
        cr.translate(CX, CY + BODY_HALF_H + 2)
        cr.scale(BODY_HALF_W * 0.8 * scale, 3 * scale)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.set_source_rgba(0, 0, 0, 0.18)
        cr.fill()

    def draw_sprite(self, cr: cairo.Context, cy: float, moving: bool) -> None:
        left = CX - BODY_HALF_W
        top = cy - BODY_HALF_H
        blinking = self.blink_t < 0
        # While walking one pair of legs is lifted, then the other.
        lifted = ("L" if math.sin(self.step_phase * 0.5) > 0 else "R") if moving else ""

        for row, line in enumerate(SPRITE):
            for col, cell in enumerate(line):
                if cell == ".":
                    continue
                x = left + col * PX_W
                y = top + row * PX_H
                h = PX_H
                if cell == "o":
                    cr.set_source_rgb(*ORANGE)
                    cr.rectangle(x, y, PX_W + 0.5, PX_H + 0.5)
                    cr.fill()
                    if blinking:
                        y, h = y + PX_H * 0.7, PX_H * 0.3  # closed eye: thin line
                    cr.set_source_rgb(*INK)
                else:
                    if cell == lifted:
                        h = PX_H * 0.5
                    cr.set_source_rgb(*ORANGE)
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
    # The application id makes it single-instance: a second launch does nothing.
    app = Gtk.Application(application_id="ua.yasha.ClaudeBuddy")
    app.connect("activate", lambda a: a.get_windows() or Buddy(a).show_all())
    app.run(None)


if __name__ == "__main__":
    main()
