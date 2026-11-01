"""Read-only Wikibase place lookup; CC0 statements are not verified ground truth."""
from urllib.parse import quote
import math
import re

from .images import GeointError
from ..visual_models.pipeline import haversine_km

ENDPOINT='https://www.wikidata.org/w/api.php'
SCHEMA={'type':'object','properties':{'query':{'type':'string','minLength':2,'maxLength':160},
    'latitude':{'type':'number','minimum':-90,'maximum':90},'longitude':{'type':'number','minimum':-180,'maximum':180},
    'radius_km':{'type':'number','minimum':.1,'maximum':100},'limit':{'type':'integer','minimum':1,'maximum':5}},
    'required':['query'],'additionalProperties':False}


def lookup(args,maps,cancel=None):
    lat,lon=args.get('latitude'),args.get('longitude')
    if (lat is None)!=(lon is None):raise GeointError('invalid_arguments','Широта и долгота задаются вместе.')
    language='ru' if re.search('[а-яА-ЯёЁ]',args['query']) else 'en'
    found,_=maps._request(ENDPOINT,{'action':'wbsearchentities','format':'json','search':args['query'],
        'language':language,'uselang':language,'type':'item','limit':min(5,args.get('limit',3))},cancel)
    if not isinstance(found,dict) or not isinstance(found.get('search'),list):raise GeointError('invalid_response','Wikidata не вернула список поиска.')
    ids=[row['id'] for row in found['search'] if isinstance(row,dict) and re.fullmatch(r'Q[1-9][0-9]*',str(row.get('id','')))]
    if not ids:return []
    data,_=maps._request(ENDPOINT,{'action':'wbgetentities','format':'json','ids':'|'.join(ids),
        'props':'labels|descriptions|claims|sitelinks','languages':'ru|en','sitefilter':'ruwiki|enwiki'},cancel)
    if not isinstance(data,dict) or not isinstance(data.get('entities'),dict):raise GeointError('invalid_response','Некорректные сущности Wikidata.')
    result=[]
    for identifier in ids:
        row=data['entities'].get(identifier,{})
        claims=row.get('claims') or {}
        coordinates=[c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in claims.get('P625',[]) if c.get('rank')!='deprecated']
        coordinate=next((c for c in coordinates if isinstance(c,dict) and c.get('globe','').endswith('/Q2') and
            all(type(c.get(k)) in (int,float) and math.isfinite(c[k]) for k in ('latitude','longitude')) and
            -90<=c['latitude']<=90 and -180<=c['longitude']<=180),None)
        if not coordinate:continue
        distance=haversine_km([lat,lon],[coordinate['latitude'],coordinate['longitude']]) if lat is not None else None
        if distance is not None and distance>args.get('radius_km',10):continue
        def localized(key):
            values=row.get(key) or {};return str((values.get(language) or values.get('en') or values.get('ru') or {}).get('value',''))[:700]
        images=[c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in claims.get('P18',[]) if c.get('rank')!='deprecated']
        result.append({'entity_id':identifier,'title':localized('labels') or identifier,'description':localized('descriptions'),
            'latitude':coordinate['latitude'],'longitude':coordinate['longitude'],'coordinate_precision':coordinate.get('precision'),
            'distance_m':round(distance*1000,1) if distance is not None else None,
            'source_url':'https://www.wikidata.org/wiki/'+identifier,'provider':'Wikidata','data_license':'CC0-1.0',
            'reference_file_pages':['https://commons.wikimedia.org/wiki/File:'+quote(name.replace(' ','_')) for name in images[:2] if isinstance(name,str)],
            'reference_location_verified':False,'limitations':['Wikidata statements may be incomplete or wrong. File licenses must be read on each Commons file page.']})
    return result


def execute(args,settings,cancel=None):
    from ..geoint_tools import mapping_client
    from ..agent_web import _envelope,_record
    try:
        rows=lookup(args,mapping_client(settings),cancel)
        records=[_record('Wikidata',row['entity_id'],row['title'],row['source_url'],row['description'],kind='map',
            details={**row,'capability':'wikidata_places','source_record':True,'acquisition':'official_wikibase_api'}) for row in rows]
        return _envelope('wikidata_places',args['query'],results=records,status='complete' if records else 'empty')
    except GeointError as error:
        return _envelope('wikidata_places',args['query'],status='timeout' if error.code=='timeout' else 'error',error_code=error.code,limitations=[str(error)])
