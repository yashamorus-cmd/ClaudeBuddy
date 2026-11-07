"""Скіни для Claude Buddy: аксесуари та сезонні образи.

Як додати свій аксесуар
-----------------------
1. Намалюй його символами в `art`: "." — прозоро, будь-яка інша літера — колір із `palette`.
2. Сітка аксесуарів — квадратні «пікселі», вдвічі нижчі за пікселі тіла.
   Тіло займає рядки 0..7 цієї сітки (ніжки — 8..9) і колонки 0..17:

       колонки:  0         1
                 012345678901234567
       рядок 0-1 ...############...   верх голови
       рядок 2-3 ...##o######o##...   очі (колонки 5 і 12)
       рядок 4-5 .################.   «руки»
       рядок 6-7 ...############...
       рядок 8-9 ....L.R....L.R....   ніжки

3. `row` — у якому рядку сітки починається малюнок (мінус — над головою),
   `col` — з якої колонки.
4. Додай аксесуар у потрібний словник (HEAD / FACE / BODY) — він сам з'явиться в меню.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

Color = tuple[float, float, float]


@dataclass(frozen=True)
class Accessory:
    name: str  # як називається в меню
    art: tuple[str, ...]
    palette: dict[str, Color]
    row: int  # рядок сітки, де починається перший рядок малюнка
    col: int = 0
    float_amp: float = 0.0  # якщо > 0, аксесуар плавно гойдається вгору-вниз (px)
    frames: tuple[tuple[str, ...], ...] = ()  # додаткові кадри анімації (art — перший кадр)
    fps: float = 8.0  # швидкість анімації, кадрів на секунду

    @property
    def all_frames(self) -> tuple[tuple[str, ...], ...]:
        return (self.art, *self.frames)

    def frame(self, t: float) -> tuple[str, ...]:
        frames = self.all_frames
        return frames[int(t * self.fps) % len(frames)]

    @property
    def width(self) -> int:
        return max(len(line) for art in self.all_frames for line in art)


# ---------------------------------------------------------------- головні убори
HEAD: dict[str, Accessory] = {
    "beanie": Accessory(
        name="Шапка-біні",
        art=(
            "........WW........",
            ".....BBBBBBBB.....",
            "....BBBBBBBBBB....",
            "...BBBBBBBBBBBB...",
            "...SSSSSSSSSSSS...",
        ),
        palette={"B": (0.20, 0.45, 0.85), "S": (0.13, 0.32, 0.65), "W": (0.97, 0.97, 0.97)},
        row=-4,
    ),
    "crown": Accessory(
        name="Корона",
        art=(
            ".....Y..YY..Y.....",
            ".....YY.YY.YY.....",
            ".....YYYYYYYY.....",
            ".....YRYYYYRY.....",
        ),
        palette={"Y": (0.98, 0.78, 0.20), "R": (0.85, 0.15, 0.25)},
        row=-4,
    ),
    "headphones": Accessory(
        name="Навушники",
        art=(
            ".....KKKKKKKK.....",
            "....K........K....",
            "...K..........K...",
            "..CC..........CC..",
            "..CC..........CC..",
            "..CC..........CC..",
        ),
        palette={"K": (0.18, 0.18, 0.20), "C": (0.30, 0.55, 0.95)},
        row=-2,
    ),
    "tophat": Accessory(
        name="Циліндр",
        art=(
            ".....KKKKKKKK.....",
            ".....KKKKKKKK.....",
            ".....KKKKKKKK.....",
            ".....KKKKKKKK.....",
            ".....RRRRRRRR.....",
            "..KKKKKKKKKKKKKK..",
        ),
        palette={"K": (0.10, 0.10, 0.12), "R": (0.75, 0.12, 0.18)},
        row=-6,
    ),
    "cap": Accessory(
        name="Кепка",
        art=(
            "........WW........",
            ".....CCCCCCCC.....",
            "....CCCCCCCCCC....",
            "...CCCCCCCCCCDDDDD",
        ),
        palette={"C": (0.85, 0.20, 0.20), "D": (0.62, 0.12, 0.12), "W": (0.97, 0.97, 0.97)},
        row=-4,
    ),
    "cowboy": Accessory(
        name="Ковбойський капелюх",
        art=(
            "......NN..NN......",
            "......NNNNNN......",
            "......BBBBBB......",
            "N...NNNNNNNNNN...N",
            ".NNNNNNNNNNNNNNNN.",
        ),
        palette={"N": (0.55, 0.35, 0.18), "B": (0.30, 0.18, 0.08)},
        row=-5,
    ),
    "wreath": Accessory(
        name="Вінок",
        art=(
            "....R.Y.RR.Y.R....",
            "...GRGYGRRGYGRG...",
            "..BY..............",
            "..BY..............",
            ".BY...............",
            ".BY...............",
        ),
        palette={"R": (0.85, 0.12, 0.15), "Y": (0.98, 0.80, 0.15),
                 "G": (0.25, 0.60, 0.25), "B": (0.15, 0.45, 0.85)},
        row=-2,
    ),
    "chef": Accessory(
        name="Кухарський ковпак",
        art=(
            "......WWWWWW......",
            ".....WWSWWSWW.....",
            "....WWWWWWWWWW....",
            ".....WWWWWWWW.....",
            ".....WWWWWWWW.....",
            ".....SSSSSSSS.....",
        ),
        palette={"W": (0.98, 0.98, 0.98), "S": (0.80, 0.82, 0.86)},
        row=-6,
    ),
    "viking": Accessory(
        name="Шолом вікінга",
        art=(
            "..H............H..",
            "..H....MMMM....H..",
            "..HH.MMMMMMMM.HH..",
            "...HHMMMMMMMMHH...",
            "...LLLLLLLLLLLL...",
        ),
        palette={"H": (0.95, 0.92, 0.82), "M": (0.62, 0.65, 0.70), "L": (0.42, 0.44, 0.48)},
        row=-4,
    ),
    "wizard": Accessory(
        name="Капелюх чарівника",
        art=(
            "...........K......",
            "..........KK......",
            ".........KKK......",
            "........KKYKK.....",
            ".......KKKKKK.....",
            "......KYKKKKKK....",
            ".....KKKKKKKYK....",
            "..KKKKKKKKKKKKKK..",
        ),
        palette={"K": (0.25, 0.20, 0.65), "Y": (1.00, 0.85, 0.25)},
        row=-8,
    ),
    "propeller": Accessory(
        name="Кепка з пропелером",
        art=(
            "....RRRRYBBBB.....",
            "........K.........",
            ".....RRYYYYBB.....",
            "....RRRYYYYBBB....",
            "...RRRRYYYYBBBB...",
        ),
        frames=((
            ".......RYB........",
            "........K.........",
            ".....RRYYYYBB.....",
            "....RRRYYYYBBB....",
            "...RRRRYYYYBBBB...",
        ),),
        palette={"R": (0.90, 0.20, 0.20), "Y": (0.98, 0.80, 0.15),
                 "B": (0.15, 0.45, 0.85), "K": (0.20, 0.20, 0.22)},
        row=-5,
        fps=10,
    ),
}

# ---------------------------------------------------------------- обличчя
FACE: dict[str, Accessory] = {
    "glasses": Accessory(
        name="Окуляри",
        art=(
            "....FFF....FFF....",
            "...FF.FFFFFF.FF...",
            "....F.F....F.F....",
            "....FFF....FFF....",
        ),
        palette={"F": (0.80, 0.83, 0.88)},  # silver, so the frame does not merge with the black eyes
        row=1,
    ),
    "sunglasses": Accessory(
        name="Сонцезахисні окуляри",
        art=(
            "...LWLLLLLLWLLL...",
            "....LLL....LLL....",
        ),
        palette={"L": (0.08, 0.08, 0.10), "W": (0.85, 0.90, 1.00)},
        row=2,
    ),
    "mustache": Accessory(
        name="Вуса",
        art=(
            ".....K.KKKK.K.....",
            ".....KKK..KKK.....",
        ),
        palette={"K": (0.25, 0.15, 0.08)},
        row=4,
    ),
    "monocle": Accessory(
        name="Монокль",
        art=(
            "...........YYY....",
            "..........Y...Y...",
            "..........Y...Y...",
            "...........YYY....",
            "..............Y...",
            "...............Y..",
        ),
        palette={"Y": (0.98, 0.78, 0.20)},
        row=1,
    ),
    "hero_mask": Accessory(
        name="Маска супергероя",
        art=(
            "....MMM....MMM....",
            "..MMM.MMMMMM.MMM..",
            "...MM.MMMMMM.MM...",
            "....MMM....MMM....",
        ),
        palette={"M": (0.80, 0.10, 0.15)},
        row=1,
    ),
    "blush": Accessory(
        name="Рум'янець з усмішкою",
        art=(
            "...PP........PP...",
            ".......K..K.......",
            "........KK........",
        ),
        palette={"P": (1.00, 0.55, 0.62), "K": (0.13, 0.12, 0.11)},
        row=4,
    ),
    "heart_glasses": Accessory(
        name="Окуляри-сердечка",
        art=(
            "...RR.RR..RR.RR...",
            "...RPRRRKKRPRRR...",
            "....RRR....RRR....",
            ".....R......R.....",
        ),
        palette={"R": (0.95, 0.20, 0.40), "P": (1.00, 0.75, 0.85), "K": (0.30, 0.10, 0.15)},
        row=1,
    ),
    "eyepatch": Accessory(
        name="Піратська пов'язка",
        art=(
            "...KKKKKKKKKKKK...",
            "....KKK...........",
            "....KKK...........",
            ".....K............",
        ),
        palette={"K": (0.10, 0.10, 0.10)},
        row=1,
    ),
    "clown_nose": Accessory(
        name="Клоунський ніс",
        art=(
            "........WR........",
            "........RR........",
        ),
        palette={"R": (0.92, 0.12, 0.15), "W": (1.00, 0.80, 0.80)},
        row=3,
    ),
}

# ---------------------------------------------------------------- одяг
BODY: dict[str, Accessory] = {
    "vyshyvanka": Accessory(
        name="Вишиванка",
        art=(
            ".R..............R.",
            ".K...R..KK..R...K.",
            "....RKR.RR.RKR....",
            ".....R..KK..R.....",
        ),
        palette={"R": (0.80, 0.10, 0.15), "K": (0.10, 0.08, 0.08)},
        row=4,
    ),
    "bowtie": Accessory(
        name="Краватка-метелик",
        art=(
            "......BB..BB......",
            "......BBKKBB......",
            "......BB..BB......",
        ),
        palette={"B": (0.75, 0.10, 0.18), "K": (0.50, 0.05, 0.10)},
        row=4,
    ),
    "scarf": Accessory(
        name="Смугастий шарф",
        art=(
            "...RRWWRRWWRRWW...",
            "...WWRRWWRRWWRR...",
            "...........RR.....",
            "...........WW.....",
        ),
        palette={"R": (0.85, 0.15, 0.20), "W": (0.97, 0.97, 0.97)},
        row=4,
    ),
    "sweater": Accessory(
        name="Светр",
        art=(
            ".GGGGGGGGGGGGGGGG.",
            ".WGGWGGWGGWGGWGGW.",
            "...GGGGGGGGGGGG...",
            "...RRRRRRRRRRRR...",
        ),
        palette={"G": (0.18, 0.55, 0.30), "W": (0.97, 0.97, 0.97), "R": (0.80, 0.15, 0.18)},
        row=4,
    ),
    "apron": Accessory(
        name="Фартух кухаря",
        art=(
            "......W....W......",
            "......W....W......",
            ".....WWWWWWWW.....",
            ".....WWWWWWWW.....",
            ".....WWSSWWWW.....",
            ".....WWWWWWWW.....",
        ),
        palette={"W": (0.98, 0.98, 0.98), "S": (0.80, 0.82, 0.86)},
        row=2,
    ),
    "suit": Accessory(
        name="Костюм з краваткою",
        art=(
            ".KKKKKKWRRWKKKKKK.",
            ".KKKKKKKRRKKKKKKK.",
            "...KKKKKRRKKKKK...",
            "...KKKKKKKKKKKK...",
        ),
        palette={"K": (0.15, 0.17, 0.25), "W": (0.97, 0.97, 0.97), "R": (0.80, 0.12, 0.18)},
        row=4,
    ),
    "cape": Accessory(
        name="Плащ супергероя",
        art=(
            ".RR............RR.",
            ".RR.....YY.....RR.",
            ".RR....YYYY....RR.",
            ".RR.....YY.....RR.",
            ".RR............RR.",
            "RRR............RRR",
        ),
        palette={"R": (0.80, 0.10, 0.15), "Y": (1.00, 0.84, 0.10)},
        row=4,
    ),
    "hawaiian": Accessory(
        name="Гавайська сорочка",
        art=(
            ".TTTTTTTTTTTTTTTT.",
            ".TFTTTTYTTTTFTTTT.",
            "...TTTFTTTTTYTT...",
            "...TTYTTFTTTTTT...",
        ),
        palette={"T": (0.10, 0.70, 0.75), "F": (1.00, 0.45, 0.65), "Y": (1.00, 0.85, 0.20)},
        row=4,
    ),
    "medal": Accessory(
        name="Медаль чемпіона",
        art=(
            "......BY..YB......",
            ".......BYYB.......",
            "........GG........",
            ".......GWGG.......",
            "........GG........",
        ),
        palette={"B": (0.00, 0.36, 0.73), "Y": (1.00, 0.84, 0.00),
                 "G": (0.95, 0.72, 0.15), "W": (1.00, 0.95, 0.70)},
        row=4,
    ),
}

# Слоти, які показуються в меню: id слота -> (назва, аксесуари)
SLOTS: dict[str, tuple[str, dict[str, Accessory]]] = {
    "head": ("Головний убір", HEAD),
    "face": ("Обличчя", FACE),
    "body": ("Одяг", BODY),
}

# ---------------------------------------------------------------- сезонні аксесуари
SEASONAL: dict[str, Accessory] = {
    "santa": Accessory(
        name="Шапка Санти",
        art=(
            "...............WW.",
            "..........RRRRRWW.",
            "........RRRRRRR...",
            "......RRRRRRRRR...",
            "....RRRRRRRRRRR...",
            "...WWWWWWWWWWWW...",
        ),
        palette={"R": (0.85, 0.12, 0.15), "W": (0.98, 0.98, 0.98)},
        row=-5,
    ),
    "witch": Accessory(
        name="Капелюх відьми",
        art=(
            "..........KK......",
            ".........KKK......",
            "........KKKK......",
            ".......KKKKKK.....",
            "......GGGGGGGG....",
            "......KKKKKKKK....",
            ".KKKKKKKKKKKKKKKK.",
        ),
        palette={"K": (0.18, 0.10, 0.25), "G": (0.45, 0.85, 0.25)},
        row=-6,
    ),
    "flag": Accessory(
        name="Прапорець",
        art=(
            "KBBBBB",
            "KBBBBB",
            "KYYYYY",
            "KYYYYY",
            "K.....",
            "K.....",
            "K.....",
            "K.....",
        ),
        palette={"K": (0.45, 0.30, 0.18), "B": (0.00, 0.36, 0.73), "Y": (1.00, 0.84, 0.00)},
        row=-4,
        col=16,
    ),
    "hearts": Accessory(
        name="Сердечка",
        art=(
            ".RR.RR.",
            "RPRRRRR",
            "RRRRRRR",
            ".RRRRR.",
            "..RRR..",
            "...R...",
        ),
        palette={"R": (0.90, 0.15, 0.30), "P": (1.00, 0.70, 0.78)},
        row=-9,
        col=5,
        float_amp=3.0,
    ),
}


@dataclass(frozen=True)
class Season:
    name: str
    start: tuple[int, int]  # (місяць, день), включно
    end: tuple[int, int]
    outfit: dict[str, Accessory] = field(default_factory=dict)  # слот -> аксесуар
    greeting: str = ""
    body_color: Color | None = None
    eye_color: Color | None = None

    def is_active(self, day: dt.date) -> bool:
        md = (day.month, day.day)
        if self.start <= self.end:
            return self.start <= md <= self.end
        return md >= self.start or md <= self.end  # період через Новий рік


SEASONS: list[Season] = [
    Season("Новорічний 🎅", (12, 15), (1, 15), {"head": SEASONAL["santa"]},
           greeting="Хо-хо-хо! 🎅🎄"),
    Season("Хелловін 🎃", (10, 25), (11, 2), {"head": SEASONAL["witch"]},
           greeting="Бу! 🎃 Страшно?", body_color=(0.93, 0.48, 0.13), eye_color=(0.70, 1.00, 0.25)),
    Season("День Незалежності 💙💛", (8, 23), (8, 25),
           {"body": BODY["vyshyvanka"], "extra": SEASONAL["flag"]},
           greeting="Слава Україні! 💙💛"),
    Season("День закоханих ❤️", (2, 14), (2, 14), {"extra": SEASONAL["hearts"]},
           greeting="Люблю тебе, друже! ❤️"),
]


def active_season(day: dt.date) -> Season | None:
    return next((s for s in SEASONS if s.is_active(day)), None)


def _validate() -> None:
    """Ловить помилки в малюнках одразу при запуску, а не під час малювання."""
    all_acc = [*HEAD.values(), *FACE.values(), *BODY.values(), *SEASONAL.values()]
    for acc in all_acc:
        for art in acc.all_frames:
            widths = {len(line) for line in art}
            assert len(widths) == 1, f"{acc.name}: рядки малюнка різної довжини {widths}"
            assert len(art) == len(acc.art), f"{acc.name}: кадри анімації різної висоти"
            for line in art:
                for ch in line:
                    assert ch == "." or ch in acc.palette, f"{acc.name}: немає кольору для «{ch}»"


_validate()
