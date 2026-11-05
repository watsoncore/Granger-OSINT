"""Finite reviewed public research actions with explicit source attribution."""
from copy import deepcopy
import base64
import hashlib
import json
import re
import threading
import time
from urllib.parse import quote

from .agent_web import _run,_record,_envelope,_FetchError
from .agent_browser import PageReadError
from .entity_forms import organization,JURISDICTIONS
from .source_registry_v2 import SOURCES,record_health

COMPANY_SCHEMA={'type':'object','properties':{
    'query':{'type':'string','minLength':1,'maxLength':300},
    'jurisdiction':{'type':'string','enum':list(JURISDICTIONS),'default':'OTHER'},
    'identifier_type':{'type':'string','enum':['name','bin','inn','ogrn','company_number','cik','registration_number','lei','website'],'default':'name'},
    'limit':{'type':'integer','minimum':1,'maximum':20,'default':5}},'required':['query'],'additionalProperties':False}
QUERY_SCHEMA={'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':300},
    'limit':{'type':'integer','minimum':1,'maximum':20,'default':5}},'required':['query'],'additionalProperties':False}
EMAIL_SCHEMA={'type':'object','properties':{'email':{'type':'string','minLength':3,'maxLength':254},
    'limit':{'type':'integer','minimum':1,'maximum':10,'default':5}},'required':['email'],'additionalProperties':False}
_LOCK=threading.RLock();_CACHE={};_NEXT={};_SLOTS=threading.BoundedSemaphore(2)
UA='Granger-OSINT/3.1 public-research (+https://github.com/watsoncore/Granger-OSINT)'

def _check(cancelled,end):
    if cancelled and cancelled.is_set():raise _FetchError('cancelled',status='cancelled')
    if time.monotonic()>=end:raise _FetchError('source_timeout',status='timeout')

def _json_source(source,path,params,*,cancelled,end,key='',client_factory=None,resolver=None,diagnostics=None):
    """Authorization stays on one fixed reviewed HTTPS origin; redirects are refused."""
    import asyncio
    import httpx
    from .agent_browser import PinnedTransport,resolve_public,public_address
    from .download_budget import check as check_download,consume
    descriptor=SOURCES[source]
    check_download()
    if not path.startswith('/') or path.startswith('//') or any(c in path for c in ('?','#','\\')):raise ValueError('Invalid source path')
    endpoint='https://'+descriptor.host+path
    async def request():
        addresses=await (resolver or resolve_public)(descriptor.host,443)
        if not addresses or any(not public_address(address) for address in addresses):raise _FetchError('unsafe_source_address',status='blocked')
        headers={'User-Agent':UA,'Accept':'application/json'}
        values=dict(params)
        if key:
            if source=='company_companies_house':headers['Authorization']='Basic '+base64.b64encode((key+':').encode()).decode()
            elif source=='company_opensanctions':headers['Authorization']='ApiKey '+key
            elif source=='company_opencorporates':values['api_token']=key
        transport=PinnedTransport(descriptor.host,443,addresses)
        async with (client_factory or httpx.AsyncClient)(transport=transport,trust_env=False,follow_redirects=False,
                headers=headers,timeout=httpx.Timeout(min(12,max(.2,end-time.monotonic())))) as client:
            if diagnostics is not None:diagnostics['http_requests']+=1
            async with client.stream('GET',endpoint,params=values) as response:
                status=response.status_code
                if diagnostics is not None:
                    code=str(status);diagnostics['http_statuses'][code]=diagnostics['http_statuses'].get(code,0)+1
                if status in (401,402,403):raise _FetchError('source_access_required',status='auth_required' if status!=403 else 'blocked')
                if status==429:
                    retry=response.headers.get('retry-after','60')
                    with _LOCK:_NEXT[descriptor.host]=time.monotonic()+min(300,max(1,int(retry) if retry.isdigit() else 60))
                    raise _FetchError('source_rate_limited',status='rate_limited')
                if status==404:return None,{'endpoint':endpoint,'http_status':404,'content_sha256':hashlib.sha256(b'').hexdigest()}
                if status!=200:raise _FetchError('source_http_'+str(status),status='unavailable')
                mime=response.headers.get('content-type','').split(';')[0].lower()
                if mime not in ('application/json','application/vnd.api+json','application/ld+json'):raise _FetchError('source_invalid_content')
                body=bytearray()
                async for chunk in response.aiter_bytes():
                    _check(cancelled,end)
                    if len(body)+len(chunk)>2_000_000:raise _FetchError('source_response_too_large',status='limit_reached')
                    consume(len(chunk));body.extend(chunk)
                try:data=json.loads(body.decode('utf-8-sig'))
                except (ValueError,UnicodeError,RecursionError):raise _FetchError('source_invalid_json') from None
                return data,{'endpoint':endpoint,'http_status':status,'content_sha256':hashlib.sha256(body).hexdigest()}
    try:return _run(request,cancel_event=cancelled,deadline=end,timeout=15)
    except PageReadError as error:raise _FetchError(error.code,status=error.status) from None

