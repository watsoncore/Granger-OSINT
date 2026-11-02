"""Explicit local response fixtures, not live provider verification."""
import json
import httpx
import pytest
from grangerpet.ai import AIError,DEFAULT_DEEPSEEK_MODEL
from test_deepseek_api import TransportFixture,completion
from test_agent_completion import Bytes,frame


@pytest.mark.parametrize('status',[400,401,402,403,422,429,500,502,503])
def test_provider_diagnostics_keep_status_and_hash_without_echoing_request_or_key(status):
    secret='explicit-private-fixture-key'
    fixture=TransportFixture(lambda _:httpx.Response(status,json={'error':{'message':'Private prompt '+secret,'param':secret}}))
    with pytest.raises(AIError) as error:fixture.client().generate(DEFAULT_DEEPSEEK_MODEL,'Private prompt')
    details=error.value.diagnostic
    assert details['http_status']==status and len(details['response_body_sha256'])==64
    assert secret not in str(details)+str(error.value) and 'Private prompt' not in str(details)
    assert details['parameter'] is None and len(fixture.calls)==1


def test_explicit_unsupported_optional_stream_usage_is_negotiated_once_and_cached():
    def handler(request):
        payload=json.loads(request.content)
        if 'stream_options' in payload:
            return httpx.Response(400,json={'error':{'message':'Unsupported parameter stream_options','param':'stream_options'}})
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes([
            frame('Тестовый ответ'),frame('',finish='stop'),b'data: [DONE]\n\n']))
    fixture=TransportFixture(handler);client=fixture.client()
    for _ in range(2):assert client.stream_chat(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':'Привет'}],on_text=lambda _:None)=='Тестовый ответ'
    assert len(fixture.calls)==3
    assert 'stream_options' not in json.loads(fixture.calls[-1].content)


def test_tools_are_never_silently_removed_when_provider_rejects_them():
    fixture=TransportFixture(lambda _:httpx.Response(400,json={'error':{'message':'tools is not supported','param':'tools'}}))
    with pytest.raises(AIError) as error:
        fixture.client().complete_turn(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','content':'Проверка'}],
            tools=[{'type':'function','function':{'name':'fixture','parameters':{'type':'object'}}}])
    assert error.value.diagnostic['cause']=='unsupported_parameter' and 'tools' in str(error.value)
    assert len(fixture.calls)==1


def test_oversize_malformed_provider_error_is_bounded():
    fixture=TransportFixture(lambda _:httpx.Response(400,content=b'x'*100000))
    with pytest.raises(AIError) as error:fixture.client().generate(DEFAULT_DEEPSEEK_MODEL,'Test')
    assert error.value.diagnostic['response_bytes_observed']==16000
    assert error.value.diagnostic['response_truncated']
