"""Opt-in MusicBrainz + Cover Art Archive matching, not a music service login.
Metadata-matched covers can differ from the phone's exact edition. Never scrape
Spotify/YouTube. See ARTWORK.md for privacy, rights and commercial-use caveats.
"""
import json
import re
import threading
import time
import unicodedata
from urllib.parse import urlencode, urljoin, urlsplit
from uuid import UUID
import requests
from .artwork import ArtResult, MAX_DOWNLOAD_BYTES, thumbnail


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", str(text)).casefold().split())


def quoted(text):
    # Literal Lucene term inside quotes, then separately URL encoded.
    return '"' + re.sub(r'([+\-!(){}\[\]^"~*?:\\/|&])', r'\\\1', str(text)[:300]) + '"'


def allowed_url(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    hosts = {"musicbrainz.org", "coverartarchive.org", "archive.org"}
    return (parts.scheme == "https" and not parts.username and not parts.password
        and parts.port in {None, 443} and (host in hosts or host.endswith(".archive.org")))


def choose_release(payload, state):
    """Conservative exact text match; no fuzzy-remix or first-search-hit fallback."""
    candidates = {}
    for recording in payload.get("recordings", [])[:5]:
        credit = "".join(c.get("name", c.get("artist", {}).get("name", ""))
            + c.get("joinphrase", "") for c in recording.get("artist-credit", []) if isinstance(c, dict))
        if normalized(recording.get("title", "")) != normalized(state.title):
            continue
        if normalized(credit) != normalized(state.artist):
            continue
        length = recording.get("length")
        if state.duration is not None and length is not None:
            if abs(float(length)/1000-state.duration) > 3:
                continue
        releases = []
        for release in recording.get("releases", []):
            if normalized(release.get("title", "")) == normalized(state.album):
                try:
                    releases.append(str(UUID(release["id"])))
                except (ValueError, KeyError, TypeError):
                    pass
        if releases:
            candidates[recording.get("id", "")] = sorted(releases)
    if len(candidates) != 1:
        return None
    return next(iter(candidates.values()))[0]


class MusicBrainzLookup:
    _rate_lock = threading.Lock()
    _last_request = 0.0

    def __init__(self, contact):
        if (not isinstance(contact, str) or not contact.strip() or len(contact) > 200
                or any(ord(c) < 32 or ord(c) > 126 for c in contact)):
            raise ValueError("Online artwork requires artwork_contact: your public contact URL/email")
        self.user_agent = f"Raven-Muse-Control/1.3.0 ({contact.strip()})"

    def _get(self, url, deadline, musicbrainz=False):
        # Bound every redirect and response; do not send phone credentials/cookies.
        with requests.Session() as session:
            session.trust_env = False
            for _ in range(5):
                if not allowed_url(url) or time.monotonic() >= deadline:
                    raise ValueError("Artwork URL or time limit")
                if urlsplit(url).hostname == "musicbrainz.org":
                    # Rate limit actual HTTP requests, including redirects.
                    with self._rate_lock:
                        wait = max(0, 1.1 - (time.monotonic()-type(self)._last_request))
                        time.sleep(wait)
                        type(self)._last_request = time.monotonic()
                    if time.monotonic() >= deadline:
                        raise ValueError("Artwork time limit")
                with session.get(url, headers={"User-Agent": self.user_agent,
                    "Accept": "application/json" if musicbrainz else "image/jpeg,image/png,image/webp"},
                    timeout=(3, 5), allow_redirects=False, stream=True) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        url = urljoin(url, response.headers.get("Location", ""))
                        # Older CAA redirects can name HTTP Archive URLs. Upgrade;
                        # never actually issue a cleartext request.
                        p = urlsplit(url)
                        if p.scheme == "http" and ((p.hostname or "") == "archive.org"
                                or (p.hostname or "").endswith(".archive.org")):
                            url = "https:" + url[5:]
                        continue
                    response.raise_for_status()
                    if int(response.headers.get("Content-Length", "0")) > MAX_DOWNLOAD_BYTES:
                        raise ValueError("Artwork download too large")
                    data = bytearray()
                    for chunk in response.iter_content(8192):
                        if time.monotonic() >= deadline or len(data)+len(chunk) > MAX_DOWNLOAD_BYTES:
                            raise ValueError("Artwork response limit")
                        data.extend(chunk)
                    return bytes(data)
        raise ValueError("Artwork redirect limit")

    def lookup(self, state):
        if not state.title or not state.artist or not state.album or state.truncated:
            return ArtResult()
        deadline = time.monotonic() + 25
        query = " AND ".join(("recording:"+quoted(state.title),
            "artist:"+quoted(state.artist), "release:"+quoted(state.album)))
        url = "https://musicbrainz.org/ws/2/recording/?" + urlencode(
            {"query": query, "fmt": "json", "limit": 5})
        release = choose_release(json.loads(self._get(url, deadline, True)), state)
        if release is None:
            return ArtResult()
        raw = self._get(f"https://coverartarchive.org/release/{release}/front-250", deadline)
        return ArtResult(thumbnail(raw), "matched",
            f"MusicBrainz / Cover Art Archive; metadata match, not phone artwork. Release: {release}")
