import asyncio
import hashlib
import hmac
import io
import json
import struct
import wave
from dataclasses import replace
import pytest
from muse.model import State, finite, supported_player
from muse.demo import DemoTransport
from muse.voice import parse, pcm16_mono, Transcriber
from muse.android import auth_parts, command_frame, decode_state, AndroidTransport, AUTH, STATE, COMMAND
from muse.iphone import apply_attribute, parse_update, IphoneTransport, REMOTE, UPDATE, ATTRIBUTE


@pytest.mark.parametrize("text,op", [
    ("Pause", "pause"), ("muse next song", "next"), ("please resume music", "play"),
    ("volume up", "volume_up"), ("quieter", "volume_down"), ("What's playing?", "now_playing"),
    ("skip forward", "forward"), ("skip back", "back"), ("previous track", "previous"),
    ("cancel", "cancel"), ("play a song called pause", None), ("next and pause", None),
    ("search for jazz", None), ("delete playlist", None), ("", None)])
def test_voice_allowlist(text, op):
    assert parse(text) == op


@pytest.mark.parametrize("value", [None, "bad", "NaN", float("inf"), -1])
def test_unknown_numbers(value):
    assert finite(value) is None


def test_position_and_unknowns():
    s = State(playing=True, rate=1, position=10, sampled_at=100, duration=20)
    assert s.elapsed(104) == 14
    assert s.elapsed(200) == 20
    assert replace(s, playing=False).elapsed(200) == 10
    assert replace(s, position=None).elapsed(200) is None
    assert not s.can("next")


def test_scope_and_capabilities():
    assert supported_player("Spotify") and supported_player("YouTube Music")
    s = State(connected=True, player="Other", capabilities=frozenset({"next"}))
    assert not s.can("next")
    s = replace(s, player="Spotify", playing=None, capabilities=frozenset({"toggle"}))
    assert s.toggle_action() == "toggle"
    assert s.offline("disconnected").capabilities == frozenset()


def test_demo_controls_and_scenarios():
    d = DemoTransport()
    assert d.snapshot().simulated
    d.send("pause"); assert d.snapshot().playing is False
    d.send("play"); assert d.snapshot().playing is True
    d.send("next"); assert "Golden Hour" in d.snapshot().title
    d.send("previous"); assert "Midnight" in d.snapshot().title
    d.send("volume_up"); assert d.snapshot().volume == pytest.approx(.45)
    d.scenario("switch_app"); assert d.snapshot().player == "YouTube Music"
    d.scenario("unsupported")
    with pytest.raises(ValueError): d.send("next")
    d.scenario("reset"); d.scenario("missing_metadata"); assert d.snapshot().title == ""
    d.scenario("disconnect")
    with pytest.raises(ValueError): d.send("play")


def test_android_auth_and_frames():
    key, nonce = bytes(range(32)), bytes(range(16))
    a, b = auth_parts(key, nonce)
    assert len(a) == len(b) == 17
    assert a[1:] + b[1:] == hmac.new(key, b"RMC1" + nonce, hashlib.sha256).digest()
    assert command_frame("next", 17, "YouTube Music") == struct.pack("<BBIB", 1, 4, 17, 2)
    for wrong in (0, 2**31):
        with pytest.raises(ValueError): command_frame("next", wrong, "Spotify")
    with pytest.raises(ValueError): auth_parts(b"short", nonce)


def test_android_unknown_metadata_and_version():
    s = decode_state(b'{"v":1,"player":"Spotify","caps":["next"],"playing":null}')
    assert s.title == "" and s.playing is None and s.duration is None and s.can("next")
    with pytest.raises(ValueError): decode_state(b'{"v":2}')
    with pytest.raises(ValueError): decode_state(b"x" * 513)


def test_ams_parsing_and_elapsed_anchor():
    assert parse_update(bytes([2, 2, 1]) + b"Long name") == (2, 2, True, "Long name")
    with pytest.raises(ValueError): parse_update(b"\x00")
    s = apply_attribute(State(), 0, 0, "Spotify", now=100)
    s = apply_attribute(s, 0, 1, "1,1,5", now=100)
    assert s.playing and s.elapsed(105) == 10
    s = apply_attribute(s, 2, 2, "Track", now=104)
    assert s.elapsed(105) == 10  # title update must NOT reset elapsed time's clock
    s = apply_attribute(s, 0, 1, "0,0,10", now=106)
    assert not s.playing and s.elapsed(200) == 10
    assert apply_attribute(s, 2, 3, "bad").duration is None


def test_wav_validation_and_resample():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
        w.writeframes(b"\0\0\0\0" * 48000)
    assert len(pcm16_mono(buf.getvalue())) == 32000
    with pytest.raises(ValueError):
        Transcriber({"voice_backend":"openai", "cloud_voice_consent":False}).recognize(buf.getvalue())


class Services:
    def get_service(self, value): return True
    def get_characteristic(self, value): return True


class FakeClient:
    services = Services()
    def __init__(self):
        self.writes = []; self.callbacks = {}
    async def start_notify(self, key, callback): self.callbacks[key] = callback
    async def write_gatt_char(self, key, value, response=True): self.writes.append((key, value))
    async def read_gatt_char(self, key):
        if key == AUTH: return bytes(range(16))
        if key == STATE:
            return b'{"v":1,"player":"Spotify","title":"Reported","caps":["next"],"playing":true}'
        if key == ATTRIBUTE: return b"Full title"
        raise ValueError(key)


def test_android_adapter_with_fake_gatt():
    async def run():
        client = FakeClient(); transport = AndroidTransport("test", "01" * 32)
        await transport.setup(client)
        assert transport.snapshot().title == "Reported"
        await transport.execute(client, "next", "Spotify")
        assert client.writes[-1][0] == COMMAND
        assert client.writes[-1][1] == command_frame("next", 1, "Spotify")
        assert transport.snapshot().title == "Reported"  # no invented post-command track
    asyncio.run(run())


def test_iphone_adapter_with_fake_gatt():
    async def run():
        client = FakeClient(); transport = IphoneTransport("test")
        await transport.setup(client)
        client.callbacks[REMOTE](None, bytes([0, 1, 2, 3]))
        client.callbacks[UPDATE](None, bytes([0, 0, 0]) + b"Spotify")
        client.callbacks[UPDATE](None, bytes([2, 2, 1]) + b"Truncated")
        assert transport.snapshot().can("next")
        await transport.tick(client)
        assert transport.snapshot().title == "Full title"
        await transport.execute(client, "pause", "Spotify")
        assert client.writes[-1] == (REMOTE, b"\x01")
        assert transport.snapshot().playing is None  # forwarding is not execution
        client.callbacks[UPDATE](None, bytes([0, 0, 0]) + b"Other App")
        assert not transport.snapshot().can("next")
    asyncio.run(run())
