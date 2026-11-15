"""No-audio fake-phone clock for the original lyric demo catalog."""
from dataclasses import replace
import time
from .demo import DemoTransport
from .lyrics import Catalog
from .demo_art import demo_cover


class CatalogDemoTransport(DemoTransport):
    def __init__(self):
        super().__init__()
        self.catalog=Catalog()
        self.select(0)

    def select(self,index):
        self.index=index%len(self.catalog.tracks)
        track=self.catalog.tracks[self.index]
        self.state=replace(self.state,title='Demo: '+track.title,artist=track.artist,
            duration=track.duration,position=0,sampled_at=time.monotonic(),
            track_id='mvp:'+track.id,artwork_id='demo-'+str(self.index),
            artwork_bytes=demo_cover(self.index),revision=self.state.revision+1,
            message='DEMO clock only — no audio output')

    def send(self,op):
        with self.lock:
            if op in {'next','previous'}:
                if not self.state.can(op): raise ValueError('Command unavailable')
                self.commands.append(op)
                self.select(self.index+(1 if op=='next' else -1))
            else: super().send(op)

    def snapshot(self):
        with self.lock:
            if (self.state.connected and self.state.playing and self.state.duration is not None
                    and self.state.elapsed() is not None and self.state.elapsed()>=self.state.duration):
                self.select(self.index+1)
            return self.state

    def scenario(self,name):
        if name=='reset':
            with self.lock:
                fresh=CatalogDemoTransport(); self.state,self.index=fresh.state,fresh.index
        else: super().scenario(name)
