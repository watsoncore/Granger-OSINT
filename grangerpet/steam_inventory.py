"""Passive, bounded public inventory pages. No login, trades or inspect execution."""
from collections import Counter
from decimal import Decimal,InvalidOperation
from html.parser import HTMLParser
import json
import hashlib
import re
import time
import httpx
import httpcore
from urllib.parse import quote,urlsplit

INPUT_SCHEMA={'type':'object','properties':{
    'profile':{'type':'string','minLength':1,'maxLength':300},
    'appid':{'type':'integer','minimum':1,'maximum':2147483647},
    'contextid':{'type':'string','minLength':1,'maxLength':20},
    'cursor':{'type':'string','minLength':1,'maxLength':30},
    'max_pages':{'type':'integer','minimum':1,'maximum':10},
    'page_size':{'type':'integer','minimum':10,'maximum':200},
    'price_limit':{'type':'integer','minimum':0,'maximum':5}},
    'required':['profile'],'additionalProperties':False}


class _Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,text):self.parts.append(text)


def plain(value,limit=1600):
    if not isinstance(value,str):return ''
    parser=_Text();parser.feed(value[:12000]);return ' '.join(' '.join(parser.parts).split())[:limit]


def validate(args):
    from .tool_inputs import validate_object
    from .steam_public import normalize
    value=validate_object(args,INPUT_SCHEMA)
    identity,url=normalize(value['profile'],allow_inventory=True)
    value['profile']=identity.steamid64 if identity else url
    for key,default in (('appid',730),('contextid','2'),('max_pages',3),('page_size',100),('price_limit',3)):
        value.setdefault(key,default)
    for field in ('contextid','cursor'):
        if field in value and not re.fullmatch(r'[1-9]\d{0,29}',value[field]):raise ValueError('Invalid inventory context or cursor')
    return value


def _id(value):
    return str(value) if type(value) in (int,str) and re.fullmatch(r'\d{1,30}',str(value)) else None


