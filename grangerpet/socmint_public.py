"""Bounded public observations. No cookies, token guessing or challenge bypass."""
from copy import deepcopy
from html.parser import HTMLParser
import json
import re
import threading
import time
from urllib.parse import urlsplit
from .agent_web import _record,_envelope,_run,_FetchError
from .agent_browser import PageReadError
from .socmint_targets import vk,tiktok

PROFILE_SCHEMA={'type':'object','properties':{'target':{'type':'string','minLength':1,'maxLength':2000}},
                'required':['target'],'additionalProperties':False}
_CACHE={};_LOCK=threading.RLock()


def vk_public(value,*,reader,cancel_event=None,deadline=None,browser_read=None):
    target=vk(value);url=target['canonical_url'];reader.allow_url(url)
    outcome=reader.read(url,cancel_event=cancel_event,deadline=deadline)
    return vk_observation(target,outcome,browser_read=browser_read)


def vk_observation(target,outcome,*,browser_read=None):
    url=target['canonical_url']
    if outcome.get('status') not in ('complete','partial'):return {**outcome,'tool':'vk_public','query':url}
    records=[]
    for raw in outcome.get('results',[])[:1]:
        details=raw.get('details',{});metadata=details.get('metadata',{})
        text=str(details.get('content_text') or details.get('content_excerpt') or raw.get('description') or '')
        title=metadata.get('og:title') or raw.get('title','')
        # A 200 login/challenge document is not a publicly observed profile.
        name=re.sub(r'\s*[|—–-]\s*(?:ВКонтакте|VK)\s*$','',str(title),flags=re.I).strip()
        outdated=bool(re.search(r'(?iu)ваш браузер устарел|browser.{0,15}outdated|unsupported browser',text[:800]))
        if outdated and callable(browser_read):
            # Genuine installed browser, not a forged UA or challenge workaround.
            return vk_observation(target,browser_read(url))
        gate=bool(re.search(r'(?iu)^(?:вход|регистрация|login|sign in)(?:\s*[|—-].*)?$',name))
        generic=bool(re.fullmatch(r'(?iu)вконтакте|vk',name))
        shell=details.get('render_wait')=='bounded_wait_expired' and len(re.sub(r'[\s\u200b-\u200f\ufeff]','',text))<20
        observed=bool(metadata.get('og:title') and metadata.get('og:image') and
                      (metadata.get('og:description') or metadata.get('description')))
        if not name or generic or gate or not observed or re.search(r'(?iu)captcha|подтвердите.{0,20}(?:человек|номер)|access denied',text[:800]):
            return _envelope('vk_public',url,status='auth_required' if gate else 'blocked',
                error_code='vk_login_gate' if gate else 'vk_unsupported_browser' if outdated else 'vk_js_shell' if shell else 'vk_public_fields_unconfirmed',
                limitations=['Источник вернул заглушку устаревшего браузера.' if outdated else
                    'Браузер получил JS-каркас; за ограниченное ожидание публичные поля не появились. Это не доказательство закрытого профиля.' if shell else
                    'Этот URL вернул вход/ограничение либо не подтвердил публичный объект; имя и поля профиля не извлекались.'])
        links=details.get('links',[])
        posts=[row['url'] for row in links if isinstance(row,dict) and re.fullmatch(r'https://(?:m\.)?vk\.(?:com|ru)/wall-?\d+_\d+',row.get('url',''))]
        fields={**details,**target,'capability':'vk_public','display_name':name,
            'avatar_url':metadata.get('og:image'),'description':metadata.get('og:description') or metadata.get('description'),
            'public_links':[row for row in links if isinstance(row,dict)][:30],'visible_posts':posts[:20],
            'source_status':'public_content_observed','access_mode':'public','identity_verified':False,
            'object_type_verified':False,'field_origin':'public_page_metadata_and_links'}
        fields['identifier_origin']='input_url_not_independent_identity_verification'
        row=deepcopy(raw);row.update(title=name,platform='VK',type='public_post' if target['kind']=='post' else
            'community' if target['kind']=='community' else 'profile',details=fields)
        records.append(row)
    return _envelope('vk_public',url,status='partial' if records else 'empty',results=records,
        limitations=['Только фактически доступные метаданные и ссылки; непоказанные поля и закрытые публикации не установлены.'])


class _Embed(HTMLParser):
    def __init__(self):super().__init__();self.attributes={}
    def handle_starttag(self,tag,attrs):
        if tag=='blockquote':self.attributes.update(dict(attrs))


