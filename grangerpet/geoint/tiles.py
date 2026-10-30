"""Visible-only OSM tiles. No prefetch, credentials, model or bulk map download."""
import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time

from ..config import data_directory
from ..credentials import CredentialsStore, protected_path
from ..portable_vault import atomic_write

TEMPLATE='https://tile.openstreetmap.org/{z}/{x}/{y}.png'
ATTRIBUTION='© OpenStreetMap contributors'
_SLOTS=threading.BoundedSemaphore(4)
_LOCK=threading.Lock()
MAX_TILES=2048
MAX_CACHE_BYTES=256*1024*1024
MAX_TILE_BYTES=400_000


def coordinates(z,x,y):
    if type(z) is not int or not 0<=z<=19 or any(type(value) is not int or not 0<=value<2**z for value in (x,y)):
        raise ValueError('Invalid map tile')
    return f'{z}/{x}/{y}'


class TileStore:
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory else data_directory()/'map-tiles'

    def _path(self,key):
        return protected_path(self.directory/('tile_'+hashlib.sha256((TEMPLATE+'|'+key).encode()).hexdigest()+'.dpapi'))

    def cached(self,z,x,y):
        key=coordinates(z,x,y);path=self._path(key)
        if not path.exists():return None
        if path.stat().st_size>800_000:raise ValueError('Map tile cache size')
        value=json.loads(CredentialsStore._protect(path.read_bytes(),decrypt=True).decode('utf-8'))
        if value.get('key')!=key:raise ValueError('Map tile cache identity')
        if value.get('expires_at',0)<time.time():return None
        return {k:v for k,v in value.items() if k not in ('expires_at',)}

    def get(self,z,x,y,*,cancel_event=None,deadline=None,fetcher=None):
        key=coordinates(z,x,y)
        cached=self.cached(z,x,y)
        if cached:return cached
        end=deadline or time.monotonic()+25
        while not _SLOTS.acquire(timeout=.05):
            if cancel_event and cancel_event.is_set():raise InterruptedError('Tile cancelled')
            if time.monotonic()>=end:raise TimeoutError('Tile timeout')
        try:
            cached=self.cached(z,x,y)
            if cached:return cached
            path=self._path(key)
            with _LOCK:
                files=list(path.parent.glob('tile_*.dpapi')) if path.parent.exists() else []
                if len(files)>=MAX_TILES and not path.exists() or sum(item.stat().st_size for item in files)>MAX_CACHE_BYTES:
                    raise ValueError('Map tile cache capacity reached')
            async def download():
                from ..web_http import fetch_public
                return await (fetcher or fetch_public)(TEMPLATE.format(z=z,x=x,y=y),cancel_event=cancel_event,
                    deadline=end,allowed_types=('image/png',),user_agent='Granger-OSINT/3.1 (+https://github.com/watsoncore/Granger-OSINT) map-view')
            response=asyncio.run(download())
            raw=response['body']
            if len(raw)>MAX_TILE_BYTES or not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid map tile raster')
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as image:
                if image.format!='PNG' or image.size!=(256,256):raise ValueError('Invalid map tile dimensions')
                image.verify()
            if cancel_event and cancel_event.is_set():raise InterruptedError('Tile cancelled')
            value={'key':key,'state':'ready','image':'data:image/png;base64,'+base64.b64encode(raw).decode('ascii'),
                'source_url':TEMPLATE.format(z=z,x=x,y=y),'sha256':hashlib.sha256(raw).hexdigest(),
                'fetched_at':time.time(),'expires_at':time.time()+7*86400,'attribution':ATTRIBUTION}
            with _LOCK:
                atomic_write(path,CredentialsStore._protect(json.dumps(value).encode('utf-8')))
            return {k:v for k,v in value.items() if k!='expires_at'}
        finally:_SLOTS.release()
