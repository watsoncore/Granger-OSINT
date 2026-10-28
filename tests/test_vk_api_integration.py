"""Real installed vk_api request serialization with a controlled HTTP boundary."""
import json
from types import SimpleNamespace

import pytest
import requests

from grangerpet.engine import platforms


@pytest.fixture
def vk(monkeypatch):
    module = platforms._load('vk','vk_api',{})
    monkeypatch.setattr(platforms,'_load',lambda *args:module)
    calls, replies = [], []

    def send(session, request, **kwargs):
        assert request.url.startswith('https://api.vk.ru/method/')
        assert request.headers['Authorization']=='Bearer private-fixture'
        assert 'private-fixture' not in request.url
        assert 'access_token' not in (request.body or '')
        assert kwargs['allow_redirects'] is False
        assert kwargs['timeout'][0]==3
        calls.append(request)
        response=requests.Response()
        response.status_code=200
        response._content=json.dumps(replies.pop(0),ensure_ascii=False).encode('utf-8')
        response.encoding='utf-8';response.request=request
        return response
    monkeypatch.setattr(requests.Session,'send',send)
    return calls,replies


def run(text):
    return platforms.run_adapter('vk',{'text':text,'timeout':5},{'vk_token':'private-fixture'})


@pytest.mark.parametrize('text',['12345','id12345','https://vk.com/id12345'])
def test_numeric_id_uses_one_users_get_with_documented_public_fields(vk,text):
    calls,replies=vk
    replies.append({'response':[{'id':12345,'first_name':'Тест','last_name':'Пример','status':'Русский UTF-8',
        'country':{'id':1,'title':'Россия'},'photo_max_orig':'https://example.org/photo.jpg','sex':1,
        'request_params':{'access_token':'private-fixture'}}]})
    result=run(text)
    assert result['status']=='complete' and len(calls)==1
    assert calls[0].url.endswith('/users.get')
    assert 'photo_max_orig' in calls[0].body and 'v=5.199' in calls[0].body
    row=result['results'][0]
    assert row['title']=='Тест Пример'
    assert row['details']['acquisition']=='official_api'
    assert row['details']['country']['title']=='Россия'
    assert 'private-fixture' not in json.dumps(result)


def test_screenname_resolves_then_reads_user(vk):
    calls,replies=vk
    replies.extend([{'response':{'object_id':12345,'type':'user'}},
                    {'response':[{'id':12345,'first_name':'Тест','is_closed':True,'can_access_closed':False}]}])
    result=run('fixture_name')
    assert len(calls)==2 and result['status']=='complete'
    assert 'закрыт' in result['results'][0]['description']


@pytest.mark.parametrize(('code','status'),[(5,'auth_required'),(7,'auth_required'),(15,'auth_required'),
    (18,'empty'),(30,'unavailable'),(6,'rate_limited'),(9,'rate_limited'),(29,'rate_limited'),
    (14,'unavailable'),(10,'unavailable'),(113,'empty')])
def test_vk_errors_are_specific_and_never_echo_response(vk,code,status):
    _,replies=vk
    replies.append({'error':{'error_code':code,'error_msg':'private-fixture','request_params':[{'value':'private-fixture'}]}})
    result=run('12345')
    assert result['status']==status
    assert 'private-fixture' not in json.dumps(result)


@pytest.mark.parametrize('response',[{'bad':'shape'},[{'id':12345,'deactivated':'deleted'}]])
def test_unknown_and_deleted_profiles_never_produce_a_verified_result(vk,response):
    _,replies=vk;replies.append({'response':response})
    result=run('12345')
    assert result['status'] in ('error','empty') and result['results']==[]
