"""Bounded read-only official API/open-dataset adapters; no model-controlled URLs."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import ipaddress
import json
import re
import threading
import time
from urllib.parse import quote

from .agent_web import _run, _client, _fetch, _json, _FetchError, _envelope, _record

_LOCK = threading.RLock()
_NEXT = {}
_CACHE = {}
_SLOTS = threading.BoundedSemaphore(2)


def validate(tool, value):
    if not isinstance(value, str): raise ValueError('Expected string')
    if tool == 'github_repository':
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}', value):
            raise ValueError('owner/repository required')
        if value.split('/')[1] in ('.','..'): raise ValueError('Invalid repository')
    elif tool == 'threat_feodo':
        address=ipaddress.ip_address(value)
        if not address.is_global or address.is_multicast: raise ValueError('Public IP required')
        value=str(address)
    elif tool == 'hash_virustotal':
        if not re.fullmatch(r'[a-fA-F0-9]{64}',value): raise ValueError('SHA-256 required')
        value=value.lower()
    else: raise ValueError('Unknown adapter')
    return value


def _gate(service, cancel_event, deadline):
    while not _SLOTS.acquire(timeout=.05):
        _check(cancel_event,deadline)
    try:
        while True:
            _check(cancel_event,deadline)
            with _LOCK:
                wait=_NEXT.get(service,0)-time.monotonic()
                if wait <= 0:
                    _NEXT[service]=time.monotonic()+({'hash_virustotal':16,'threat_feodo':1}.get(service,1))
                    return
            if cancel_event: cancel_event.wait(min(.05,wait))
            else: time.sleep(min(.05,wait))
    except BaseException:
        _SLOTS.release()
        raise


def _check(cancel_event,deadline):
    if cancel_event and cancel_event.is_set(): raise _FetchError('cancelled',status='cancelled')
    if deadline is not None and time.monotonic()>=deadline: raise _FetchError('timeout',status='timeout')


def execute(tool, value, *, secret='', cancel_event=None, deadline=None, client_factory=None):
    try: value=validate(tool,value)
    except (ValueError,TypeError): return _envelope(tool,'',status='invalid_arguments',error_code='invalid_input')
    if tool=='hash_virustotal' and not secret:
        return _envelope(tool,value,status='auth_required',error_code='api_key_required')
    deadline=min(deadline,time.monotonic()+25) if deadline is not None else time.monotonic()+25
    try:
        _check(cancel_event,deadline)
    except _FetchError as exc:
        return _envelope(tool,value,status=exc.status,error_code=exc.code)
    cache_key=(tool,value,hashlib.sha256(secret.encode()).digest() if secret else b'')
    with _LOCK:
        cached=_CACHE.get(cache_key)
    if cached and time.monotonic()-cached[0]<300:
        result=deepcopy(cached[1]); result['limitations'].append('Кэш результата, не новый запрос; исходное время получения сохранено.')
        return result
    acquired=False
    try:
        _gate(tool,cancel_event,deadline);acquired=True
        async def operation():
            async with _client(client_factory) as client:
                if tool=='github_repository':
                    endpoint='https://api.github.com/repos/'+quote(value,safe='/')
                    data=await _json(client,endpoint)
                    if not isinstance(data.get('full_name'),str) or data.get('private') is not False:
                        raise _FetchError('invalid_response')
                    fields={k:data.get(k) for k in ('full_name','description','language','stargazers_count','forks_count','archived','disabled','created_at','updated_at','pushed_at','default_branch')}
                    url='https://github.com/'+value
                    rows=[_record('github_api',value,data['full_name'],url,'Публичные метаданные репозитория GitHub; содержимое кода не исследовалось.',kind='repository',details={**fields,'acquisition':'official_api','endpoint':endpoint})]
                elif tool=='threat_feodo':
                    endpoint='https://feodotracker.abuse.ch/downloads/ipblocklist_recommended.json'
                    data=json.loads((await _fetch(client,endpoint)).decode('utf-8-sig'))
                    if not isinstance(data,list) or any(not isinstance(row,dict) or 'ip_address' not in row for row in data):
                        raise _FetchError('invalid_response')
                    matches=[row for row in data if row.get('ip_address')==value]
                    # A non-match is an actual limited dataset observation, never a claim of safety.
                    fields={'address':value,'matched':bool(matches),'dataset_records':len(data),'matches':[
                        {k:row.get(k) for k in ('ip_address','port','status','first_seen','last_online','malware')} for row in matches[:20]],'acquisition':'open_dataset'}
                    rows=[_record('feodo_tracker',value,'Feodo Tracker · '+value,endpoint,'Совпадение в рекомендованном C2-списке.' if matches else 'В текущем рекомендованном C2-списке совпадений нет. Это не означает безопасность адреса.',kind='threat_indicator',details=fields)]
                else:
                    # API keys travel only in a header, never query strings/log URLs.
                    client.headers['x-apikey']=secret
                    endpoint='https://www.virustotal.com/api/v3/files/'+value
                    data=await _json(client,endpoint)
                    entity=data.get('data'); attributes=entity.get('attributes') if isinstance(entity,dict) else None
                    if not isinstance(attributes,dict) or entity.get('id')!=value: raise _FetchError('invalid_response')
                    fields={k:attributes.get(k) for k in ('sha256','size','type_description','last_analysis_date','last_analysis_stats','reputation')}
                    rows=[_record('virustotal',value,'VirusTotal · '+value[:16], 'https://www.virustotal.com/gui/file/'+value,
                        'Отчёт по ранее известному SHA-256; файл не загружался и повторный анализ не запускался.',kind='hash',details={**fields,'acquisition':'official_api'})]
                return _envelope(tool,value,results=rows,limitations=['Сведения относятся к ответу конкретного источника. Нулевой результат не устанавливает безопасность или личность.'])
        result=_run(operation,cancel_event=cancel_event,deadline=deadline,timeout=25)
        with _LOCK:
            if len(_CACHE)>128: _CACHE.clear()
            _CACHE[cache_key]=(time.monotonic(),deepcopy(result))
        return result
    except _FetchError as exc:
        status={401:'auth_required',402:'auth_required',403:'blocked',404:'empty',429:'rate_limited'}.get(exc.http_status,exc.status)
        return _envelope(tool,value,status=status,error_code=exc.code,limitations=['Источник не предоставил сведения; ограничения доступа не обходились.'])
    except (ValueError,TypeError,UnicodeError):
        return _envelope(tool,value,status='error',error_code='invalid_response')
    finally:
        if acquired: _SLOTS.release()
