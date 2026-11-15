from pathlib import Path
from dataclasses import replace
import io
import wave
import pytest
from muse.android import auth_parts
from muse.iphone import IphoneTransport
from muse.model import State
from muse.voice import pcm16_mono

ROOT = Path(__file__).resolve().parents[1]


def test_no_phone_music_player_or_internet_permission():
    manifest = (ROOT / 'android/app/src/main/AndroidManifest.xml').read_text()
    assert 'android.permission.INTERNET' not in manifest
    assert 'connectedDevice' in manifest
    assert 'mediaPlayback' not in manifest
    code = '\n'.join(p.read_text() for p in (ROOT / 'android').rglob('*.kt'))
    assert 'ExoPlayer' not in code and 'onNotificationPosted' not in code
    assert 'com.spotify.music' in code and 'com.google.android.apps.youtube.music' in code


def test_queued_action_does_not_mutate_playback_and_is_clearable():
    transport = IphoneTransport('not-a-real-radio-target')
    transport.state = State(connected=True, player='Spotify', playing=True,
        capabilities=frozenset({'pause'}), title='Existing song')
    transport.send('pause')
    assert transport.snapshot().playing is True
    assert transport.outgoing.qsize() == 1
    transport.clear_queue()
    assert transport.outgoing.empty()


def test_nonce_changes_authentication_proof():
    key = b'K' * 32
    assert auth_parts(key, b'A' * 16) != auth_parts(key, b'B' * 16)


def test_overlong_audio_rejected():
    output = io.BytesIO()
    with wave.open(output, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b'\0\0' * 16000 * 9)
    with pytest.raises(ValueError):
        pcm16_mono(output.getvalue())