def _company_record(source,company,identifier,url,proof,details):
    row=_record(source,company['identifier'],details.get('legal_name') or identifier,url,
        'Запись указанного источника. Совпадение названия является кандидатом, а не подтверждением тождества организаций.',
        kind='company_registration',details={**details,**proof,'source_id':source,'parser_version':'1',
            'canonical_identifier':source+'|'+identifier,'requested_jurisdiction':company['jurisdiction'],
            'candidate_status':'registry_record','identity_match_verified':False,'source_record':True})
    row['status']='source_reported'
    return row

def _extract(source,data,company,limit,proof):
    if data is None:return []
    rows=[]
    if source=='company_gleif':
        if not isinstance(data,dict) or not isinstance(data.get('data'),list):raise _FetchError('source_schema_changed')
        for item in data['data'][:limit]:
            attrs=item.get('attributes',{});entity=attrs.get('entity',{});lei=attrs.get('lei') or item.get('id')
            if not isinstance(lei,str) or not re.fullmatch(r'[A-Z0-9]{20}',lei):raise _FetchError('source_schema_changed')
            country=entity.get('legalAddress',{}).get('country','')
            if company['jurisdiction']!='OTHER' and country!=company['jurisdiction']:continue
            registration=entity.get('registrationAuthority',{})
            details={'legal_name':entity.get('legalName',{}).get('name'),'country':country,
                'jurisdiction':entity.get('legalJurisdiction'),'lei':lei,'registration_number':registration.get('otherRegistrationAuthorityID') or registration.get('registrationAuthorityEntityID'),
                'registry':registration.get('registrationAuthorityID'),'status':entity.get('status'),
                'registration_status':attrs.get('registration',{}).get('status')}
            rows.append(_company_record(source,company,lei,'https://api.gleif.org/api/v1/lei-records/'+lei,proof,details))
    elif source=='company_sec':
        if not isinstance(data,dict) or not isinstance(data.get('cik'),(str,int)) or not isinstance(data.get('name'),str):raise _FetchError('source_schema_changed')
        cik=str(data['cik']).zfill(10)
        rows.append(_company_record(source,company,cik,'https://www.sec.gov/edgar/browse/?CIK='+cik,proof,
            {'legal_name':data['name'],'country':'US','cik':cik,'registration_number':cik,'registry':'SEC EDGAR',
             'tickers':data.get('tickers',[])[:10],'filings_coverage':'Latest returned submissions; not a national business registry'}))
        recent=data.get('filings',{}).get('recent',{})
        for index,accession in enumerate(recent.get('accessionNumber',[])[:max(0,limit-1)]):
            forms=recent.get('form',[]);documents=recent.get('primaryDocument',[])
            if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',accession) or index>=len(documents):continue
            filename=documents[index]
            if not isinstance(filename,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,180}',filename):continue
            url='https://www.sec.gov/Archives/edgar/data/'+str(int(cik))+'/'+accession.replace('-','')+'/'+filename
            rows.append(_record(source,company['identifier'],data['name']+' · '+str(forms[index] if index<len(forms) else 'Filing'),url,
                'Публичный документ из SEC EDGAR.',kind='company_filing',details={**proof,'source_id':source,'company_cik':cik,'accession':accession,'source_record':True,'parser_version':'1'}))
    elif source=='company_companies_house':
        records=data.get('items') if isinstance(data,dict) else None
        if records is None and isinstance(data,dict) and data.get('company_number'):records=[data]
        if not isinstance(records,list):raise _FetchError('source_schema_changed')
        for item in records[:limit]:
            number=item.get('company_number')
            if not isinstance(number,str) or not re.fullmatch(r'[A-Z0-9]{8}',number):raise _FetchError('source_schema_changed')
            rows.append(_company_record(source,company,number,'https://find-and-update.company-information.service.gov.uk/company/'+number,proof,
                {'legal_name':item.get('company_name') or item.get('title'),'country':'GB','registration_number':number,
                 'status':item.get('company_status'),'registry':'Companies House','company_type':item.get('type')}))
    elif source=='company_opencorporates':
        records=data.get('results',{}).get('companies') if isinstance(data,dict) else None
        if not isinstance(records,list):raise _FetchError('source_schema_changed')
        for wrapped in records[:limit]:
            item=wrapped.get('company',{});number=str(item.get('company_number',''));jurisdiction=str(item.get('jurisdiction_code',''))
            if not number or not re.fullmatch(r'[a-z0-9_]{2,32}',jurisdiction):continue
            url='https://opencorporates.com/companies/'+jurisdiction+'/'+quote(number,safe='')
            rows.append(_company_record(source,company,jurisdiction+'|'+number,url,proof,{'legal_name':item.get('name'),
                'jurisdiction':jurisdiction,'registration_number':number,'status':item.get('current_status'),'registry':'OpenCorporates'}))
    elif source=='company_opensanctions':
        records=data.get('results') if isinstance(data,dict) else None
        if not isinstance(records,list):raise _FetchError('source_schema_changed')
        for item in records[:limit]:
            identifier=item.get('id');properties=item.get('properties',{})
            if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,180}',identifier):continue
            row=_record(source,company['identifier'],str(item.get('caption') or identifier),'https://www.opensanctions.org/entities/'+identifier+'/',
                'Кандидат из OpenSanctions. Совпадение имени не устанавливает включение исследуемой компании в санкционный список.',
                kind='company_candidate',details={**proof,'source_id':source,'candidate_status':'name_match_only','identity_match_verified':False,
                    'datasets':item.get('datasets',[])[:12],'schema':item.get('schema'),'names':properties.get('name',[])[:8],'parser_version':'1','source_record':True})
            rows.append(row)
    elif source=='publication_crossref':
        records=data.get('message',{}).get('items') if isinstance(data,dict) else None
        if not isinstance(records,list):raise _FetchError('source_schema_changed')
        for item in records[:limit]:
            doi=item.get('DOI');title=item.get('title')
            if not isinstance(doi,str) or not doi.startswith('10.') or not isinstance(title,list) or not title:continue
            rows.append(_record(source,company['identifier'],str(title[0])[:300],'https://doi.org/'+quote(doi,safe='/'),
                'Библиографическая запись Crossref. Содержимое публикации отдельно не загружалось.',kind='public_document',
                details={**proof,'doi':doi,'publisher':item.get('publisher'),'publication_type':item.get('type'),'source_id':source,'parser_version':'1','source_record':True}))
    elif source=='software_osv':
        if not isinstance(data,dict) or not isinstance(data.get('id'),str):raise _FetchError('source_schema_changed')
        identifier=data['id']
        rows.append(_record(source,company['identifier'],data.get('summary') or identifier,'https://osv.dev/vulnerability/'+quote(identifier,safe=''),
            'Публичная запись об уязвимости. Применимость к конкретной версии приложения требует отдельной проверки.',kind='public_document',
            details={**proof,'source_id':source,'vulnerability_id':identifier,'aliases':data.get('aliases',[])[:20],'parser_version':'1','source_record':True}))
    return rows

