"""Стан комп'ютера: температура процесора, навантаження, пам'ять і диск.

Читаємо прямо з файлів, які Linux надає в /proc і /sys, — без сторонніх бібліотек.
Функції розбору тексту окремо від читання файлів, щоб їх було легко перевірити тестами.
"""

from __future__ import annotations

import shutil
from pathlib import Path

CPU_SENSORS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")


def cpu_temp(hwmon: Path = Path("/sys/class/hwmon")) -> float | None:
    """Температура процесора в °C, або None, якщо датчика немає."""
    try:
        devices = sorted(hwmon.iterdir())
    except OSError:
        return None
    for device in devices:
        try:
            name = (device / "name").read_text().strip()
        except OSError:
            continue
        if name not in CPU_SENSORS:
            continue
        temps = []
        for sensor in sorted(device.glob("temp*_input")):
            try:
                value = int(sensor.read_text().strip()) / 1000
            except (OSError, ValueError):
                continue
            label_file = sensor.with_name(sensor.name.replace("_input", "_label"))
            try:
                label = label_file.read_text().strip()
            except OSError:
                label = ""
            # «Package» (Intel) і «Tctl» (AMD) — температура всього процесора.
            if label.startswith(("Package", "Tctl", "Tdie")):
                return value
            temps.append(value)
        if temps:
            return max(temps)
    return None


def parse_cpu_times(stat_text: str) -> tuple[int, int]:
    """Перший рядок /proc/stat -> (час простою, загальний час)."""
    fields = stat_text.splitlines()[0].split()[1:]
    values = [int(v) for v in fields]
    idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
    return idle, sum(values)


class CpuLoad:
    """Навантаження процесора у % між двома викликами."""

    def __init__(self) -> None:
        self.last = self._read()

    @staticmethod
    def _read() -> tuple[int, int] | None:
        try:
            return parse_cpu_times(Path("/proc/stat").read_text())
        except (OSError, ValueError, IndexError):
            return None

    def percent(self) -> float | None:
        now = self._read()
        last, self.last = self.last, now
        if now is None or last is None or now[1] == last[1]:
            return None
        busy = (now[1] - last[1]) - (now[0] - last[0])
        return max(0.0, min(100.0, busy * 100 / (now[1] - last[1])))


def parse_meminfo(text: str) -> float | None:
    """/proc/meminfo -> скільки пам'яті зайнято, у %."""
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            try:
                values[key] = int(parts[0])
            except ValueError:
                pass
    total, available = values.get("MemTotal"), values.get("MemAvailable")
    if not total or available is None:
        return None
    return (total - available) * 100 / total


def memory_used() -> float | None:
    try:
        return parse_meminfo(Path("/proc/meminfo").read_text())
    except OSError:
        return None


def disk_free(path: Path = Path.home()) -> tuple[float, float] | None:
    """(вільно ГБ, вільно %) на диску з домашньою папкою."""
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return usage.free / 1024 ** 3, usage.free * 100 / usage.total
