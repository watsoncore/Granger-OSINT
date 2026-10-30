"""Bounded geographic research from saved pixel/model observations.

Public queries never upload the user's photograph. Archive coordinates belong
to reference photographs, not automatically to the original. Scores are not
calibrated geographic probabilities. Full records persist in existing evidence.
"""
from copy import deepcopy
from datetime import datetime, timezone
import asyncio
import hashlib
import html
import json
import math
import re
import time

from .mapping import MappingClient, OSM_ATTRIBUTION
from .images import GeointError
from ..agent_evidence import current_observation, normalize_evidence
from ..public_media import MediaStore, media_reference
from ..visual_models.pipeline import haversine_km

INPUT_SCHEMA = {'type':'object','properties':{
    'attachment_id':{'type':'string','minLength':68,'maxLength':68},
    'max_candidates':{'type':'integer','minimum':1,'maximum':3},
    'references_per_candidate':{'type':'integer','minimum':1,'maximum':4},
    'compare':{'type':'boolean'}},'required':['attachment_id'],'additionalProperties':False}


def _text(value, limit=1200):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))).strip()[:limit]


def hypotheses(records, attachment_id, maximum=3):
    points = []
    for original in records:
        row = current_observation(original)
        details = row.get('details') or {}
        if details.get('attachment_id') != attachment_id:
            continue
        values = details.get('predictions', [])
        for rank, item in enumerate(values if isinstance(values, list) else []):
            if not isinstance(item, dict):
                continue
            lat, lon = item.get('lat',item.get('latitude')), item.get('lon',item.get('longitude'))
            if (type(lat) not in (int,float) or type(lon) not in (int,float) or not math.isfinite(lat+lon)
                    or not -90 <= lat <= 90 or not -180 <= lon <= 180):
                continue
            points.append({'latitude':lat, 'longitude':lon, 'rank':rank+1,
                'source_model':details.get('model_version') or row.get('platform'), 'raw_score':item.get('raw_score'),
                'evidence_id':row.get('evidence_id'), 'source_kind':'model_candidate',
                'model_lat_std':item.get('lat_std'),'model_lon_std':item.get('lon_std'),
                'dateline_warning':item.get('dateline_warning',False)})
        gps = (details.get('metadata') or {}).get('gps') if isinstance(details.get('metadata'),dict) else None
        if isinstance(gps, dict):
            lat, lon = gps.get('latitude'), gps.get('longitude')
            if type(lat) in (int,float) and type(lon) in (int,float) and -90 <= lat <= 90 and -180 <= lon <= 180:
                points.append({'latitude':lat,'longitude':lon,'rank':0,'source_model':'EXIF GPS (authenticity unverified)',
                    'evidence_id':row.get('evidence_id'),'source_kind':'metadata_candidate','raw_score':None})
    points.sort(key=lambda value:value['rank'])
    candidates = []
    for point in points:
        nearby = next((candidate for candidate in candidates if haversine_km(
            [point['latitude'],point['longitude']], [candidate['latitude'],candidate['longitude']]) < 2), None)
        if nearby:
            nearby['model_observations'].append(point)
            continue
        if len(candidates) >= maximum:
            continue
        identifier = 'geo_'+hashlib.sha256((attachment_id+f"|{point['latitude']:.5f}|{point['longitude']:.5f}").encode()).hexdigest()[:24]
        candidates.append({'candidate_id':identifier, 'attachment_id':attachment_id, 'latitude':point['latitude'],
            'longitude':point['longitude'], 'source_model':point['source_model'], 'raw_score':point['raw_score'],
            'model_observations':[point], 'verification_status':'model_candidate' if point['source_kind']=='model_candidate' else 'metadata_candidate',
            'supporting_evidence':[point['evidence_id']], 'contradicting_evidence':[], 'nearby_landmarks':[],
            'reference_images':[], 'region':'', 'uncertainty_radius_m':None})
    return candidates


