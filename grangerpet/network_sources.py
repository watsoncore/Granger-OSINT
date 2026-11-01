"""Passive network capabilities over pinned, bounded public HTTPS requests.

Registry endpoints come from IANA bootstrap, never a model-supplied destination.
No port scans, shell commands, browser credentials or secret values are accepted.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import re
import threading
import time
import httpx
from urllib.parse import quote, urlsplit, urlencode

from .agent_browser import PageReadError, public_url
from .agent_web import _run, _FetchError, _record, _envelope
from .web_http import fetch_public
from .web_scraping import bounded_json

TOOLS = {
    'network_rdap': ('ip', 'resource', 'Регистрация IP/CIDR/ASN через IANA и авторитетный RDAP'),
    'network_routing': ('ip', 'resource', 'RIPE RIS: текущая маршрутизация, ASN и история наблюдений'),
    'network_reverse_dns': ('ip', 'address', 'PTR публичного IPv4/IPv6 через DNS over HTTPS'),
    'network_reputation': ('ip', 'address', 'Сопоставление IP с открытым Spamhaus DROP; не вердикт безопасности'),
    'domain_dns': ('domain', 'domain', 'AAAA/SOA/TXT/CAA/SPF/DMARC публичного домена'),
    'domain_rdap': ('domain', 'domain', 'Авторитетный RDAP домена через текущий IANA bootstrap'),
    'domain_certificates': ('domain', 'domain', 'Публичные Certificate Transparency наблюдения crt.sh'),
}
_CACHE = {}
_LOCK = threading.RLock()
_JSON_TYPES = ('application/json', 'application/rdap+json', 'application/x-ndjson', 'text/json', 'text/plain')


def validate(tool, value):
    if tool not in TOOLS or not isinstance(value, str) or not 1 <= len(value) <= 253:
        raise ValueError('Invalid network operation/input')
    value = value.strip()
    if TOOLS[tool][0] == 'domain':
        from .agent_web import _domain
        return _domain(value)
    if re.fullmatch(r'AS[1-9][0-9]{0,9}', value, re.I) and tool in ('network_rdap', 'network_routing'):
        if int(value[2:]) > 4294967295: raise ValueError('Invalid ASN')
        return value.upper()
    if '%' in value: raise ValueError('Scoped IP forbidden')
    if '/' in value and tool in ('network_rdap', 'network_routing'):
        address = ipaddress.ip_network(value, strict=False)
    else:
        address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast or address.is_reserved or address.is_unspecified:
        raise ValueError('Public IP/range required')
    return str(address)


def _bootstrap_endpoint(payload, resource, *, domain=False):
    if not isinstance(payload, dict) or not isinstance(payload.get('services'), list):
        raise ValueError('Invalid IANA bootstrap')
    candidates = []
    for service in payload['services'][:2000]:
        if not isinstance(service, list) or len(service) != 2 or not all(isinstance(v, list) for v in service): continue
        score = -1
        for key in service[0]:
            if not isinstance(key, str): continue
            try:
                if domain and (resource == key or resource.endswith('.'+key)):
                    score = max(score, len(key))
                elif not domain and resource.startswith('AS'):
                    low, high = map(int, key.split('-'))
                    if low <= int(resource[2:]) <= high: score = 1
                elif not domain:
                    net = ipaddress.ip_network(key)
                    address = ipaddress.ip_network(resource, strict=False).network_address
                    if address in net: score = max(score, net.prefixlen)
            except (ValueError, TypeError): continue
        if score < 0: continue
        for endpoint in service[1]:
            if not isinstance(endpoint, str) or not endpoint.startswith('https://'): continue
            try: endpoint = public_url(endpoint)
            except PageReadError: continue
            candidates.append((score, endpoint))
    if not candidates: raise ValueError('No authoritative RDAP service in IANA bootstrap')
    return max(candidates, key=lambda row: row[0])[1]


def _rdap_fields(data):
    if not isinstance(data, dict) or data.get('objectClassName') not in ('ip network', 'autnum', 'domain'):
        raise ValueError('Invalid RDAP response')
    fields = {k: data[k] for k in ('objectClassName', 'handle', 'name', 'type', 'startAddress',
        'endAddress', 'ipVersion', 'country', 'parentHandle', 'ldhName', 'unicodeName', 'startAutnum', 'endAutnum')
        if isinstance(data.get(k), (str, int))}
    fields['events'] = [{k: event[k] for k in ('eventAction', 'eventDate') if isinstance(event.get(k), str)}
                        for event in data.get('events', [])[:20] if isinstance(event, dict)] if isinstance(data.get('events'), list) else []
    fields['status'] = [v[:150] for v in data.get('status', [])[:20] if isinstance(v, str)] if isinstance(data.get('status'), list) else []
    fields['nameservers'] = [row['ldhName'] for row in data.get('nameservers', [])[:20]
        if isinstance(row, dict) and isinstance(row.get('ldhName'), str)] if isinstance(data.get('nameservers'), list) else []
    organizations = []
    for entity in data.get('entities', [])[:30] if isinstance(data.get('entities'), list) else []:
        if not isinstance(entity, dict): continue
        card = entity.get('vcardArray')
        if not isinstance(card, list) or len(card) != 2 or not isinstance(card[1], list): continue
        for prop in card[1]:
            if isinstance(prop, list) and len(prop) >= 4 and prop[0] in ('fn', 'org') and isinstance(prop[3], str):
                organizations.append({'name': prop[3][:400], 'roles': entity.get('roles', [])[:8] if isinstance(entity.get('roles'), list) else []})
    fields['registry_entities'] = organizations[:20]
    # No addresses, telephone numbers, secrets or complete vCards copied.
    return fields


def execute(tool, value, *, cancel_event=None, deadline=None, client_factory=None, resolver=None):
    try: value = validate(tool, value)
    except (ValueError, TypeError): return _envelope(tool, '', status='invalid_arguments', error_code='invalid_network_target')
    end = min(deadline or float('inf'), time.monotonic()+40)
    rows, diagnostics = [], []
    async def fetch(url, params=None):
        key = url + ('?'+urlencode(params) if params else '')
        with _LOCK: cached = _CACHE.get(key)
        if client_factory is None and cached and time.monotonic()-cached[0] < (3600 if 'data.iana.org' in url or '/drop/' in url else 300):
            result = deepcopy(cached[1]); result['cache_hit'] = True
            return result
        try:
            response = await fetch_public(url, params=params, cancel_event=cancel_event, deadline=end,
                client_factory=client_factory, resolver=resolver, allowed_types=_JSON_TYPES,
                rate_interval=.5, accepted_statuses=(200, 400, 401, 403, 404, 429, 500, 502, 503))
        except httpx.TimeoutException:raise PageReadError('timeout','timeout') from None
        except httpx.TransportError:raise PageReadError('network','unavailable') from None
        if response['status'] != 200:
            code = response['status']
            raise PageReadError('http_'+str(code), 'rate_limited' if code == 429 else 'auth_required' if code == 401 else 'unavailable')
        response['observed_at'] = datetime.now(timezone.utc).isoformat()
        response['cache_hit'] = False
        if client_factory is None:
            with _LOCK:
                if len(_CACHE) >= 128: _CACHE.pop(next(iter(_CACHE)))
                _CACHE[key] = (time.monotonic(), deepcopy(response))
        return response
    async def get_json(url, params=None):
        response = await fetch(url, params)
        try: return json.loads(response['body'].decode('utf-8-sig')), response
        except (ValueError, UnicodeError): raise ValueError('Invalid JSON') from None
    def add(source, title, response, fields, description, *, kind=None):
        observed = response.get('observed_at') or datetime.now(timezone.utc).isoformat()
        response.setdefault('observed_at', observed)
        row = _record(source, value, title, response['final_url'], description,
            kind=kind or TOOLS[tool][0], details={('domain' if TOOLS[tool][0]=='domain' else 'address'):value,
                **fields, 'operation': tool,
                'acquisition': 'public_api', 'http_status': response['status'],
                'source_observed_at': observed, 'cache_hit': response.get('cache_hit', False),
                'redirects': response.get('redirects', [])})
        row['date'] = observed
        rows.append(row)
    async def attempt(label, operation):
        try:
            await operation(); diagnostics.append({'source': label, 'status': 'complete'})
        except (PageReadError, _FetchError) as error:
            if error.status=='cancelled' or time.monotonic()>=end: raise
            diagnostics.append({'source': label, 'status': error.status, 'error_code': error.code})
        except (ValueError, TypeError, KeyError, UnicodeError):
            diagnostics.append({'source': label, 'status': 'error', 'error_code': 'invalid_source_response'})
    async def rdap():
        domain = tool == 'domain_rdap'
        family = 'dns' if domain else 'asn' if value.startswith('AS') else 'ipv6' if ':' in value else 'ipv4'
        bootstrap, _ = await get_json('https://data.iana.org/rdap/'+family+'.json')
        base = _bootstrap_endpoint(bootstrap, value, domain=domain)
        endpoint = base.rstrip('/') + '/' + ('domain/' if domain else 'autnum/' if value.startswith('AS') else 'ip/') + quote(value[2:] if value.startswith('AS') else value, safe=':/')
        data, response = await get_json(endpoint)
        fields = _rdap_fields(data); fields['bootstrap_source'] = 'https://data.iana.org/rdap/'+family+'.json'
        add('rdap_registry', 'RDAP · '+value, response, fields,
            'Регистрация ресурса в авторитетном реестре; организация диапазона не устанавливает пользователя устройства.')
    async def ptr():
        reverse = ipaddress.ip_address(value).reverse_pointer
        data, response = await get_json('https://dns.google/resolve', {'name': reverse, 'type': 'PTR'})
        if not isinstance(data, dict) or type(data.get('Status')) is not int: raise ValueError()
        if data['Status'] not in (0,3):raise PageReadError('dns_rcode_'+str(data['Status']),'unavailable')
        answers = data.get('Answer', [])
        if not isinstance(answers, list): raise ValueError()
        records = [{'value': row['data'], 'ttl': row.get('TTL')} for row in answers[:30]
            if isinstance(row, dict) and row.get('type') == 12 and isinstance(row.get('data'), str)]
        add('google_dns', 'PTR · '+value, response, {'address': value, 'record_type': 'PTR', 'response_code': data['Status'], 'answers': records},
            'Наблюдение публичного резолвера. PTR задаётся оператором DNS и не доказывает владельца или геолокацию.')
    async def routing():
        resource = value
        if not value.startswith('AS') and '/' not in value:
            data, response = await get_json('https://stat.ripe.net/data/network-info/data.json', {'resource': value})
            payload = data.get('data') if isinstance(data, dict) else None
            if not isinstance(payload, dict) or not payload.get('prefix'): raise ValueError()
            resource = str(ipaddress.ip_network(payload['prefix'], strict=False))
        endpoints = ['as-overview', 'announced-prefixes', 'routing-status'] if resource.startswith('AS') else ['prefix-overview', 'routing-status', 'routing-history']
        for name in endpoints:
            async def one(name=name):
                params = {'resource': resource}
                if name == 'routing-history':
                    params.update(starttime=(datetime.now(timezone.utc)-timedelta(days=30)).strftime('%Y-%m-%d'), min_peers=10)
                data, response = await get_json('https://stat.ripe.net/data/'+name+'/data.json', params)
                if not isinstance(data, dict) or data.get('status') != 'ok' or not isinstance(data.get('data'), dict): raise ValueError()
                add('ripestat', 'RIPE RIS · '+name+' · '+resource, response,
                    {'resource': resource, 'address': value, 'prefix':resource if not resource.startswith('AS') else None,
                        'dataset': name, 'data': bounded_json(data['data'], maximum=20000)},
                    'Наблюдения route collectors RIPE RIS; история ограничена окном запроса и покрытием коллекторов.')
            await attempt('ripestat_'+name, one)
    async def reputation():
        address = ipaddress.ip_address(value)
        response = await fetch('https://www.spamhaus.org/drop/drop_v'+str(address.version)+'.json')
        records = []; metadata = {}; count = 0
        for line in response['body'].decode('utf-8-sig').splitlines():
            item = json.loads(line)
            if not isinstance(item, dict): raise ValueError()
            if 'cidr' in item:
                net = ipaddress.ip_network(item['cidr'])
                if net.version != address.version: raise ValueError('Wrong DROP family')
                count += 1
                if address in net: records.append({k: item[k] for k in ('cidr', 'sblid', 'rir') if k in item})
            elif 'timestamp' in item: metadata = {k: item[k] for k in ('timestamp', 'copyright') if k in item}
        if not count or not metadata: raise ValueError('Incomplete DROP dataset')
        add('spamhaus_drop', 'Spamhaus DROP · '+value, response,
            {'address': value, 'matched': bool(records), 'matches': records[:20], 'dataset_records': count, 'dataset_metadata': metadata},
            'Сопоставление с опубликованными DROP-диапазонами. Отсутствие совпадения не означает безопасность адреса.', kind='threat_indicator')
    async def dns():
        for name, kind in [(value, kind) for kind in ('AAAA', 'SOA', 'TXT', 'CAA')] + [('_dmarc.'+value, 'TXT')]:
            async def one(name=name, kind=kind):
                data, response = await get_json('https://dns.google/resolve', {'name': name, 'type': kind})
                if not isinstance(data, dict) or type(data.get('Status')) is not int or not isinstance(data.get('Answer', []), list): raise ValueError()
                if data['Status'] not in (0,3):raise PageReadError('dns_rcode_'+str(data['Status']),'unavailable')
                answers = [{k: row[k] for k in ('name', 'type', 'TTL', 'data') if k in row}
                    for row in data.get('Answer', [])[:30] if isinstance(row, dict)]
                add('google_dns', 'DNS · '+name+' · '+kind, response,
                    {'domain': value, 'query_name': name, 'query_type': kind, 'response_code': data['Status'], 'answers': answers},
                    'Публичная DNS-запись либо наблюдаемое отсутствие записи; SPF и DMARC сохраняются как опубликованный TXT.')
            await attempt('dns_'+name+'_'+kind, one)
    async def certificates():
        data, response = await get_json('https://crt.sh/', {'q': value, 'output': 'json'})
        if not isinstance(data, list): raise ValueError()
        names = {}; observations = []
        for item in data[:500]:
            if not isinstance(item, dict): continue
            for name in str(item.get('name_value', '')).splitlines():
                name = name.lower().strip().removeprefix('*.')
                if name == value or name.endswith('.'+value): names[name] = True
            observations.append({k: item[k] for k in ('id', 'issuer_name', 'common_name', 'name_value', 'not_before', 'not_after', 'entry_timestamp') if k in item})
        add('crtsh', 'Certificate Transparency · '+value, response,
            {'domain': value, 'observed_names': sorted(names)[:100], 'certificates': observations[:30], 'returned_rows': len(data), 'examined_rows': min(500, len(data))},
            'Архивные certificate observations; имя в сертификате не доказывает текущую DNS-связь или общего владельца.')
    async def operation():
        fn = {'network_rdap': rdap, 'domain_rdap': rdap, 'network_routing': routing,
              'network_reverse_dns': ptr, 'network_reputation': reputation,
              'domain_dns': dns, 'domain_certificates': certificates}[tool]
        await attempt(tool, fn)
    status = None
    try: _run(operation, cancel_event=cancel_event, deadline=end, timeout=40)
    except (PageReadError, _FetchError) as error:
        status = error.status; diagnostics.append({'source': tool, 'status': status, 'error_code': error.code})
    failed = [d for d in diagnostics if d['status'] != 'complete']
    status = status or ('partial' if rows and failed else 'complete' if rows else failed[-1]['status'] if failed else 'empty')
    result = _envelope(tool, value, status=status, results=rows,
        limitations=['Пассивные публичные наблюдения; порты не сканировались. Оператор диапазона, сервис и пользователь — разные сущности.']
            + [d['source']+': '+d.get('error_code', d['status']) for d in failed])
    result.update(operation=tool, input_parameters={TOOLS[tool][1]: value}, source_diagnostics=diagnostics)
    if failed: result['error_code'] = failed[-1].get('error_code', 'source_unavailable')
    return result
