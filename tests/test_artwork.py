"""Offline artwork/protocol tests. Fake BLE and HTTP, never physical phones."""
import asyncio
from dataclasses import replace
import hashlib
from io import BytesIO
import json
import struct
import threading
import time
from uuid import UUID
import pytest
from PIL import Image
from muse.artwork import (ArtResult, ArtworkManager, ChunkAssembler, HEADER,
    LruCache, MAX_IMAGE_BYTES, thumbnail)
from muse.artwork_lookup import allowed_url, choose_release, MusicBrainzLookup, quoted
from muse.demo_art import demo_cover
from muse.iphone import apply_attribute
from muse.model import State
from muse.android import AndroidTransport, ARTWORK, STATE, COMMAND, decode_state


def playing(**kw):
    return replace(State(connected=True, player="Spotify", title="Night", artist="Artist",
        album="Album", duration=180, capabilities=frozenset({"pause", "next"}), playing=True), **kw)


def wait_for(test, timeout=2):
    end = time.monotonic() + timeout
    while not test():
        if time.monotonic() > end:
            raise AssertionError("Artwork worker timed out")
        time.sleep(.01)


def test_thumbnail_bounds_and_no_metadata():
    raw = thumbnail(demo_cover(0))
    assert len(raw) <= MAX_IMAGE_BYTES
    with Image.open(BytesIO(raw)) as image:
        assert image.size == (64, 64) and image.format == "JPEG" and not image.getexif()


@pytest.mark.parametrize("raw", [b"", b"not an image", b"x" * 1_048_577])
def test_invalid_image_rejected(raw):
    with pytest.raises((ValueError, OSError)):
        thumbnail(raw)


def test_pixel_bomb_rejected_before_full_decode():
    image = Image.new("RGB", (2100, 2100))
    out = BytesIO(); image.save(out, "PNG")
    with pytest.raises(ValueError, match="pixel"):
        thumbnail(out.getvalue())


def test_animation_rejected():
    out = BytesIO()
    Image.new("RGB", (64,64), "red").save(out, "PNG", save_all=True,
        append_images=[Image.new("RGB", (64,64), "blue")])
    with pytest.raises(ValueError, match="Animated"):
        thumbnail(out.getvalue())


def test_lru_bounded_and_expiring():
    cache = LruCache(2)
    cache.put("a", b"a", now=0, ttl=10)
    cache.put("b", b"b", now=0, ttl=10)
    assert cache.get("a", now=1) == b"a"
    cache.put("c", b"c", now=2, ttl=10)
    assert cache.get("b", now=2) is None
    assert cache.get("a", now=11) is None and len(cache.items) == 1


def test_chunk_roundtrip_and_request_default_mtu():
    token = "0123456789abcdef"
    a = ChunkAssembler(token)
    assert len(a.request()) == 13 <= 20
    raw = b"x" * 1000
    for offset in range(0, len(raw), 480):
        packet = HEADER.pack(1, bytes.fromhex(token), offset, len(raw)) + raw[offset:offset+480]
        done = a.append(packet)
    assert done and bytes(a.data) == raw


@pytest.mark.parametrize("version,token,offset,total,payload", [
    (2, "0123456789abcdef", 0, 1, b"a"),
    (1, "1123456789abcdef", 0, 1, b"a"),
    (1, "0123456789abcdef", 1, 2, b"a"),
    (1, "0123456789abcdef", 0, 20000, b"a"),
    (1, "0123456789abcdef", 0, 1, b"ab"),
    (1, "0123456789abcdef", 0, 0, b"a"),
    (1, "0123456789abcdef", 0, 481, b"a"*481),
])
def test_bad_chunk_rejected(version, token, offset, total, payload):
    a = ChunkAssembler("0123456789abcdef")
    with pytest.raises(ValueError):
        a.append(HEADER.pack(version, bytes.fromhex(token), offset, total)+payload)


def test_chunk_total_cannot_change():
    a = ChunkAssembler("0123456789abcdef")
    a.append(HEADER.pack(1, a.token, 0, 4)+b"a")
    with pytest.raises(ValueError):
        a.append(HEADER.pack(1, a.token, 1, 3)+b"b")


