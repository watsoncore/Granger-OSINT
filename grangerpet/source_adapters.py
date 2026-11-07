"""Reviewed public adapters, executed only through the existing ToolRegistry.

Endpoints, field mappings and network origins are repository-owned. The model
supplies a typed identifier, never a URL template, parser, headers or code.
"""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import threading
import time
import unicodedata
from urllib.parse import quote, urlsplit

_REGIONS={
    'brreg':'NO','prh':'FI','fr_entreprises':'FR','ares':'CZ','krs':'PL','brasilapi':'BR',
    'cms_npi':'US','nhtsa':'US','noaa_nws':'US','uk_flood':'GB','uk_police':'GB',
    'uk_nationalarchives':'GB','data_gov_au':'AU','data_gov_ca':'CA','data_gov_ie':'IE',
    'data_gov_uk':'GB','data_fi':'FI','data_swiss':'CH','govdata_de':'DE',
    'data_gouv_fr':'FR','dados_pt':'PT','data_lu':'LU',
}


@dataclass(frozen=True)
class AdapterContract:
    adapter_id: str
    provider_id: str
    display_name: str
    category: str
    input_kind: str
    supported_entity_types: tuple
    documentation_url: str
    terms_url: str
    license: str
    host: str
    supported_operations: tuple = ('lookup',)
    requires_credentials: tuple = ()
    timeout: int = 18
    rate_limit: float = 1.2
    cache_policy: str = '5 minutes; 64 entries bounded by investigation scope; original observed_at retained'
    execution_mode: str = 'PUBLIC_API_NO_KEY'
    normalizer: str = 'reviewed-field-mapping/1'
    graph_mapping: str = 'typed observation + returned_for_query; no identity inference'
    capability_status: str = 'implemented_unverified'

    @property
    def input_schema(self):
        description={
            'username':'Точный публичный username без URL.',
            'handle':'Полный Bluesky handle, например bsky.app.',
            'software':'Точное имя пакета в выбранном реестре.',
            'package_path':'Точный идентификатор owner/package из выбранного реестра.',
            'repository':'GitHub owner/repository без URL.',
            'coordinates':'Широта,долгота WGS-84. Покрытие зависит от источника.',
            'date':'Календарная дата YYYY-MM-DD.',
            'domain':'Полный публичный домен без URL или пути.',
            'site':'Полный публичный домен без URL или пути.',
            'numeric':'Точный числовой ID записи в выбранном источнике.',
            'cve':'Точный CVE-YYYY-NNNN…; не команда и не поиск эксплойта.',
            'crypto_btc':'Публичный адрес Bitcoin mainnet.',
            'crypto_eth':'Публичный адрес Ethereum mainnet; сеть не выводится из владельца.',
            'crypto_ton':'Публичный адрес TON mainnet.',
        }.get(self.input_kind,'Поисковый запрос; совпадение не доказывает личность.')
        definition=_DEFINITIONS.get(self.provider_id)
        query_schema={'type':'string','minLength':1,'maxLength':300,'description':description}
        if definition and definition.query_pattern:
            query_schema.update(pattern='^(?:'+definition.query_pattern+')$',description=description+' Формат: '+definition.query_pattern)
        return {'type':'object','properties':{
            'query':query_schema,
            'limit':{'type':'integer','minimum':1,'maximum':10}},
            'required':['query'],'additionalProperties':False}

    def describe(self):
        value=asdict(self)
        value.update(input_schema=self.input_schema,
            name=self.display_name,region=[_REGIONS.get(self.provider_id,'global')],parser_version=self.normalizer,formats=['json'],
            authentication='own_api_key' if self.requires_credentials else 'none',status=self.capability_status,
            limits=f'До 10 записей за запрос, 2 МБ на ответ, таймаут до {self.timeout} с; действуют квоты источника.',
            output_schema={'type':'object','required':['status','results','limitations'],
                'observation_path':'results[].details.observation',
                'observation_required':['source','target','value','entity_type','canonical_identifier','timestamp','evidence_url','confidence_basis','verification_status']},
            network_permissions={'methods':['GET'],'origins':['https://'+self.host]},
            counting_unit=self.provider_id)
        with _LOCK:health=deepcopy(_HEALTH.get(self.adapter_id,{'status':'not_checked'}))
        value['health']=health
        return value