class ResearchSources:
    def __init__(self, maps=None, secret_getter=None):
        self.maps = maps or MappingClient()
        self.secret_getter = secret_getter or (lambda _: '')
        self.diagnostics=[]

    def optional(self):
        from .optional_apis import availability
        return availability(self.secret_getter)

    def mapillary(self,candidate,count,cancel,deadline):
        from .optional_apis import mapillary
        return mapillary(candidate,count,getter=self.secret_getter,cancel_event=cancel,deadline=deadline)

    def yandex_text(self,query,cancel,deadline):
        from .optional_apis import yandex_text
        return yandex_text(query,getter=self.secret_getter,cancel_event=cancel,deadline=deadline)

    def reverse(self, candidate, cancel):
        value, cached = self.maps._request(self.maps.nominatim_endpoint+'/reverse', {
            'lat':candidate['latitude'], 'lon':candidate['longitude'], 'format':'jsonv2',
            'zoom':16, 'addressdetails':1, 'namedetails':1, 'accept-language':'ru,en'}, cancel)
        if not isinstance(value,dict) or value.get('error'):
            raise GeointError('empty_geocoder', 'Местность кандидата не найдена геокодером.')
        return {'name':_text(value.get('display_name'),700), 'address':value.get('address',{}),
            'namedetails':value.get('namedetails',{}), 'source_url':f"https://www.openstreetmap.org/?mlat={candidate['latitude']}&mlon={candidate['longitude']}",
            'attribution':OSM_ATTRIBUTION, 'cached':cached}

    def landmarks(self, candidate, cancel):
        lat,lon=candidate['latitude'],candidate['longitude']
        region=f'(around:500,{lat:.7f},{lon:.7f})'
        query=f'[out:json][timeout:8][maxsize:1048576];(nwr{region}["name"]["historic"];nwr{region}["name"]["tourism"];nwr{region}["highway"="bus_stop"];way{region}["bridge"="yes"]["name"];);out center 30;'
        client=self.maps
        try:
            data,_=client._request(client.overpass_endpoint,{'data':query},cancel)
        except GeointError as error:
            self.diagnostics.append({'source':client.overpass_endpoint,'status':error.code})
            from .mapping import DEFAULT_OVERPASS
            if client.overpass_endpoint!=DEFAULT_OVERPASS or error.code not in ('timeout','service_unavailable','network_error'):
                raise
            client=MappingClient(overpass_endpoint='https://overpass.private.coffee/api/interpreter')
            data,_=client._request(client.overpass_endpoint,{'data':query},cancel)
        if not isinstance(data,dict) or not isinstance(data.get('elements'),list):
            raise GeointError('invalid_landmark_response','OSM не вернул список ориентиров.')
        rows=[]
        for item in data['elements'][:30]:
            tags=item.get('tags') or {};point=item.get('center') or item
            x,y=point.get('lat'),point.get('lon')
            if type(x) not in (float,int) or type(y) not in (float,int) or item.get('type') not in ('node','way','relation'):
                continue
            rows.append({'name':_text(tags.get('name') or tags.get('highway'),300),
                'names':{key:_text(value,300) for key,value in tags.items() if key in ('name','name:en','name:ru')},
                'latitude':x,'longitude':y,'url':f"https://www.openstreetmap.org/{item['type']}/{item['id']}",
                'tags':{key:_text(value,200) for key,value in tags.items() if key in ('historic','tourism','building','highway','bridge','amenity','natural')},
                'api_endpoint':client.overpass_endpoint,'distance_m':round(haversine_km([lat,lon],[x,y])*1000,1)})
        return sorted(rows,key=lambda row:row['distance_m'])

    def commons(self, candidate, queries, count, cancel):
        geo = self.maps.execute('map_wikimedia', f"{candidate['latitude']},{candidate['longitude']}", cancel)
        nearby = geo.get('media', [])
        selected = [row['page_id'] for row in nearby[:count]]
        params = {'action':'query','format':'json','prop':'imageinfo','iiprop':'url|size|mime|extmetadata',
            'iiurlwidth':640, 'iiextmetadatafilter':'ImageDescription|Artist|LicenseShortName|LicenseUrl|DateTimeOriginal|ObjectName'}
        if selected:
            params['pageids'] = '|'.join(map(str,selected))
        elif queries:
            params.update(generator='search', gsrsearch=queries[0]['query'], gsrnamespace=6, gsrlimit=count)
        else:
            return []
        data, _ = self.maps._request(self.maps.commons_endpoint, params, cancel)
        if not isinstance(data,dict) or data.get('error'):
            raise GeointError('invalid_commons_response','Commons не вернула metadata изображений.')
        output = []
        for page in data.get('query',{}).get('pages',{}).values():
            info = page.get('imageinfo', [])
            if not info or not isinstance(info[0],dict):
                continue
            info, metadata = info[0], info[0].get('extmetadata',{})
            if info.get('mime') not in ('image/jpeg','image/png','image/webp'):
                continue
            position = next((row for row in nearby if row['page_id']==page.get('pageid')), {})
            item = {'provider':'Wikimedia Commons','title':_text(page.get('title')), 'page_id':page.get('pageid'),
                'image_url':info.get('url') if type(info.get('size')) is int and info['size']<=2_000_000 else info.get('thumburl') or info.get('url'),
                'thumbnail_url':info.get('thumburl'), 'original_image_url':info.get('url'), 'original_bytes':info.get('size'),
                'source_url':info.get('descriptionurl') or position.get('url'),
                'description':_text((metadata.get('ImageDescription') or {}).get('value')),
                'author':_text((metadata.get('Artist') or {}).get('value'),400),
                'license':_text((metadata.get('LicenseShortName') or {}).get('value'),200),
                'license_url':_text((metadata.get('LicenseUrl') or {}).get('value'),500),
                'captured_at':_text((metadata.get('DateTimeOriginal') or {}).get('value'),100),
                'latitude':position.get('latitude'), 'longitude':position.get('longitude'),
                'distance_m':position.get('distance_m'), 'match_kind':'nearby_reference_not_verified_match'}
            if item['image_url'] and item['source_url']:
                output.append(item)
        return output[:count]

    def wikipedia(self, query, language, cancel):
        endpoint = f'https://{language}.wikipedia.org/w/api.php'
        data, _ = self.maps._request(endpoint, {'action':'query','format':'json', 'generator':'search',
            'gsrsearch':query,'gsrlimit':2,'prop':'extracts|coordinates|info','exintro':1,'explaintext':1,
            'exchars':2500,'inprop':'url'}, cancel)
        return [{'title':_text(row.get('title')), 'source_url':row.get('fullurl'),
            'description':_text(row.get('extract'),2500), 'coordinates':row.get('coordinates',[]),
            'language':language} for row in data.get('query',{}).get('pages',{}).values() if row.get('fullurl')]

    def panoramax(self, candidate, count, cancel, deadline):
        from ..integrations19.public_tools import execute
        result = execute('map_panoramax', {'latitude':candidate['latitude'],'longitude':candidate['longitude'],
            'radius_m':500,'limit':10}, cancel_event=cancel, deadline=deadline, settings=None, approved=False)
        if result.get('status') not in ('complete','partial','empty'):
            raise GeointError(str(result.get('error_code') or result.get('error') or 'panoramax_unavailable'), 'Panoramax не завершил поиск.')
        output = []
        for row in result.get('results',[]):
            details = row.get('details',{})
            media = details.get('media',[])
            image = next((asset.get('url') for asset in media if asset.get('kind')=='sd'), None) or next((asset.get('url') for asset in media),None)
            if image:
                output.append({'provider':'Panoramax','title':row['title'],'image_url':image,
                    'original_image_url':image,'source_url':row['url'], 'latitude':details.get('latitude'),
                    'longitude':details.get('longitude'),'captured_at':details.get('captured_at'),
                    'license':details.get('license'),'license_url':details.get('license_url'),'author':details.get('attribution'),
                    'match_kind':'nearby_reference_not_verified_match', 'distance_to_candidate_m':round(haversine_km(
                        [candidate['latitude'],candidate['longitude']],[details['latitude'],details['longitude']])*1000,1)})
        return sorted(output,key=lambda row:row['distance_to_candidate_m'])[:count]


