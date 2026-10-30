"""Official payload/auth/consent fixtures. These are not live provider tests."""
import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from grangerpet.geoint.optional_apis import reverse, availability, mapillary
from grangerpet.geoint.research import comparison_summary

IMAGE='img_'+'a'*64
KEY='PRIVATE-FIXTURE-ONLY-API-CREDENTIAL'


class Store:
    def __init__(self):self.reads=0
    def read_bytes(self,*args):self.reads+=1;return b'fixture image bytes'


def factory(reply):
    return lambda **kw:httpx.AsyncClient(transport=httpx.MockTransport(reply),**kw)


def test_configuration_is_not_image_upload_consent_or_live_execution():
    values=availability(lambda _:KEY)
    assert all(row['execution_verified'] is False for row in values)
    store=Store()
    result=reverse({'attachment_id':IMAGE,'provider':'google_vision'},store=store,getter=lambda _:KEY,
        client_factory=factory(lambda _:pytest.fail('No HTTP without consent')))
    assert result['error_code']=='image_upload_consent_required' and not store.reads


def test_missing_optional_credentials_never_submits_a_dummy_key():
    result=reverse({'attachment_id':IMAGE,'provider':'yandex_search'},store=Store(),getter=lambda _: '',approved=True,
        client_factory=factory(lambda _:pytest.fail('No credentials')))
    assert result['error_code']=='optional_credentials_missing'
    assert mapillary({'latitude':1,'longitude':2},2,getter=lambda _: '')['status']=='optional_unconfigured'


@pytest.mark.parametrize('provider',['google_vision','yandex_search'])
def test_official_reverse_payload_utf8_and_keys_only_in_headers(provider):
    seen=[]
    def reply(request):
        seen.append(request)
        if provider=='google_vision':return httpx.Response(200,json={'responses':[{'webDetection':{
            'visuallySimilarImages':[{'url':'https://example.org/reference.jpg'}]}}]})
        return httpx.Response(200,json={'images':[{'url':'https://example.org/reference.jpg',
            'pageUrl':'https://example.org/place','pageTitle':'Место съёмки'}]})
    result=reverse({'attachment_id':IMAGE,'provider':provider},store=Store(),getter=lambda name:'folder-id' if name=='yandex_folder_id' else KEY,
        approved=True,client_factory=factory(reply))
    assert result['status']=='complete' and len(seen)==1
    request=seen[0];payload=json.loads(request.content)
    assert KEY not in str(request.url) and KEY.encode() not in request.content and KEY not in json.dumps(result)
    assert request.headers.get('x-goog-api-key')==KEY if provider=='google_vision' else request.headers['authorization']=='Api-Key '+KEY
    encoded=payload['requests'][0]['image']['content'] if provider=='google_vision' else payload['data']
    assert base64.b64decode(encoded)==b'fixture image bytes'
    assert result['results'][0]['details']['geolocation_verified'] is False


@pytest.mark.parametrize('status',[401,402,403,429,503])
def test_provider_error_never_includes_body_or_credential(status):
    result=reverse({'attachment_id':IMAGE,'provider':'google_vision'},store=Store(),getter=lambda _:KEY,approved=True,
        client_factory=factory(lambda _:httpx.Response(status,text='Echo '+KEY)))
    assert result['status']!='complete' and not result['results'] and result['http_status']==status
    assert KEY not in json.dumps(result)


def test_reflected_key_in_image_metadata_is_redacted():
    result=reverse({'attachment_id':IMAGE,'provider':'yandex_search'},store=Store(),getter=lambda _:KEY,approved=True,
        client_factory=factory(lambda _:httpx.Response(200,json={'images':[{'url':'https://example.org/'+KEY+'.jpg',
            'pageTitle':'Reflected '+KEY}]})))
    assert KEY not in json.dumps(result)


def test_mapillary_uses_oauth_header_without_token_in_query():
    seen=[]
    def reply(request):
        seen.append(request)
        return httpx.Response(200,json={'data':[{'id':'1234','thumb_1024_url':'https://example.org/ref.jpg',
            'computed_geometry':{'type':'Point','coordinates':[2,1]},'creator':{'username':'Fixture author'}}]})
    result=mapillary({'latitude':1,'longitude':2},2,getter=lambda _:KEY,client_factory=factory(reply))
    assert result['status']=='complete' and len(result['images'])==1
    assert seen[0].headers['authorization']=='OAuth '+KEY and KEY not in str(seen[0].url)


def test_many_matches_in_small_facade_region_are_not_exact_location_proof():
    matches=[{'point0':[100+i,100+i/2],'point1':[200+i,200+i/2]} for i in range(40)]
    value=comparison_summary({'status':'completed','match_count':40,'matches':matches,'input_sizes':[[500,400],[1000,800]],
        'geometry':{'inliers':40,'inlier_indices':list(range(40))}})
    assert value['spatial_coverage'][0]<.15 and value['support_kind']=='localized_or_insufficient_features'
    assert value['geolocation_verified'] is False and value['score_calibrated'] is False


def test_official_yandex_text_search_decodes_utf8_xml_and_sends_no_image():
    from grangerpet.geoint.optional_apis import yandex_text
    seen=[]
    xml='<yandexsearch><response><results><doc><url>https://example.org/place</url><image-url>https://example.org/ref.jpg</image-url><title>Башня</title></doc></results></response></yandexsearch>'
    def reply(request):
        seen.append(request)
        return httpx.Response(200,json={'rawData':base64.b64encode(xml.encode('utf-8')).decode()})
    result=yandex_text('Башня часы',getter=lambda _:KEY,client_factory=factory(reply))
    payload=json.loads(seen[0].content)
    assert result['status']=='complete' and result['images'][0]['title']=='Башня'
    assert payload['query']['queryText']=='Башня часы' and 'data' not in payload and KEY not in str(seen[0].url)


@pytest.mark.parametrize('xml',['<!DOCTYPE x [<!ENTITY e "bad">]><x>&e;</x>','<bad>','<yandexsearch><response/></yandexsearch>'])
def test_yandex_xml_unknown_or_unsafe_schema_is_not_an_image_success(xml):
    from grangerpet.geoint.optional_apis import yandex_text
    result=yandex_text('test',getter=lambda _:KEY,client_factory=factory(lambda _:httpx.Response(200,
        json={'rawData':base64.b64encode(xml.encode()).decode()})))
    assert result['status']!='complete' and not result['images']
