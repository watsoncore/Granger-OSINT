"""Schemas for documented anonymous GeoIP APIs, without account keys."""
import ipaddress
import math

SOURCES={
 'ipwhois':{'endpoint':'https://ipwho.is/','documentation':'https://ipwhois.io/documentation','anonymous_daily_limit':1000},
 'ipapi_is':{'endpoint':'https://api.ipapi.is/','documentation':'https://ipapi.is/free-tier.html','anonymous_daily_limit':30},
}


def parse(source,address,payload):
    if source not in SOURCES or not isinstance(payload,dict):raise ValueError('Invalid GeoIP source schema')
    returned=payload.get('ip')
    if not isinstance(returned,str) or ipaddress.ip_address(returned)!=ipaddress.ip_address(address):
        raise ValueError('GeoIP response does not match requested IP')
    if source=='ipwhois' and payload.get('success') is not True or payload.get('error'):
        raise ValueError('GeoIP source refused query')
    def text(value):return value[:200] if isinstance(value,str) and value.strip() else None
    country=text(payload.get('country'));region=text(payload.get('region'));city=text(payload.get('city'))
    lat=payload.get('latitude') if source=='ipwhois' else payload.get('lat')
    lon=payload.get('longitude') if source=='ipwhois' else payload.get('lon')
    valid=type(lat) in (int,float) and type(lon) in (int,float) and math.isfinite(lat+lon) and -90<=lat<=90 and -180<=lon<=180
    if not (country or region or city or valid):raise ValueError('GeoIP response has no geographic fields')
    connection=payload.get('connection');connection=connection if isinstance(connection,dict) else {}
    return {'provider':source,'country_name':country,'country_code':text(payload.get('country_code')),
        'region':region,'city':city,'latitude':lat if valid else None,'longitude':lon if valid else None,
        'accuracy_radius_km':None,'database_updated_at':None,'location_kind':'ip_database_estimate',
        'exact_device_location_verified':False,'registration_country_is_not_geolocation':True,
        'provider_network_label':text(connection.get('org') or connection.get('isp')) if source=='ipwhois' else text(payload.get('company')),
        'documentation_url':SOURCES[source]['documentation'],'anonymous_daily_limit':SOURCES[source]['anonymous_daily_limit'],
        'limitations':['Оценка базы по IP, возможен центр сети/города; не координаты человека или устройства.',
                       'Источник не предоставил точность/радиус и дату обновления конкретной записи.']}
