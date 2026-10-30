"""Official optional APIs. A key never implies consent to upload a photograph."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import time

import httpx

from ..agent_browser import public_url, PageReadError
from ..agent_web import _run, _FetchError
from ..agent_evidence import redact
from .research import _text

REVERSE_INPUT = {'type':'object','properties':{
    'attachment_id':{'type':'string','minLength':68,'maxLength':68},
    'provider':{'type':'string','enum':['google_vision','yandex_search']}},
    'required':['attachment_id','provider'],'additionalProperties':False}
KEYS = {'google_vision':'google_vision_api_key','yandex_search':'yandex_search_api_key','mapillary':'mapillary_token'}


def availability(getter):
    return [{'provider':provider,'state':'configured_not_tested' if getter(name) and
        (provider!='yandex_search' or getter('yandex_folder_id')) else 'optional_unconfigured',
        'image_upload_requires_consent':provider!='mapillary','execution_verified':False}
        for provider,name in KEYS.items()]


def _url(value):
    try:return public_url(value) if isinstance(value,str) else ''
    except PageReadError:return ''


async def _json_request(method, endpoint, *, headers, payload=None, params=None, client_factory=None):
    async with (client_factory or httpx.AsyncClient)(timeout=httpx.Timeout(20,connect=8),trust_env=False,follow_redirects=False) as client:
        async with client.stream(method,endpoint,headers={**headers,'User-Agent':'Granger-OSINT/3.1 (+https://github.com/watsoncore/Granger-OSINT)'},
            content=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None,params=params) as response:
            if response.status_code != 200:
                code={401:'http_401',402:'http_402',403:'http_403',429:'http_429'}.get(response.status_code,'provider_unavailable')
                raise _FetchError(code,status='rate_limited' if response.status_code==429 else 'unavailable',http_status=response.status_code)
            body=bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body)>1_000_000:raise _FetchError('api_response_limit')
        try:
            data=json.loads(body)
            if not isinstance(data,dict) or data.get('error'):raise ValueError()
        except (ValueError,UnicodeError):raise _FetchError('invalid_api_response') from None
        return data


def reverse(args, *, store, getter, approved=False, cancel_event=None, deadline=None, client_factory=None):
    provider=args['provider']
    if not approved:
        return {'status':'approval_required','error_code':'image_upload_consent_required','results':[],
            'limitations':['Передача фотографии '+provider+' требует отдельного разрешения; ключ не является разрешением.']}
    key=getter(KEYS[provider])
    folder=getter('yandex_folder_id') if provider=='yandex_search' else ''
    if not key or provider=='yandex_search' and not folder:
        return {'status':'unavailable','error_code':'optional_credentials_missing','results':[]}
    raw=store.read_bytes(args['attachment_id'],cancel_event)
    if len(raw)>2_000_000:
        return {'status':'unavailable','error_code':'image_upload_size_limit','results':[],
            'limitations':['Для этого ограниченного API-запроса нужен исходный файл не более 2 МБ. Изображение не отправлено.']}
    encoded=base64.b64encode(raw).decode('ascii')
    if provider=='google_vision':
        endpoint='https://vision.googleapis.com/v1/images:annotate'
        payload={'requests':[{'image':{'content':encoded},'features':[{'type':'WEB_DETECTION','maxResults':10}]}]}
        headers={'X-Goog-Api-Key':key,'Content-Type':'application/json; charset=utf-8'}
    else:
        endpoint='https://searchapi.api.cloud.yandex.net/v2/image/search_by_image'
        payload={'folderId':folder,'data':encoded,'page':'0','familyMode':'FAMILY_MODE_MODERATE'}
        headers={'Authorization':'Api-Key '+key,'Content-Type':'application/json; charset=utf-8'}
    matches=[];entities=[];labels=[]
    try:
        result=_run(lambda:_json_request('POST',endpoint,headers=headers,payload=payload,client_factory=client_factory),
            cancel_event=cancel_event,deadline=deadline,timeout=25)
        if provider=='google_vision':
            responses=result.get('responses',[])
            response=responses[0] if responses and isinstance(responses[0],dict) else {}
            if response.get('error'):raise _FetchError('google_vision_response_error')
            data=response.get('webDetection',{})
            entities=[{'description':_text(row.get('description')),'entity_id':_text(row.get('entityId'),200),
                'raw_score':row.get('score'),'score_calibrated':False} for row in data.get('webEntities',[])[:20] if isinstance(row,dict)]
            labels=[_text(row.get('label')) for row in data.get('bestGuessLabels',[])[:10] if isinstance(row,dict)]
            for field,kind in (('fullMatchingImages','provider_reported_full_match'),('partialMatchingImages','provider_reported_partial_match'),
                    ('visuallySimilarImages','visually_similar')):
                for row in data.get(field,[])[:10]:
                    if url:=_url(row.get('url')):matches.append({'image_url':url,'match_kind':kind})
            for row in data.get('pagesWithMatchingImages',[])[:10]:
                if url:=_url(row.get('url')):matches.append({'source_url':url,'title':_text(row.get('pageTitle')),
                    'match_kind':'page_with_provider_reported_image_match'})
        else:
            for row in result.get('images',[])[:20]:
                if image:=_url(row.get('url')):matches.append({'image_url':image,'source_url':_url(row.get('pageUrl')),
                    'title':_text(row.get('pageTitle')),'description':_text(row.get('passage')),'match_kind':'visually_similar'})
        details={'tool':'image_reverse_search','provider':provider,'attachment_id':args['attachment_id'],'image_uploaded':True,
            'submitted_sha256':hashlib.sha256(raw).hexdigest(),'matches':matches,'web_entities':entities,'best_guess_labels':labels,'geolocation_verified':False,
            'limitations':['Результаты API — указатели. Даже совпадение картинки не устанавливает координаты без проверки первичного источника.']}
        return redact({'status':'complete' if matches else 'empty','results':[{'id':'image_reverse_search:'+provider+':'+args['attachment_id'],
            'type':'image_research','platform':provider,'title':'Поиск по изображению · '+provider,'url':'',
            'description':'Получены реальные указатели официального API; координаты не подтверждены.',
            'status':'unconfirmed','details':details,'sources':['image_reverse_search']}], 'limitations':details['limitations']}, (key,))
    except _FetchError as error:
        return {'status':error.status,'error_code':error.code,'http_status':error.http_status,'results':[],
            'limitations':['Официальный API не завершил запрос; результат не выдан за успешный.']}


def yandex_text(query, *, getter, cancel_event=None, deadline=None, client_factory=None):
    """Official text-to-image endpoint; conservative parsing of variable XML."""
    key,folder=getter('yandex_search_api_key'),getter('yandex_folder_id')
    if not key or not folder:return {'status':'optional_unconfigured','images':[]}
    try:
        payload={'folderId':folder,'query':{'queryText':query[:400],'searchType':'SEARCH_TYPE_RU',
            'familyMode':'FAMILY_MODE_MODERATE','page':'0'},'docsOnPage':'4'}
        result=_run(lambda:_json_request('POST','https://searchapi.api.cloud.yandex.net/v2/image/search',
            headers={'Authorization':'Api-Key '+key,'Content-Type':'application/json; charset=utf-8'},
            payload=payload,client_factory=client_factory),cancel_event=cancel_event,deadline=deadline,timeout=25)
        raw=base64.b64decode(result.get('rawData',''),validate=True)
        if not raw or len(raw)>512_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise _FetchError('unsafe_or_missing_yandex_xml')
        from xml.etree import ElementTree
        root=ElementTree.fromstring(raw.decode('utf-8'))
        if sum(1 for _ in root.iter())>20_000:raise _FetchError('yandex_xml_node_limit')
        images=[]
        for doc in root.iter('doc'):
            fields={element.tag:_text(element.text) for element in doc.iter() if element.text and element.text.strip()}
            page=_url(fields.get('url'))
            title=fields.get('title','')
            # The provider documents no mandatory XML fields. A URL becomes an
            # image candidate only when explicitly returned as image-url data;
            # unknown fields are not assigned invented semantics.
            image=next((_url(fields[name]) for name in ('image-url','image_url','imageurl','imgurl') if _url(fields.get(name))), '')
            if image:
                images.append({'provider':'Yandex Search API','title':title,'image_url':image,'source_url':page,
                    'original_image_url':image,'license':'not_provided','author':'not_provided',
                    'match_kind':'text_search_reference_not_verified_match'})
        return redact({'status':'complete' if images else 'unavailable','images':images[:4],
            **({'error_code':'no_unambiguous_image_fields_in_xml'} if not images else {})}, (key,))
    except _FetchError as error:
        return {'status':error.status,'error_code':error.code,'http_status':error.http_status,'images':[]}
    except (ValueError,KeyError,TypeError,SyntaxError):
        return {'status':'unavailable','error_code':'invalid_yandex_image_xml','images':[]}


def mapillary(candidate, count, *, getter, cancel_event=None, deadline=None, client_factory=None):
    key=getter('mapillary_token')
    if not key:return {'status':'optional_unconfigured','images':[]}
    from ..integrations19.panoramax import bbox
    box=bbox({'latitude':candidate['latitude'],'longitude':candidate['longitude'],'radius_m':750})
    try:
        data=_run(lambda:_json_request('GET','https://graph.mapillary.com/images',headers={'Authorization':'OAuth '+key},
            params={'bbox':box,'limit':min(4,count),'fields':'id,thumb_1024_url,computed_geometry,captured_at,compass_angle,creator'},
            client_factory=client_factory),cancel_event=cancel_event,deadline=deadline,timeout=25)
        images=[]
        for row in data.get('data',[])[:count]:
            coords=(row.get('computed_geometry') or {}).get('coordinates',[])
            if not isinstance(coords,list) or len(coords)<2 or not _url(row.get('thumb_1024_url')):continue
            images.append({'provider':'Mapillary','title':'Mapillary '+str(row.get('id')),
                'source_url':'https://www.mapillary.com/app/?pKey='+str(row.get('id')),
                'image_url':row['thumb_1024_url'],'original_image_url':row['thumb_1024_url'],
                'latitude':coords[1],'longitude':coords[0],'captured_at_ms':row.get('captured_at'),
                'compass_angle':row.get('compass_angle'),'author':_text((row.get('creator') or {}).get('username')),
                'license':'Mapillary terms; verify original source','match_kind':'nearby_reference_not_verified_match'})
        return redact({'status':'complete','images':images}, (key,))
    except _FetchError as error:
        return {'status':error.status,'error_code':error.code,'http_status':error.http_status,'images':[]}
