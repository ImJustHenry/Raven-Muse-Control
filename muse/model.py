"""Capability-driven state. None means unknown; do not invent progress or status."""
from dataclasses import dataclass, field, replace
import math
import time

OPS = frozenset({"play", "pause", "toggle", "next", "previous", "volume_up",
                 "volume_down", "forward", "back", "shuffle", "repeat"})
PLAYERS = frozenset({"spotify", "youtube music"})


def supported_player(name: str) -> bool:
    return name.strip().casefold() in PLAYERS


def finite(value, minimum=0):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= minimum else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class State:
    connected: bool = False
    player: str = ""
    title: str = ""
    artist: str = ""
    playing: bool | None = None
    position: float | None = None
    duration: float | None = None
    rate: float = 0
    sampled_at: float = field(default_factory=time.monotonic)
    volume: float | None = None
    capabilities: frozenset[str] = frozenset()
    message: str = "Disconnected"
    simulated: bool = False
    truncated: bool = False
    revision: int = 0
    album: str = ""
    track_id: str = ""
    artwork_id: str = ""
    artwork_bytes: bytes = field(default=b"", repr=False)

    def elapsed(self, now=None):
        if self.position is None:
            return None
        age = max(0, (now if now is not None else time.monotonic()) - self.sampled_at)
        value = max(0, self.position + (age * self.rate if self.playing else 0))
        return min(value, self.duration) if self.duration is not None else value

    def can(self, op):
        return (self.connected and supported_player(self.player)
                and op in self.capabilities and op in OPS)

    def toggle_action(self):
        if self.playing is True and self.can("pause"):
            return "pause"
        if self.playing is False and self.can("play"):
            return "play"
        return "toggle" if self.can("toggle") else None

    def offline(self, reason):
        return replace(self, connected=False, playing=None, rate=0,
                       position=None, capabilities=frozenset(), message=reason,
                       artwork_id="", artwork_bytes=b"")
