"""Deterministic fake phone. No audio, accounts, Spotify API, or YouTube API."""
import threading
import time
from dataclasses import replace
from .model import State, OPS
from .demo_art import demo_cover

TRACKS = (("Demo: Midnight Drive", "Simulated artist", 208),
          ("Demo: Golden Hour", "Simulated artist", 181),
          ("Demo: Blue Horizon", "Simulated artist", 246))


class DemoTransport:
    def __init__(self):
        self.lock = threading.RLock()
        self.index = 0
        self.commands = []
        self.state = State(connected=True, player="Spotify", title=TRACKS[0][0],
            artist=TRACKS[0][1], playing=True, position=24, duration=208, rate=1,
            volume=.4, capabilities=OPS, message="SIMULATION - no phone audio", simulated=True,
            album="Original demo covers", track_id="demo-0", artwork_id="demo-0", artwork_bytes=demo_cover(0))

    def start(self):
        pass

    def close(self):
        pass

    def snapshot(self):
        with self.lock:
            return self.state

    def send(self, op):
        with self.lock:
            s = self.state
            if not s.can(op):
                raise ValueError("Command unavailable")
            self.commands.append(op)
            s = replace(s, position=s.elapsed(), sampled_at=time.monotonic())
            if op in {"play", "pause", "toggle"}:
                playing = op == "play" or (op == "toggle" and s.playing is not True)
                s = replace(s, playing=playing, rate=1 if playing else 0)
            elif op in {"next", "previous"}:
                self.index = (self.index + (1 if op == "next" else -1)) % len(TRACKS)
                title, artist, duration = TRACKS[self.index]
                s = replace(s, title=title, artist=artist, duration=duration, position=0,
                    track_id=f"demo-{self.index}", artwork_id=f"demo-{self.index}",
                    artwork_bytes=demo_cover(self.index))
            elif op in {"volume_up", "volume_down"}:
                s = replace(s, volume=max(0, min(1, (s.volume or 0) + (.05 if op == "volume_up" else -.05))))
            elif op in {"forward", "back"}:
                s = replace(s, position=max(0, min(s.duration or 0,
                    (s.position or 0) + (10 if op == "forward" else -10))))
            self.state = replace(s, revision=s.revision + 1,
                message=f"Simulated {op.replace('_', ' ')} - no phone audio")

    def scenario(self, name):
        with self.lock:
            if name == "disconnect":
                self.state = self.state.offline("SIMULATED connection loss")
            elif name == "unsupported":
                self.state = replace(self.state, capabilities=frozenset({"play", "pause", "toggle"}))
            elif name == "missing_artwork":
                self.state = replace(self.state, artwork_id="", artwork_bytes=b"")
            elif name == "missing_metadata":
                self.state = replace(self.state, title="", artist="", duration=None, position=None,
                    artwork_id="", artwork_bytes=b"")
            elif name == "other_app":
                self.state = replace(self.state, player="Other app", capabilities=frozenset())
            elif name == "switch_app":
                name = "YouTube Music" if self.state.player == "Spotify" else "Spotify"
                self.state = replace(self.state, player=name)
            elif name == "reset":
                fresh = DemoTransport()
                self.state, self.index = fresh.state, fresh.index
            else:
                raise ValueError("Unknown scenario")
