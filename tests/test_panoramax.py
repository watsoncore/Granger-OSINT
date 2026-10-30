"""Bounded STAC reference observations, never a user's photo geolocation proof."""
from copy import deepcopy
import json
import time
import pytest
from grangerpet.integrations19 import panoramax,public_tools
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings

FEATURE={'type':'Feature','id':'de4877f6-0d9a-445b-87c1-2c14ce35ee7e','geometry':{'type':'Point','coordinates':[2.2945,48.8584]},
    'properties':{'license':'etalab-2.0','datetime':'2025-06-26T12:48:56Z','exif':{'Exif.Image.Artist':'Archive author'}},
    'assets':{'sd':{'href':'https://images.example.org/public.jpg'},'thumb':{'href':'http://127.0.0.1/private'}}}


@pytest.mark.parametrize('args',[{'latitude':True,'longitude':0},{'latitude':float('nan'),'longitude':0},{'latitude':86,'longitude':0},
    {'latitude':0,'longitude':180},{'latitude':0,'longitude':0,'radius_m':10000},{'latitude':0,'longitude':0,'limit':100},
    {'latitude':0,'longitude':0,'url':'http://private/'}])
def test_unsafe_or_mass_search_parameters_rejected_before_any_http(monkeypatch,args):
    monkeypatch.setattr(public_tools,'_json',lambda *a,**k:pytest.fail('Invalid request reached network'))
    assert public_tools.execute('map_panoramax',args)['status']=='invalid_arguments'


def test_actual_record_schema_keeps_attribution_and_never_fetches_assets(monkeypatch):
    calls=[]
    async def api(url,params,**kwargs):
        calls.append((url,params));return {'type':'FeatureCollection','features':[deepcopy(FEATURE)]}
    monkeypatch.setattr(public_tools,'_json',api)
    public_tools._CACHE.clear()
    result=ToolRegistry(Settings()).execute('map_panoramax',{'latitude':48.8584,'longitude':2.2945,'limit':1})
    assert result['status']=='complete' and len(calls)==1 and calls[0][0]==panoramax.ENDPOINT
    record=result['results'][0];details=record['details']
    assert record['evidence_id'] and details['license']=='etalab-2.0' and details['attribution']=='Archive author'
    assert details['latitude']==48.8584 and details['pixels_downloaded'] is False
    assert details['reference_location_verified'] is False and len(details['media'])==1
    assert '127.0.0.1' not in json.dumps(record)


@pytest.mark.parametrize('change',[{'geometry':{'type':'Point','coordinates':[181,0]}},{'geometry':{'type':'Polygon','coordinates':[]}},
    {'assets':[]},{'id':'../../private'},{'properties':['wrong']}])
def test_malformed_archive_items_do_not_become_coordinate_evidence(monkeypatch,change):
    feature={**deepcopy(FEATURE),**change}
    async def api(*a,**k):return {'features':[feature]}
    monkeypatch.setattr(public_tools,'_json',api);public_tools._CACHE.clear()
    result=public_tools.execute('map_panoramax',{'latitude':48.8584,'longitude':2.2945})
    assert result['status']=='unavailable' and result['error_code'].startswith('invalid_panoramax_') and not result['results']


def test_empty_archive_is_an_empty_observation_not_an_absence_proof(monkeypatch):
    async def api(*a,**k):return {'features':[]}
    monkeypatch.setattr(public_tools,'_json',api);public_tools._CACHE.clear()
    result=public_tools.execute('map_panoramax',{'latitude':20,'longitude':20})
    assert result['status']=='empty' and result['limitations']


def test_archive_producer_and_license_link_survive_when_exif_artist_is_absent(monkeypatch):
    feature=deepcopy(FEATURE)
    feature['properties']['exif']={}
    feature['properties']['geovisio:producer']='Public archive contributor'
    feature['links']=[{'rel':'license','href':'https://example.org/license'}]
    async def api(*a,**k):return {'features':[feature]}
    monkeypatch.setattr(public_tools,'_json',api);public_tools._CACHE.clear()
    result=public_tools.execute('map_panoramax',{'latitude':48.8584,'longitude':2.2945})
    details=result['results'][0]['details']
    assert details['attribution']=='Public archive contributor'
    assert details['attribution_basis']=='archive_producer' and details['license_url']=='https://example.org/license'
