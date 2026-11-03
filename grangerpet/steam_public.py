"""Reviewed SteamRecon public subset behind a bounded disposable own worker."""
from __future__ import annotations
from copy import deepcopy
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from .research_vendor import steamid

TOOLS=('steam_profile','steam_aliases','steam_friends','steam_inventory')
_CACHE={};_LOCK=threading.RLock();_COOLDOWN={}


def normalize(value,*,allow_inventory=False):
    if not isinstance(value,str) or not 1<=len(value)<=200 or any(ord(c)<33 for c in value):raise ValueError('Invalid Steam target')
    if re.match(r'(?i)^STEAM_[2-9]:',value):raise ValueError('Non-public Steam universe')
    if '://' in value or value.startswith(('steamcommunity.com/','www.steamcommunity.com/')):
        parsed=urlsplit(value if '://' in value else 'https://'+value)
        if parsed.scheme not in ('https','http') or parsed.hostname not in ('steamcommunity.com','www.steamcommunity.com') or parsed.username or parsed.password or parsed.port:
            raise ValueError('Steam Community URL required')
        parts=parsed.path.strip('/').split('/')
        if allow_inventory and len(parts)==3 and parts[2]=='inventory':parts=parts[:2]
        if len(parts)!=2 or parts[0] not in ('profiles','id') or parsed.query or parsed.fragment:raise ValueError('Exact public Steam profile required')
        value=parts[1]
        if parts[0]=='profiles' and not re.fullmatch(r'\d{17}',value):raise ValueError('SteamID64 required')
    identity=steamid.parse_local(value)
    if identity:return identity,identity.profile_url
    if not re.fullmatch(r'[A-Za-z0-9_-]{2,64}',value) or value.isdigit():raise ValueError('Invalid Steam identifier')
    return None,'https://steamcommunity.com/id/'+value


def validate(tool,value):
    if tool not in TOOLS:raise ValueError('Unknown Steam operation')
    if tool=='steam_inventory':
        from .steam_inventory import validate as inventory_validate
        return inventory_validate(value)
    identity,url=normalize(value)
    return identity.steamid64 if identity else url


def _xml(body):
    if len(body)>2_000_000 or re.search(br'<!\s*(?:DOCTYPE|ENTITY)',body,re.I):raise ValueError('Unsafe or oversized XML')
    root=ET.fromstring(body)
    if sum(1 for _ in root.iter())>25_000:raise ValueError('XML complexity limit')
    return root