def test_ams_album_received_without_invented_art():
    state = apply_attribute(playing(), 2, 1, "New album")
    assert state.album == "New album" and not state.artwork_bytes


def test_offline_clears_artwork_bytes():
    state = playing(artwork_bytes=demo_cover(0), artwork_id="a").offline("gone")
    assert not state.artwork_bytes and not state.artwork_id


@pytest.mark.parametrize("config", [
    {"mode":"iphone"}, {"mode":"iphone", "artwork_lookup":"musicbrainz"},
    {"mode":"iphone", "online_artwork_consent":True},
    {"mode":"android", "online_artwork_consent":True, "artwork_lookup":"musicbrainz"},
])
def test_no_network_without_exact_iphone_opt_in(config):
    class Forbidden:
        def lookup(self, state):
            raise AssertionError("Network must not be used")
    manager = ArtworkManager(config, Forbidden())
    manager.observe(playing(), now=0); manager.observe(playing(), now=3)
    assert not manager.online and manager.worker is None
    manager.close()


def test_disabling_art_prevents_worker():
    manager = ArtworkManager({"mode":"demo", "artwork_enabled":False})
    assert not manager.observe(playing(artwork_bytes=demo_cover(0))).data
    assert manager.worker is None
    manager.close()


def test_direct_art_and_track_change_clear_immediately():
    manager = ArtworkManager({"mode":"android"})
    state = playing(artwork_bytes=demo_cover(0))
    manager.observe(state)
    wait_for(lambda: bool(manager.observe(state).data))
    assert manager.observe(state).source == "phone"
    assert not manager.observe(replace(state, title="Next", artwork_bytes=b"")).data
    assert not manager.observe(state.offline("gone")).data
    manager.close()


def test_late_online_result_never_published_for_new_track():
    start = threading.Event(); release = threading.Event()
    class Slow:
        def lookup(self, state):
            start.set(); release.wait(2)
            return ArtResult(thumbnail(demo_cover(0)), "matched")
    manager = ArtworkManager({"mode":"iphone", "online_artwork_consent":True,
        "artwork_lookup":"musicbrainz"}, Slow())
    state = playing()
    manager.observe(state, now=0); manager.observe(state, now=1)
    assert start.wait(2)
    assert not manager.observe(replace(state, title="Next"), now=2).data
    release.set(); wait_for(lambda: bool(manager.cache.items))
    assert not manager.result.data
    manager.close()


def test_progress_ticks_reuse_cache():
    manager = ArtworkManager({"mode":"demo"})
    state = playing(simulated=True, artwork_bytes=demo_cover(0))
    manager.observe(state); wait_for(lambda: bool(manager.observe(state).data))
    image = manager.observe(state)
    assert manager.observe(replace(state, revision=555, position=80)) == image
    assert len(manager.cache.items) == 1
    manager.close()


def test_lookup_requires_metadata_and_settle_interval():
    manager = ArtworkManager({"mode":"iphone", "online_artwork_consent":True,
        "artwork_lookup":"musicbrainz"}, object())
    manager.observe(playing(album=""), now=0); manager.observe(playing(album=""), now=3)
    assert manager.worker is None
    manager.observe(playing(), now=4); manager.observe(playing(), now=4.5)
    assert manager.worker is None
    manager.close()


def payload():
    return {"recordings":[{"id":"11111111-1111-4111-8111-111111111111", "title":"Night", "length":180000,
        "artist-credit":[{"name":"Artist"}],
        "releases":[{"id":"22222222-2222-4222-8222-222222222222", "title":"Album"}]}]}


def test_exact_lookup_match():
    assert choose_release(payload(), playing()) == "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize("changes", [{"title":"Night (Live)"}, {"artist":"Someone else"},
    {"album":"Different"}, {"duration":190}])
def test_inexact_lookup_rejected(changes):
    assert choose_release(payload(), playing(**changes)) is None


def test_ambiguous_recordings_rejected():
    p = payload(); p["recordings"].append(dict(p["recordings"][0], id="different"))
    assert choose_release(p, playing()) is None


@pytest.mark.parametrize("url", ["http://musicbrainz.org/a", "https://localhost/x", "https://127.0.0.1/",
    "https://archive.org.evil.example/x", "https://x@archive.org/x", "https://archive.org:444/x"])
