"""Specific, key-free, documented public sources with bounded real extraction.

No user credential is accepted by this module. Endpoints and JSON mappings are
fixed per source; model output cannot select a host, HTTP verb or JSON selector.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from html.parser import HTMLParser
import json
import re
import threading
import time
from collections import deque
from urllib.parse import quote, urlsplit

from .agent_browser import PageReadError
from .agent_web import _FetchError, _run, _envelope, _record

SOURCES = {
 'github_profile':('GitHub · публичный профиль','username','https://docs.github.com/en/rest/users/users#get-a-user'),
 'github_users':('GitHub · поиск профилей','dork','https://docs.github.com/en/rest/search/search#search-users'),
 'github_repositories':('GitHub · поиск репозиториев','dork','https://docs.github.com/en/rest/search/search#search-repositories'),
 'hn_search':('Hacker News · публикации','dork','https://hn.algolia.com/api'),
 'hn_profile':('Hacker News · публичный профиль','username','https://github.com/HackerNews/API#users'),
 'openlibrary_search':('Open Library · публикации','dork','https://openlibrary.org/dev/docs/api/search'),
 'archive_search':('Internet Archive · метаданные','dork','https://archive.org/advancedsearch.php'),
 'wikipedia_search':('Wikipedia · статьи','dork','https://www.mediawiki.org/wiki/Extension:TextExtracts#API'),
}
_LOCK=threading.RLock()
_NEXT={}
_COOLDOWN={}
_CACHE={}
_HISTORY={}
_SLOTS=threading.BoundedSemaphore(2)
MAX_BYTES=2_000_000
USER_AGENT='Granger-OSINT/3.1 (public research; https://github.com/watsoncore/Granger-OSINT)'


def validate(source,value):
    if source not in SOURCES or not isinstance(value,str):raise ValueError('Unknown source/input')
    value=value.strip()
    if not value or len(value)>300 or any(ord(c)<32 for c in value):raise ValueError('Invalid query')
    if source=='github_profile' and not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?',value):
        raise ValueError('Invalid GitHub username')
    if source=='hn_profile' and not re.fullmatch(r'[A-Za-z0-9_-]{2,32}',value):raise ValueError('Invalid HN username')
    if source.startswith('github_') and len(value)>256:raise ValueError('GitHub query too long')
    return value


class _Text(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,value):self.parts.append(value)


def plain(value,maximum=2200):
    parser=_Text();parser.feed(str(value or '')[:20000])
    return ' '.join(' '.join(parser.parts).split())[:maximum]


def _bounded(value,depth=0):
    if depth>3:return None
    if isinstance(value,str):return value[:2500]
    if isinstance(value,list):return [_bounded(v,depth+1) for v in value[:10]]
    if isinstance(value,dict):return {str(k)[:80]:_bounded(v,depth+1) for k,v in list(value.items())[:25]}
    return value if value is None or type(value) in (int,float,bool) else None


def _check(cancel,deadline):
    if cancel is not None and cancel.is_set():raise _FetchError('cancelled',status='cancelled')
    if time.monotonic()>=deadline:raise _FetchError('timeout',status='timeout')


def _endpoint(source,value,limit):
    escaped=quote(value,safe='')
    if source=='github_profile':return 'https://api.github.com/users/'+escaped,{},'api.github.com'
    if source in ('github_users','github_repositories'):
        return 'https://api.github.com/search/'+('users' if source=='github_users' else 'repositories'),{'q':value,'per_page':limit},'api.github.com'
    if source=='hn_profile':return 'https://hacker-news.firebaseio.com/v0/user/'+escaped+'.json',{},'hacker-news.firebaseio.com'
    if source=='hn_search':return 'https://hn.algolia.com/api/v1/search',{'query':value,'hitsPerPage':limit},'hn.algolia.com'
    if source=='openlibrary_search':return 'https://openlibrary.org/search.json',{'q':value,'limit':limit,'fields':'key,title,author_name,first_publish_year,edition_count,ia'},'openlibrary.org'
    if source=='archive_search':return 'https://archive.org/advancedsearch.php',{'q':value,'rows':limit,'page':1,'output':'json','fl[]':['identifier','title','creator','date','mediatype','description']},'archive.org'
    return 'https://en.wikipedia.org/w/api.php',{'action':'query','generator':'search','gsrsearch':value,'gsrlimit':min(limit,5),'prop':'extracts|info','inprop':'url','exintro':1,'explaintext':1,'exchars':2200,'format':'json','formatversion':2,'maxlag':5},'en.wikipedia.org'


def _mapping(source,data,query,limit,endpoint):
    """Explicit source schemas: malformed containers never mean empty success."""
    if source=='github_profile':
        if not isinstance(data,dict) or not isinstance(data.get('login'),str) or not isinstance(data.get('id'),int):raise ValueError()
        items=[data]
    elif source in ('github_users','github_repositories'):
        if not isinstance(data,dict) or not isinstance(data.get('items'),list) or type(data.get('total_count')) is not int:raise ValueError()
        items=data['items']
    elif source=='hn_profile':
        if data is None:return []
        if not isinstance(data,dict) or data.get('id')!=query or type(data.get('created')) is not int:raise ValueError()
        items=[data]
    elif source=='hn_search':
        if not isinstance(data,dict) or not isinstance(data.get('hits'),list) or type(data.get('nbHits')) is not int:raise ValueError()
        items=data['hits']
    elif source=='openlibrary_search':
        if not isinstance(data,dict) or not isinstance(data.get('docs'),list) or type(data.get('numFound')) is not int:raise ValueError()
        items=data['docs']
    elif source=='archive_search':
        response=data.get('response') if isinstance(data,dict) else None
        if not isinstance(response,dict) or not isinstance(response.get('docs'),list) or type(response.get('numFound')) is not int:raise ValueError()
        items=response['docs']
    else:
        if not isinstance(data,dict) or 'error' in data:raise ValueError()
        if 'query' not in data and data.get('batchcomplete') is True:return []
        section=data.get('query')
        if not isinstance(section,dict) or not isinstance(section.get('pages'),list):raise ValueError()
        items=section['pages']
    rows=[]
    for item in items[:limit]:
        if not isinstance(item,dict):raise ValueError()
        fields={};kind='publication'
        if source in ('github_profile','github_users'):
            login=item.get('login')
            if not isinstance(login,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,39}',login) or type(item.get('id')) is not int:raise ValueError()
            url='https://github.com/'+quote(login,safe='');title=login;kind='profile'
            fields={k:item[k] for k in ('id','login','type','name','bio','company','location','public_repos','followers','following','created_at','updated_at','avatar_url') if k in item}
            description=plain(item.get('bio') or item.get('name') or 'Публичная запись GitHub; совпадение имени не устанавливает владельца других профилей.')
        elif source=='github_repositories':
            name=item.get('full_name')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',name) or item.get('private') is not False:raise ValueError()
            url='https://github.com/'+quote(name,safe='/');title=name;kind='repository'
            fields={k:item[k] for k in ('full_name','description','language','stargazers_count','forks_count','created_at','updated_at','pushed_at') if k in item}
            description=plain(item.get('description')) or 'Публичные метаданные репозитория.'
        elif source=='hn_profile':
            url='https://news.ycombinator.com/user?id='+quote(query,safe='');title=query;kind='profile'
            fields={k:item[k] for k in ('id','created','karma') if k in item};fields['submitted_count']=len(item.get('submitted',[])) if isinstance(item.get('submitted'),list) else None
            description=plain(item.get('about')) or 'Публичная запись Hacker News.'
        elif source=='hn_search':
            identifier=item.get('objectID')
            if not isinstance(identifier,str) or not identifier.isdigit():raise ValueError()
            url='https://news.ycombinator.com/item?id='+identifier;title=plain(item.get('title') or item.get('story_title') or 'Hacker News · '+identifier,500)
            description=plain(item.get('comment_text') or item.get('story_text') or item.get('title'))
            fields={k:item[k] for k in ('objectID','author','created_at','points','num_comments') if k in item}
            fields['text_excerpt']=description;fields['text_may_be_truncated']=True
        elif source=='openlibrary_search':
            key=item.get('key')
            if not isinstance(key,str) or not re.fullmatch(r'/works/OL[0-9]+W',key) or not isinstance(item.get('title'),str):raise ValueError()
            url='https://openlibrary.org'+key;title=item['title'];fields={k:item[k] for k in ('key','title','author_name','first_publish_year','edition_count') if k in item}
            description=plain(' · '.join([str(item.get('first_publish_year','')),', '.join(str(v) for v in item.get('author_name',[])[:5])]))
        elif source=='archive_search':
            identifier=item.get('identifier')
            if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,255}',identifier) or not isinstance(item.get('title'),str):raise ValueError()
            url='https://archive.org/details/'+quote(identifier,safe='');title=item['title'];kind='archive'
            fields={k:item[k] for k in ('identifier','title','creator','date','mediatype') if k in item}
            description=plain(item.get('description') or item.get('title'))
        else:
            if type(item.get('pageid')) is not int or not isinstance(item.get('title'),str) or not isinstance(item.get('extract'),str):raise ValueError()
            url='https://en.wikipedia.org/?curid='+str(item['pageid']);title=item['title'];description=plain(item['extract'])
            fields={'pageid':item['pageid'],'title':title,'article_intro':description,'intro_only':True}
        fields=_bounded(fields)
        fields.update(acquisition='official_api',endpoint=endpoint,extraction_status='record_extracted',source_record=True,source_id=source)
        rows.append(_record(source,query,title,url,description or 'Источник вернул структурированную публичную запись.',kind=kind,details=fields))
    return rows


def execute(source,value,*,limit=5,cancel_event=None,deadline=None,client_factory=None,resolver=None,agent_model=''):
    try:
        value=validate(source,value)
        if type(limit) is not int or not 1<=limit<=20:raise ValueError()
    except (ValueError,TypeError):return _envelope(source,'',status='invalid_arguments',error_code='invalid_input')
    end=min(deadline,time.monotonic()+15) if deadline is not None else time.monotonic()+15
    endpoint,params,host=_endpoint(source,value,limit)
    model=agent_model if isinstance(agent_model,str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,100}',agent_model) else ''
    user_agent=USER_AGENT+(' model='+model if model else '')
    key=(source,value,limit)
    acquired=False
    try:
        _check(cancel_event,end)
        with _LOCK:
            cached=_CACHE.get(key)
            cooldown=_COOLDOWN.get(host,0)
        if cached and time.monotonic()-cached[0]<300:
            result=deepcopy(cached[1]);result['limitations'].append('Кэш до5мин; сохранено исходное время получения.');return result
        if time.monotonic()<cooldown:raise _FetchError('provider_cooldown',status='rate_limited')
        while not _SLOTS.acquire(timeout=.05):_check(cancel_event,end)
        acquired=True
        interval=6.1 if source in ('github_users','github_repositories') else 1.1
        while True:
            _check(cancel_event,end)
            with _LOCK:
                delay=_NEXT.get(host,0)-time.monotonic()
                if delay<=0:
                    now=time.monotonic()
                    if host=='api.github.com':
                        history=_HISTORY.setdefault(host,deque())
                        while history and now-history[0]>=3600:history.popleft()
                        if len(history)>=60:raise _FetchError('local_hourly_quota',status='rate_limited')
                        history.append(now)
                    _NEXT[host]=now+interval;break
            if cancel_event:cancel_event.wait(min(.05,delay))
            else:time.sleep(min(.05,delay))
        async def operation():
            from .web_http import fetch_public
            try:
                response=await fetch_public(endpoint,params=params,cancel_event=cancel_event,deadline=end,
                    client_factory=client_factory,resolver=resolver,rate_interval=1.1,user_agent=user_agent,
                    accepted_statuses=(200,401,403,404,429,500,503))
            except PageReadError as exc:raise _FetchError(exc.code,status=exc.status) from None
            status=response['status'];headers=response['headers']
            if urlsplit(response['final_url']).hostname!=host:raise _FetchError('unexpected_api_origin',status='blocked')
            if status==404 and source=='github_profile':return []
            if status in (429,503) or status==403 and headers.get('x-ratelimit-remaining')=='0':
                with _LOCK:_COOLDOWN[host]=time.monotonic()+min(300,max(30,int(headers.get('retry-after','60')) if headers.get('retry-after','').isdigit() else 60))
                raise _FetchError('http_'+str(status),status='rate_limited')
            if status!=200:
                if status in (401,403):
                    with _LOCK:_COOLDOWN[host]=time.monotonic()+60
                raise _FetchError('http_'+str(status),status='auth_required' if status==401 else 'unavailable')
            if headers.get('x-ratelimit-remaining')=='0':
                reset=headers.get('x-ratelimit-reset','')
                wait=min(3600,max(60,int(reset)-time.time())) if reset.isdigit() else 60
                with _LOCK:_COOLDOWN[host]=time.monotonic()+wait
            try:data=json.loads(response['body'].decode('utf-8-sig'));return _mapping(source,data,value,limit,endpoint)
            except (ValueError,TypeError,RecursionError,UnicodeError):raise _FetchError('invalid_response') from None
        rows=_run(operation,cancel_event=cancel_event,deadline=end,timeout=15)
        result=_envelope(source,value,status='complete' if rows else 'empty',results=rows,limitations=['Ограниченный поиск в указанном публичном источнике, не глобальный индекс и не доказательство общей личности.'])
        with _LOCK:
            if len(_CACHE)>=32:_CACHE.pop(next(iter(_CACHE)))
            _CACHE[key]=(time.monotonic(),deepcopy(result))
        return result
    except _FetchError as exc:
        return _envelope(source,value,status=exc.status,error_code=exc.code,limitations=['Источник не вернул проверяемый результат. Авторизация, CAPTCHA и ограничения не обходились.'])
    finally:
        if acquired:_SLOTS.release()


def search(query,*,limit=5,cancel_event=None,deadline=None,client_factory=None,resolver=None,agent_model=''):
    """Small key-free federation, exposing each source failure and real scope."""
    try:query=validate('hn_search',query)
    except ValueError:return _envelope('web_search','',status='invalid_arguments',error_code='invalid_query')
    if type(limit) is not int or not 1<=limit<=10:return _envelope('web_search','',status='invalid_arguments',error_code='invalid_query')
    end=min(deadline,time.monotonic()+20) if deadline is not None else time.monotonic()+20
    try:_check(cancel_event,end)
    except _FetchError as exc:return _envelope('web_search',query,status=exc.status,error_code=exc.code)
    providers=('github_users','hn_search','wikipedia_search') if re.fullmatch(r'@?[A-Za-z0-9_.-]{1,64}',query) else ('hn_search','wikipedia_search','openlibrary_search')
    outcomes=[]
    from contextvars import copy_context
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='GrangerPublicSearch') as pool:
        jobs={pool.submit(copy_context().run,execute,p,query,limit=min(3,limit),cancel_event=cancel_event,deadline=end,client_factory=client_factory,resolver=resolver,agent_model=agent_model):p for p in providers}
        for future in as_completed(jobs):outcomes.append(future.result())
    rows=[];seen=set()
    for result in sorted(outcomes,key=lambda r:providers.index(r['tool'])):
        for row in result['results']:
            if row['url'] not in seen:rows.append(row);seen.add(row['url'])
    failed=[r for r in outcomes if r['status'] not in ('complete','empty')]
    status='cancelled' if cancel_event and cancel_event.is_set() else ('partial' if failed else 'complete') if rows else 'empty' if not failed else 'unavailable'
    result=_envelope('web_search',query,status=status,results=rows[:limit],limitations=['Поиск по документированным публичным источникам: '+', '.join(providers)+'. Это не полная выдача Google/всего интернета.']+[r['tool']+': '+str(r.get('error_code') or r['status']) for r in failed])
    result['source_attempts']=[{'source':r['tool'],'status':r['status'],'count':len(r['results']),'error_code':r.get('error_code')} for r in outcomes]
    return result