def execute_source(source,args,*,cancel_event=None,deadline=None,secret_getter=lambda _: '',client_factory=None,resolver=None):
    if source not in SOURCES:return _envelope(source,'',status='unavailable',error_code='unknown_source')
    descriptor=SOURCES[source];end=min(deadline or float('inf'),time.monotonic()+18)
    try:
        query=args.get('query','');limit=args.get('limit',5)
        if type(limit) is not int or not 1<=limit<=20:raise ValueError()
        if source.startswith('company_'):company=organization({'identifier':query,'jurisdiction':args.get('jurisdiction','OTHER'),'identifier_type':args.get('identifier_type','name')})
        else:
            if not isinstance(query,str) or not 1<=len(query.strip())<=300 or any(ord(c)<32 for c in query):raise ValueError()
            company={'identifier':query.strip(),'jurisdiction':'OTHER','identifier_type':'name'}
        key=secret_getter(descriptor.auth_key) if descriptor.auth_key else ''
        if descriptor.auth_key and not key:return _envelope(source,query,status='auth_required',error_code='own_api_key_required',limitations=['Источник требует собственный официальный API-ключ и подходящие условия использования.'])
        mode=company['identifier_type'];value=company['identifier']
        if source=='company_gleif':
            path='/api/v1/lei-records';params={'page[size]':limit}
            if mode=='lei':params['filter[lei]']=value
            elif mode=='name':params['filter[entity.legalName]']=value
            elif mode in ('bin','inn','ogrn','registration_number','company_number'):params['filter[entity.registrationAuthority.registrationAuthorityEntityID]']=value
            else:return _envelope(source,query,status='unavailable',error_code='identifier_not_supported',limitations=['GLEIF не является поиском по домену. Укажите название, LEI или регистрационный номер.'])
            if company['jurisdiction']!='OTHER':params['filter[entity.legalAddress.country]']=company['jurisdiction']
        elif source=='company_sec':
            if mode!='cik':return _envelope(source,query,status='unavailable',error_code='cik_required',limitations=['Для точного запроса SEC EDGAR нужен CIK. Название не подменяется угаданным номером.'])
            path='/submissions/CIK'+value.zfill(10)+'.json';params={}
        elif source=='company_companies_house':
            if company['jurisdiction']!='GB' or mode not in ('name','company_number'):return _envelope(source,query,status='unavailable',error_code='british_company_identifier_required')
            path='/search/companies' if mode=='name' else '/company/'+value;params={'q':value,'items_per_page':limit} if mode=='name' else {}
        elif source=='company_opencorporates':path='/v0.4/companies/search';params={'q':value,'per_page':limit}
        elif source=='company_opensanctions':path='/search/default';params={'q':value,'schema':'Company','limit':limit}
        elif source=='publication_crossref':path='/works';params={'query':value,'rows':limit}
        else:
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',value):raise ValueError()
            path='/v1/vulns/'+value;params={}
    except (ValueError,TypeError):return _envelope(source,'',status='invalid_arguments',error_code='invalid_typed_input')
    cache_key=(source,json.dumps(args,sort_keys=True),hashlib.sha256(key.encode()).hexdigest() if key else '')
    diagnostics={'providers_attempted':1,'http_requests':0,'http_statuses':{}}
    acquired=False
    try:
        _check(cancel_event,end)
        with _LOCK:cached=_CACHE.get(cache_key)
        if cached and time.monotonic()-cached[0]<300:
            result=deepcopy(cached[1]);result['from_saved_data']=True
            result['source_diagnostics']={'providers_attempted':0,'http_requests':0,'http_statuses':{}}
            return result
        while not _SLOTS.acquire(timeout=.05):_check(cancel_event,end)
        acquired=True
        while True:
            _check(cancel_event,end)
            with _LOCK:
                pause=_NEXT.get(descriptor.host,0)-time.monotonic()
                if pause<=0:_NEXT[descriptor.host]=time.monotonic()+1.1;break
            if cancel_event:cancel_event.wait(min(.05,pause))
            else:time.sleep(min(.05,pause))
        data,proof=_json_source(source,path,params,cancelled=cancel_event,end=end,key=key,client_factory=client_factory,resolver=resolver,diagnostics=diagnostics)
        rows=_extract(source,data,company,limit,proof)
        result=_envelope(source,query,status='complete' if rows else 'empty',results=rows,
            limitations=['Источник имеет собственное покрытие. Отсутствие записи не означает, что компании или документа не существует.'])
        with _LOCK:
            if len(_CACHE)>=48:_CACHE.pop(next(iter(_CACHE)))
            _CACHE[cache_key]=(time.monotonic(),deepcopy(result))
    except _FetchError as error:result=_envelope(source,query,status=error.status,error_code=error.code)
    except Exception:result=_envelope(source,query,status='unavailable',error_code='official_source_unavailable')
    finally:
        if acquired:_SLOTS.release()
    record_health(source,result['status'],len(result['results']))
    result['source_diagnostics']=diagnostics
    return result