async def collect(tool,value,*,deadline,cancel_event=None,client_factory=None,resolver=None):
    from .agent_browser import PageReadError
    from .agent_web import _record,_envelope
    from .web_http import fetch_public
    from .research_vendor.steam_community import SteamPublicParser
    identity,url=normalize(value)
    async def get(endpoint):
        response=await fetch_public(endpoint,deadline=deadline,cancel_event=cancel_event,
            client_factory=client_factory,resolver=resolver,rate_interval=1.,
            allowed_types=('text/xml','application/xml','application/json','text/html','text/plain'),
            accepted_statuses=(200,401,403,404,429,500,503))
        if urlsplit(response['final_url']).hostname not in ('steamcommunity.com','www.steamcommunity.com'):raise PageReadError('unexpected_steam_origin','blocked')
        if response['status']!=200:raise PageReadError('http_'+str(response['status']),
            'rate_limited' if response['status']==429 else 'auth_required' if response['status'] in (401,403) else 'unavailable')
        return response
    response=None;root=None
    if identity is None or tool=='steam_profile':
        response=await get(url+'/?xml=1&l=english')
        root=_xml(response['body'])
        if root.tag!='profile':raise PageReadError('steam_profile_unavailable','unavailable')
        actual=steamid.parse_local(root.findtext('steamID64',''))
        if actual is None:raise ValueError('Missing SteamID64')
        if identity is not None and actual.steamid64!=identity.steamid64:raise ValueError('Mismatched Steam profile')
        identity=actual
    canonical=identity.profile_url
    fields={**identity.to_dict(),'canonical_url':canonical,'requested_profile':url,'operation':tool,'source_project':'SteamRecon reviewed MIT subset',
        'acquisition':'permitted_public_steam_page','identity_verified':False}
    title='Steam · '+identity.steamid64;status='complete';limitations=['Только опубликованные Steam Community сведения; закрытые данные не обходятся. Совпадение имени не устанавливает личность.']
    if tool=='steam_profile':
        parser=SteamPublicParser();profile={k:v[:4000] for k,v in parser._profile(root,identity).items()}
        fields.update(profile=profile,groups=parser._groups(root)[:20],recent_games=parser._games(root)[:20],
            avatar_url=profile.get('avatarFull'),display_name=profile.get('personaname'))
        title='Steam · '+(profile.get('personaname') or identity.steamid64)
        if profile.get('privacy') not in ('public','3'):
            status='partial';limitations.append('Профиль ограничен: возвращены только доступные поля, а не нулевые значения закрытых разделов.')
        description='Публичные поля Steam: имя '+str(profile.get('personaname') or 'не указано')+'; SteamID64 '+identity.steamid64+'; видимость '+str(profile.get('privacy') or 'не сообщена')+'.'
    elif tool=='steam_aliases':
        response=await get(canonical+'/ajaxaliases/')
        payload=json.loads(response['body'].decode('utf-8-sig'))
        if not isinstance(payload,list):raise ValueError('Invalid aliases JSON')
        aliases=[]
        for item in payload[:100]:
            if not isinstance(item,dict):continue
            name=item.get('newname') or item.get('name')
            if isinstance(name,str) and name.strip():aliases.append({'name':name.strip()[:200],'seen_at':str(item.get('timechanged') or item.get('time') or '')[:150]})
        fields['aliases']=aliases[:20];fields['returned_aliases']=len(aliases)
        description='Прежние имена Steam: '+('; '.join(item['name'] for item in aliases[:10]) or 'источник не опубликовал записей')+'. История может быть неполной; имя не доказывает владельца.'
        title='Steam · публичные прежние имена · '+identity.steamid64
    else:
        response=await get(canonical+'/friends/?l=english')
        text=response['body'].decode('utf-8','replace')
        class Friends(HTMLParser):
            def __init__(self):super().__init__();self.urls=[];self.frames=[]
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                classes=set(attrs.get('class','').split())
                inside=bool(self.frames and self.frames[-1][1]) or 'friend_block_v2' in classes
                if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):
                    self.frames.append((tag,inside))
                if tag!='a' or not inside:return
                try:
                    peer,link=normalize(attrs.get('href',''))
                    if link not in self.urls:self.urls.append(link)
                except ValueError:pass
            def handle_endtag(self,tag):
                for index in range(len(self.frames)-1,-1,-1):
                    if self.frames[index][0]==tag:del self.frames[index:];break
        parser=Friends();parser.feed(text)
        if not parser.urls:
            if re.search(r'(?i)profile_private_info|private.{0,35}profile|профиль.{0,30}скрыт',text):raise PageReadError('private_friend_list','blocked')
            raise PageReadError('no_parseable_public_friend_list','unavailable')
        fields.update(friends=parser.urls[:20],observed_friends=len(parser.urls),sampled=len(parser.urls)>20)
        title='Steam · публичные ссылки друзей · '+identity.steamid64
        description='В публичном разделе друзей обнаружено '+str(len(parser.urls))+' ссылок; сохранено до20. Это наблюдение источника, не общность владельцев.'
    fields['endpoint']=response['final_url']
    row=_record('steam',identity.steamid64,title,canonical,description,kind='profile',details=fields)
    return _envelope(tool,value,status=status,results=[row],limitations=limitations)