def test_unsafe_artwork_hosts_rejected(url):
    assert not allowed_url(url)


def test_known_https_hosts_allowed_and_query_escaped():
    assert allowed_url("https://ia800000.us.archive.org/test")
    assert allowed_url("https://coverartarchive.org/test")
    assert '\\"' in quoted('Name" OR *') and '\\*' in quoted('*')


def test_lookup_uses_api_and_image_validation_without_live_network(monkeypatch):
    lookup = MusicBrainzLookup("https://example.org/contact")
    calls = []
    def fake_get(url, deadline, musicbrainz=False):
        calls.append(url)
        return json.dumps(payload()).encode() if musicbrainz else demo_cover(1)
    monkeypatch.setattr(lookup, "_get", fake_get)
    result = lookup.lookup(playing())
    assert result.source == "matched" and result.data and len(calls) == 2
    assert "front-250" in calls[-1]


class FakePhone:
    def __init__(self, bad=False, switch_at_end=False):
        self.raw = thumbnail(demo_cover(0))
        self.tid = "1234567890abcdef"
        self.token = hashlib.sha256(self.tid.encode()+self.raw).hexdigest()[:16]
        self.packet = b""
        self.calls = []
        self.bad = bad
        self.switch_at_end = switch_at_end
        self.finished = False
    async def write_gatt_char(self, char, value, response=True):
        self.calls.append(("write", char))
        if char == ARTWORK:
            _, token, offset = struct.unpack("<B8sI", value)
            self.packet = HEADER.pack(1, token, offset, len(self.raw)) + self.raw[offset:offset+480]
            self.finished = offset+480 >= len(self.raw)
    async def read_gatt_char(self, char):
        self.calls.append(("read", char))
        if char == ARTWORK:
            return b"broken" if self.bad else self.packet
        return json.dumps({"v":1, "player":"Spotify", "title":"New" if self.finished and self.switch_at_end else "Night",
            "artist":"Artist", "tid":"aaaaaaaaaaaaaaaa" if self.finished and self.switch_at_end else self.tid,
            "art":"" if self.finished and self.switch_at_end else self.token,
            "caps":["pause", "next"], "playing":True}).encode()


def transport():
    t = AndroidTransport("fake", "00"*32)
    t.has_artwork = True; t.dirty = True; t.last_read = 0
    return t


def test_fake_ble_full_transfer_and_cache():
    async def run():
        t = transport(); phone = FakePhone()
        for _ in range(30):
            await t.tick(phone)
            if t.snapshot().artwork_bytes: break
        assert t.snapshot().artwork_bytes
        count = len(phone.calls)
        await t.tick(phone)
        assert len(phone.calls) == count
        await t.read_state(phone)
        assert t.snapshot().artwork_bytes
    asyncio.run(run())


def test_fake_ble_failure_keeps_playback_enabled():
    async def run():
        t = transport(); phone = FakePhone(bad=True)
        await t.tick(phone)
        assert not t.snapshot().artwork_bytes and t.snapshot().can("pause")
        assert t.art_retry > time.monotonic()
    asyncio.run(run())


def test_fake_ble_recheck_rejects_previous_track():
    async def run():
        t = transport(); phone = FakePhone(switch_at_end=True)
        for _ in range(30): await t.tick(phone)
        assert t.snapshot().title == "New" and not t.snapshot().artwork_bytes
    asyncio.run(run())


def test_queued_command_takes_priority_over_artwork():
    async def run():
        t = transport(); phone = FakePhone()
        await t.read_state(phone)
        t.send("pause"); phone.calls.clear()
        await t.tick(phone)
        assert not phone.calls
    asyncio.run(run())


def test_old_bridge_without_artwork_still_decodes():
    s = decode_state(b'{"v":1,"player":"Spotify","caps":["pause"]}')
    assert s.can("pause") and not s.artwork_id and not s.artwork_bytes


def test_no_artwork_gatt_on_legacy_bridge():
    async def run():
        t = transport(); t.has_artwork = False; phone = FakePhone()
        await t.tick(phone)
        assert all(char != ARTWORK for _, char in phone.calls)
    asyncio.run(run())
