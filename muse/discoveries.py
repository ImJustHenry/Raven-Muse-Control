"""Private, local metadata bookmarks. Never Spotify/YouTube account likes."""
from pathlib import Path
import hashlib
import json
import math
import os
import tempfile
import threading
import time
from urllib.parse import quote, urlencode


class DiscoveryStore:
    def __init__(self,path=None,limit=200):
        self.path=Path(path) if path else Path.home()/'.config/raven-muse-control/discoveries.json'
        self.limit=max(1,min(200,int(limit)))
        self.lock=threading.RLock()

    def _read(self):
        if not self.path.exists(): return []
        if self.path.is_symlink() or self.path.stat().st_size>1_000_000:
            raise ValueError('Unsafe discovery file')
        data=json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data,list) or len(data)>200: raise ValueError('Invalid discoveries')
        for row in data:
            if not isinstance(row,dict) or any(not isinstance(row.get(k),str) for k in ('id','title','artist','source')):
                raise ValueError('Invalid discovery entry')
            if any(len(row[k])>512 for k in ('id','title','artist','source')): raise ValueError('Invalid discovery size')
        return data

    def list(self):
        with self.lock: return self._read()

    def _write(self,rows):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.path.is_symlink(): raise ValueError('Refusing symlink')
        fd,temp=tempfile.mkstemp(prefix='.muse-discoveries-',dir=self.path.parent)
        try:
            os.chmod(temp,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as file:
                json.dump(rows,file,ensure_ascii=False)
                file.flush(); os.fsync(file.fileno())
            os.replace(temp,self.path)
            os.chmod(self.path,0o600)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def save(self,title,artist,source,position=None):
        def clean(value):
            return ' '.join(str(value).split())[:300]
        title,artist,source=map(clean,(title,artist,source))
        if not title: raise ValueError('No song to save')
        if position is not None:
            position=float(position)
            if not math.isfinite(position) or position<0: position=None
        identity=hashlib.sha256((title.casefold()+'\0'+artist.casefold()).encode()).hexdigest()[:24]
        row=dict(id=identity,title=title,artist=artist,source=source,
                 position=position,saved_at=time.time())
        with self.lock:
            rows=[r for r in self._read() if r['id']!=identity]
            rows.insert(0,row)
            self._write(rows[:self.limit])
        return row

    def delete(self,id):
        with self.lock: self._write([r for r in self._read() if r['id']!=id])

    def clear(self):
        with self.lock:
            # Corrupt files are not silently overwritten; explicit Clear can remove them.
            if self.path.is_symlink(): raise ValueError('Refusing symlink')
            self._write([])


def search_link(row,service):
    query=f"{row['title']} {row['artist']}".strip()
    if service=='spotify': return 'https://open.spotify.com/search/'+quote(query,safe='')
    if service=='youtube': return 'https://music.youtube.com/search?'+urlencode({'q':query})
    raise ValueError('Unsupported service')