def execute(tool,value,*,cancel_event=None,deadline=None):
    from .agent_web import _envelope
    try:value=validate(tool,value)
    except (ValueError,TypeError):return _envelope(tool,'',status='invalid_arguments',error_code='invalid_steam_target')
    cache_key=(tool,json.dumps(value,sort_keys=True) if isinstance(value,dict) else value)
    summary=value.get('profile','') if isinstance(value,dict) else value
    with _LOCK:cached=_CACHE.get(cache_key)
    if cached and time.monotonic()-cached[0]<300:
        result=deepcopy(cached[1]);result['from_saved_data']=True
        result['limitations'].append('Сохранённый результат до5мин; исходное время наблюдения не изменено.');return result
    with _LOCK:remaining=_COOLDOWN.get(tool,0)-time.monotonic()
    if remaining>0:return _envelope(tool,summary,status='rate_limited',error_code='steam_retry_after',
        limitations=['Steam ранее сообщил об ограничении; новый запрос не выполнялся. Повторите через '+str(int(remaining)+1)+' с.'])
    end=min(deadline or float('inf'),time.monotonic()+35)
    from .engine.runtime import _WindowsJob,_PROCESS_SLOTS
    while not _PROCESS_SLOTS.acquire(timeout=.05):
        if cancel_event and cancel_event.is_set():return _envelope(tool,summary,status='cancelled')
        if time.monotonic()>=end:return _envelope(tool,summary,status='timeout')
    process=job=None
    checkpoint=tempfile.TemporaryDirectory(prefix='granger-steam-') if tool=='steam_inventory' else None
    checkpoint_path=Path(checkpoint.name)/'inventory.dpapi' if checkpoint else None
    def interrupted(status):
        if checkpoint_path and checkpoint_path.is_file():
            try:
                from .credentials import WindowsLegacyStore,CredentialError
                from .tool_contracts import validate_outcome
                if checkpoint_path.stat().st_size>8_065_536:raise ValueError()
                result=json.loads(WindowsLegacyStore._protect(checkpoint_path.read_bytes(),decrypt=True))
                validate_outcome(result)
                if result.get('tool')!=tool:raise ValueError()
                result.update(status=status,error_code='steam_inventory_'+status,from_page_checkpoint=True)
                result.setdefault('limitations',[]).append('Сохранены полученные до остановки страницы. Продолжение доступно с наблюдённого next_cursor; цены не обновлялись после остановки.')
                return result
            except (OSError,ValueError,UnicodeError,CredentialError):pass
        return _envelope(tool,summary,status=status)
    try:
        if cancel_event and cancel_event.is_set():return _envelope(tool,summary,status='cancelled')
        root=Path(__file__).resolve().parents[1]
        line=[sys.executable,'--passive-research-worker'] if getattr(sys,'frozen',False) else [sys.executable,str(root/'main.py'),'--passive-research-worker']
        env={k:v for k,v in os.environ.items() if not re.search(r'KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|GRANGERPET_|PYTHONPATH|PYTHONHOME',k,re.I)}
        process=subprocess.Popen(line,cwd=root,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if os.name=='nt':
            job=_WindowsJob(process,memory_limit=384*1024*1024)
            if not job.handle:return _envelope(tool,summary,status='unavailable',error_code='worker_job_unavailable')
        payload=json.dumps({'tool':tool,'value':value,'seconds':max(.1,end-time.monotonic()),
            **({'checkpoint':str(checkpoint_path)} if checkpoint_path else {})}).encode();sent=False
        while True:
            if cancel_event and cancel_event.is_set():return interrupted('cancelled')
            if time.monotonic()>=end:return interrupted('timeout')
            try:raw,_=process.communicate(input=None if sent else payload,timeout=.05);break
            except subprocess.TimeoutExpired:sent=True
        if process.returncode or len(raw)>(8_000_000 if tool=='steam_inventory' else 500_000):raise ValueError('Invalid worker output')
        result=json.loads(raw)
        if not isinstance(result,dict) or result.get('tool')!=tool:raise ValueError('Invalid worker contract')
        from .tool_contracts import validate_outcome
        validate_outcome(result)
        throttled=[failure for row in result.get('results',[]) if isinstance(row,dict)
            for failure in row.get('details',{}).get('source_failures',[]) if isinstance(failure,dict) and '429' in str(failure.get('error_code',''))]
        if result.get('status')=='rate_limited' or throttled:
            delay=max((entry.get('retry_after_seconds') or 60 for entry in throttled),default=60)
            with _LOCK:_COOLDOWN[tool]=time.monotonic()+min(86400,max(60,delay))
        if result.get('status') in ('complete','partial'):
            with _LOCK:
                if len(_CACHE)>64:_CACHE.pop(next(iter(_CACHE)))
                _CACHE[cache_key]=(time.monotonic(),deepcopy(result))
        return result
    except (OSError,ValueError):return _envelope(tool,summary,status='error',error_code='steam_worker_failed')
    finally:
        if job:job.close()
        if process:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        _PROCESS_SLOTS.release()
        if checkpoint:checkpoint.cleanup()


def worker_main():
    from .web_render_worker import _binary_pipe
    from .agent_web import _run,_FetchError,_envelope
    from .agent_browser import PageReadError
    stream=_binary_pipe('stdin');payload=json.loads(stream.read(32000));tool=payload.get('tool');value=payload.get('value')
    try:
        value=validate(tool,value);seconds=payload.get('seconds',30)
        if type(seconds) not in (int,float) or not .1<=seconds<=40:raise ValueError()
        end=time.monotonic()+seconds
        if tool=='steam_inventory':
            from .steam_inventory import collect as inventory_collect
            checkpoint=payload.get('checkpoint')
            def on_page(value):
                if not checkpoint:return
                from .credentials import WindowsLegacyStore
                from .portable_vault import atomic_write
                path=Path(checkpoint).resolve()
                if (path.name!='inventory.dpapi' or path.parent.parent!=Path(tempfile.gettempdir()).resolve()
                        or not path.parent.name.startswith('granger-steam-') or not path.parent.is_dir()):raise ValueError('Invalid owned inventory checkpoint')
                raw=json.dumps(value,ensure_ascii=True).encode('utf-8')
                if len(raw)>8_000_000:raise ValueError('Inventory checkpoint limit')
                atomic_write(path,WindowsLegacyStore._protect(raw))
            result=_run(lambda:inventory_collect(value,deadline=end-min(2,seconds/4),on_page=on_page),deadline=end,timeout=seconds)
        else:result=_run(lambda:collect(tool,value,deadline=end),deadline=end,timeout=seconds)
    except (PageReadError,_FetchError) as error:result=_envelope(tool,str(value)[:200],status=error.status,error_code=error.code)
    except (ValueError,TypeError,ET.ParseError):result=_envelope(tool,str(value)[:200],status='error',error_code='invalid_steam_response')
    _binary_pipe('stdout').write(json.dumps(result,ensure_ascii=True).encode('utf-8'))
    return 0