def contract(identifier,name,category,kind,types,host,docs,terms,license):
    return AdapterContract('source_'+identifier,identifier,name,category,kind,types,docs,terms,license,host)


CONTRACTS={c.adapter_id:c for c in (
    contract('gitlab','GitLab · публичный профиль','socmint','username',('username','public_profile'),
        'gitlab.com','https://docs.gitlab.com/api/users/','https://about.gitlab.com/terms/',
        'GitLab terms; public profile fields only; no blanket licence to user content'),
    contract('codeberg','Codeberg · публичный профиль','socmint','username',('username','public_profile'),
        'codeberg.org','https://docs.codeberg.org/advanced/accessing-the-api/','https://codeberg.org/Codeberg/org/src/branch/main/TermsOfUse.md',
        'Codeberg terms; Forgejo software licence does not license user content'),
    contract('bluesky','Bluesky · публичный профиль','socmint','handle',('public_profile','username'),
        'public.api.bsky.app','https://docs.bsky.app/docs/api/app-bsky-actor-get-profile','https://bsky.social/about/support/tos',
        'Bluesky terms; reference public metadata; user content rights retained'),
    contract('mastodon','Mastodon.social · публичный профиль','socmint','username',('username','public_profile'),
        'mastodon.social','https://docs.joinmastodon.org/methods/accounts/#lookup','https://mastodon.social/terms',
        'Instance terms; user content rights retained; fixed mastodon.social instance only'),
    contract('stackexchange','Stack Overflow · кандидаты профилей','socmint','person',('person','username','public_profile'),
        'api.stackexchange.com','https://api.stackexchange.com/docs/users','https://stackoverflow.com/legal/api-terms-of-use',
        'Stack Exchange API terms; user contributions CC BY-SA; preserve links and attribution'),
    contract('pypi','PyPI · метаданные пакета','software','software',('document','repository','organization'),
        'pypi.org','https://docs.pypi.org/api/json/','https://policies.python.org/pypi.org/Terms-of-Service/',
        'PyPI terms; package-specific licences retained; no package downloads'),
    contract('rubygems','RubyGems · метаданные gem','software','software',('document','repository','organization'),
        'rubygems.org','https://guides.rubygems.org/rubygems-org-api/','https://rubygems.org/policies/terms-of-service',
        'RubyGems terms; package-specific licences retained; metadata only'),
    contract('pubdev','pub.dev · метаданные пакета','software','software',('document','repository'),
        'pub.dev','https://github.com/dart-lang/pub-dev/blob/master/doc/Api.md','https://pub.dev/policy',
        'pub.dev policy; package-specific licences retained; no code downloads'),
    contract('datacite','DataCite · публичные DOI','academic','document',('document','person','organization'),
        'api.datacite.org','https://support.datacite.org/docs/api-queries','https://datacite.org/terms.html',
        'DataCite metadata CC0; linked works retain their own rights'),
    contract('hal','HAL · научные публикации','academic','document',('document','person','organization'),
        'api.archives-ouvertes.fr','https://api.archives-ouvertes.fr/docs/search/','https://about.hal.science/conditions-generales-dutilisation/',
        'HAL metadata CC0; document content is not downloaded or relicensed'),
)}
from .source_definitions import DEFINITIONS
_DEFINITIONS={d.provider:d for d in DEFINITIONS}
CONTRACTS.update({c.adapter_id:c for c in (
    contract(d.provider,d.name,d.category,d.kind,d.entity_types,urlsplit(d.endpoint).hostname,d.docs,d.terms,d.license)
    for d in DEFINITIONS)})
_LOCK=threading.RLock()
_CACHE=OrderedDict()
_HEALTH={}