def parse_page(payload,*,steamid,appid,contextid):
    if (not isinstance(payload,dict) or payload.get('success') not in (1,True) or
        not isinstance(payload.get('assets'),list) or not isinstance(payload.get('descriptions'),list)):
        raise ValueError('Invalid public inventory schema')
    if len(payload['assets'])>200 or len(payload['descriptions'])>1000:raise ValueError('Inventory page limit exceeded')
    descriptions={}
    for row in payload['descriptions']:
        if not isinstance(row,dict):raise ValueError('Invalid item description')
        if row.get('appid')!=appid:raise ValueError('Mismatched description app')
        classid,instanceid=_id(row.get('classid')),_id(row.get('instanceid'))
        if classid is None or instanceid is None:raise ValueError('Missing description identity')
        descriptions[classid,instanceid]=row
    properties={}
    for row in payload.get('asset_properties',[]) if isinstance(payload.get('asset_properties'),list) else []:
        if not isinstance(row,dict) or row.get('appid')!=appid or str(row.get('contextid'))!=contextid:continue
        assetid=_id(row.get('assetid'))
        if assetid:
            properties[assetid]=[{key:item[key] for key in ('propertyid','name','int_value','float_value','string_value')
                if key in item and type(item[key]) in (int,float,str) and len(str(item[key]))<=512}
                for item in row.get('asset_properties',[])[:30] if isinstance(item,dict)]
    items=[];seen=set()
    for asset in payload['assets']:
        if not isinstance(asset,dict) or asset.get('appid')!=appid or str(asset.get('contextid'))!=contextid:
            raise ValueError('Mismatched inventory asset scope')
        assetid,classid,instanceid=(_id(asset.get(key)) for key in ('assetid','classid','instanceid'))
        amount=_id(asset.get('amount'))
        if assetid is None or classid is None or instanceid is None or amount is None or int(amount)<=0:raise ValueError('Invalid asset identity')
        if assetid in seen:continue
        seen.add(assetid);description=descriptions.get((classid,instanceid),{})
        tags=[{key:str(tag[key])[:200] for key in ('category','internal_name','localized_category_name','localized_tag_name','color') if key in tag}
              for tag in description.get('tags',[])[:30] if isinstance(tag,dict)]
        tagmap={tag.get('category'):tag.get('localized_tag_name') or tag.get('internal_name') for tag in tags}
        icon=description.get('icon_url')
        image='https://community.fastly.steamstatic.com/economy/image/'+icon+'/256fx256f' if isinstance(icon,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,1000}',icon) else None
        observed=properties.get(assetid,[])
        float_value=next((row.get('float_value') for row in observed if row.get('name')=='Wear Rating'),None)
        pattern=next((row.get('int_value') for row in observed if row.get('name')=='Pattern Template'),None)
        items.append({'steamid64':steamid,'appid':appid,'contextid':contextid,'assetid':assetid,'classid':classid,'instanceid':instanceid,
            'amount':amount,'name':plain(description.get('name'),300) or None,
            'market_hash_name':plain(description.get('market_hash_name'),300) or None,
            'description':' '.join(plain(row.get('value'),1200) for row in description.get('descriptions',[])[:15] if isinstance(row,dict))[:2400],
            'type':plain(description.get('type'),200) or None,'tags':tags,
            'category':tagmap.get('Type') or 'Не классифицировано','rarity':tagmap.get('Rarity'),
            'quality':tagmap.get('Quality'),'exterior':tagmap.get('Exterior'),
            'tradable':bool(description['tradable']) if type(description.get('tradable')) is int else None,
            'marketable':bool(description['marketable']) if type(description.get('marketable')) is int else None,
            'image_url':image,'image_attribution':'Steam / Valve; ссылка на публичное изображение предмета, не свободная лицензия',
            'observed_properties':observed,'float_value':float_value,'pattern_template':pattern,
            'stickers':None,'price':None,'description_observed':bool(description)})
    total=payload.get('total_inventory_count')
    if type(total) is not int or not 0<=total<=10_000_000:total=None
    more=payload.get('more_items') in (1,True)
    cursor=_id(payload.get('last_assetid')) if more else None
    if more and not cursor:raise ValueError('Missing inventory continuation cursor')
    return {'items':items,'reported_total':total,'more_items':more,'next_cursor':cursor}


def parse_price(payload,*,name,endpoint,observed_at):
    if not isinstance(payload,dict) or payload.get('success') is not True:return None
    raw=payload.get('lowest_price');amount=None
    if isinstance(raw,str) and re.fullmatch(r'\$\s*[\d,]+(?:\.\d{1,2})?(?:\s*USD)?',raw):
        try:amount=str(Decimal(raw.replace('$','').replace(',','').replace('USD','').strip()))
        except InvalidOperation:pass
    return {'market_hash_name':name,'currency':'USD','currency_id':1,'lowest_price':raw if isinstance(raw,str) else None,
        'amount_decimal':amount,'median_price':payload.get('median_price') if isinstance(payload.get('median_price'),str) else None,
        'volume':payload.get('volume') if isinstance(payload.get('volume'),str) else None,
        'source_url':endpoint,'observed_at':observed_at,'method':'public_market_lowest_listing',
        'limitations':'Цена лота Market, не оценка редкости pattern/float/наклеек и не гарантированная цена продажи.'}


