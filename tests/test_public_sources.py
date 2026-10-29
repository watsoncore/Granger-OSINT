"""Controlled HTTP fixtures; live public requests have a separate QA report."""
import asyncio
import json
import threading
import time

import httpx
import pytest

from grangerpet import public_sources as sources


PAYLOADS={
 'github_profile':{'login':'octocat','id':1,'name':'Public fixture','public_repos':5},
 'github_users':{'total_count':1,'items':[{'login':'octocat','id':1}]},
 'github_repositories':{'total_count':1,'items':[{'full_name':'octocat/Hello-World','private':False,'description':'Public fixture'}]},
 'hn_profile':{'id':'pg','created':123,'karma':10,'about':'Actual <b>public</b> field'},
 'hn_search':{'nbHits':1,'hits':[{'objectID':'123','title':'Public story','author':'pg','created_at':'2020-01-01','story_text':'Actual <em>fixture</em> text'}]},
 'openlibrary_search':{'numFound':1,'docs':[{'key':'/works/OL1W','title':'Public book','author_name':['Public author'],'first_publish_year':1900}]},
 'archive_search':{'response':{'numFound':1,'docs':[{'identifier':'public-fixture','title':'Public document','description':'Actual metadata'}]}},
 'wikipedia_search':{'query':{'pages':[{'pageid':42,'title':'Public article','extract':'Actual article introduction'}]}},
}


@pytest.fixture(autouse=True)
def fresh_limits():
    sources._NEXT.clear();sources._COOLDOWN.clear();sources._CACHE.clear();sources._HISTORY.clear()
    from grangerpet import agent_browser
    agent_browser._DOMAIN_NEXT.clear()


async def resolver(host,port):return ['93.184.216.34']


class Transport:
    def __init__(self,handler):self.handler=handler;self.requests=[];self.clients=[]
    def factory(self,**kwargs):
        assert kwargs['transport'].__class__.__name__=='PinnedTransport'
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        async def handle(request):
            self.requests.append(request);value=self.handler(request)
            return await value if hasattr(value,'__await__') else value
        kwargs['transport']=httpx.MockTransport(handle)
        client=httpx.AsyncClient(**kwargs);self.clients.append(client);return client


def execute(source,transport,**kwargs):
    return sources.execute(source,'pg' if source=='hn_profile' else 'octocat',client_factory=transport.factory,resolver=resolver,**kwargs)


@pytest.mark.parametrize('source',list(PAYLOADS))
def test_each_adapter_extracts_validated_source_record_and_closes_transport(source):
    transport=Transport(lambda _:httpx.Response(200,json=PAYLOADS[source]))
    result=execute(source,transport)
    assert result['status']=='complete' and len(result['results'])==1
    row=result['results'][0]
    assert row['details']['source_id']==source
    assert row['details']['source_record'] and row['details']['extraction_status']=='record_extracted'
    assert row['details']['endpoint'].startswith('https://') and row['url'].startswith('https://')
    assert not any(k.lower()=='authorization' for k in transport.requests[0].headers)
    assert 'Granger-OSINT' in transport.requests[0].headers['user-agent']
    assert all(c.is_closed for c in transport.clients)


@pytest.mark.parametrize('source',list(PAYLOADS))
@pytest.mark.parametrize('payload',[{}, {'items':'broken'}, {'error':'maintenance'}])
def test_changed_or_malformed_schema_never_reports_success(source,payload):
    result=execute(source,Transport(lambda _:httpx.Response(200,json=payload)))
    assert result['status']=='unavailable' and result['error_code']=='invalid_response' and not result['results']


@pytest.mark.parametrize('status',[401,403,429,500,503])
def test_http_failure_and_backoff_never_retries_a_blocked_source(status):
    transport=Transport(lambda _:httpx.Response(status))
    result=execute('github_profile',transport)
    assert result['status'] not in ('complete','empty') and not result['results']
    assert len(transport.requests)==(2 if status==503 else 1)
    if status in (429,503):
        assert execute('github_profile',transport)['error_code']=='provider_cooldown'
        assert len(transport.requests)==(2 if status==503 else 1)


def test_distinguishes_true_empty_missing_profile_and_malformed_response():
    assert execute('github_profile',Transport(lambda _:httpx.Response(404)))['status']=='empty'
    assert execute('hn_profile',Transport(lambda _:httpx.Response(200,text="null")))['status']=='empty'
    sources._NEXT.clear()
    assert execute('github_users',Transport(lambda _:httpx.Response(200,json={'total_count':0,'items':[]})))['status']=='empty'


def test_validation_and_private_dns_block_before_any_request():
    transport=Transport(lambda _:pytest.fail('Network must not run'))
    assert sources.execute('github_profile','../private',client_factory=transport.factory)['status']=='invalid_arguments'
    async def private(host,port):return ['127.0.0.1']
    result=sources.execute('github_profile','octocat',client_factory=transport.factory,resolver=private)
    assert result['status']=='blocked' and not transport.requests


def test_explicit_redirect_is_not_followed_to_any_host():
    result=execute('github_profile',Transport(lambda _:httpx.Response(302,headers={'Location':'http://127.0.0.1/'})))
    assert result['status']=='blocked' and not result['results']


def test_size_bound_bad_json_and_real_async_cancellation():
    for response,code in [(httpx.Response(200,content=b'x'*2_000_001,headers={'Content-Type':'application/json'}),'response_too_large'),(httpx.Response(200,text='{broken',headers={'Content-Type':'application/json'}),'invalid_response')]:
        sources._NEXT.clear()
        assert execute('github_profile',Transport(lambda _:response))['error_code']==code
    event=threading.Event()
    async def pending(_):event.set();await asyncio.sleep(5);return httpx.Response(200,json=PAYLOADS['github_profile'])
    sources._NEXT.clear()
    from grangerpet import agent_browser
    agent_browser._DOMAIN_NEXT.clear()
    transport=Transport(pending);started=time.monotonic()
    result=execute('github_profile',transport,cancel_event=event)
    assert result['status']=='cancelled' and time.monotonic()-started<1
    assert all(c.is_closed for c in transport.clients)
    assert execute('github_profile',transport,deadline=time.monotonic()-1)['status']=='timeout'


def test_cache_is_a_copy_and_preserves_original_time_without_network():
    transport=Transport(lambda _:httpx.Response(200,json=PAYLOADS['github_profile']))
    first=execute('github_profile',transport);saved=first['obtained_at'];first['results'].clear()
    second=execute('github_profile',transport)
    assert second['results'] and second['obtained_at']==saved and len(transport.requests)==1


def test_keyfree_federation_keeps_second_source_after_first_fails():
    def handler(request):
        if request.url.host=='api.github.com':return httpx.Response(403)
        key='hn_search' if request.url.host=='hn.algolia.com' else 'wikipedia_search'
        return httpx.Response(200,json=PAYLOADS[key])
    transport=Transport(handler)
    result=sources.search('octocat',client_factory=transport.factory,resolver=resolver)
    assert result['status']=='partial' and len(result['results'])==2
    assert {r['platform'] for r in result['results']}=={'hn_search','wikipedia_search'}
    assert any(r['source']=='github_users' and r['status']=='unavailable' for r in result['source_attempts'])
    assert len(transport.requests)==3 and all(c.is_closed for c in transport.clients)
