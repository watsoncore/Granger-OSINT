"""Bounded no-key capabilities reviewed against the 19-project request.

Independent adapters reuse Granger's pinned HTTP transport. They do not import
the large upstream apps, account sessions or API clients. No login/probing,
contact import, messages, archive dump download or secret-bearing request exists.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import math
import re
import threading
import time
from urllib.parse import quote, urlsplit

import phonenumbers

from ..agent_browser import PageReadError, public_url, _decode
from ..agent_web import _FetchError, _run, _record, _envelope
from ..engine.router import normalize_email, _domain
from ..web_http import fetch_public
from . import nuclei


def schema(properties,required):
    return {'type':'object','properties':properties,'required':required,'additionalProperties':False}


INPUT_SCHEMAS={
 'nuclei_check':nuclei.INPUT_SCHEMA,
 'mail_dns':schema({'email':{'type':'string','minLength':3,'maxLength':254}},['email']),
 'historical_contacts':schema({'domain':{'type':'string','minLength':3,'maxLength':253},'max_snapshots':{'type':'integer','minimum':1,'maximum':3}},['domain']),
 'x_post':schema({'url':{'type':'string','maxLength':300}},['url']),
 'x_profile':schema({'username':{'type':'string','minLength':1,'maxLength':16}},['username']),
 **{name:schema({'query':{'type':'string','maxLength':150},'author':{'type':'string','maxLength':32},'subreddit':{'type':'string','maxLength':32},
        'after':{'type':'string','description':'UTC date YYYY-MM-DD','maxLength':10},'before':{'type':'string','description':'UTC date YYYY-MM-DD','maxLength':10},
        'limit':{'type':'integer','minimum':1,'maximum':20}},[]) for name in ('arctic_posts','arctic_comments')},
}
_LOCK=threading.RLock();_CACHE=OrderedDict();_BACKOFF={}
_UA='Granger-OSINT/3.1 (model=deepseek-v4-flash; +https://github.com/watsoncore/Granger-OSINT)'
_ARCTIC='https://arctic-shift.photon-reddit.com'
_NAME=re.compile(r'[A-Za-z0-9_-]{1,32}')


def validate(tool,args):
    if tool=='nuclei_check':return nuclei.validate(args)
    if tool not in INPUT_SCHEMAS or not isinstance(args,dict) or set(args)-set(INPUT_SCHEMAS[tool]['properties']):raise ValueError('Invalid arguments')
    values=deepcopy(args)
    if any(name not in args for name in INPUT_SCHEMAS[tool]['required']):raise ValueError('Required input missing')
    if tool=='mail_dns':
        if not isinstance(args['email'],str):raise ValueError('Email string required')
        values['email']=normalize_email(args['email'])
    elif tool=='historical_contacts':
        if not isinstance(args['domain'],str) or any(c in args['domain'] for c in '/:@%\\'):raise ValueError('Public domain required')
        values['domain']=_domain(args['domain'])
        public_url('https://'+values['domain']+'/')
        count=args.get('max_snapshots',2)
        if type(count) is not int or not 1<=count<=3:raise ValueError('Snapshot budget')
        values['max_snapshots']=count
    elif tool=='x_post':
        url=public_url(args['url']);parts=urlsplit(url)
        match=re.fullmatch(r'/([A-Za-z0-9_]{1,15})/status/([0-9]{1,20})/?',parts.path)
        if parts.hostname not in ('x.com','www.x.com','twitter.com','www.twitter.com') or not match or parts.query:raise ValueError('Exact public post URL required')
        if int(match[2])<=0:raise ValueError('Invalid post id')
        values['url']='https://x.com/'+match[1]+'/status/'+match[2]
    elif tool=='x_profile':
        raw=args['username']
        if not isinstance(raw,str) or not re.fullmatch(r'@?[A-Za-z0-9_]{1,15}',raw):raise ValueError('Exact username required')
        values['username']=raw.lstrip('@')
    else:
        if not args.get('author') and not args.get('subreddit'):raise ValueError('Bound search by author or subreddit')
        for key in ('author','subreddit'):
            if key in args and (not isinstance(args[key],str) or not _NAME.fullmatch(args[key])):raise ValueError('Invalid identifier')
        if 'query' in args and (not isinstance(args['query'],str) or not 1<=len(args['query'])<=150 or any(ord(c)<32 for c in args['query'])):raise ValueError('Invalid query')
        for key in ('after','before'):
            if key in args:
                if not isinstance(args[key],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',args[key]):raise ValueError('Invalid UTC date')
                datetime.strptime(args[key],'%Y-%m-%d')
        if args.get('after') and args.get('before') and args['after']>=args['before']:raise ValueError('Invalid time interval')
        limit=args.get('limit',5)
        if type(limit) is not int or not 1<=limit<=20:raise ValueError('Result budget')
        values['limit']=limit
    return values


def readiness(tool,settings=None):
    if tool=='nuclei_check':return nuclei.readiness(settings)
    if tool not in INPUT_SCHEMAS:return {'available':False,'state':'unavailable','reason':'Неизвестная capability.'}
    return {'available':True,'state':'ready_local','reason':'Встроенный проверяемый адаптер без персональных ключей; внешний доступ подтверждается фактическим запросом.'}


def _check(cancel,deadline):
    if cancel is not None and cancel.is_set():raise _FetchError('cancelled',status='cancelled')
    if time.monotonic()>=deadline:raise _FetchError('timeout',status='timeout')


async def _request(url,*,params=None,cancel=None,deadline=None,client_factory=None,resolver=None):
    _check(cancel,deadline)
    host=urlsplit(url).hostname
    with _LOCK:backoff=_BACKOFF.get(host)
    if backoff and backoff[0]>time.monotonic():raise _FetchError('source_backoff_'+backoff[2],status=backoff[1])
    try:
        result=await fetch_public(url,params=params,cancel_event=cancel,deadline=deadline,client_factory=client_factory,resolver=resolver,
            rate_interval=1.1,user_agent=_UA,accepted_statuses=(200,400,401,403,404,422,429,500,503))
    except PageReadError as exc:raise _FetchError(exc.code,status=exc.status) from None
    if urlsplit(result['final_url']).hostname!=host:raise _FetchError('unexpected_source_origin',status='blocked')
    status=result['status']
    if status==429 or status==503:
        headers=result['headers'];value=headers.get('retry-after') or headers.get('x-ratelimit-reset') or '60'
        try:wait=min(300,max(5,float(value)))
        except (ValueError,TypeError):wait=60
        with _LOCK:_BACKOFF[host]=(time.monotonic()+wait,'rate_limited','http_'+str(status))
        raise _FetchError('http_'+str(status),status='rate_limited')
    if status in (401,403):
        with _LOCK:_BACKOFF[host]=(time.monotonic()+60,'auth_required' if status==401 else 'blocked','http_'+str(status))
        raise _FetchError('http_'+str(status),status='auth_required' if status==401 else 'blocked')
    if status==404:return None
    if status!=200:raise _FetchError('http_'+str(status))
    if any(m in result['body'][:100000].lower() for m in (b'cf-chl-',b'challenge-platform',b'verify you are human')):raise _FetchError('source_challenge',status='blocked')
    return result


async def _json(url,**kwargs):
    result=await _request(url,**kwargs)
    if result is None:return None
    try:value=json.loads(result['body'].decode('utf-8-sig'))
    except (ValueError,UnicodeError,RecursionError):raise _FetchError('invalid_json') from None
    if not isinstance(value,(dict,list)):raise _FetchError('invalid_schema')
    return value


def _row(tool,query,title,url,description,kind,details):
    details.update(acquisition='official_api' if tool.startswith(('arctic_','mail_')) else 'public_api' if tool.startswith('x_') else 'archive_snapshot',
        source_record=True,extraction_status='record_extracted',capability=tool)
    return _record(tool,query,title,url,description,kind=kind,details=details)


async def _mail(args,call):
    email=args['email'];domain=email.rsplit('@',1)[1];observations=[];warnings=[]
    for name,kind in ((domain,'MX'),(domain,'TXT'),('_dmarc.'+domain,'TXT')):
        try:
            data=await _json('https://dns.google/resolve',params={'name':name,'type':kind},**call)
            if not isinstance(data,dict) or type(data.get('Status')) is not int or not 0<=data['Status']<=16 or not isinstance(data.get('Answer',[]),list):raise _FetchError('invalid_dns_response')
            answers=[]
            for answer in data.get('Answer',[])[:20]:
                if not isinstance(answer,dict) or type(answer.get('type')) is not int or not isinstance(answer.get('data'),str) or len(answer['data'])>4096:raise _FetchError('invalid_dns_response')
                if 'TTL' in answer and (type(answer['TTL']) is not int or not 0<=answer['TTL']<=2**31):raise _FetchError('invalid_dns_response')
                if 'name' in answer and (not isinstance(answer['name'],str) or len(answer['name'])>254):raise _FetchError('invalid_dns_response')
                answers.append({k:answer[k] for k in ('name','type','TTL','data') if k in answer})
            observations.append({'name':name,'record_type':kind,'dns_status':data['Status'],'answers':answers})
        except _FetchError as exc:
            if exc.status=='cancelled':raise
            warnings.append(name+' '+kind+': '+exc.code)
    if not observations:raise _FetchError('dns_queries_failed')
    def texts(rows):return [''.join(re.findall(r'"([^"]*)"',a['data'])) or a['data'] for row in rows for a in row['answers'] if a['type']==16]
    values=texts(observations)
    details={'email':email,'domain':domain,'syntax_valid':True,'dns_observations':observations,
        'spf':[v for v in values if v.lower().startswith('v=spf1')],
        'dmarc':[v for v in values if v.lower().startswith('v=dmarc1')],
        'mailbox_existence_checked':False,'messages_sent':False,
        'verification':'Проверены синтаксис и публичные DNS-политики домена. Это не подтверждает существование ящика, владельца или доставляемость.'}
    rows=[_row('mail_dns',email,'Публичные DNS-политики '+domain,'https://dns.google/query?name='+quote(domain,safe='')+'&type=MX',details['verification'],'email_domain',details)]
    return rows,warnings


async def _arctic(tool,args,call):
    params={k:v for k,v in args.items() if k!='query'};params['sort']='desc'
    if args.get('query'):params['query' if tool=='arctic_posts' else 'body']=args['query']
    fields=['id','author','created_utc','subreddit','score']+(['title','selftext','url','num_comments'] if tool=='arctic_posts' else ['body','link_id','parent_id'])
    params['fields']=','.join(fields)
    endpoint=_ARCTIC+'/api/'+('posts' if tool=='arctic_posts' else 'comments')+'/search'
    data=await _json(endpoint,params=params,**call)
    if not isinstance(data,dict) or not isinstance(data.get('data'),list):raise _FetchError('invalid_arctic_schema')
    rows=[]
    for item in data['data'][:args['limit']]:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not re.fullmatch(r'[a-z0-9]{1,16}',item['id']) or type(item.get('created_utc')) not in (int,float):raise _FetchError('invalid_arctic_record')
        if not math.isfinite(item['created_utc']) or not 0<=item['created_utc']<=253402214400:raise _FetchError('invalid_arctic_record')
        if not isinstance(item.get('author'),str) or not isinstance(item.get('subreddit'),str):raise _FetchError('invalid_arctic_record')
        if any(key in item and (type(item[key]) is not int or abs(item[key])>10**12) for key in ('score','num_comments')):raise _FetchError('invalid_arctic_record')
        if tool=='arctic_posts' and (not isinstance(item.get('title'),str) or not isinstance(item.get('url',''),str)):raise _FetchError('invalid_arctic_record')
        text=item.get('selftext','') if tool=='arctic_posts' else item.get('body','')
        if not isinstance(text,str):raise _FetchError('invalid_arctic_record')
        link='https://www.reddit.com/comments/'+item['id'] if tool=='arctic_posts' else _ARCTIC+'/api/comments/ids?ids='+item['id']
        public_url(link)
        fields_out={k:item[k] for k in fields if k in item and k not in ('selftext','body')}
        fields_out.update(text=text[:12000],text_truncated=len(text)>12000,published_at=datetime.fromtimestamp(item['created_utc'],timezone.utc).isoformat(),endpoint=endpoint,historical_archive=True,
            removed_or_deleted_marker=text.strip() in ('[removed]','[deleted]'),verification='Наблюдение стороннего исторического архива Reddit; полнота, наличие удалённых записей и нынешняя актуальность не гарантируются.')
        title=str(item.get('title') or 'Комментарий '+item['id'])[:500]
        rows.append(_row(tool,json.dumps(args,ensure_ascii=False),title,link,text[:1800] or title,'post' if tool=='arctic_posts' else 'comment',fields_out))
    return rows,['Архив может быть неполным. Отсутствие результата не доказывает отсутствия публикации. Scores могут быть ранними архивными значениями.']


async def _xpost(args,call):
    parts=urlsplit(args['url']).path.split('/');username,identifier=parts[1],parts[3]
    endpoint='https://api.fxtwitter.com/'+username+'/status/'+identifier
    data=await _json(endpoint,**call)
    if data is None:return [],['Публичный API не нашёл этот пост; приватные/удалённые публикации не обходятся.']
    if not isinstance(data,dict) or type(data.get('code')) is not int:raise _FetchError('invalid_fxtwitter_schema')
    if data['code']==404:return [],['FxTwitter сообщил, что пост не найден.']
    item=data.get('tweet')
    if data['code']!=200 or not isinstance(item,dict) or str(item.get('id'))!=identifier or not isinstance(item.get('text'),str) or not isinstance(item.get('author'),dict):raise _FetchError('invalid_fxtwitter_record')
    author=item['author']
    if not isinstance(author.get('screen_name'),str) or not re.fullmatch(r'[A-Za-z0-9_]{1,15}',author['screen_name']):raise _FetchError('invalid_fxtwitter_record')
    canonical='https://x.com/'+author['screen_name']+'/status/'+identifier
    media=[]
    for entry in item.get('media',{}).get('all',[])[:10] if isinstance(item.get('media'),dict) else []:
        if not isinstance(entry,dict):continue
        url=entry.get('url') or entry.get('thumbnail_url')
        try:url=public_url(url)
        except (PageReadError,TypeError):continue
        media.append({'type':str(entry.get('type','unknown'))[:40],'url':url,'downloaded':False})
    if any(key in item and item[key] is not None and (type(item[key]) is not int or not 0<=item[key]<=10**15) for key in ('likes','retweets','replies','views','bookmarks')):raise _FetchError('invalid_fxtwitter_record')
    details={k:item[k] for k in ('id','created_at','created_timestamp','lang','likes','retweets','replies','views','bookmarks') if k in item and isinstance(item[k],(str,int,type(None)))}
    details.update(text=item['text'][:12000],text_truncated=len(item['text'])>12000,author={k:author[k] for k in ('id','screen_name','name','url') if k in author},media=media,
        endpoint=endpoint,provider='FxTwitter/FxEmbed public API',verification='Один публичный пост по данным стороннего FxTwitter API. Лента, поиск, replies и личность владельца не проверялись.')
    return [_row('x_post',args['url'],'Публичный пост @'+author['screen_name'],canonical,item['text'][:1800],'post',details)],['Использован сторонний документированный API FxTwitter; не официальный X API. Медиа не скачивались.']


async def _xprofile(args,call):
    username=args['username'];endpoint='https://api.fxtwitter.com/'+username
    data=await _json(endpoint,**call)
    if data is None or isinstance(data,dict) and data.get('code')==404:return [],['FxTwitter не нашёл публичный профиль.']
    if not isinstance(data,dict) or type(data.get('code')) is not int or data['code']!=200 or not isinstance(data.get('user'),dict):raise _FetchError('invalid_fxtwitter_profile')
    user=data['user'];screen=user.get('screen_name')
    if not isinstance(screen,str) or screen.lower()!=username.lower() or not re.fullmatch(r'[A-Za-z0-9_]{1,15}',screen):raise _FetchError('invalid_fxtwitter_profile')
    if not isinstance(user.get('id'),str) or not re.fullmatch(r'[0-9]{1,30}',user['id']):raise _FetchError('invalid_fxtwitter_profile')
    details={'id':user['id'],'screen_name':screen,'endpoint':endpoint,'provider':'FxTwitter/FxEmbed public API','media_downloaded':False}
    for key in ('name','description','location','joined'):
        value=user.get(key,'')
        if not isinstance(value,str):raise _FetchError('invalid_fxtwitter_profile')
        details[key]=value[:5000]
    for key in ('followers','following','likes','tweets','media_count'):
        value=user.get(key)
        if value is not None:
            if type(value) is not int or not 0<=value<=10**15:raise _FetchError('invalid_fxtwitter_profile')
            details[key]=value
    for key in ('avatar_url','banner_url'):
        if user.get(key):
            try:details[key]=public_url(user[key])
            except (PageReadError,TypeError):pass
    details.update(verification='Публичные метаданные стороннего API. Bio/location — заявления профиля; совпадение username не устанавливает личность. Лента и ответы не запрашивались.')
    return [_row('x_profile',username,'Публичный профиль @'+screen,'https://x.com/'+screen,details['description'],'profile',details)],['Использован сторонний FxTwitter API. Счётчики и профиль могут быть устаревшими; приватное содержимое не запрашивалось.']


class _Text(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.values=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        for k,v in attrs:
            if k=='href' and isinstance(v,str) and v.startswith(('mailto:','tel:')):self.values.append(v.split(':',1)[1].split('?',1)[0])
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
    def handle_data(self,value):
        if not self.skip:self.values.append(value)


def extract_contacts(html):
    """Independent bounded extractor; audited kronikier semantics, no account probes."""
    p=_Text();p.feed(html[:500000]);text=unescape(' '.join(p.values)).replace('＠','@')
    text=re.sub(r'\s*[\[({]\s*(?:at|собака)\s*[\])}]\s*','@',text,flags=re.I)
    text=re.sub(r'\s*[\[({]\s*(?:dot|точка)\s*[\])}]\s*','.',text,flags=re.I)
    found={}
    for raw in re.findall(r'(?<![\w/.-])([A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24})(?!\w)',text):
        if raw.lower().endswith(('.png','.jpg','.svg','.js','.css')):continue
        try:value=normalize_email(raw).lower()
        except ValueError:continue
        found[('email',value)]={'kind':'email','value':value,'raw':raw[:254]}
    # Require international '+' syntax; ambiguous national numbers, dates,
    # tax identifiers and the upstream's 5000-domain sweep are deliberately absent.
    for match in phonenumbers.PhoneNumberMatcher(text,None,leniency=phonenumbers.Leniency.VALID):
        if not match.raw_string.lstrip().startswith('+'):continue
        value=phonenumbers.format_number(match.number,phonenumbers.PhoneNumberFormat.E164)
        found[('phone',value)]={'kind':'phone','value':value,'raw':match.raw_string[:80]}
        if len(found)>=50:break
    return list(found.values())[:50]


async def _historical(args,call):
    domain=args['domain'];maximum=args['max_snapshots']
    endpoint='https://web.archive.org/cdx/search/cdx'
    params=[('url',domain),('matchType','domain'),('output','json'),('filter','statuscode:200'),('filter','mimetype:text/html'),('collapse','urlkey'),('limit',10),('fl','timestamp,original,statuscode,mimetype')]
    data=await _json(endpoint,params=params,**call)
    if data is None:return [],['Архивный индекс не найден.']
    if not isinstance(data,list) or data and not all(isinstance(v,list) for v in data):raise _FetchError('invalid_cdx_schema')
    if not data:return [],['Архив не вернул снимков.']
    header=data[0]
    if not all(k in header for k in ('timestamp','original')):raise _FetchError('invalid_cdx_schema')
    snapshots=[]
    for line in data[1:11]:
        if len(line)!=len(header):raise _FetchError('invalid_cdx_row')
        record=dict(zip(header,line));ts=record.get('timestamp');original=record.get('original')
        if not isinstance(ts,str) or not re.fullmatch(r'\d{14}',ts) or not isinstance(original,str):raise _FetchError('invalid_cdx_row')
        try:
            datetime.strptime(ts,'%Y%m%d%H%M%S');safe=public_url(original);host=urlsplit(safe).hostname
        except (ValueError,PageReadError):continue
        if host!=domain and not host.endswith('.'+domain):continue
        snapshots.append({'timestamp':ts,'original_url':safe,'snapshot_url':'https://web.archive.org/web/'+ts+'id_/'+safe})
    # Prefer actual contact pages in the small returned set, as upstream's
    # classifier does; do not invent unobserved contact URLs.
    snapshots.sort(key=lambda r:(not bool(re.search(r'contact|about|impress|kontakt',r['original_url'],re.I)),r['timestamp']))
    contacts=[];warnings=[];fetched=[]
    for snapshot in snapshots[:maximum]:
        try:
            if time.monotonic()+1>=call['deadline']:
                warnings.append('Оставшийся бюджет не позволяет запросить следующий снимок.');break
            response=await _request(snapshot['snapshot_url'],**{**call,'deadline':min(call['deadline']-.3,time.monotonic()+8)})
            if response is None:warnings.append('Архивный снимок недоступен: '+snapshot['timestamp']);continue
            html=_decode(response['body'],response['content_type'])
            if 'html' not in response['content_type'] and 'text/plain' not in response['content_type']:raise _FetchError('unsupported_snapshot_content')
            for contact in extract_contacts(html):contacts.append({**contact,**snapshot})
            fetched.append(snapshot)
        except _FetchError as exc:
            if exc.status=='cancelled':raise
            warnings.append(snapshot['timestamp']+': '+exc.code)
    details={'domain':domain,'contacts':contacts[:100],'snapshots':snapshots[:maximum],'snapshots_fetched':len(fetched),'snapshots_considered':len(snapshots),
        'source_urls':[s['snapshot_url'] for s in fetched],'endpoint':endpoint,'historical_only':True,'verification':'Контакты относятся к конкретной архивной версии. Не доказаны нынешний владелец, существование почтового ящика или доступность телефона.'}
    rows=[_row('historical_contacts',domain,'Исторические контакты '+domain,endpoint+'?url='+quote(domain,safe=''),details['verification'],'historical_contacts',details)] if snapshots else []
    if snapshots and not fetched:warnings.append('Получен только индекс снимков; контакты не подтверждены содержимым страниц.')
    return rows,warnings


def execute(tool,args,*,cancel_event=None,deadline=None,approved=False,settings=None,client_factory=None,resolver=None):
    if tool=='nuclei_check':return nuclei.execute(args,cancel_event=cancel_event,deadline=deadline,approved=approved,settings=settings)
    try:values=validate(tool,args)
    except (TypeError,ValueError,PageReadError):return _envelope(tool,'',status='invalid_arguments',error_code='invalid_input')
    end=min(deadline,time.monotonic()+25) if deadline is not None else time.monotonic()+25
    query=json.dumps(values,ensure_ascii=False,sort_keys=True);key=(tool,query)
    try:
        _check(cancel_event,end)
        with _LOCK:cached=_CACHE.get(key)
        if cached and time.monotonic()-cached[0]<300:
            result=deepcopy(cached[1]);result['limitations'].append('Кэш до 5 минут: исходное время получения сохранено, нового запроса нет.');return result
        async def operation():
            call={'cancel':cancel_event,'deadline':end,'client_factory':client_factory,'resolver':resolver}
            if tool=='mail_dns':return await _mail(values,call)
            if tool.startswith('arctic_'):return await _arctic(tool,values,call)
            if tool=='x_post':return await _xpost(values,call)
            if tool=='x_profile':return await _xprofile(values,call)
            return await _historical(values,call)
        rows,warnings=_run(operation,cancel_event=cancel_event,deadline=end,timeout=25)
        result=_envelope(tool,query,status='partial' if warnings and tool in ('mail_dns','historical_contacts') else 'complete' if rows else 'empty',results=rows,limitations=warnings)
        if tool=='historical_contacts' and rows and rows[0]['details']['snapshots_fetched']==0:result['status']='partial'
        with _LOCK:
            if len(_CACHE)>=32:_CACHE.popitem(last=False)
            _CACHE[key]=(time.monotonic(),deepcopy(result))
        return result
    except _FetchError as exc:return _envelope(tool,query,status=exc.status,error_code=exc.code,limitations=['Запрос не дал проверяемого окончательного результата. Ограничения и авторизация не обходились.'])
