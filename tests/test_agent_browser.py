"""Direct-page extraction and network-boundary tests; all transport fixtures local."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import threading
import time

import httpcore
import httpx
import pytest

from grangerpet.agent_browser import (MAX_BYTES, PageParser, PageReadError, PinnedNetworkBackend,
                                      PublicPageReader, public_address, public_url)
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings


HTML='''<!doctype html><html><head><title>Пример профиля</title>
<meta property="og:title" content="Публичный профиль"><meta name="description" content="Описание страницы">
<script type="application/ld+json">{"@type":"Person","name":"Example","alternateName":"old_name"}</script>
<script>window.secret='not-executed'; fetch('http://localhost/');</script></head>
<body><nav>Unrelated navigation</nav><main><h1>Профиль Example</h1><p>Это непосредственно прочитанный текст публичной страницы, а не сниппет. Ранее использовался ник old_name.</p>
<table><tr><th>Год</th><th>Имя</th></tr><tr><td>2020</td><td>old_name</td></tr></table>
<a href="/about">О себе</a><a href="https://example.net/history">Исторический источник</a>
<a href="http://localhost/private">Forbidden</a><a href="javascript:alert(1)">Bad</a></main><footer>Unrelated footer</footer></body></html>'''


class Fixture:
    def __init__(self, handler=None, resolver=None):
        self.requests, self.options, self.resolutions=[],[],[]
        self.handler=handler or (lambda request:httpx.Response(200,headers={'content-type':'text/html; charset=utf-8'},content=HTML.encode()))
        self.resolve_override=resolver
    async def resolve(self,host,port):
        self.resolutions.append((host,port))
        return await self.resolve_override(host,port) if self.resolve_override else ['1.1.1.1']
    async def handle(self,request):
        self.requests.append(request)
        result=self.handler(request)
        return await result if hasattr(result,'__await__') else result
    def factory(self,**options):
        self.options.append(options)
        options['transport']=httpx.MockTransport(self.handle)
        return httpx.AsyncClient(**options)
    def reader(self,**kwargs):
        return PublicPageReader(resolver=self.resolve,client_factory=self.factory,**kwargs)


@pytest.mark.parametrize('url',[
    'http://localhost/','http://127.0.0.1/','http://10.0.0.1/','http://172.16.0.1/','http://192.168.1.1/',
    'http://169.254.169.254/latest/meta-data/','http://100.100.100.200/','http://168.63.129.16/',
    'http://[::1]/','http://[::ffff:127.0.0.1]/','http://[fe80::1%25eth0]/','https://user:password@example.org/',
    'file:///C:/private','ftp://example.org/file','https://example.org:8443/','https://example.org/%0d%0aHost:x',
    'https://example.org\\@127.0.0.1/','http://2130706433/','http://metadata.google.internal/',
    'https://example.org/?api_key=secret','https://example.org/logout','javascript:alert(1)',
])
def test_unsafe_public_page_urls_are_rejected_before_dns(url):
    with pytest.raises(PageReadError):public_url(url)


def test_actual_html_content_metadata_tables_and_related_links_are_separate_from_search():
    fixture=Fixture();reader=fixture.reader();reader.seed_urls_from_user('Прочитай https://example.org/profile')
    outcome=reader.read('https://example.org/profile')
    assert outcome['status']=='complete' and len(outcome['results'])==1
    result=outcome['results'][0];details=result['details']
    assert result['title']=='Пример профиля' and 'непосредственно прочитанный' in result['description']
    assert details['reading_method']=='direct_http' and details['evidence_category']=='page_content'
    assert details['metadata']['og:title']=='Публичный профиль'
    assert details['json_ld'][0]['alternateName']=='old_name'
    assert details['tables'][0][1]==['2020','old_name']
    assert details['headings'][0]['text']=='Профиль Example'
    assert {row['url'] for row in details['links']}=={'https://example.org/about','https://example.net/history'}
    assert 'Unrelated navigation' not in details['content_text'] and 'not-executed' not in details['content_text']
    assert details['crawl_depth']==0 and details['parent_url']==''
    assert fixture.options[0]['trust_env'] is False and fixture.options[0]['follow_redirects'] is False
    request=fixture.requests[0]
    assert request.url.host=='example.org' and request.headers['host']=='example.org'
    assert 'authorization' not in request.headers and 'cookie' not in request.headers


def test_url_must_be_discovered_or_explicitly_given_by_human():
    fixture=Fixture();reader=fixture.reader()
    assert reader.read('https://example.org/')['error']=='url_not_discovered'
    assert not fixture.requests and not fixture.resolutions
    reader.add_evidence([{'url':'https://example.org/','details':{}}])
    assert reader.read('https://example.org/')['status']=='complete'


def test_related_page_is_allowed_with_origin_and_depth_and_does_not_reset_to_zero():
    fixture=Fixture();reader=fixture.reader(max_depth=1);reader.allow_url('https://example.org/')
    first=reader.read('https://example.org/');second=reader.read('https://example.org/about')
    assert second['results'][0]['details']['crawl_depth']==1
    assert second['results'][0]['details']['parent_url']=='https://example.org/'
    assert not second['results'][0]['details']['links'] or all(row['url'] in ('https://example.org/about','https://example.net/history') for row in second['results'][0]['details']['links'])
    # A direct-read result is not treated as a new search root.
    reader.add_evidence(second['results'])
    assert reader._known['https://example.org/about']['depth']==1


def test_depth_zero_never_authorizes_linked_pages():
    fixture=Fixture();reader=fixture.reader(max_depth=0);reader.allow_url('https://example.org/')
    assert reader.read('https://example.org/')['status']=='complete'
    assert reader.read('https://example.org/about')['error']=='url_not_discovered'
    assert len(fixture.requests)==1


def test_page_budget_and_repeat_cache_are_real_request_limits():
    fixture=Fixture();reader=fixture.reader(max_pages=1);reader.allow_url('https://example.org/')
    assert reader.read('https://example.org/')['status']=='complete'
    assert reader.read('https://example.org/')['status']=='complete'
    assert len(fixture.requests)==1
    assert reader.read('https://example.org/about')['status']=='limit_reached'
    reader.begin_run()
    assert reader.read('https://example.org/about')['status']=='complete' and len(fixture.requests)==2


def test_parallel_repeat_does_not_remove_another_reads_socket_guard():
    entered=threading.Event();release=threading.Event()
    async def handler(request):
        entered.set()
        while not release.is_set():await asyncio.sleep(.005)
        return httpx.Response(200,headers={'content-type':'text/html'},text=HTML)
    fixture=Fixture(handler);reader=fixture.reader();reader.allow_url('https://example.org/')
    completed=[]
    worker=threading.Thread(target=lambda:completed.append(reader.read('https://example.org/')))
    worker.start();assert entered.wait(2)
    try:
        assert reader.read('https://example.org/')['error']=='already_reading'
        assert reader.read('https://example.org/')['error']=='already_reading'
    finally:
        release.set();worker.join(3)
    assert len(fixture.requests)==1 and completed[0]['status']=='complete'


@pytest.mark.parametrize('addresses',[['127.0.0.1'],['1.1.1.1','10.0.0.1'],['::ffff:127.0.0.1'],['168.63.129.16']])
def test_private_dns_or_mixed_dns_results_never_open_a_socket(addresses):
    async def resolver(host,port):return addresses
    fixture=Fixture(resolver=resolver);reader=fixture.reader();reader.allow_url('https://example.org/')
    result=reader.read('https://example.org/')
    assert result['status']=='blocked' and not fixture.requests


def test_dns_rebinding_cannot_change_numeric_socket_target():
    attempts=[]
    class Backend:
        async def connect_tcp(self,host,port,**kwargs):
            attempts.append((host,port));return object()
    pinned=PinnedNetworkBackend('example.org',443,['1.1.1.1'],Backend())
    asyncio.run(pinned.connect_tcp('example.org',443,timeout=1))
    assert attempts==[('1.1.1.1',443)]
    # A core request may not reuse the backend for another host/port.
    with pytest.raises(PageReadError):asyncio.run(pinned.connect_tcp('attacker.example',443))
    with pytest.raises(PageReadError):asyncio.run(pinned.connect_unix_socket('/private'))


def test_each_redirect_gets_a_new_dns_check_and_private_redirect_is_blocked():
    fixture=Fixture(lambda request:httpx.Response(302,headers={'location':'http://127.0.0.1/admin'}))
    reader=fixture.reader();reader.allow_url('https://example.org/')
    assert reader.read('https://example.org/')['status']=='blocked' and len(fixture.requests)==1


def test_redirect_to_private_dns_is_blocked_without_second_request():
    async def resolver(host,port):return ['1.1.1.1'] if host=='example.org' else ['192.168.0.1']
    fixture=Fixture(lambda request:httpx.Response(302,headers={'location':'https://other.example.org/'}),resolver)
    reader=fixture.reader();reader.allow_url('https://example.org/')
    assert reader.read('https://example.org/')['error']=='private_or_service_address'
    assert len(fixture.requests)==1 and len(fixture.resolutions)==2


def test_valid_redirect_records_final_url_and_has_no_cookie_carryover():
    def handler(request):
        if request.url.path=='/':return httpx.Response(302,headers={'location':'https://example.net/done','set-cookie':'secret=session'})
        return httpx.Response(200,headers={'content-type':'text/html'},text=HTML)
    fixture=Fixture(handler);reader=fixture.reader();reader.allow_url('https://example.org/')
    result=reader.read('https://example.org/')['results'][0]
    assert result['url']=='https://example.net/done'
    assert result['details']['requested_url']=='https://example.org/' and len(result['details']['redirects'])==1
    assert 'cookie' not in fixture.requests[-1].headers and len(fixture.resolutions)==2


@pytest.mark.parametrize('status',[202,401,403,429,500])
def test_challenge_auth_rate_limit_and_server_errors_are_not_fabricated_page_content(status):
    fixture=Fixture(lambda request:httpx.Response(status,headers={'content-type':'text/html'},text=HTML))
    reader=fixture.reader();reader.allow_url('https://example.org/')
    outcome=reader.read('https://example.org/')
    assert not outcome['results'] and outcome['status'] in ('auth_required','unavailable') and len(fixture.requests)==1


def test_captcha_in_successful_http_response_is_not_bypassed():
    fixture=Fixture(lambda request:httpx.Response(200,headers={'content-type':'text/html'},text='<div class="g-recaptcha">challenge</div>'))
    reader=fixture.reader();reader.allow_url('https://example.org/')
    assert reader.read('https://example.org/')['error']=='access_challenge' and len(fixture.requests)==1


def test_legacy_encoding_is_decoded_from_html_meta():
    text='<html><head><meta charset="windows-1251"><title>Пример</title></head><body>Кириллица страницы</body></html>'
    fixture=Fixture(lambda request:httpx.Response(200,headers={'content-type':'text/html'},content=text.encode('cp1251')))
    reader=fixture.reader();reader.allow_url('https://example.org/')
    assert 'Кириллица' in reader.read('https://example.org/')['results'][0]['description']


def test_oversized_or_binary_response_never_becomes_page_evidence():
    for headers,payload in [({'content-type':'application/pdf'},b'PDF'),({'content-type':'text/html'},b'x'*(MAX_BYTES+1))]:
        fixture=Fixture(lambda request:httpx.Response(200,headers=headers,content=payload))
        reader=fixture.reader();reader.allow_url('https://example.org/')
        assert not reader.read('https://example.org/')['results']


def test_cancellation_and_deadline_stop_before_later_requests():
    event=threading.Event();event.set();fixture=Fixture();reader=fixture.reader();reader.allow_url('https://example.org/')
    assert reader.read('https://example.org/',cancel_event=event)['status']=='cancelled' and not fixture.requests
    assert reader.read('https://example.org/',deadline=time.monotonic()-1)['status']=='timeout' and not fixture.requests


def test_javascript_only_page_reports_limit_not_invented_rendered_content():
    fixture=Fixture(lambda request:httpx.Response(200,headers={'content-type':'text/html'},text='<html><title>Shell</title><div id="app"></div><script src="app.js"></script></html>'))
    reader=fixture.reader();reader.allow_url('https://example.org/')
    outcome=reader.read('https://example.org/')
    assert any('JavaScript' in item for item in outcome['limitations'])
    assert 'app.js' not in outcome['results'][0]['details']['content_text']


def test_registry_adds_page_tool_and_uses_only_evidence_or_explicit_human_urls():
    settings=Settings(ai_provider='deepseek')
    registry=ToolRegistry(settings,readiness=lambda *a,**k:{'runtime_ready':False},secret_getter=lambda name:'')
    fixture=Fixture();registry.web_reader=fixture.reader()
    assert 'web_read' in {item['function']['name'] for item in registry.schemas()}
    assert registry.execute('web_read',{'url':'https://example.org/'})['status']=='blocked'
    registry.seed_urls_from_user('Прочитай https://example.org/')
    outcome=registry.execute('web_read',{'url':'https://example.org/'})
    assert outcome['status']=='complete' and outcome['results'][0]['evidence_id'].startswith('ev_')
    assert outcome['results'][0]['provenance']['tool']=='web_read'
    assert registry.execute('web_read',{'url':'file:///private'})['status']=='invalid_arguments'
    assert not registry.execute('web_read',{'url':'https://example.org/','headers':{'Authorization':'x'}})['results']