async def collect(args,*,deadline,cancel_event=None,client_factory=None,resolver=None,on_page=None):
    from .steam_public import normalize,collect as profile_collect
    from .web_http import fetch_public
    from .agent_browser import PublicPageReader,PageReadError
    from .agent_web import _record,_envelope,_utc
    args=validate(args);identity,profile=normalize(args['profile'])
    reader=PublicPageReader(respect_robots=client_factory is None)
    async def get(url):
        try:
            result=await fetch_public(url,deadline=deadline,cancel_event=cancel_event,client_factory=client_factory,resolver=resolver,
                rate_interval=1,allowed_types=('application/json','text/json'),accepted_statuses=(200,401,403,404,429,500,502,503),
                before_request=(lambda target:reader._check_robots(target,cancel_event,deadline)) if client_factory is None else None)
        except (httpx.HTTPError,httpcore.NetworkError,OSError,TimeoutError) as error:
            raise PageReadError('steam_source_timeout' if isinstance(error,(TimeoutError,httpx.TimeoutException)) else 'steam_source_network',
                                'timeout' if isinstance(error,(TimeoutError,httpx.TimeoutException)) else 'unavailable') from None
        if urlsplit(result['final_url']).hostname!='steamcommunity.com':raise PageReadError('unexpected_steam_origin','blocked')
        if result['status']!=200:
            error=PageReadError('steam_inventory_http_'+str(result['status']),
                'rate_limited' if result['status']==429 else 'auth_required' if result['status']==401 else 'blocked' if result['status']==403 else 'unavailable')
            retry=result.get('headers',{}).get('retry-after','')
            error.retry_after_seconds=min(86400,max(60,int(retry))) if str(retry).isdigit() and len(str(retry))<8 else 60
            raise error
        return result,json.loads(result['body'].decode('utf-8-sig'))
    if identity is None:
        resolved=await profile_collect('steam_profile',args['profile'],deadline=deadline,cancel_event=cancel_event,client_factory=client_factory,resolver=resolver)
        identity,_=normalize(resolved['results'][0]['details']['steamid64'])
    steamid=identity.steamid64;appid=args['appid'];context=args['contextid'];base=f'https://steamcommunity.com/inventory/{steamid}/{appid}/{context}'
    items={};pages=[];seen_cursors=set();cursor=args.get('cursor');total=None;more=True;stop='page_limit';failures=[]
    for index in range(args['max_pages']):
        if cancel_event and cancel_event.is_set():stop='cancelled';break
        if time.monotonic()>=deadline:stop='timeout';break
        if cursor in seen_cursors:stop='repeated_cursor';break
        seen_cursors.add(cursor)
        endpoint=base+'?l=english&count='+str(args['page_size'])+('&start_assetid='+cursor if cursor else '')
        try:
            response,payload=await get(endpoint)
            if isinstance(payload,dict) and not payload.get('success') and re.search(r'(?i)private',str(payload.get('Error') or payload.get('error') or '')):
                raise PageReadError('private_steam_inventory','blocked')
            page=parse_page(payload,steamid=steamid,appid=appid,contextid=context)
        except (PageReadError,ValueError,UnicodeError) as error:
            stop=error.code if isinstance(error,PageReadError) else 'inventory_schema_drift'
            failures.append({'endpoint':endpoint,'status':getattr(error,'status','error'),'error_code':stop,
                'retry_after_seconds':getattr(error,'retry_after_seconds',None)});break
        if total is not None and page['reported_total'] is not None and total!=page['reported_total']:failures.append({'error_code':'inventory_count_changed'})
        total=page['reported_total'] if page['reported_total'] is not None else total
        added=0;observed_at=_utc()
        for item in page['items']:
            item.update(source_endpoint=response['final_url'],inventory_observed_at=observed_at)
            if item['assetid'] not in items:items[item['assetid']]=item;added+=1
        pages.append({'endpoint':response['final_url'],'http_status':response['status'],'observed_at':observed_at,
            'body_sha256':hashlib.sha256(response['body']).hexdigest(),'response_bytes':len(response['body']),
            'returned_assets':len(page['items']),'new_assets':added,'reported_total':page['reported_total'],
            'cursor':cursor,'next_cursor':page['next_cursor']})
        cursor=page['next_cursor'];more=page['more_items']
        if on_page:on_page(_inventory_outcome(args,identity,profile,items,pages,cursor,total,more,'in_progress',failures,False))
        if not more:stop='exhausted';break
        if not added:stop='no_new_assets';break
    complete=stop=='exhausted' and not args.get('cursor') and total is not None and len(items)==total and not failures
    prices={}
    for item in items.values():
        if len(prices)>=args['price_limit'] or cancel_event and cancel_event.is_set():break
        name=item.get('market_hash_name')
        if not name or not item.get('marketable') or name in prices:continue
        endpoint=f'https://steamcommunity.com/market/priceoverview/?appid={appid}&currency=1&l=english&market_hash_name='+quote(name,safe='')
        try:
            response,payload=await get(endpoint);price=parse_price(payload,name=name,endpoint=response['final_url'],observed_at=_utc())
            prices[name]=price
        except (PageReadError,ValueError,UnicodeError) as error:
            failures.append({'stage':'price','error_code':getattr(error,'code','price_schema_drift'),
                'retry_after_seconds':getattr(error,'retry_after_seconds',None)});break
    for item in items.values():item['price']=prices.get(item.get('market_hash_name'))
    return _inventory_outcome(args,identity,profile,items,pages,cursor,total,more,stop,failures,complete)