def queries_for(candidate, records):
    text = ' '.join(str((row.get('details') or {}).get('description') or '') for row in records)
    words = 'clock tower' if re.search(r'\bclock\b',text,re.I) else 'architecture street' if re.search(r'building|city|street',text,re.I) else 'landscape'
    region = candidate.get('region','')
    landmarks=candidate.get('nearby_landmarks',[])
    named=next((row for row in landmarks if row.get('name')), {})
    name = named.get('name') or region[:150]
    english=(named.get('names') or {}).get('name:en') or name
    russian=(named.get('names') or {}).get('name:ru') or name
    return [{'language':'en','query':(english+' '+words).strip(), 'basis':'observed_scene_and_candidate_place'},
        {'language':'ru','query':(russian+' '+('башня часы' if words=='clock tower' else 'архитектура' if words=='architecture street' else 'пейзаж')).strip(),
         'basis':'translated_observed_features_not_country_identification'}]


def comparison_summary(result):
    """Spatial support is diagnostic, not a probability or exact-location test."""
    value={key:deepcopy(result[key]) for key in ('status','error_code','match_count','geometry','matches','input_sizes','keypoints') if key in result}
    matches=result.get('matches',[])
    sizes=result.get('input_sizes',[])
    indices=(result.get('geometry') or {}).get('inlier_indices',[])
    coverage=[]
    for index in (0,1):
        if len(sizes)<=index or len(sizes[index])!=2 or min(sizes[index])<=0:
            coverage.append(None);continue
        points=[matches[i].get('point'+str(index)) for i in indices if type(i) is int and 0<=i<len(matches)]
        points=[point for point in points if isinstance(point,list) and len(point)==2]
        if len(points)<3:coverage.append(0.0);continue
        area=(max(p[0] for p in points)-min(p[0] for p in points))*(max(p[1] for p in points)-min(p[1] for p in points))
        coverage.append(round(area/(sizes[index][0]*sizes[index][1]),4))
    value.update(score_calibrated=False, spatial_coverage=coverage, geolocation_verified=False,
        interpretation='Совпавшие признаки могут отражать повторяющиеся окна и фасады, а не уникальный ориентир. Одно место съёмки не подтверждено.')
    value['support_kind']='localized_or_insufficient_features' if any(value is None or value<.15 for value in coverage) else 'distributed_feature_matches_not_location_proof'
    return value