def company_research(args,**kwargs):
    # Providers receive the exact typed company query; no DNS or invented domain.
    country=args.get('jurisdiction','OTHER');mode=args.get('identifier_type','name')
    sources=['company_gleif']
    if country=='GB':sources.append('company_companies_house')
    if country=='US' and mode=='cik':sources=['company_sec']
    outcomes=[execute_source(source,args,**kwargs) for source in sources]
    records=[row for outcome in outcomes for row in outcome['results']]
    failed=[outcome for outcome in outcomes if outcome['status'] not in ('complete','empty')]
    result=_envelope('company_research',args.get('query',''),status=('partial' if failed else 'complete') if records else 'unavailable' if failed else 'empty',results=records,
        limitations=['GLEIF охватывает юридические лица с LEI, а не все компании. Национальные реестры могут требовать авторизацию. Кандидаты не объединяются по названию.']+[source+' — '+str(outcome.get('error_code') or outcome['status']) for source,outcome in zip(sources,outcomes) if outcome in failed])
    result['source_attempts']=[{'source':source,'status':outcome['status'],'count':len(outcome['results']),'error_code':outcome.get('error_code')} for source,outcome in zip(sources,outcomes)]
    diagnostics={'providers_attempted':0,'http_requests':0,'http_statuses':{}}
    for outcome in outcomes:
        source=outcome.get('source_diagnostics',{})
        for key in ('providers_attempted','http_requests'):diagnostics[key]+=source.get(key,0)
        for code,count in source.get('http_statuses',{}).items():diagnostics['http_statuses'][code]=diagnostics['http_statuses'].get(code,0)+count
    result['source_diagnostics']=diagnostics
    return result