def normalize_query(adapter_id, query):
    item=CONTRACTS[adapter_id]
    if not isinstance(query,str):raise ValueError('query must be text')
    value=unicodedata.normalize('NFC',query).strip()
    if not 1<=len(value)<=300 or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('invalid query')
    if item.input_kind=='username':
        value=value.removeprefix('@')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',value):raise ValueError('Expected exact username')
    if item.input_kind=='handle':
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{1,250}\.[A-Za-z]{2,63}',value):raise ValueError('Expected Bluesky handle')
        value=value.lower()
    if item.input_kind in ('domain','site'):
        from .engine.router import _domain
        value=_domain(value)
    if item.input_kind=='coordinates':
        from .geoint.mapping import coordinates
        from .geoint import GeointError
        try:latitude,longitude=coordinates(value)
        except GeointError:raise ValueError('Invalid coordinates') from None
        value=f'{latitude},{longitude}'
    if item.input_kind=='date':
        from datetime import date
        value=date.fromisoformat(value).isoformat()
    if item.input_kind.startswith('crypto_'):
        from .crypto_targets import resolve_crypto_target
        resolved=resolve_crypto_target(value,item.input_kind.removeprefix('crypto_'))
        if not resolved['valid'] or resolved['requires_network'] or resolved['target_kind']!='address':raise ValueError('Invalid network-specific address')
        value=resolved['canonical_address']
    if item.input_kind=='software' and not re.fullmatch(r'[A-Za-z0-9@][A-Za-z0-9_./@-]{0,150}' if item.provider_id=='npm' else r'[A-Za-z0-9][A-Za-z0-9_.-]{0,150}',value):
        raise ValueError('Expected package name')
    if item.input_kind in ('package_path','repository') and any(part in ('','..','.') for part in value.split('/')):
        raise ValueError('Invalid scoped package/repository identifier')
    definition=_DEFINITIONS.get(item.provider_id)
    if definition and definition.query_pattern and not re.fullmatch(definition.query_pattern,value):raise ValueError('Identifier does not match this register')
    return value


def endpoint(adapter_id, query, limit):
    value=quote(query,safe='')
    provider=CONTRACTS[adapter_id].provider_id
    if provider in _DEFINITIONS:
        from .source_definitions import request
        return request(_DEFINITIONS[provider],query,limit)
    if provider=='gitlab':return 'https://gitlab.com/api/v4/users',{'username':query,'per_page':limit}
    if provider=='codeberg':return 'https://codeberg.org/api/v1/users/'+value,{}
    if provider=='bluesky':return 'https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile',{'actor':query}
    if provider=='mastodon':return 'https://mastodon.social/api/v1/accounts/lookup',{'acct':query}
    if provider=='stackexchange':return 'https://api.stackexchange.com/2.3/users',{'site':'stackoverflow','inname':query,'pagesize':limit}
    if provider=='pypi':return 'https://pypi.org/pypi/'+value+'/json',{}
    if provider=='rubygems':return 'https://rubygems.org/api/v1/gems/'+value+'.json',{}
    if provider=='pubdev':return 'https://pub.dev/api/packages/'+value,{}
    if provider=='datacite':
        return 'https://api.datacite.org/dois',{'query':query,'page[size]':limit,
            'fields[dois]':'titles,creators,publicationYear','disable-facets':'true'}
    if provider=='hal':return 'https://api.archives-ouvertes.fr/search/',{'q':query,'rows':limit,'wt':'json','fl':'docid,title_s,uri_s,authFullName_s,producedDate_s'}
    raise ValueError('No reviewed endpoint')


def object_at(data,*path):
    for key in path:
        if not isinstance(data,dict) or key not in data:raise ValueError('Provider schema changed')
        data=data[key]
    return data


def rows_at(data,*path):
    rows=object_at(data,*path) if path else data
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('Expected records')
    return rows


def text(value,maximum=1200):
    from .public_sources import plain
    if isinstance(value,list):value='; '.join(str(v) for v in value[:6] if isinstance(v,(str,int)))
    return plain(value,maximum) if isinstance(value,(str,int,float)) else ''


