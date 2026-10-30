"""Evidence-bound public raster previews. Network access stays in the backend."""
import asyncio
import base64
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time
import warnings
from urllib.parse import urljoin

from .config import data_directory
from .credentials import CredentialsStore,protected_path
from .portable_vault import atomic_write

_SLOTS=threading.BoundedSemaphore(2)


def media_reference(record):
    from .agent_browser import public_url,PageReadError
    details=record.get('details') or {}
    metadata=details.get('metadata') or {}
    candidates=[('avatar',details.get('avatar_url')),('image',details.get('image_url')),
        ('open_graph',metadata.get('og:image') if isinstance(metadata,dict) else None)]
    for kind,value in candidates:
        if not isinstance(value,str) or not value:continue
        try:url=public_url(urljoin(record.get('url',''),value))
        except (PageReadError,ValueError):continue
        evidence=record.get('evidence_id')
        if not isinstance(evidence,str) or not evidence.startswith('ev_'):continue
        return {'id':'media_'+hashlib.sha256((url+'\0'+evidence).encode()).hexdigest(),
            'url':url,'source_url':record.get('url',''),'kind':kind,'evidence_id':evidence,
            'observed_at':details.get('collected_at') or (record.get('provenance') or {}).get('obtained_at')}
    return None


class MediaStore:
    def __init__(self,directory=None):self.directory=Path(directory) if directory else data_directory()/'public-media'
    def _path(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'media_[a-f0-9]{64}',identifier):raise ValueError('Invalid media reference')
        return protected_path(self.directory/(identifier+'.dpapi'))
    def cached(self,reference):
        path=self._path(reference['id'])
        if not path.exists():return None
        if path.stat().st_size>4_000_000:raise ValueError('Media cache exceeds budget')
        value=json.loads(CredentialsStore._protect(path.read_bytes(),decrypt=True).decode('utf-8'))
        if not isinstance(value,dict) or value.get('id')!=reference['id'] or value.get('url')!=reference['url']:raise ValueError('Invalid media cache')
        return {k:v for k,v in value.items() if k!='original_base64'}
    async def fetch(self,reference,cancel_event=None,deadline=None,fetcher=None):
        cached=self.cached(reference)
        if cached:return cached
        from .web_http import fetch_public
        from .agent_browser import PublicPageReader,PageReadError
        from PIL import Image,ImageOps
        end=deadline or time.monotonic()+20
        while not _SLOTS.acquire(blocking=False):
            if cancel_event and cancel_event.is_set():raise InterruptedError('Media cancelled')
            if time.monotonic()>=end:raise TimeoutError('Media queue timed out')
            await asyncio.sleep(.03)
        try:
            reader=PublicPageReader(max_pages=1,max_depth=0)
            async def robots(url):await reader._check_robots(url,cancel_event,end)
            response=await (fetcher or fetch_public)(reference['url'],cancel_event=cancel_event,deadline=end,
                allowed_types=('image/jpeg','image/png','image/webp'),before_request=robots if fetcher is None else None)
            body=response['body'];mime=response['content_type'].split(';')[0].strip().lower()
            if mime not in ('image/jpeg','image/png','image/webp') or len(body)>2_000_000:raise ValueError('Unsupported public media')
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(body)) as probe:
                    if probe.format not in ('JPEG','PNG','WEBP') or probe.width*probe.height>16_000_000 or max(probe.size)>8192:raise ValueError('Public media resolution exceeds budget')
                    probe.verify()
                with Image.open(io.BytesIO(body)) as image:
                    image=ImageOps.exif_transpose(image);width,height=image.size
                    image.thumbnail((320,320));preview=io.BytesIO();image.convert('RGB').save(preview,format='JPEG',quality=80)
            if cancel_event and cancel_event.is_set():raise InterruptedError('Media cancelled')
            value={**reference,'state':'ready','mime':mime,'width':width,'height':height,'bytes':len(body),
                'final_url':response['final_url'],'fetched_at':datetime.now(timezone.utc).isoformat(),
                'sha256':hashlib.sha256(body).hexdigest(),'thumbnail':'data:image/jpeg;base64,'+base64.b64encode(preview.getvalue()).decode('ascii'),
                'original_base64':base64.b64encode(body).decode('ascii')}
            atomic_write(self._path(reference['id']),CredentialsStore._protect(json.dumps(value,ensure_ascii=False).encode('utf-8')))
            return {k:v for k,v in value.items() if k!='original_base64'}
        except (Image.DecompressionBombWarning,Image.DecompressionBombError):
            raise ValueError('Public media resolution exceeds budget') from None
        finally:_SLOTS.release()

    def read_original(self, reference):
        """Backend-only decoded bytes for a scoped local comparison, never IPC."""
        if not self.cached(reference):
            raise ValueError('Public media has not been fetched')
        value=json.loads(CredentialsStore._protect(self._path(reference['id']).read_bytes(),decrypt=True).decode('utf-8'))
        raw=base64.b64decode(value['original_base64'],validate=True)
        if len(raw)>2_000_000 or hashlib.sha256(raw).hexdigest()!=value['sha256']:
            raise ValueError('Public media cache failed integrity check')
        return raw

    def comparison_preview(self,reference):
        """A larger local preview for GEOINT; it is never sent to a provider."""
        from PIL import Image,ImageOps
        with Image.open(io.BytesIO(self.read_original(reference))) as image:
            image=ImageOps.exif_transpose(image)
            image.thumbnail((960,960))
            encoded=io.BytesIO();image.convert('RGB').save(encoded,format='JPEG',quality=85)
        return 'data:image/jpeg;base64,'+base64.b64encode(encoded.getvalue()).decode('ascii')
