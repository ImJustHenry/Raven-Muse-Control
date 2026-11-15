"""Rebuild the three original spoken-word fixtures; requires ffmpeg with flite.
This is an external test-stimulus generator, not a Muse playback engine.
"""
from pathlib import Path
from io import BytesIO
import json
import subprocess
import wave
import numpy as np

ROOT=Path(__file__).resolve().parents[1]/'muse'/'demo_catalog'
VERSES=[
 ('paper-lanterns','Paper Lanterns',[
  'Paper lanterns cross the rain','Quiet colors wake again',
  'Every window holds a spark','Little maps inside the dark',
  'Let the long day drift away','Keep one light for yesterday',
  'When the street turns soft and blue','There is still a road for you']),
 ('small-signals','Small Signals',[
  'Small signals in the air','Tell me someone else is there',
  'Every step becomes a sound','Every echo comes around',
  'Leave a little room to grow','Take the time you need to know',
  'In the space between the lines','We can find our own designs']),
 ('open-window','Open Window',[
  'Open windows meet the sun','Nothing finished nothing done',
  'Morning gathers on the floor','There is always something more',
  'Let the breeze rearrange the day','Let the old noise fall away',
  'Keep the question keep the view','Let the morning start with you'])]


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    rate=16000; duration=36; rows=[]
    for k,(id,title,lines) in enumerate(VERSES):
        rng=np.random.default_rng(6200+k)
        signal=np.zeros(rate*duration,dtype=np.float64)
        # Distinct, reproducible melodic fingerprints; not existing recordings.
        scale=np.array([0,2,4,7,9,12,14,16])+[45,50,55][k]
        for beat in range(duration*4):
            start=int(beat*.25*rate); count=int(.245*rate)
            t=np.arange(count)/rate
            freq=440*2**((int(rng.choice(scale))-69)/12)
            env=np.minimum(t/.012,1)*np.exp(-t*5)
            tone=sum(np.sin(2*np.pi*freq*h*t)/h for h in (1,2,3,4))
            signal[start:start+count]+=.16*env*tone
        lrc=['[ar:Muse Demo Ensemble]',f'[ti:{title}]']
        for i,line in enumerate(lines):
            sec=2+i*4
            audio=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                 f'flite=text={line}:voice=slt','-ar',str(rate),'-ac','1','-f','wav','pipe:1'],
                 check=True,stdout=subprocess.PIPE).stdout
            with wave.open(BytesIO(audio),'rb') as wav:
                voice=np.frombuffer(wav.readframes(rate*4),dtype='<i2').astype(float)/32768
            voice=voice[:int(3.8*rate)]
            start=sec*rate
            signal[start:start+len(voice)]+=.7*voice
            lrc.append(f'[00:{sec:02d}.00]{line}')
        lrc.append('[00:34.00]')
        signal/=max(1,np.max(np.abs(signal))/.9)
        with wave.open(str(ROOT/f'{id}.wav'),'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
            wav.writeframes((signal*32767).astype('<i2').tobytes())
        # Generated data assets, not modifications to existing code.
        (ROOT/f'{id}.lrc').write_text('\n'.join(lrc)+'\n',encoding='utf-8')
        rows.append(dict(id=id,title=title,artist='Muse Demo Ensemble',duration=duration,
            rights='Original project verse and procedural backing; synthetic speech generated with Flite. Demo assets may be used with this project.',
            lrc=f'{id}.lrc',audio=f'{id}.wav',demo=True))
    (ROOT/'catalog.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('Generated 3 original spoken-word demo tracks and LRC files; no external music downloaded.')

if __name__=='__main__': main()