def mapped(adapter_id,data,query,limit):
    """Per-provider schema assertions; no JSON paths supplied by external data."""
    p=CONTRACTS[adapter_id].provider_id
    if p in _DEFINITIONS:
        from .source_definitions import parse
        if p=='hackage':
            if not isinstance(data,dict) or not data or any(not re.fullmatch(r'\d+(?:\.\d+)*',v) or status not in ('normal','deprecated','unpreferred') for v,status in data.items()):
                raise ValueError('Expected Hackage version preferences')
            data=[{'package_name':query,'version':v,'release_status':status} for v,status in sorted(data.items(),key=lambda row:tuple(map(int,row[0].split('.'))),reverse=True)]
        if p=='cisa_kev':
            rows=rows_at(data,'vulnerabilities')
            if any(not isinstance(row.get('cveID'),str) for row in rows):raise ValueError('Invalid KEV catalogue')
            data={'vulnerabilities':[row for row in rows if row['cveID']==query]}
        values=parse(_DEFINITIONS[p],data,limit)
        if p=='hackage':
            for row in values:
                row['canonical_identifier']=p+':'+query+':'+row['fields']['version']
                row['title']=query+' '+row['title']
        if p=='endoflife':
            for row in values:
                row['canonical_identifier']=p+':'+query+':'+row['fields']['release_cycle']
                row['url']='https://endoflife.date/'+quote(query,safe='')
                row['title']=query+' '+row['title']
        return values
    if p=='gitlab':rows=rows_at(data)
    elif p=='stackexchange':rows=rows_at(data,'items')
    elif p=='datacite':rows=rows_at(data,'data')
    elif p=='hal':rows=rows_at(data,'response','docs')
    else:
        if not isinstance(data,dict):raise ValueError('Expected object')
        rows=[data]
    result=[]
    for row in rows[:limit]:
        entity='public_profile';fields={};description='';candidate=False
        if p in ('gitlab','codeberg'):
            ident=object_at(row,'id');username=object_at(row,'username' if p=='gitlab' else 'login')
            title=text(row.get('name') or row.get('full_name') or username)
            url=object_at(row,'web_url' if p=='gitlab' else 'html_url')
            fields={'username':text(username),'display_name':title,'platform':p}
        elif p=='bluesky':
            ident=object_at(row,'did');username=object_at(row,'handle');title=text(row.get('displayName') or username)
            url='https://bsky.app/profile/'+quote(str(ident),safe=':')
            fields={key:row[key] for key in ('did','handle','followersCount','followsCount','postsCount','createdAt') if key in row}
            fields.update(username=username,platform='bluesky');description=text(row.get('description'))
        elif p=='mastodon':
            ident=object_at(row,'id');username=object_at(row,'acct');url=object_at(row,'url')
            title=text(row.get('display_name') or username);description=text(row.get('note'))
            fields={key:row[key] for key in ('username','acct','followers_count','following_count','statuses_count','created_at') if key in row}
            fields['platform']='mastodon'
        elif p=='stackexchange':
            ident=object_at(row,'user_id');title=text(object_at(row,'display_name'));url=object_at(row,'link');candidate=True
            fields={key:row[key] for key in ('reputation','creation_date','user_id') if key in row};fields['platform']='stackoverflow'
        elif p in ('pypi','rubygems','pubdev'):
            entity='public_document';info=object_at(row,'info') if p=='pypi' else object_at(row,'latest','pubspec') if p=='pubdev' else row
            ident=object_at(info,'name');title=text(ident)
            url='https://pypi.org/project/'+quote(str(ident),safe='')+'/' if p=='pypi' else 'https://pub.dev/packages/'+quote(str(ident),safe='') if p=='pubdev' else object_at(row,'project_uri')
            fields={'package_name':title,'version':text(info.get('version')),'declared_license':text(info.get('license') or info.get('licenses')),'publication_type':'software_package','registry':p}
            description=text(info.get('summary') or info.get('description') or info.get('info'))
        elif p=='datacite':
            entity='public_document';ident=object_at(row,'id');a=object_at(row,'attributes')
            titles=rows_at(a,'titles');title=text(titles[0].get('title')) if titles else text(ident)
            url='https://doi.org/'+quote(str(ident),safe='/')
            fields={'doi':text(ident),'publication_year':a.get('publicationYear'),'publication_type':'publication',
                    'creators':[text(v.get('name')) for v in rows_at(a,'creators')[:6]]};candidate=True
        elif p=='hal':
            entity='public_document';ident=object_at(row,'docid');title=text(object_at(row,'title_s'));url=object_at(row,'uri_s');candidate=True
            fields={'authors':row.get('authFullName_s',[])[:6],'published_at':text(row.get('producedDate_s')),'publication_type':'publication'}
        else:raise ValueError('No reviewed mapping')
        from .engine.models import canonical_url
        url=canonical_url(url) if isinstance(url,str) else ''
        if not title or not url or isinstance(ident,(dict,list,bool)) or ident is None:raise ValueError('Missing canonical identity')
        result.append({'canonical_identifier':p+':'+str(ident),'entity_type':entity,'title':title,'url':url,
                       'fields':fields,'description':description,'candidate':candidate})
    return result


