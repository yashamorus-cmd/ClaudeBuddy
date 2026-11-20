"""Погода для бадді: у дощ він бере парасольку, у мороз радить одягтися тепліше.

Дані — з Open-Meteo (безкоштовно, без ключа й реєстрації). Запит іде лише тоді,
коли ти сам вказав місто в меню; надсилаються тільки його назва та координати.
Функції тут блокують (мережа), тому бадді викликає їх в окремому потоці.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

USER_AGENT = "ClaudeBuddy/1.0 (desktop pet)"
TIMEOUT_S = 10


@dataclass(frozen=True)
class City:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Weather:
    temp: float  # °C
    code: int  # код погоди WMO
    kind: str  # clear / cloudy / fog / rain / snow / storm
    label: str  # як сказати українською


def _get(url: str, params: dict) -> dict:
    request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.load(response)


def find_city(name: str) -> City | None:
    data = _get("https://geocoding-api.open-meteo.com/v1/search",
                {"name": name, "count": 1, "language": "uk", "format": "json"})
    results = data.get("results") or []
    if not results:
        return None
    found = results[0]
    return City(str(found["name"]), float(found["latitude"]), float(found["longitude"]))


def describe(code: int) -> tuple[str, str]:
    """Код WMO -> (вид, назва українською)."""
    if code == 0:
        return "clear", "ясно"
    if code in (1, 2):
        return "cloudy", "мінлива хмарність"
    if code == 3:
        return "cloudy", "хмарно"
    if code in (45, 48):
        return "fog", "туман"
    if 51 <= code <= 57:
        return "rain", "мряка"
    if 61 <= code <= 67:
        return "rain", "дощ"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow", "сніг"
    if 80 <= code <= 82:
        return "rain", "злива"
    if code >= 95:
        return "storm", "гроза"
    return "cloudy", "хмарно"


def current(city: City) -> Weather:
    data = _get("https://api.open-meteo.com/v1/forecast", {
        "latitude": city.lat,
        "longitude": city.lon,
        "current": "temperature_2m,weather_code",
        "timezone": "auto",
    })
    now = data["current"]
    code = int(now["weather_code"])
    kind, label = describe(code)
    return Weather(float(now["temperature_2m"]), code, kind, label)