def execute(args, *, records, store, settings=None, sources=None, media_store=None, secret_getter=None, cancel_event=None, deadline=None, on_result=None):
    from ..integrations19.solar import check, LocalToolError
    if sources is None:
        from ..geoint_tools import mapping_client
        sources=ResearchSources(maps=mapping_client(settings),secret_getter=secret_getter)
    media_store = media_store or MediaStore()
    optional = getattr(sources,'optional',lambda:[])()
    started = time.monotonic()
    end = min(deadline, started+180) if deadline else started+180
    attachment_id = args['attachment_id']
    selected = [current_observation(row) for row in records if isinstance(row,dict)
        and (row.get('details') or {}).get('attachment_id')==attachment_id]
    candidates = hypotheses(selected, attachment_id, args.get('max_candidates',2))
    rows, stages, limitations = [], [], []
    def emit(kind, key, title, details, url='', description=''):
        row = {'id':kind+':'+key,'type':kind,'platform':'GEOINT Research','title':title,'url':url,
            'description':description or title,'status':'hypothesis','sources':['geoint_research'],
            'details':{**details,'tool':'geoint_research','capability':'geoint_research', 'attachment_id':attachment_id,
                'source_record':True, 'acquisition':'public_api_and_local_comparison', 'collected_at':datetime.now(timezone.utc).isoformat()}}
        rows.append(row)
        if on_result:
            on_result(row)
        return row
    def stage(name, function):
        check(cancel_event,end)
        try:
            value = function()
            state=value.get('status') if isinstance(value,dict) else None
            stages.append({'stage':name,'status':state if state in ('error','timeout','cancelled','unavailable') else 'complete',
                **({'error_code':value.get('error_code')} if state in ('error','timeout','cancelled','unavailable') else {})})
            return value
        except LocalToolError:
            raise
        except Exception as error:
            code = str(getattr(error,'code', type(error).__name__))
            if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}',code):code='provider_unavailable'
            stages.append({'stage':name,'status':'unavailable','error_code':code})
            return None
    try:
        if not candidates:
            return {'status':'unavailable','error_code':'no_saved_geographic_candidates','results':[],
                'limitations':['Нет сохранённых координатных гипотез; сначала выполните visual_geoint. Место не выдумано.']}
        comparisons = 0
        for candidate in candidates:
            position = stage('reverse_geocode', lambda:sources.reverse(candidate,cancel_event))
            if position:
                candidate['region'] = position['name']
                candidate['geocoding'] = position
            landmarks = stage('osm_landmarks',lambda:sources.landmarks(candidate,cancel_event)) or []
            candidate['nearby_landmarks'] = landmarks
            queries = queries_for(candidate, selected)
            candidate['research_queries'] = queries
            emit('geoint_candidate',candidate['candidate_id'], candidate['region'] or 'Географическая гипотеза', deepcopy(candidate),
                (position or {}).get('source_url',''), 'Координатная гипотеза; найденная поблизости инфраструктура не доказывает место исходного фото.')
            references = stage('commons_image_research',lambda:sources.commons(candidate,queries,args.get('references_per_candidate',3),cancel_event)) or []
            references += stage('panoramax_street_research',lambda:sources.panoramax(candidate,2,cancel_event,end)) or []
            if any(row.get('provider')=='yandex_search' and row.get('state')=='configured_not_tested' for row in optional):
                extra=stage('optional_yandex_text_images',lambda:sources.yandex_text(queries[1]['query'],cancel_event,end)) or {}
                references+=extra.get('images',[])
            if any(row.get('provider')=='mapillary' and row.get('state')=='configured_not_tested' for row in optional):
                extra=stage('optional_mapillary',lambda:sources.mapillary(candidate,2,cancel_event,end)) or {}
                references+=extra.get('images',[])
            if candidate['region']:
                articles = stage('web_landmark_research',lambda:sources.wikipedia(queries[0]['query'],'en',cancel_event)) or []
                for article in articles:
                    emit('web',candidate['candidate_id']+'|'+article['source_url'],article['title'],
                        {**article,'candidate_id':candidate['candidate_id'],'source_family':'Wikimedia'},article['source_url'],article['description'])
            for index, reference in enumerate(references):
                check(cancel_event,end)
                if len(candidate['reference_images'])>=args.get('references_per_candidate',3):break
                key = candidate['candidate_id']+'|'+str(reference['source_url'])
                raw = emit('reference_image',key,reference['title'],{**reference,'candidate_id':candidate['candidate_id'],
                    'reference_location_verified':False,'match_kind':'nearby_reference_not_verified_match'},reference['source_url'],reference.get('description',''))
                normalized = normalize_evidence(raw,'geoint_research',attachment_id)
                media = media_reference(normalized)
                if not media:
                    continue
                preview = stage('reference_image_download',lambda:asyncio.run(media_store.fetch(media,cancel_event,end)))
                if preview:
                    raw['details']['media'] = {key:value for key,value in preview.items() if key!='thumbnail'}
                    raw['details']['image_fetched'] = True
                    candidate['reference_images'].append({'evidence_id':normalized['evidence_id'],'image_url':reference['image_url'],
                        'source_url':reference['source_url'],'title':reference['title'],'media_id':media['id']})
                    if args.get('compare',True) and comparisons < 2 and time.monotonic()+20 < end:
                        comparisons += 1
                        def reference_scene():
                            from ..visual_models.scene import understand
                            return understand(media_store.read_original(media),cancel_event=cancel_event,
                                deadline=min(end,time.monotonic()+60))
                        semantics=stage('reference_pixel_understanding',reference_scene)
                        if semantics and semantics.get('status')=='completed':
                            raw['details']['reference_scene']={key:semantics[key] for key in
                                ('description','observations','model_version','limitations') if key in semantics}
                        def compare():
                            from ..visual_models.manager import get_manager
                            return get_manager().match(store.read_bytes(attachment_id,cancel_event),media_store.read_original(media),
                                cancel_event=cancel_event,deadline=min(end,time.monotonic()+60))
                        comparison = stage('local_visual_comparison',compare)
                        if comparison:
                            raw['details']['comparison'] = comparison_summary(comparison)
                    if on_result:
                        on_result(raw)
            if candidate['reference_images']:
                candidate['verification_status'] = 'geographically_plausible'
            else:
                limitations.append('Сравнительные фотографии для '+(candidate['region'] or candidate['candidate_id'])+' не найдены или не загрузились.')
            emit('geoint_candidate',candidate['candidate_id'],candidate['region'] or 'Географическая гипотеза',deepcopy(candidate),
                (position or {}).get('source_url',''))
        status = 'partial' if any(stage['status']!='complete' for stage in stages) else 'complete'
    except LocalToolError as error:
        status = error.code if error.code in ('cancelled','timeout') else 'error'
        limitations.append(str(error))
    limitations += ['Координаты моделей не являются подтверждённым адресом. Похожая архитектура и соседние фотографии не доказывают ту же улицу.',
        'Пользовательское изображение не передавалось внешним провайдерам. Google/Yandex reverse image search требуют отдельного ключа и разрешения.']
    emit('geoint_research_report',attachment_id,'Покрытие географического исследования',
        {'stages':stages,'source_diagnostics':getattr(sources,'diagnostics',[]),'limitations':limitations,
         'candidates':candidates,'optional_providers':optional,'image_uploaded':False,'status':status})
    return {'status':status,'tool':'geoint_research','query':attachment_id,'results':rows,'candidates':candidates,
        'stages':stages,'limitations':limitations,'elapsed_seconds':round(time.monotonic()-started,3)}
