"""HTTP boundary tests with an entirely fake requests.Session."""
import json
import time
import pytest
import requests
from muse.artwork_lookup import MusicBrainzLookup
from muse.artwork import MAX_DOWNLOAD_BYTES


class Response:
    def __init__(self, status=200, headers=None, chunks=None):
        self.status_code = status; self.headers = headers or {}; self.chunks = chunks or [b"ok"]
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError(str(self.status_code))
    def iter_content(self, size): yield from self.chunks


def fake_session(monkeypatch, responses):
    calls = []
    class Session:
        trust_env = True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            assert not self.trust_env
            assert kwargs["timeout"] == (3,5) and not kwargs["allow_redirects"] and kwargs["stream"]
            assert "Raven-Muse-Control/1.3.0" in kwargs["headers"]["User-Agent"]
            calls.append(url)
            return responses.pop(0)
    monkeypatch.setattr(requests, "Session", Session)
    return calls


def test_redirect_host_validated_before_second_request(monkeypatch):
    calls = fake_session(monkeypatch, [Response(307, {"Location":"https://evil.example/image"})])
    with pytest.raises(ValueError):
        MusicBrainzLookup("https://example.org/contact")._get("https://coverartarchive.org/test", time.monotonic()+10)
    assert len(calls) == 1


def test_archive_redirect_upgraded_not_fetched_in_cleartext(monkeypatch):
    calls = fake_session(monkeypatch, [Response(307, {"Location":"http://archive.org/image"}), Response()])
    assert MusicBrainzLookup("https://example.org/contact")._get(
        "https://coverartarchive.org/test", time.monotonic()+10) == b"ok"
    assert calls[-1] == "https://archive.org/image"


@pytest.mark.parametrize("response", [
    Response(headers={"Content-Length":str(MAX_DOWNLOAD_BYTES+1)}),
    Response(chunks=[b"x"*MAX_DOWNLOAD_BYTES, b"y"]),
])
def test_response_limits_enforced(monkeypatch, response):
    fake_session(monkeypatch, [response])
    with pytest.raises(ValueError):
        MusicBrainzLookup("https://example.org/contact")._get("https://archive.org/test", time.monotonic()+10)


def test_expired_request_does_not_access_network(monkeypatch):
    calls = fake_session(monkeypatch, [])
    with pytest.raises(ValueError):
        MusicBrainzLookup("https://example.org/contact")._get("https://archive.org/test", time.monotonic()-1)
    assert not calls


def test_redirect_limit(monkeypatch):
    calls = fake_session(monkeypatch, [Response(307, {"Location":"https://archive.org/loop"}) for _ in range(5)])
    with pytest.raises(ValueError, match="redirect"):
        MusicBrainzLookup("https://example.org/contact")._get("https://archive.org/test", time.monotonic()+10)
    assert len(calls) == 5


def test_http_404_not_silently_decoded_as_image(monkeypatch):
    fake_session(monkeypatch, [Response(404)])
    with pytest.raises(requests.HTTPError):
        MusicBrainzLookup("https://example.org/contact")._get("https://archive.org/test", time.monotonic()+10)


def test_musicbrainz_rate_limiter(monkeypatch):
    fake_session(monkeypatch, [Response()])
    sleeps = []
    monkeypatch.setattr(time, "monotonic", lambda: 100)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    monkeypatch.setattr(MusicBrainzLookup, "_last_request", 99.7)
    MusicBrainzLookup("https://example.org/contact")._get("https://musicbrainz.org/test", 110, True)
    assert sleeps[0] >= .79


@pytest.mark.parametrize("contact", ["", "\r\nHeader: broken", "☃", "x"*201])
def test_user_agent_contact_validated(contact):
    with pytest.raises(ValueError): MusicBrainzLookup(contact)
