"""Offline recognition for the explicitly limited, approved local demo catalog.
Real acoustic matching, not a filename lookup. Never claims a universal catalog.
"""
from dataclasses import dataclass
from io import BytesIO
import math
import threading
import time
import wave
import numpy as np
from scipy.signal import correlate, resample_poly, stft

RATE=8000
HOP=256
MAX_CLIP=8


def audio_samples(data, max_seconds=MAX_CLIP, minimum=3):
    if not isinstance(data,bytes) or len(data)>4_000_000:
        raise ValueError('Audio must be a bounded WAV clip')
    with wave.open(BytesIO(data),'rb') as wav:
        rate,channels,width,frames=wav.getframerate(),wav.getnchannels(),wav.getsampwidth(),wav.getnframes()
        if channels not in (1,2) or width!=2 or not 8000<=rate<=48000:
            raise ValueError('Use mono/stereo PCM16 WAV at 8–48 kHz')
        if not minimum<=frames/rate<=max_seconds:
            raise ValueError('Clip duration out of range')
        raw=wav.readframes(frames)
        if len(raw)!=frames*channels*2: raise ValueError('Incomplete WAV')
    x=np.frombuffer(raw,dtype='<i2').astype(np.float64).reshape(-1,channels).mean(axis=1)/32768
    if np.sqrt(np.mean(x*x))<.002: raise ValueError('Audio too quiet')
    if rate!=RATE:
        gcd=math.gcd(rate,RATE)
        x=resample_poly(x,RATE//gcd,rate//gcd)
    return x


def features(samples):
    _,_,s=stft(samples,fs=RATE,nperseg=1024,noverlap=1024-HOP,boundary=None,padded=False)
    magnitude=np.abs(s)[10:394]  # 78–3078 Hz, 64 linear bands
    bands=magnitude.reshape(64,6,-1).max(axis=1)
    bands=np.maximum(0,np.log1p(bands*500)-np.median(np.log1p(bands*500),axis=0))
    bands/=np.maximum(np.linalg.norm(bands,axis=0),1e-8)
    return bands.astype(np.float32)


@dataclass(frozen=True)
class Recognition:
    track_id: str
    title: str
    artist: str
    duration: float
    position_at_capture: float
    captured_at: float
    score: float
    source: str='LOCAL DEMO CATALOG'

    def estimated_position(self, now=None):
        now=time.monotonic() if now is None else now
        age=max(0,now-self.captured_at)
        # Ambient audio has no pause/change feed: stop claiming sync after 20 s.
        if age>20: return None
        return min(self.duration,self.position_at_capture+age)


class LocalRecognizer:
    def __init__(self,catalog):
        self.catalog=catalog
        self.references=None

    def recognize(self,data,captured_at,cancel=None):
        cancel=cancel or threading.Event()
        query=features(audio_samples(data))
        if self.references is None:
            refs=[]
            for track in self.catalog.tracks:
                if cancel.is_set(): return None
                raw=track.audio.read_bytes()
                refs.append((track,features(audio_samples(raw,max_seconds=900))))
            self.references=refs
        scores=[]
        for track,ref in self.references:
            if cancel.is_set(): return None
            if query.shape[1]>ref.shape[1]: continue
            aligned=sum(correlate(ref[i],query[i],mode='valid',method='fft') for i in range(64))/query.shape[1]
            index=int(np.argmax(aligned))
            scores.append((float(aligned[index]),index*HOP/RATE,track))
        scores.sort(key=lambda s:s[0],reverse=True)
        if not scores or scores[0][0]<.76: return None
        if len(scores)>1 and scores[0][0]-scores[1][0]<.045: return None
        score,position,track=scores[0]
        return Recognition(track.id,track.title,track.artist,track.duration,position,captured_at,score)


class RecognitionJob:
    """One daemon job; cancellation discards late results, never queues recordings."""
    def __init__(self,recognizer):
        self.recognizer=recognizer
        self.thread=None
        self.cancel_event=threading.Event()
        self.lock=threading.Lock()
        self.result=None
        self.generation=0

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self,data,captured_at):
        if self.busy: return False
        self.generation+=1
        generation=self.generation
        self.result=None
        self.cancel_event=threading.Event()
        cancel=self.cancel_event
        def run():
            try:
                found=self.recognizer.recognize(data,captured_at,cancel)
                result=('matched',found) if found else ('no_match',None)
            except Exception:
                result=('error',None)  # Never log clips, metadata or exception payloads.
            with self.lock:
                if generation==self.generation and not cancel.is_set():
                    self.result=result
        self.thread=threading.Thread(target=run,daemon=True,name='muse-local-recognition')
        self.thread.start()
        return True

    def poll(self):
        with self.lock:
            result,self.result=self.result,None
            return result

    def cancel(self):
        with self.lock:
            self.generation+=1
            self.cancel_event.set()
            self.result=None