def email_research(args,*,cancel_event=None,deadline=None,settings=None,public_execute=None,dns_execute=None):
    """Independent public observations; never registration/reset/SMTP probes."""
    from .engine.router import normalize_email
    from .public_sources import execute as public_source
    from .integrations19.public_tools import execute as public_dns
    try:
        email=normalize_email(args.get('email',''));limit=args.get('limit',5)
        if type(limit) is not int or not 1<=limit<=10:raise ValueError()
    except (ValueError,TypeError):return _envelope('email_research','',status='invalid_arguments',error_code='invalid_email')
    end=min(deadline or float('inf'),time.monotonic()+35)
    steps=[('mail_dns',lambda:(dns_execute or public_dns)('mail_dns',{'email':email},cancel_event=cancel_event,deadline=end,settings=settings)),
        ('github_users',lambda:(public_execute or public_source)('github_users','"'+email+'" in:email',limit=limit,cancel_event=cancel_event,deadline=end)),
        ('hn_search',lambda:(public_execute or public_source)('hn_search','"'+email+'"',limit=limit,cancel_event=cancel_event,deadline=end))]
    records=[];attempts=[];limitations=[]
    for source,call in steps:
        if cancel_event and cancel_event.is_set() or time.monotonic()>=end:
            attempts.append({'source':source,'status':'cancelled' if cancel_event and cancel_event.is_set() else 'timeout','count':0});continue
        try:outcome=call()
        except Exception:outcome=_envelope(source,email,status='unavailable',error_code='source_unavailable')
        selected=[]
        for incoming in outcome.get('results',[]):
            # A general index match must actually mention this exact address.
            if source=='hn_search' and email.casefold() not in (str(incoming.get('title',''))+' '+str(incoming.get('description',''))+' '+json.dumps(incoming.get('details',{}),ensure_ascii=False)).casefold():continue
            row=deepcopy(incoming);row.setdefault('details',{}).update(workflow='email_research',workflow_step=source,requested_email=email,
                mailbox_verified=False,identity_match_verified=False)
            if source=='github_users':row['details'].update(match_basis='public_email_search_index',exact_email_confirmed=False)
            selected.append(row)
        records.extend(selected)
        attempts.append({'source':source,'status':outcome['status'],'count':len(selected),'returned_records':len(outcome.get('results',[])),
            'error_code':outcome.get('error_code'),'from_saved_data':outcome.get('from_saved_data') is True})
        limitations.extend(source+': '+str(text) for text in outcome.get('limitations',[])[:3])
    failed=[row for row in attempts if row['status'] not in ('complete','empty')]
    status='cancelled' if cancel_event and cancel_event.is_set() else ('partial' if failed else 'complete') if records else 'unavailable' if failed else 'empty'
    result=_envelope('email_research',email,status=status,results=records,limitations=[
        'Синтаксис проверен локально. MX/SPF/DMARC относятся к домену и не подтверждают существование ящика.',
        'GitHub: индекс публичного email возвращает кандидатов. Hacker News: только точные публичные упоминания. Это ограниченное покрытие, не поиск всех аккаунтов.',
        'Письма, SMTP, регистрация, восстановление пароля и утечки не запрашивались. Никнеймы из локальной части email не угадываются.']+limitations)
    result['source_attempts']=attempts
    return result
