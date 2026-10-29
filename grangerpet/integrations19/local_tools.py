"""No-key local capabilities from reviewed19-project audit.

No login, cookies, browser profile, web request or externalAI is used here.
The root registry owns invocation IDs/evidence and wraps these actual results.
"""
from __future__ import annotations
from datetime import datetime,timezone
import re
from urllib.parse import urlsplit
from .solar import LocalToolError,check,shadow_regions

INPUT_SCHEMAS={
 'tiktok_timestamp':{'type':'object','properties':{'value':{'type':'string','minLength':1,'maxLength':1000,'description':'Full TikTok /@user/video/decimalID URL or decimal videoID; no shortlinks.'}},'required':['value'],'additionalProperties':False},
 'shadow_regions':{'type':'object','properties':{
    'datetime_utc':{'type':'string','maxLength':40,'description':'KnownISO8601time withZ or explicitoffset; no assumedlocaltimezone.'},
    'object_height':{'type':'number','exclusiveMinimum':0,'maximum':1000000},'shadow_length':{'type':'number','exclusiveMinimum':0,'maximum':1000000},
    'sun_altitude_deg':{'type':'number','minimum':.1,'maximum':89.9},'tolerance_fraction':{'type':'number','minimum':.001,'maximum':.5},
    'grid_step_deg':{'type':'number','minimum':.5,'maximum':10},'bounds':{'type':'array','minItems':4,'maxItems':4,'items':{'type':'number'}},
    'max_cells':{'type':'integer','minimum':1,'maximum':2000},'candidates':{'type':'array','maxItems':100,'items':{'type':'object','properties':{'latitude':{'type':'number','minimum':-90,'maximum':90},'longitude':{'type':'number','minimum':-180,'maximum':180},'label':{'type':'string','maxLength':150}},'required':['latitude','longitude'],'additionalProperties':False}}},'required':['datetime_utc'],'additionalProperties':False},
 'role_classify':{'type':'object','properties':{'titles':{'type':'array','minItems':1,'maxItems':100,'items':{'type':'string','minLength':1,'maxLength':256}}},'required':['titles'],'additionalProperties':False}}

def tiktok_timestamp(value,*,cancel_event=None,deadline=None):
    check(cancel_event,deadline)
    if not isinstance(value,str) or not value or len(value)>1000 or value!=value.strip():raise LocalToolError('invalid_arguments','Нужен полныйURLвидео TikTok или числовойvideoID.')
    source_url=''
    if re.fullmatch(r'[0-9]{18,20}',value):identifier=value
    else:
        try:
            parsed=urlsplit(value)
            if parsed.scheme!='https' or parsed.hostname not in ('www.tiktok.com','tiktok.com','m.tiktok.com') or parsed.username or parsed.password or parsed.port:
                raise ValueError()
            match=re.fullmatch(r'/@([A-Za-z0-9_.]{1,64})/video/([0-9]{18,20})/?',parsed.path)
            if not match:raise ValueError()
            identifier=match.group(2);source_url='https://www.tiktok.com/@'+match.group(1)+'/video/'+identifier
        except ValueError:raise LocalToolError('invalid_arguments','Поддерживается полный tiktok.com/@user/video/ID. Сокращённые URL не раскрываются автоматически.') from None
    number=int(identifier)
    if not 0<number<2**63 or number.bit_length()!=63:raise LocalToolError('invalid_arguments','videoID не соответствует поддержанному63-значимому-битовому формату до2038года.')
    # This is exactly the upstream algorithm: first31 significant binary bits,
    # not a float conversion (which would lose precision for19-digit IDs).
    timestamp=int(bin(number)[2:][:31],2)
    if not 1420070400<=timestamp<=int(datetime.now(timezone.utc).timestamp())+86400:
        raise LocalToolError('invalid_arguments','Из ID получается неправдоподобное время для TikTok-видео.')
    date=datetime.fromtimestamp(timestamp,timezone.utc)
    return {'tool':'tiktok_timestamp','status':'complete','execution_mode':'LOCAL_PYTHON','video_id':identifier,
        'timestamp_unix':timestamp,'date_utc':date.isoformat().replace('+00:00','Z'),'human_date_utc':date.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'source_url':source_url,'method':'Bellingcat TikTok Date Extract: first31 significantbits of videoID',
        'upstream_url':'https://github.com/bellingcat/tiktok-timestamp','network_requests':0,
        'warnings':['Это время, кодируемое поддержанным форматом ID, не независимо подтверждённый факт публикации.',
         'Существование видео, автор и содержимое не проверены. Новые форматыIDмогут иметь другие свойства.']}

def role_classify(titles,*,cancel_event=None,deadline=None):
    check(cancel_event,deadline)
    if not isinstance(titles,list) or not 1<=len(titles)<=100 or any(not isinstance(v,str) or not v.strip() or len(v)>256 for v in titles):
        raise LocalToolError('invalid_arguments','Укажите1–100 непустых должностей, максимум256символов каждая.')
    from ._role_classifier import classify_title
    rows=[]
    for index,title in enumerate(titles):
        check(cancel_event,deadline)
        result=classify_title(title)
        rows.append({'input_index':index,'title':title,**result})
    return {'tool':'role_classify','status':'complete','execution_mode':'LOCAL_PYTHON','results':rows,
        'upstream_url':'https://github.com/michaelelizarov/linkedin-osint-toolkit','network_requests':0,
        'warnings':['Классификация по английским ключевым словам — эвристика по уже полученному тексту, не проверка трудоустройства или реальной иерархии.',
         'СборLinkedIn,логин,stealth,GroqAIиоргструктураконкретнойкомпании не выполняются. Неизвестные/неанглийские должности могут попасть вобщийStaff/General.']}

def readiness(tool,settings=None):
    if tool not in INPUT_SCHEMAS:return {'available':False,'state':'unsupported','reason':'Неизвестная локальная операция.'}
    return {'available':True,'state':'ready','reason':'Локальный вычислительный модуль со стандартной библиотекой; сеть и персональные ключи не нужны.'}

def execute(tool,args,*,cancel_event=None,deadline=None,settings=None,**kwargs):
    if not isinstance(args,dict):raise LocalToolError('invalid_arguments','Параметры должны бытьJSONобъектом.')
    if tool=='shadow_regions':return shadow_regions(args,cancel_event=cancel_event,deadline=deadline)
    if tool=='tiktok_timestamp' and set(args)=={'value'}:return tiktok_timestamp(args['value'],cancel_event=cancel_event,deadline=deadline)
    if tool=='role_classify' and set(args)=={'titles'}:return role_classify(args['titles'],cancel_event=cancel_event,deadline=deadline)
    raise LocalToolError('invalid_arguments','Неизвестная операция или поля параметров.')
