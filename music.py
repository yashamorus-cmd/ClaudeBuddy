"""Що зараз грає: бадді питає музичні плеєри через MPRIS (стандарт D-Bus).

MPRIS підтримують Spotify, браузери (YouTube), VLC, Rhythmbox та інші.
Примітка: Spotify зі Snap відповідає лише незахищеним (unconfined) програмам, тож бадді,
запущений з автозапуску чи меню програм, його бачить, а запущений з пісочниці — ні.
"""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

MPRIS_PREFIX = "org.mpris.MediaPlayer2."
TIMEOUT_MS = 300


@dataclass(frozen=True)
class Track:
    player: str
    title: str
    artist: str

    def label(self) -> str:
        return f"{self.title} — {self.artist}" if self.artist else self.title


def track_from_metadata(player: str, metadata: dict) -> Track:
    title = str(metadata.get("xesam:title") or "").strip()
    artists = metadata.get("xesam:artist") or []
    if isinstance(artists, str):
        artists = [artists]
    artist = ", ".join(str(a) for a in artists if a).strip()
    return Track(player, title or "Без назви", artist)


class MusicWatcher:
    def __init__(self) -> None:
        try:
            self.bus: Gio.DBusConnection | None = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self.bus = None

    def _call(self, name: str, path: str, interface: str, method: str,
              params: GLib.Variant | None, reply: str):
        return self.bus.call_sync(name, path, interface, method, params,
                                  GLib.VariantType.new(reply), Gio.DBusCallFlags.NONE,
                                  TIMEOUT_MS, None).unpack()

    def _get(self, name: str, prop: str):
        return self._call(name, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "Get",
                          GLib.Variant("(ss)", ("org.mpris.MediaPlayer2.Player", prop)), "(v)")[0]

    def now_playing(self) -> Track | None:
        """Перша пісня, що зараз грає (не на паузі), або None."""
        if self.bus is None:
            return None
        try:
            names = self._call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                               "ListNames", None, "(as)")[0]
        except GLib.Error:
            return None
        for name in sorted(n for n in names if n.startswith(MPRIS_PREFIX)):
            try:
                if self._get(name, "PlaybackStatus") != "Playing":
                    continue
                metadata = self._get(name, "Metadata")
            except GLib.Error:
                continue  # плеєр не відповів або не пустив — пробуємо наступний
            player = name[len(MPRIS_PREFIX):].split(".")[0]
            return track_from_metadata(player, metadata if isinstance(metadata, dict) else {})
        return None
