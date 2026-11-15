import io
import json
import os
import threading
import time
import wave
from dataclasses import replace
import numpy as np
import pytest
from muse.lyrics import Catalog, LyricCursor, parse_lrc
from muse.recognition import LocalRecognizer, RecognitionJob, Recognition, audio_samples
from muse.discoveries import DiscoveryStore, search_link
from muse.mvp_demo import CatalogDemoTransport


@pytest.fixture(scope='module')
def catalog(): return Catalog()


@pytest.fixture(scope='module')
def recognizer(catalog): return LocalRecognizer(catalog)


def clip(track,start=8,length=6,noise=0,gain=1,rate=16000,stereo=False):
    from scipy.signal import resample_poly
    with wave.open(str(track.audio),'rb') as w:
        w.setpos(int(start*w.getframerate()))
        samples=np.frombuffer(w.readframes(int(length*w.getframerate())),dtype='<i2').astype(float)/32768
    if rate!=16000: samples=resample_poly(samples,rate,16000)
    samples=samples*gain+np.random.default_rng(891).normal(0,noise,len(samples))
    if stereo: samples=np.column_stack((samples,samples*.8)).ravel()
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(2 if stereo else 1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
    return out.getvalue()


def test_lrc_multiple_stamps_duplicates_offsets():
    rows=parse_lrc('[offset:500]\n[00:01.00][00:03.5]first\n[00:03.50]second\n[00:05.000]')
    assert [(r.seconds,r.text) for r in rows]==[(1.5,'first'),(4,'second'),(5.5,'')]


@pytest.mark.parametrize('text',['hello','[00:60]bad','[00:00.0000]bad','[offset:99999]\n[00:01]bad','[00:01]'+('x'*301),'x'*256001])
def test_bad_lrc(text):
    with pytest.raises(ValueError): parse_lrc(text)


def test_cursor_follow_browse_seek_pause_and_reset(catalog):
    cursor=LyricCursor(); t=catalog.tracks[0]
    cursor.select('a',t)
    assert cursor.update(1)[0]=='Lyrics begin shortly'
    assert cursor.update(2)[0]==t.lines[0].text
    assert cursor.update(10)[0]==t.lines[2].text
    cursor.browse(-1)
    assert cursor.update(25)[0]==t.lines[1].text
    assert cursor.update(None)[0]==t.lines[1].text
    cursor.following=True
    assert cursor.update(6)[0]==t.lines[1].text
    cursor.adjust(1)
    assert cursor.update(9)[0]==t.lines[2].text
    cursor.select('b',catalog.tracks[1])
    assert cursor.following and cursor.adjustment==0 and cursor.index==-1


def test_cursor_missing_timing(catalog):
    c=LyricCursor(); c.select('x',catalog.tracks[0])
    assert c.update(None)[0]=='Timing uncertain'
    assert c.update(float('nan'))[0]=='Timing uncertain'
    c.adjust(100); assert c.adjustment==10
    c.adjust(-100); assert c.adjustment==-10


def test_catalog_exact_match_only(catalog):
    t=catalog.tracks[0]
    assert catalog.match('Demo: '+t.title,t.artist,t.duration,True)==t
    assert catalog.match(t.title,'wrong artist',t.duration) is None
    assert catalog.match(t.title,t.artist,t.duration+3) is None
    assert catalog.match(t.title,t.artist,None) is None


def test_catalog_path_traversal(tmp_path):
    (tmp_path/'catalog.json').write_text(json.dumps([dict(id='x',title='x',artist='x',duration=10,rights='mine',lrc='../escape',audio='x.wav')]))
    with pytest.raises(ValueError,match='traversal'): Catalog(tmp_path)


@pytest.mark.parametrize('index',[0,1,2])
@pytest.mark.parametrize('start',[.5,8.25,22.75])
def test_acoustic_identification_and_offset(recognizer,catalog,index,start):
    t=catalog.tracks[index]
    result=recognizer.recognize(clip(t,start=start,noise=.012,gain=.5),100)
    assert result is not None
    assert result.track_id==t.id and abs(result.position_at_capture-start)<.12
    assert result.captured_at==100


@pytest.mark.parametrize('rate,stereo',[(44100,False),(48000,True),(8000,False)])
def test_sample_rates(recognizer,catalog,rate,stereo):
    result=recognizer.recognize(clip(catalog.tracks[1],rate=rate,stereo=stereo),100)
    assert result and result.track_id==catalog.tracks[1].id


def test_unknown_audio_no_match(recognizer):
    data=np.random.default_rng(183).normal(0,.1,16000*6)
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes((data*32767).astype('<i2').tobytes())
    assert recognizer.recognize(out.getvalue(),0) is None


@pytest.mark.parametrize('length',[.1,2.9,8.1])
def test_reject_clip_duration(catalog,length):
    with pytest.raises(ValueError): audio_samples(clip(catalog.tracks[0],length=length))


def test_reject_quiet_and_corrupt(catalog):
    with pytest.raises(ValueError): audio_samples(clip(catalog.tracks[0],gain=0))
    with pytest.raises(Exception): audio_samples(b'not a wave')
    with pytest.raises(ValueError): audio_samples(b'x'*4_000_001)


def test_recognition_expiry_and_capture_delay():
    r=Recognition('x','title','artist',36,8,100,.9)
    assert r.estimated_position(107)==15
    assert r.estimated_position(121) is None


def test_worker_cancellation_discards_late_reply():
    started=threading.Event(); release=threading.Event()
    class Blocking:
        def recognize(self,*args): started.set(); release.wait(2); return Recognition('x','x','x',36,0,0,1)
    job=RecognitionJob(Blocking())
    assert job.start(b'fixture',0) and started.wait(1)
    assert not job.start(b'new',0)
    job.cancel(); release.set(); job.thread.join(2)
    assert job.poll() is None


def test_store_persistence_dedup_cap_mode(tmp_path):
    path=tmp_path/'discoveries.json'; store=DiscoveryStore(path,limit=3)
    for i in range(5): store.save('Song '+str(i),'Artist','Local',i)
    rows=DiscoveryStore(path).list()
    assert len(rows)==3 and rows[0]['title']=='Song 4'
    if os.name=='posix':  # Windows chmod only toggles read-only; POSIX mode bits are not representable.
        assert path.stat().st_mode&0o777==0o600
    store.save('Song 4','Artist','Local',10)
    assert len(store.list())==3 and store.list()[0]['position']==10
    store.delete(rows[0]['id']); assert len(store.list())==2
    store.clear(); assert store.list()==[]


def test_store_corrupt_refuses_to_overwrite(tmp_path):
    path=tmp_path/'bad.json'; path.write_text('broken')
    store=DiscoveryStore(path)
    with pytest.raises(Exception): store.save('Title','Artist','Local')
    assert path.read_text()=='broken'
    store.clear(); assert store.list()==[]


def test_store_atomic_failure_preserves_old_file(tmp_path,monkeypatch):
    path=tmp_path/'store.json'; store=DiscoveryStore(path); store.save('Old','Artist','Local')
    before=path.read_bytes()
    def fail(*args): raise OSError('test')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError): store.save('New','Artist','Local')
    assert path.read_bytes()==before and len(list(tmp_path.iterdir()))==1


def test_store_no_prints_no_audio(tmp_path,capsys):
    store=DiscoveryStore(tmp_path/'store.json')
    store.save('Private title','Private artist','Phone',float('nan'))
    row=store.list()[0]
    assert row['position'] is None and 'audio' not in row
    assert capsys.readouterr().out==''


def test_search_links_are_search_not_fabricated_track_ids():
    row=dict(title='A / B?',artist='A&B')
    assert search_link(row,'spotify').startswith('https://open.spotify.com/search/')
    assert 'q=' in search_link(row,'youtube')
    with pytest.raises(ValueError): search_link(row,'unsafe')


def test_demo_clock_pause_skip_missing_metadata():
    demo=CatalogDemoTransport(); first=demo.snapshot().title
    demo.send('pause'); a=demo.snapshot().elapsed(); time.sleep(.01)
    assert demo.snapshot().elapsed()==a
    demo.send('next'); assert demo.snapshot().title!=first
    demo.scenario('missing_metadata'); assert demo.snapshot().duration is None
    demo.scenario('reset'); assert demo.snapshot().title==first