def tiktok_observation(target,payload):
    """Documented oEmbed fields only. The returned HTML is never executed."""
    if not isinstance(payload,dict) or payload.get('provider_name')!='TikTok' or payload.get('type') not in ('rich','video'):
        raise ValueError('TikTok oEmbed schema drift')
    fields={key:payload[key][:2000] for key in ('title','author_name','author_url','thumbnail_url','embed_product_id','embed_type')
            if isinstance(payload.get(key),str)}
    author=fields.get('author_url')
    if author:
        observed=tiktok(author)
        if observed['kind']!='profile' or observed['username'].casefold()!=target['username'].casefold():raise ValueError('Mismatched TikTok creator')
    parser=_Embed();parser.feed(str(payload.get('html') or '')[:30000])
    unique=parser.attributes.get('data-unique-id')
    if unique and unique.casefold()!=target['username'].casefold():raise ValueError('Mismatched TikTok uniqueId')
    return {**fields,**({'uniqueId':unique} if unique else {}),
        'nickname':fields.get('author_name'),'avatar_url':None,'counters':None,
        'userId':None,'secUid':None,'signature':None,'verified':None,'region':None,'language':None,
        'accountCreationTimestamp':None,'account_creation_status':'not_provided',
        'video_id':target.get('video_id'),'field_origin':'official_oembed_response',
        'input_username':target['username'],'input_kind':target['kind'],
        'public_profile_url':target['profile_url'],'unavailable_fields_reason':'Документированный публичный API не предоставил эти поля.'}


def tiktok_public(value,*,cancel_event=None,deadline=None,client_factory=None,resolver=None):
    target=tiktok(value)
    cache_key=target['canonical_url']
    if client_factory is None:
        with _LOCK:cached=_CACHE.get(cache_key)
        if cached and time.monotonic()<cached[0]:return {**deepcopy(cached[1]),'from_saved_data':True}
    async def collect():
        from .web_http import fetch_public
        response=await fetch_public('https://www.tiktok.com/oembed',params={'url':target['canonical_url']},
            deadline=deadline,cancel_event=cancel_event,client_factory=client_factory,resolver=resolver,rate_interval=1,
            allowed_types=('application/json','text/json'),accepted_statuses=(200,400,401,403,404,429,500,503))
        if urlsplit(response['final_url']).hostname!='www.tiktok.com':raise PageReadError('unexpected_tiktok_origin','blocked')
        status=response['status']
        if status!=200:
            failure=PageReadError('tiktok_oembed_http_'+str(status),
                'rate_limited' if status==429 else 'auth_required' if status==401 else 'blocked' if status==403 else 'unavailable')
            retry=response.get('headers',{}).get('retry-after','')
            failure.retry_after=min(86400,max(60,int(retry))) if str(retry).isdigit() else 60
            raise failure
        fields=tiktok_observation(target,json.loads(response['body'].decode('utf-8-sig')))
        description='TikTok: '+str(fields.get('nickname') or '@'+target['username'])+'. Источник — официальный oEmbed; полная статистика и дата создания аккаунта этим ответом не подтверждены.'
        record=_record('tiktok_public_profile',value,'TikTok · '+str(fields.get('nickname') or '@'+target['username']),
            target['canonical_url'],description,kind='public_post' if target['kind']=='video' else 'profile',
            details={**fields,'capability':'tiktok_public_profile','canonical_url':target['canonical_url'],
                     'source_status':'official_embed_observed','source_endpoint':response['final_url'],'identity_verified':False})
        return _envelope('tiktok_public_profile',value,status='partial',results=[record],limitations=[
            'Публичный официальный oEmbed не гарантирует avatar/counters/userId/secUid/region/language/creation; null не означает ноль.',
            'Автоматическое извлечение полного профиля из сайта не выполняется: общие условия TikTok запрещают scripts для сбора информации. Research/Display API требуют отдельного разрешённого доступа.'])
    ttl=300
    try:result=_run(collect,cancel_event=cancel_event,deadline=deadline,timeout=25)
    except (PageReadError,_FetchError) as error:
        ttl=getattr(error,'retry_after',60)
        result=_envelope('tiktok_public_profile',value,status=error.status,error_code=error.code,
            limitations=['Официальный TikTok oEmbed недоступен для этого URL: '+error.code+'. Закрытость профиля этим не доказана.'])
    except (ValueError,TypeError,UnicodeError):
        result=_envelope('tiktok_public_profile',value,status='error',
            error_code='tiktok_oembed_schema_drift',limitations=['Ответ не соответствует проверенной публичной схеме TikTok; поля не выдумывались.'])
    if client_factory is None and result.get('status') not in ('cancelled','timeout'):
        with _LOCK:
            if len(_CACHE)>=256:_CACHE.pop(next(iter(_CACHE)),None)
            _CACHE[cache_key]=(time.monotonic()+ttl,deepcopy(result))
    return result