def execute(adapter_id,args,*,cancel_event=None,deadline=None,client_factory=None,resolver=None,cache_scope=None):
    from .agent_web import _envelope,_record,_run,_FetchError
    from .agent_browser import PageReadError
    item=CONTRACTS[adapter_id]
    try:
        from .tool_inputs import validate_object
        args=validate_object(args,item.input_schema);query=normalize_query(adapter_id,args['query']);limit=args.get('limit',5)
    except (ValueError,TypeError):return _envelope(adapter_id,'',status='invalid_arguments',error_code='invalid_source_input')
    end=min(deadline or float('inf'),time.monotonic()+item.timeout)
    key=(cache_scope,adapter_id,query,limit)
    def health(status,count,cached=False):
        checked_at=datetime.now(timezone.utc).isoformat()
        with _LOCK:
            previous=_HEALTH.get(adapter_id,{})
            last_success_at=checked_at if status=='complete' and count and not cached else previous.get('last_success_at')
            _HEALTH[adapter_id]={'status':status,'result_count':count,'checked_at':checked_at,
                'cached':cached,'last_success_at':last_success_at}
    try:
        if cancel_event and cancel_event.is_set():raise _FetchError('cancelled',status='cancelled')
        if time.monotonic()>=end:raise _FetchError('timeout',status='timeout')
        with _LOCK:cached=_CACHE.get(key)
        if cached and time.monotonic()-cached[0]<300:
            value=deepcopy(cached[1]);value['from_saved_data']=True
            diagnostic=value.setdefault('source_diagnostics',{})
            diagnostic.update(saved_http_status=diagnostic.get('http_status'),http_status=None,
                providers_attempted=0,http_requests=0,http_statuses=[],logical_requests=0,http_attempts=0,from_saved_data=True)
            value['limitations'].append('Кэш до 5 минут; сохранено исходное время получения.');return value
        url,params=endpoint(adapter_id,query,limit)
        assert urlsplit(url).hostname==item.host
        async def request():
            from .web_http import fetch_public
            async def reviewed_origin(target):
                parsed=urlsplit(target)
                if parsed.scheme!='https' or parsed.hostname!=item.host or parsed.port not in (None,443):
                    raise PageReadError('unexpected_api_origin','blocked')
            try:
                response=await fetch_public(url,params=params,cancel_event=cancel_event,deadline=end,
                    client_factory=client_factory,resolver=resolver,rate_interval=item.rate_limit,
                    before_request=reviewed_origin,
                    accepted_statuses=(200,400,401,403,404,429,500,502,503),
                    allowed_types=('application/json','application/vnd.api+json','application/ld+json','application/hal+json','application/geo+json'))
            except PageReadError as error:raise _FetchError(error.code,status=error.status) from None
            if urlsplit(response['final_url']).hostname!=item.host:raise _FetchError('unexpected_api_origin',status='blocked')
            code=response['status']
            if code==404:return response,[]
            if code!=200:raise _FetchError('http_'+str(code),status='rate_limited' if code==429 else 'auth_required' if code==401 else 'unavailable')
            if len(response['body'])>2_000_000:raise _FetchError('response_too_large',status='limit_reached')
            def invalid_constant(value):raise ValueError('Non-finite JSON number')
            data=json.loads(response['body'].decode('utf-8-sig'),parse_constant=invalid_constant)
            return response,mapped(adapter_id,data,query,limit)
        response,observations=_run(request,cancel_event=cancel_event,deadline=end,timeout=item.timeout)
        body_hash=hashlib.sha256(response['body']).hexdigest();records=[]
        for observation in observations:
            if item.input_kind=='coordinates':
                observation['canonical_identifier']+='|at:'+query
            now=datetime.now(timezone.utc).isoformat()
            details={'adapter_id':adapter_id,'provider_id':item.provider_id,'source_id':adapter_id,
                'acquisition':'official_api','source_endpoint':response['final_url'],'content_sha256':body_hash,
                'parser_version':item.normalizer,'canonical_identifier':observation['canonical_identifier'],
                'source_record':True,'capability':adapter_id,
                'observation':{'source':item.provider_id,'target':{'value':query,'kind':item.input_kind},
                    'value':observation['fields'],'entity_type':observation['entity_type'],
                    'canonical_identifier':observation['canonical_identifier'],'timestamp':now,
                    'evidence_url':observation['url'],'confidence_basis':'Fields returned by the documented API; search match is not identity proof',
                    'verification_status':'source_reported','candidate':observation['candidate']},'untrusted_source_data':True}
            record=_record(adapter_id,query,observation['title'],observation['url'],observation['description'],kind='public_source_entity',details=details)
            record['platform']=item.display_name
            record['sources']=[item.display_name]
            record['status']='source_reported';records.append(record)
        status='complete' if records else 'empty'
        value=_envelope(adapter_id,query,status=status,results=records,limitations=[
            'Ограниченная публичная выборка; совпадение запроса не подтверждает общую личность. Отсутствие результата не доказывает отсутствие объекта.',
            item.license])
        value['source_diagnostics']={'provider_id':item.provider_id,'http_status':response['status'],
            'providers_attempted':1,'http_requests':None,'http_statuses':[response['status']],
            'returned_records':len(records),'logical_requests':1,'http_attempts':'transport retries/redirects may add attempts; exact count not measured','from_saved_data':False}
        with _LOCK:
            _CACHE[key]=(time.monotonic(),deepcopy(value));_CACHE.move_to_end(key)
            while len(_CACHE)>64:_CACHE.popitem(last=False)
        health(status,len(records));return value
    except (PageReadError,_FetchError) as error:
        status=error.status if error.status in ('cancelled','timeout','rate_limited','auth_required','blocked','limit_reached') else 'unavailable'
        value=_envelope(adapter_id,query,status=status,error_code=error.code,limitations=['Источник не вернул проверяемые данные; ограничения не обходились.'])
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        value=_envelope(adapter_id,query,status='error',error_code='source_schema_changed',limitations=['Ответ не соответствует проверенной схеме; пустой успех не создаётся.'])
    code=value.get('error_code','')
    value['error']={
        'timeout':'Источник не ответил вовремя. Можно повторить запрос позже.',
        'http_401':'Источник требует авторизацию (401). Публичные данные не получены.',
        'http_402':'Источник требует оплаченный доступ (402). Данные не получены.',
        'http_403':'Источник отказал в доступе (403). Данные не получены.',
        'http_429':'Превышена квота источника (429). Подождите перед повтором.',
        'source_schema_changed':'Формат ответа источника изменился. Непроверенные записи не добавлены.',
        'cancelled':'Запрос отменён.',
    }.get(code,'Сервис временно недоступен.' if code.startswith('http_5') else 'Источник не вернул проверяемые данные.')
    health(value['status'],0);return value
