"""Короткі звуки бадді. Їх не треба завантажувати: мелодії генеруються кодом
(синусоїди з плавним початком і кінцем) і один раз записуються у WAV-файли в кеш.
Грає системний плеєр (pw-play / paplay / aplay), тож бадді не залежить від бібліотек звуку.
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import storage

VERSION = 1  # зміни, якщо змінюєш мелодії, — файли перегенеруються
RATE = 22050
VOLUME = 0.22

# Мелодія: список (частота в Гц, тривалість у секундах); 0 Гц — пауза.
MELODIES: dict[str, list[tuple[float, float]]] = {
    "done": [(660, 0.09), (880, 0.16)],
    "attention": [(880, 0.08), (0, 0.05), (880, 0.08), (0, 0.05), (1175, 0.14)],
    "level": [(523, 0.08), (659, 0.08), (784, 0.08), (1047, 0.22)],
    "break": [(784, 0.22), (523, 0.32)],
    "reminder": [(988, 0.1), (0, 0.06), (988, 0.1), (0, 0.06), (1319, 0.25)],
    "achievement": [(784, 0.08), (988, 0.08), (1175, 0.08), (1568, 0.28)],
}


def samples(melody: list[tuple[float, float]], rate: int = RATE) -> list[int]:
    """Мелодія -> 16-бітні відліки. Кожна нота плавно з'являється й затихає, щоб не клацала."""
    out: list[int] = []
    for freq, duration in melody:
        n = int(rate * duration)
        fade = max(1, min(n // 4, int(rate * 0.015)))
        for i in range(n):
            if freq <= 0:
                out.append(0)
                continue
            envelope = min(1.0, i / fade, (n - 1 - i) / fade)
            value = math.sin(2 * math.pi * freq * i / rate) * envelope * VOLUME
            out.append(int(value * 32767))
    return out


def write_wav(path: Path, melody: list[tuple[float, float]]) -> None:
    data = samples(melody)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(struct.pack(f"<{len(data)}h", *data))


class Player:
    def __init__(self, folder: Path | None = None) -> None:
        self.folder = folder or storage.cache_dir() / "sounds"
        self.command = next((c for c in ("pw-play", "paplay", "aplay") if shutil.which(c)), None)

    def path(self, name: str) -> Path:
        return self.folder / f"{name}-v{VERSION}.wav"

    def prepare(self) -> None:
        """Створює відсутні файли (дуже швидко — це кілька сотень мілісекунд звуку)."""
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            for name, melody in MELODIES.items():
                if not self.path(name).exists():
                    write_wav(self.path(name), melody)
        except OSError:
            self.command = None  # без файлів грати нічого

    def play(self, name: str) -> None:
        if self.command is None or name not in MELODIES:
            return
        path = self.path(name)
        if not path.exists():
            self.prepare()
        args = [self.command, str(path)]
        if self.command == "aplay":
            args.insert(1, "-q")
        try:
            subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass


def speak_english(text: str) -> bool:
    """Вимовляє англійське слово чи речення (spd-say з англійським голосом), трохи повільніше."""
    command = shutil.which("spd-say")
    if not command or not text:
        return False
    try:
        subprocess.Popen([command, "-l", "en", "-r", "-25", "--", text], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True


def can_speak() -> bool:
    return shutil.which("spd-say") is not None
