"""Small documented key-free DEM / historical / regional catalogue queries."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime,timezone
import asyncio
import hashlib
import json
import threading
import time
from urllib.parse import urlencode,urlsplit

from .images import GeointError
from .terrain import sample_points,dem_geometry

_LOCK=threading.RLock();_CACHE=OrderedDict();_COOLDOWN={}
DEM='https://api.opentopodata.org/v1/srtm90m'
OHM='https://overpass-api.openhistoricalmap.org/api/interpreter'
SWISS='https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.swissalti3d'


class OpenGeography:
    def __init__(self,requester=None):self.requester=requester or self.request

    @staticmethod
    def request(endpoint,params,cancel=None,deadline=None):
        from ..web_http import fetch_public
        from ..agent_browser import PageReadError
        key=endpoint+'?'+urlencode(params);host=urlsplit(endpoint).hostname
        with _LOCK:
            cached=_CACHE.get(key)
            if cached and time.monotonic()-cached[0]<86400:
                value,receipt=deepcopy(cached[1]);receipt['cache_hit']=True;return value,receipt
            if _COOLDOWN.get(host,0)>time.monotonic():raise GeointError('rate_limited','Источник просил отложить следующие запросы.')
        try:
            response=asyncio.run(fetch_public(endpoint,params=params,cancel_event=cancel,
                deadline=min(deadline or time.monotonic()+18,time.monotonic()+18),
                allowed_types=('application/json','application/geo+json','text/json'),rate_interval=1.1,
                accepted_statuses=(200,403,429,500,502,503,504)))
        except PageReadError as error:raise GeointError(error.code,'Публичный геоисточник не завершил запрос.') from None
        if response['status']!=200:
            if response['status'] in (403,429):
                delay=response.get('headers',{}).get('retry-after','')
                seconds=max(60,min(86400,int(delay))) if str(delay).isdigit() and len(str(delay))<8 else 3600
                with _LOCK:_COOLDOWN[host]=time.monotonic()+seconds
            raise GeointError('http_'+str(response['status']),'Публичный геоисточник отклонил запрос.')
        if len(response['body'])>1_000_000:raise GeointError('geo_response_limit','Геоответ превысил лимит размера.')
        try:value=json.loads(response['body'])
        except (ValueError,UnicodeError):raise GeointError('invalid_geo_json','Геоисточник вернул некорректный JSON.') from None
        if not isinstance(value,dict):raise GeointError('invalid_geo_schema','Неверная схема геоисточника.')
        receipt={'url':response['final_url'],'http_status':response['status'],'source_observed_at':datetime.now(timezone.utc).isoformat(),
            'body_sha256':hashlib.sha256(response['body']).hexdigest(),'response_bytes':len(response['body']),'cache_hit':False}
        with _LOCK:
            _CACHE[key]=(time.monotonic(),deepcopy((value,receipt)))
            while len(_CACHE)>96:_CACHE.popitem(last=False)
        return value,receipt

    def terrain(self,candidate,cancel=None,deadline=None):
        points=sample_points(candidate['latitude'],candidate['longitude'])
        values=[];receipts=[]
        # Keep each encoded URL within the transport's unchanged 2,000-byte limit.
        for index in range(0,len(points),49):
            value,receipt=self.requester(DEM,{'locations':'|'.join(f"{p['latitude']},{p['longitude']}" for p in points[index:index+49]),'interpolation':'bilinear'},cancel,deadline)
            if not isinstance(value,dict) or value.get('status')!='OK' or not isinstance(value.get('results'),list):raise ValueError('invalid_dem_response')
            values.extend(value['results']);receipts.append(receipt)
        return {**dem_geometry(points,{'status':'OK','results':values}),'source':'OpenTopoData SRTM90','source_url':receipts[0]['url'],'receipts':receipts,
            'dataset_documentation':'https://www.opentopodata.org/datasets/srtm/','attribution':'SRTM v3 / USGS, API OpenTopoData',
            'access_policy':'https://www.opentopodata.org/#public-api','image_uploaded':False}

    def historical(self,candidate,cancel=None,deadline=None):
        lat,lon=candidate['latitude'],candidate['longitude']
        query=f'[out:json][timeout:8][maxsize:500000];nwr(around:2000,{lat:.5f},{lon:.5f})["name"]["start_date"];out center 20;'
        value,receipt=self.requester(OHM,{'data':query},cancel,deadline)
        if not isinstance(value.get('elements'),list):raise ValueError('invalid_historical_response')
        rows=[]
        for item in value['elements'][:20]:
            if not isinstance(item,dict) or item.get('type') not in ('node','way','relation') or type(item.get('id')) is not int:continue
            tags=item.get('tags');tags=tags if isinstance(tags,dict) else {};position=item.get('center') or item
            if not isinstance(position,dict):continue
            rows.append({'name':str(tags.get('name') or '')[:200],'start_date':tags.get('start_date'),'end_date':tags.get('end_date'),
                'source':tags.get('source'),'license':tags.get('license') or 'CC0 except where otherwise noted',
                'latitude':position.get('lat'),'longitude':position.get('lon'),
                'url':f"https://www.openhistoricalmap.org/{item['type']}/{item['id']}"})
        return {'source':'OpenHistoricalMap','source_url':receipt['url'],'receipt':receipt,'features':rows,'feature_count':len(rows),
            'license_url':'https://www.openhistoricalmap.org/copyright/en','attribution':'OpenHistoricalMap contributors; individual feature source/license retained',
            'limitations':['Исторические объекты не датируют исходную фотографию. Пустой ответ не означает отсутствие истории.']}

    def regional(self,candidate,cancel=None,deadline=None):
        lat,lon=candidate['latitude'],candidate['longitude']
        if not (45.72<=lat<=47.83 and 5.95<=lon<=10.5):return {'status':'not_applicable','source':'swisstopo','reason':'outside_Switzerland_Liechtenstein_coverage'}
        collection,receipt=self.requester(SWISS,{},cancel,deadline)
        if collection.get('id')!='ch.swisstopo.swissalti3d':raise ValueError('invalid_regional_collection')
        params={'bbox':f'{lon-.002},{lat-.002},{lon+.002},{lat+.002}','limit':2}
        value,item_receipt=self.requester(SWISS+'/items',params,cancel,deadline)
        if not isinstance(value.get('features'),list):raise ValueError('invalid_regional_items')
        return {'source':'swisstopo swissALTI3D STAC','source_url':item_receipt['url'],'receipt':item_receipt,
            'collection_receipt':receipt,'collection_license':collection.get('license'),'title':collection.get('title'),
            'summaries':collection.get('summaries'),'item_count_returned':len(value['features']),'assets_downloaded':False,
            'items':[{'id':item.get('id'),'bbox':item.get('bbox'),'datetime':item.get('properties',{}).get('datetime')} for item in value['features'][:2] if isinstance(item,dict)],
            'documentation':'https://docs.geo.admin.ch/download-data/stac-api/overview.html',
            'limitations':['Каталог DEM-покрытия; большие растры/тайлы не загружаются. Применяются условия конкретного набора.',
                'Наличие DEM-тайла не подтверждает место исходной фотографии.']}
