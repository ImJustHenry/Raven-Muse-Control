"""Bounded image processing, chunk protocol and an optional artwork worker.
No Qt imports. Network lookup is off by default; no audio or music accounts.
"""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
from io import BytesIO
import struct
import threading
import time
from PIL import Image, ImageOps
from .model import supported_player

MAX_IMAGE_BYTES = 16_384
MAX_DOWNLOAD_BYTES = 1_048_576
MAX_PIXELS = 4_194_304
CHUNK_SIZE = 480
HEADER = struct.Struct("<B8sII")
REQUEST = struct.Struct("<B8sI")


def thumbnail(raw):
    """Validate before decoding. Return a metadata-free 64px JPEG (or fail)."""
    if not raw or len(raw) > MAX_DOWNLOAD_BYTES:
        raise ValueError("Artwork byte limit")
    with Image.open(BytesIO(raw)) as image:
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Unsupported artwork format")
        if image.width < 1 or image.height < 1 or image.width * image.height > MAX_PIXELS:
            raise ValueError("Artwork pixel limit")
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("Animated artwork is not supported")
        image.load()
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        # Letterbox rather than cropping a real album cover.
        rgb.thumbnail((64, 64), Image.Resampling.LANCZOS)
        square = Image.new("RGB", (64, 64), (5, 12, 15))
        square.paste(rgb, ((64-rgb.width)//2, (64-rgb.height)//2))
        buffer = BytesIO()
        square.save(buffer, "JPEG", quality=82, optimize=True)
    result = buffer.getvalue()
    if len(result) > MAX_IMAGE_BYTES:
        raise ValueError("Thumbnail size limit")
    return result


class ChunkAssembler:
    """Strict ordered chunks; token binds all bytes to the same artwork."""
    def __init__(self, token):
        if not isinstance(token, str) or len(token) != 16:
            raise ValueError("Invalid artwork token")
        self.token = bytes.fromhex(token)
        self.data = bytearray()
        self.total = None

    def request(self):
        return REQUEST.pack(1, self.token, len(self.data))

    def append(self, packet):
        if len(packet) <= HEADER.size or len(packet) > HEADER.size + CHUNK_SIZE:
            raise ValueError("Invalid artwork chunk length")
        version, token, offset, total = HEADER.unpack_from(packet)
        payload = packet[HEADER.size:]
        if version != 1 or token != self.token or offset != len(self.data):
            raise ValueError("Stale or out-of-order artwork")
        if not 0 < total <= MAX_IMAGE_BYTES or (self.total is not None and total != self.total):
            raise ValueError("Invalid artwork total")
        if offset + len(payload) > total:
            raise ValueError("Artwork chunk overflow")
        self.total = total
        self.data.extend(payload)
        return len(self.data) == total


class LruCache:
    def __init__(self, limit=48):
        self.limit = max(1, min(48, limit))
        self.items = OrderedDict()

    def get(self, key, now=None):
        now = time.monotonic() if now is None else now
        value = self.items.get(key)
        if value is None:
            return None
        expires, result = value
        if expires <= now:
            del self.items[key]
            return None
        self.items.move_to_end(key)
        return result

    def put(self, key, result, ttl=1800, now=None):
        now = time.monotonic() if now is None else now
        self.items[key] = (now + ttl, result)
        self.items.move_to_end(key)
        while len(self.items) > self.limit:
            self.items.popitem(last=False)


@dataclass(frozen=True)
class ArtResult:
    data: bytes = b""
    source: str = "unavailable"
    attribution: str = ""


def state_key(state):
    # Deliberately not revision: progress ticks must not trigger a new download.
    return (state.player, state.title, state.artist, state.album,
            state.track_id, state.artwork_id,
            hashlib.sha256(state.artwork_bytes).digest() if state.artwork_bytes else b"")


class ArtworkManager:
    """One daemon worker, one replaceable job, memory-only LRU. UI never waits.

    Calling observe after metadata changes clears the displayed result immediately.
    The worker can finish an old request but can never publish it to a new track.
    """
    def __init__(self, config, resolver=None):
        self.enabled = config.get("artwork_enabled", True) is True
        self.online = (config.get("mode") == "iphone"
            and config.get("online_artwork_consent") is True
            and config.get("artwork_lookup") == "musicbrainz")
        self.resolver = resolver
        if self.online and resolver is None:
            from .artwork_lookup import MusicBrainzLookup
            self.resolver = MusicBrainzLookup(config.get("artwork_contact", ""))
        self.lock = threading.Condition()
        self.cache = LruCache()
        self.key = None
        self.result = ArtResult()
        self.changed_at = 0.0
        self.pending = None
        self.submitted = None
        self.closed = False
        self.worker = None

    def observe(self, state, now=None):
        now = time.monotonic() if now is None else now
        active = self.enabled and state.connected and supported_player(state.player) and bool(state.title)
        key = state_key(state) if active else None
        with self.lock:
            if key != self.key:
                self.key = key
                self.result = ArtResult()
                self.changed_at = now
                self.pending = self.submitted = None
            if key is None or self.closed:
                return self.result
            cached = self.cache.get(key, now)
            if cached is not None:
                self.result = cached
                return cached
            if self.submitted == key:
                return self.result
            direct = bool(state.artwork_bytes)
            # AMS attributes arrive separately. Wait for a quiet metadata interval.
            eligible = direct or (self.online and not state.simulated
                and not state.truncated and state.artist and state.album and now-self.changed_at >= .8)
            if not eligible:
                return self.result
            self.submitted = key
            self.pending = (key, state)
            if self.worker is None:
                self.worker = threading.Thread(target=self._run, name="muse-artwork", daemon=True)
                self.worker.start()
            self.lock.notify()
            return self.result

    def _run(self):
        while True:
            with self.lock:
                while self.pending is None and not self.closed:
                    self.lock.wait()
                if self.closed:
                    return
                key, state = self.pending
                self.pending = None
            try:
                if state.artwork_bytes:
                    result = ArtResult(thumbnail(state.artwork_bytes),
                        "demo" if state.simulated else "phone", "Original demo artwork" if state.simulated else "Phone media session")
                elif self.online:
                    result = self.resolver.lookup(state)
                else:
                    result = ArtResult()
            except Exception:
                # No song titles, image bytes, credentials or queries in logs.
                result = ArtResult()
            with self.lock:
                if self.closed:
                    return
                self.cache.put(key, result, ttl=1800 if result.data else 60)
                if key == self.key:
                    self.result = result
                    self.submitted = None

    def close(self):
        with self.lock:
            self.closed = True
            self.pending = None
            self.result = ArtResult()
            self.cache.items.clear()
            self.lock.notify_all()
        # No blocking join on Qt shutdown; HTTP has timeouts and a total deadline.