def _inventory_outcome(args,identity,profile,items,pages,cursor,total,more,stop,failures,complete):
    from .agent_web import _record,_envelope
    steamid=identity.steamid64;appid=args['appid'];context=args['contextid']
    records=[];canonical=identity.profile_url
    for item in items.values():
        price=item.get('price');name=item['name'] or 'Предмет '+item['assetid']
        text=name+' · '+str(item['category'])+' · '+str(item['exterior'] or 'состояние не указано')
        if price and price.get('amount_decimal'):text+=' · публичная цена лота '+price['amount_decimal']+' USD'
        row=_record('steam',steamid,name,canonical+'/inventory/#'+str(appid)+'_'+context+'_'+item['assetid'],text,
            kind='steam_item',details={**item,'capability':'steam_inventory','canonical_url':canonical,
                'operation':'steam_inventory',
                'ownership_verified':False,'observation_basis':'public_inventory_response_not_real_world_identity'})
        row['id']='steam_item:'+steamid+':'+str(appid)+':'+context+':'+item['assetid'];records.append(row)
    coverage={'observed_assets':len(items),'reported_total':total,'starts_at_cursor':args.get('cursor'),
        'next_cursor':cursor,'more_items':more,'stop_reason':stop,'pages':pages,'all_items_observed_in_this_call':complete,
        'inventory_may_change_during_pagination':True,'counts_are_not_item_data':False}
    summary=_record('steam',steamid,'Steam · публичный инвентарь',canonical+'/inventory/',
        f'Получены данные {len(items)} предметов из {total if total is not None else "неизвестного общего числа"}. Стоп: {stop}.',
        kind='steam_inventory',details={'capability':'steam_inventory','operation':'steam_inventory','steamid64':steamid,
            'appid':appid,'contextid':context,'canonical_url':canonical,'requested_profile':profile,'coverage':coverage,
            'categories':dict(Counter(item['category'] for item in items.values())),'source_failures':failures,
            'prices_observed':len({item.get('market_hash_name') for item in items.values() if item.get('price') and item['price'].get('amount_decimal')}),
            'price_coverage':'Частичная оценка только фактически полученных публичных Market quotes; неизвестная цена не равна нулю.'})
    summary['id']='steam_inventory:'+steamid+':'+str(appid)+':'+context+':'+str(args.get('cursor') or 'start')
    if pages:records.insert(0,summary)
    status='complete' if complete else 'partial' if items else failures[0].get('status','unavailable') if failures else 'empty'
    return _envelope('steam_inventory',args['profile'],status=status,results=records,
        limitations=['Инвентарь — наблюдение публичного ответа, не доказательство личности владельца. Float/pattern только из asset_properties; наклейки и редкость не угадываются.',
                    'Цена Market может не учитывать pattern/float/наклейки; оценена только явно указанная часть.'])
