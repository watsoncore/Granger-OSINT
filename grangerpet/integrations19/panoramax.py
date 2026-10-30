"""Waypoint's key-free street imagery source, via the documented STAC API.

Only bounded public metadata and attributed asset links are returned. Coordinates
describe the archive's reference photo, not the user's photograph. No pixels are
downloaded and the user's pixels are never uploaded.
"""
import math
import re
from urllib.parse import urlsplit
from ..agent_browser import public_url,PageReadError
from ..agent_web import _FetchError

ENDPOINT='https://api.panoramax.xyz/api/search'
INPUT_SCHEMA={'type':'object','properties':{
    'latitude':{'type':'number','minimum':-85,'maximum':85},
    'longitude':{'type':'number','minimum':-180,'maximum':180},
    'radius_m':{'type':'integer','minimum':100,'maximum':2000},
    'limit':{'type':'integer','minimum':1,'maximum':10}},
    'required':['latitude','longitude'],'additionalProperties':False}


def validate(args):
    from ..tool_inputs import validate_object
    result=validate_object(args,INPUT_SCHEMA)
    result.setdefault('radius_m',500);result.setdefault('limit',5)
    bbox(result)
    return result


def bbox(args):
    lat,lon=args['latitude'],args['longitude'];span=args['radius_m']/111000
    east_span=span/max(.1,math.cos(math.radians(lat)))
    # Do not silently wrap a dateline-spanning box into an enormous search.
    if lon-east_span<-180 or lon+east_span>180:raise ValueError('Bounded box crosses date line')
    return ','.join(f'{v:.7f}' for v in (lon-east_span,lat-span,lon+east_span,lat+span))


async def search(args,call,json_fetch):
    data=await json_fetch(ENDPOINT,params={'bbox':bbox(args),'limit':str(args['limit'])},**call)
    if not isinstance(data,dict) or not isinstance(data.get('features'),list):raise _FetchError('invalid_panoramax_response')
    from .public_tools import _row
    rows=[]
    for feature in data['features'][:args['limit']]:
        if not isinstance(feature,dict):raise _FetchError('invalid_panoramax_feature')
        identifier=feature.get('id');geometry=feature.get('geometry',{});properties=feature.get('properties',{})
        if not isinstance(geometry,dict):raise _FetchError('invalid_panoramax_geometry')
        coords=geometry.get('coordinates') if geometry.get('type')=='Point' else None
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9-]{36}',identifier) or not isinstance(properties,dict):raise _FetchError('invalid_panoramax_feature')
        if not isinstance(coords,list) or len(coords)<2 or any(type(v) not in (float,int) or not math.isfinite(v) for v in coords[:2]) or abs(coords[0])>180 or abs(coords[1])>90:raise _FetchError('invalid_panoramax_coordinates')
        assets=[]
        raw_assets=feature.get('assets',{})
        if not isinstance(raw_assets,dict):raise _FetchError('invalid_panoramax_assets')
        for kind in ('thumb','sd'):
            asset=raw_assets.get(kind) or {}
            if not isinstance(asset,dict):continue
            href=asset.get('href')
            if not isinstance(href,str):continue
            try:href=public_url(href)
            except PageReadError:continue
            if urlsplit(href).scheme=='https':assets.append({'kind':kind,'url':href,'pixels_downloaded':False})
        exif=properties.get('exif') or {}
        artist=exif.get('Exif.Image.Artist') if isinstance(exif,dict) else None
        producer=properties.get('geovisio:producer')
        attribution=artist if isinstance(artist,str) and artist else producer if isinstance(producer,str) else ''
        license_url=''
        for link in feature.get('links',[]) if isinstance(feature.get('links'),list) else []:
            if isinstance(link,dict) and link.get('rel')=='license' and isinstance(link.get('href'),str):
                try:license_url=public_url(link['href'])
                except PageReadError:continue
                break
        details={'tool':'map_panoramax','id':identifier,'latitude':coords[1],'longitude':coords[0],
            'captured_at':str(properties.get('datetime',''))[:100],'license':str(properties.get('license') or feature.get('license') or 'not_specified')[:100],
            'attribution':attribution[:500],'attribution_basis':'exif_artist' if artist else 'archive_producer' if attribution else 'not_supplied',
            'license_url':license_url,
            'media':assets,'endpoint':ENDPOINT,'search_center':[args['latitude'],args['longitude']],
            'radius_m':args['radius_m'],'reference_location_verified':False,'pixels_downloaded':False,
            'verification':'Публичная запись Panoramax: координаты и дата предоставлены архивом. Близость к гипотезе модели не подтверждает место пользовательского фото.'}
        row=_row('map_panoramax',identifier,'Panoramax · '+details['captured_at'],
            'https://api.panoramax.xyz/#focus=pic&pic='+identifier,details['verification'],'street_image',details)
        row['details']['acquisition']='official_api';rows.append(row)
    return rows,['Panoramax: ограниченное покрытие. У каждого снимка собственная лицензия и автор; ссылки возвращены без загрузки пикселей. Близость и дата архива не доказывают совпадение места.']
