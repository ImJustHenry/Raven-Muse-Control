"""Authenticated BLE link to the Android media-session bridge."""
import asyncio
from dataclasses import replace
import hashlib
import hmac
import json
import struct
import time
from .ble_base import BleTransport
from .model import State, finite, OPS
from .artwork import ChunkAssembler, LruCache, thumbnail

SERVICE = "7c27f100-6baa-4ad0-8e3b-31f62b88ac50"
AUTH = "7c27f101-6baa-4ad0-8e3b-31f62b88ac50"
STATE = "7c27f102-6baa-4ad0-8e3b-31f62b88ac50"
COMMAND = "7c27f103-6baa-4ad0-8e3b-31f62b88ac50"
SIGNAL = "7c27f104-6baa-4ad0-8e3b-31f62b88ac50"
ARTWORK = "7c27f105-6baa-4ad0-8e3b-31f62b88ac50"


def hex_id(value):
    return value if isinstance(value, str) and len(value) == 16 and all(c in "0123456789abcdef" for c in value) else ""

COMMANDS = {"play": 1, "pause": 2, "toggle": 3, "next": 4, "previous": 5,
            "volume_up": 6, "volume_down": 7, "forward": 8, "back": 9}
PLAYER_CODES = {"Spotify": 1, "YouTube Music": 2}


def auth_parts(secret, nonce):
    if len(secret) != 32 or len(nonce) != 16:
        raise ValueError("Invalid authentication input length")
    digest = hmac.new(secret, b"RMC1" + nonce, hashlib.sha256).digest()
    # Each frame fits the 20-byte payload at the default BLE MTU.
    return bytes([0]) + digest[:16], bytes([1]) + digest[16:]


def command_frame(op, sequence, player):
    if not 0 < sequence < 2**31:
        raise ValueError("Reconnect before sequence exhaustion")
    return struct.pack("<BBIB", 1, COMMANDS[op], sequence, PLAYER_CODES[player])


def decode_state(raw):
    if len(raw) > 512:
        raise ValueError("Bridge state exceeds GATT attribute size")
    data = json.loads(bytes(raw))
    if data.get("v") != 1:
        raise ValueError("Unsupported bridge protocol")
    playing = data.get("playing")
    if not isinstance(playing, bool):
        playing = None
    return State(connected=True, player=str(data.get("player", ""))[:40],
        title=str(data.get("title") or "")[:160], artist=str(data.get("artist") or "")[:100],
        playing=playing, position=finite(data.get("position")), duration=finite(data.get("duration")),
        rate=(finite(data.get("rate"), -16) or 0) if playing else 0,
        volume=finite(data.get("volume")), sampled_at=time.monotonic(),
        capabilities=frozenset(data.get("caps", [])) & OPS,
        message=str(data.get("message", "Android connected"))[:140],
        truncated=bool(data.get("truncated", False)), revision=int(data.get("rev", 0)),
        album=str(data.get("album") or "")[:100], track_id=hex_id(data.get("tid")),
        artwork_id=hex_id(data.get("art")))


class AndroidTransport(BleTransport):
    def __init__(self, address, secret_hex, pair_on_connect=False, artwork_enabled=True):
        super().__init__(address, pair_on_connect)
        self.artwork_enabled = artwork_enabled
        self.art_cache = LruCache()
        self.assembly = None
        self.art_key = None
        self.art_retry = 0.0
        self.secret = bytes.fromhex(secret_hex)
        if len(self.secret) != 32:
            raise ValueError("Copy the 64-character secret from the Android companion")

    async def setup(self, client):
        if not client.services.get_service(SERVICE):
            raise ValueError("Raven-Muse-Control bridge is not running")
        nonce = bytes(await client.read_gatt_char(AUTH))
        for part in auth_parts(self.secret, nonce):
            await client.write_gatt_char(AUTH, part, response=True)
        self.sequence, self.last_read, self.dirty = 0, 0, True
        self.has_artwork = self.artwork_enabled and client.services.get_characteristic(ARTWORK) is not None
        self.assembly = self.art_key = None
        self.art_retry = 0.0
        await client.start_notify(SIGNAL, lambda *_: setattr(self, "dirty", True))
        await self.tick(client)

    async def read_state(self, client):
        self.dirty = False
        state = decode_state(await client.read_gatt_char(STATE))
        key = (state.track_id, state.artwork_id)
        if key != self.art_key:
            self.assembly = None
            self.art_key = key
            self.art_retry = 0.0
        cached = self.art_cache.get(key) if all(key) else None
        if cached:
            state = replace(state, artwork_bytes=cached)
        with self.lock:
            self.state = state
        self.last_read = time.monotonic()
        return state

    async def tick(self, client):
        if self.dirty or time.monotonic() - self.last_read > 1:
            await self.read_state(client)
        # No parallel GATT operations. At most one bounded chunk per loop;
        # queued playback commands take priority over artwork transfers.
        if getattr(self, "has_artwork", False) and self.outgoing.empty():
            await self.read_artwork_chunk(client)

    async def read_artwork_chunk(self, client):
        state = self.snapshot()
        key = (state.track_id, state.artwork_id)
        if not all(key) or state.artwork_bytes or time.monotonic() < self.art_retry:
            return
        try:
            if self.assembly is None:
                self.assembly = ChunkAssembler(state.artwork_id)
            await asyncio.wait_for(client.write_gatt_char(ARTWORK, self.assembly.request(), response=True), 1)
            packet = await asyncio.wait_for(client.read_gatt_char(ARTWORK), 1)
            if not self.assembly.append(packet):
                return
            raw = bytes(self.assembly.data)
            self.assembly = None
            if hashlib.sha256(state.track_id.encode("ascii") + raw).hexdigest()[:16] != state.artwork_id:
                raise ValueError("Artwork integrity mismatch")
            image = thumbnail(raw)
            # Re-read authoritative state before publishing a completed image.
            fresh = await self.read_state(client)
            if (fresh.track_id, fresh.artwork_id) == key:
                self.art_cache.put(key, image)
                self.update(artwork_bytes=image)
        except Exception:
            self.assembly = None
            self.art_retry = time.monotonic() + 10
            # Artwork failure never disables playback or disconnects the bridge.

    async def execute(self, client, op, player):
        self.sequence += 1
        await client.write_gatt_char(COMMAND, command_frame(op, self.sequence, player), response=True)
        self.update(message="Sent to Android; waiting for reported media state")
        self.dirty = True
