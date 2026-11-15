"""Local, permission-labelled LRC catalog and Qt-free line-following state.
No commercial lyric retrieval, scraping, or automatic Spotify lyric integration.
"""
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
import json
import math
import re
import unicodedata

DATA = Path(__file__).with_name('demo_catalog')
STAMP = re.compile(r'\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]')


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


@dataclass(frozen=True)
class Line:
    seconds: float
    text: str


def parse_lrc(text):
    if len(text.encode('utf-8')) > 256_000:
        raise ValueError('LRC exceeds 256 KB')
    offset = 0.0
    entries = []
    for raw in text.splitlines():
        if raw.startswith('[offset:'):
            match = re.fullmatch(r'\[offset:([+-]?\d+)\]', raw.strip())
            if not match or abs(int(match[1])) > 30000:
                raise ValueError('Invalid LRC offset')
            offset = int(match[1])/1000
            continue
        stamps = list(STAMP.finditer(raw))
        if not stamps:
            if raw.startswith('[') and re.match(r'\[\d', raw):
                raise ValueError('Invalid lyric timestamp')
            continue
        content = raw[stamps[-1].end():].strip()
        if len(content) > 300 or any(ord(c)<32 for c in content):
            raise ValueError('Lyric line too long or contains controls')
        for stamp in stamps:
            minute, second, fraction = stamp.groups()
            if int(second) >= 60:
                raise ValueError('Seconds must be below 60')
            entries.append((int(minute)*60+int(second)+float('0.'+(fraction or '0')), content))
    if len(entries)>2000 or not entries:
        raise ValueError('No timed lyrics, or too many lines')
    # Deterministic last-line-wins for a duplicate timestamp; empty lines end a cue.
    unique = {max(0,sec+offset):body for sec,body in entries}
    return tuple(Line(sec,body) for sec,body in sorted(unique.items()))


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artist: str
    duration: float
    rights: str
    lines: tuple[Line, ...]
    audio: Path
    demo: bool = True


class Catalog:
    def __init__(self, root=DATA):
        self.root = Path(root).resolve()
        raw = (self.root/'catalog.json').read_bytes()
        if len(raw)>64000: raise ValueError('Catalog too large')
        rows = json.loads(raw)
        if not isinstance(rows,list) or not 1<=len(rows)<=20:
            raise ValueError('Catalog must contain 1–20 approved tracks')
        self.tracks = []
        for row in rows:
            if not row.get('rights'): raise ValueError('Track requires a rights statement')
            def safe_file(key):
                p=(self.root/row[key]).resolve()
                if not p.is_relative_to(self.root): raise ValueError('Catalog path traversal')
                return p
            duration=float(row['duration'])
            if not math.isfinite(duration) or not 1<=duration<=900: raise ValueError('Invalid duration')
            lines=parse_lrc(safe_file('lrc').read_text(encoding='utf-8'))
            if lines[-1].seconds>duration+1: raise ValueError('Lyrics exceed track duration')
            self.tracks.append(Track(row['id'],row['title'],row['artist'],duration,
                row['rights'],lines,safe_file('audio'),row.get('demo',True)))
        if len({t.id for t in self.tracks}) != len(self.tracks): raise ValueError('Duplicate catalog ID')

    def by_id(self, id):
        return next((t for t in self.tracks if t.id==id),None)

    def match(self, title, artist, duration, simulated=False):
        if simulated: title=title.removeprefix('Demo: ')
        candidates=[t for t in self.tracks if normalized(t.title)==normalized(title)
                    and normalized(t.artist)==normalized(artist)
                    and duration is not None and abs(t.duration-duration)<=1]
        return candidates[0] if len(candidates)==1 else None


class LyricCursor:
    def __init__(self):
        self.identity=None
        self.track=None
        self.following=True
        self.index=-1
        self.adjustment=0.0

    def select(self, identity, track):
        if identity != self.identity or track != self.track:
            self.identity,self.track=identity,track
            self.following,self.index,self.adjustment=True,-1,0.0

    def update(self, position):
        if not self.track or (self.following and (position is None or not math.isfinite(position))):
            return ('Timing uncertain' if self.track else 'No timed lyrics available','')
        if self.following:
            self.index=bisect_right([l.seconds for l in self.track.lines],position+self.adjustment)-1
        index=self.index
        current=self.track.lines[index].text if index>=0 else 'Lyrics begin shortly'
        upcoming=self.track.lines[index+1].text if index+1<len(self.track.lines) else ''
        return current or 'Instrumental / end of verse',upcoming

    def browse(self, delta):
        if self.track:
            self.following=False
            self.index=max(0,min(len(self.track.lines)-1,self.index+delta))

    def adjust(self, seconds):
        self.adjustment=max(-10.0,min(10.0,round(self.adjustment+seconds,2)))
        self.following=True
