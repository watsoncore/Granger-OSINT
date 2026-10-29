"""Regressions use explicit local MockTransport; Qt tests execute real JS offline."""
import asyncio
import json
import threading
import time

import httpx
import pytest

from grangerpet.agent_browser import PageParser,PageReadError,PublicPageReader
from grangerpet.web_http import fetch_public
from grangerpet.web_render import render_html
from grangerpet.web_scraping import ScrapeResult


class Fixture:
    def __init__(self,handler):self.handler=handler;self.requests=[]
    async def resolve(self,host,port):return ['93.184.216.34']
    def factory(self,**options):
        def transport(request):
            self.requests.append(request)
            return self.handler(request)
        options['transport']=httpx.MockTransport(transport)
        return httpx.AsyncClient(**options)
    def reader(self,**options):
        return PublicPageReader(resolver=self.resolve,client_factory=self.factory,rate_interval=0,**options)
    def fetch(self,url,**options):
        return asyncio.run(fetch_public(url,resolver=self.resolve,client_factory=self.factory,rate_interval=0,**options))


def test_structured_html_preserves_origin_but_never_declares_a_person_identified():
    html='''<html><head><title>Actual fixture</title><link rel="canonical" href="/canonical">
    <meta property="og:type" content="profile"><meta name="author" content="Public Author">
    <script type="application/ld+json">{"@type":"Person","name":"Fixture"}</script></head>
    <body><article data-record-id="public-17"><h1>A public record</h1><time datetime="2026-10-29">Today</time>
    <p>Public source content, independently extracted from the fixture HTML and retained as a source observation.</p></article></body></html>'''
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'text/html'},text=html))
    reader=f.reader();reader.allow_url('https://example.org/a')
    out=reader.read('https://example.org/a');row=out['results'][0];s=row['details']['scrape_result']
    assert out['status']=='complete' and row['status']=='content_observed'
    assert s['extraction_status']=='record_extracted' and s['method']=='HTTP_GET'
    assert s['structured_data']['canonical_url']=='https://example.org/canonical'
    assert s['structured_data']['authors'][0]['value']=='Public Author'
    assert s['structured_data']['records'][0]['url']=='https://example.org/a'
    assert any(row['attributes'].get('data-record-id')=='public-17' for row in s['structured_data']['html_attributes'])
    assert s['evidence_id'] is None


@pytest.mark.parametrize('content_type,payload,record',[('application/rss+xml','''<rss><channel><title>Feed</title><item><title>Real fixture item</title><link>https://example.org/post</link><pubDate>2026-10-29</pubDate></item></channel></rss>''','Real fixture item'),
    ('application/atom+xml','''<feed xmlns="http://www.w3.org/2005/Atom"><title>Feed</title><entry><title>Atom item</title><id>item-1</id><link href="https://example.org/item"/></entry></feed>''','Atom item'),
    ('application/json','[{"title":"JSON item","id":17}]','JSON item')])
def test_real_parsers_decode_rss_atom_and_json_records(content_type,payload,record):
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':content_type},text=payload))
    reader=f.reader();reader.allow_url('https://example.org/feed')
    s=reader.scrape('https://example.org/feed')
    assert isinstance(s,ScrapeResult) and s.http_status==200 and s.extraction_status=='record_extracted'
    assert record in json.dumps(s.structured_data)


@pytest.mark.parametrize('mime,payload',[('application/xml','<!DOCTYPE root [<!ENTITY x SYSTEM "file:///C:/secret">]><root>&x;</root>'),
    ('application/xml','<broken>'),('application/json','{broken')])
def test_unsafe_or_invalid_structured_payloads_never_produce_findings(mime,payload):
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':mime},text=payload))
    reader=f.reader();reader.allow_url('https://example.org/unsafe')
    out=reader.read('https://example.org/unsafe')
    assert out['status']=='unavailable' and out['results']==[]


def test_xml_declared_legacy_encoding_preserves_russian_text():
    xml='<?xml version="1.0" encoding="windows-1251"?><root><title>Публичный источник</title></root>'
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'application/xml'},content=xml.encode('cp1251')))
    reader=f.reader();reader.allow_url('https://example.org/data')
    assert 'Публичный источник' in reader.scrape('https://example.org/data').extracted_text


@pytest.mark.parametrize('html,status',[('<html><body></body></html>','partial'),
    ('<html><head><title>Empty body</title></head><body></body></html>','partial'),
    ('<input type=password name=password>','auth_required'),('<div class=cf-chl-test>challenge</div>','unavailable')])
def test_empty_login_and_challenge_are_not_successful_public_reads(html,status):
    calls=[]
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'text/html'},text=html))
    reader=f.reader(allow_browser=True,browser_renderer=lambda *a,**k:calls.append(1))
    reader.allow_url('https://example.org/a');out=reader.read('https://example.org/a')
    assert out['status']==status and out['results']==[] and calls==[]


def test_entity_encoded_password_attribute_is_detected_by_inert_html_parser():
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'text/html'},text='<input type="pass&#119;ord"><p>Log in to view private source information.</p>'))
    reader=f.reader();reader.allow_url('https://example.org/a')
    result=reader.read('https://example.org/a')
    assert result['status']=='auth_required' and result['results']==[]


def test_inert_json_ld_record_is_not_a_javascript_shell_or_browser_execution():
    html='<script type="application/ld+json">{"@type":"Article","name":"Public structured record"}</script>'
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'text/html'},text=html))
    reader=f.reader(allow_browser=True,browser_renderer=lambda *a,**k:pytest.fail('JSON-LD is inert data'))
    reader.allow_url('https://example.org/record');result=reader.read('https://example.org/record')
    assert result['status']=='complete' and result['results'][0]['details']['content_fetched']
    assert result['results'][0]['details']['extraction_status']=='record_extracted'


def test_post_public_search_is_explicitly_reviewed_and_rejects_credentials():
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'application/json'},json={'matches':[{'id':1}]}))
    with pytest.raises(PageReadError):f.fetch('https://example.org/search',method='POST',form={'q':'public'})
    with pytest.raises(PageReadError):f.fetch('https://example.org/search',method='POST',form={'password':'bad'},approved_post=True)
    result=f.fetch('https://example.org/search',method='POST',form={'q':'Публичная запись'},approved_post=True)
    assert result['status']==200 and len(f.requests)==1 and f.requests[0].method=='POST'
    assert b'q=' in f.requests[0].content and 'authorization' not in f.requests[0].headers


def test_scoped_cookies_persist_only_for_the_same_origin_in_this_reader():
    def response(request):
        if request.url.path=='/first':return httpx.Response(200,headers={'content-type':'text/plain','set-cookie':'public_session=fixture; Path=/'},text='First public page')
        return httpx.Response(200,headers={'content-type':'text/plain'},text='Second public page')
    f=Fixture(response);reader=f.reader()
    for url in ('https://example.org/first','https://example.org/second','https://example.net/third'):
        reader.allow_url(url);reader.read(url)
    assert f.requests[1].headers['cookie']=='public_session=fixture'
    assert 'cookie' not in f.requests[2].headers
    assert 'public_session' not in json.dumps(reader.checkpoint_state())


def test_cache_has_a_real_ttl_and_expired_content_is_fetched_again():
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'text/plain'},text='A public cached observation'))
    reader=f.reader(cache_ttl=.01);reader.allow_url('https://example.org/a')
    reader.read('https://example.org/a');reader.read('https://example.org/a')
    assert len(f.requests)==1
    time.sleep(.03);reader.read('https://example.org/a')
    assert len(f.requests)==2


def test_retry_is_bounded_and_403_is_never_retried_or_rendered():
    calls=[0]
    def response(request):
        calls[0]+=1
        return httpx.Response(503 if calls[0]==1 else 200,headers={'content-type':'text/plain'},text='Public second response')
    f=Fixture(response);assert f.fetch('https://retry.example.org/a')['status']==200 and len(f.requests)==2
    blocked=Fixture(lambda _:httpx.Response(403))
    with pytest.raises(PageReadError):blocked.fetch('https://blocked.example.org/a')
    assert len(blocked.requests)==1


def test_actual_shared_request_scheduler_bounds_parallelism_per_domain():
    active=[0];peak=[0]
    async def response(request):
        active[0]+=1;peak[0]=max(peak[0],active[0])
        try:
            await asyncio.sleep(.025)
            return httpx.Response(200,headers={'content-type':'text/plain'},text='Public bounded response')
        finally:active[0]-=1
    f=Fixture(response)
    async def batch(same_domain):
        return await asyncio.gather(*(fetch_public('https://'+('one' if same_domain else str(i))+'.scheduler.example.org/a',
            resolver=f.resolve,client_factory=f.factory,rate_interval=0) for i in range(8)))
    asyncio.run(batch(False));assert 2<=peak[0]<=4
    peak[0]=0;asyncio.run(batch(True));assert peak[0]==1


def test_explicit_source_error_status_is_returned_even_without_content_type():
    f=Fixture(lambda _:httpx.Response(404,content=b''))
    result=f.fetch('https://example.org/missing',accepted_statuses=(200,404))
    assert result['status']==404 and result['body']==b''


def test_internal_application_identity_is_ascii_bounded_and_model_specific():
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'text/plain'},text='Public source content'))
    reader=f.reader(agent_model='deepseek-v4-flash');reader.allow_url('https://identity.example.org/a')
    assert reader.read('https://identity.example.org/a')['status']=='complete'
    assert 'model=deepseek-v4-flash' in f.requests[0].headers['user-agent']
    with pytest.raises(PageReadError):f.fetch('https://identity.example.org/a',user_agent='unsafe\r\nHeader: value')


def test_html_complexity_is_bounded_and_boolean_attributes_are_safe():
    p=PageParser('https://example.org/');p.feed('<script type></script><link rel><input required>')
    with pytest.raises(PageReadError):p.feed('<p>'*25_001)


def test_shell_to_browser_contract_requires_actual_useful_extracted_dom():
    f=Fixture(lambda _:httpx.Response(200,headers={'content-type':'text/html'},text='<div id="app"></div><script>/* fixture */</script>'))
    reader=f.reader(allow_browser=True,browser_renderer=lambda *a,**k:{'status':'rendered','html':'<main><p>Actual fixture rendered body with useful source text, independently extracted and kept separate from a search snippet.</p></main>'})
    reader.allow_url('https://example.org/js');out=reader.read('https://example.org/js')
    assert out['status']=='complete' and out['results'][0]['details']['reading_method']=='browser_dom'
    assert out['results'][0]['details']['scrape_result']['method']=='browser_dom'


def test_real_offline_qt_worker_executes_delayed_javascript_and_denies_network():
    html='''<html><head></head><body><div id="app"></div><script>
    fetch('http://127.0.0.1/private').catch(()=>{});
    let denied=false;try{new Worker('https://example.org/worker.js')}catch{denied=true}
    setTimeout(()=>{document.getElementById('app').innerText='Actual offline DOM evidence from real JavaScript. Private network and worker requests were denied: '+denied},40)
    </script></body></html>'''
    result=render_html(html,deadline=time.monotonic()+12)
    assert result['status']=='rendered' and 'were denied: true' in result['html']
    assert result['network_mode']=='offline_pinned_prefetched_classic_scripts'


def test_real_offline_worker_cancellation_does_not_wait_for_untrusted_infinite_js():
    cancel=threading.Event();timer=threading.Timer(.6,cancel.set);timer.start();start=time.monotonic()
    try:
        result=render_html('<html><body><script>while(true){}</script></body></html>',cancel_event=cancel,deadline=time.monotonic()+12)
    finally:timer.join()
    assert result['status']=='cancelled' and time.monotonic()-start<5


def test_robots_denial_prevents_document_request_and_browser_render():
    def handle(request):
        assert request.url.path=='/robots.txt'
        return httpx.Response(200,text='User-agent: *\nDisallow: /private',headers={'content-type':'text/plain'})
    f=Fixture(handle);reader=f.reader(respect_robots=True,allow_browser=True,browser_renderer=lambda *a,**k:pytest.fail('No renderer for forbidden URL'))
    reader.allow_url('https://example.org/private')
    result=reader.read('https://example.org/private')
    assert result['status']=='blocked' and result['error']=='robots_disallowed' and not result['results']
    assert len(f.requests)==1


@pytest.mark.parametrize('robot_status',[200,404])
def test_robots_allow_and_missing_policy_support_real_document_extraction(robot_status):
    def handle(request):
        if request.url.path=='/robots.txt':return httpx.Response(robot_status,text='User-agent: *\nAllow: /',headers={'content-type':'text/plain'})
        return httpx.Response(200,text='<main>Public document text with an actual useful sentence from the test transport.</main>',headers={'content-type':'text/html'})
    f=Fixture(handle);reader=f.reader(respect_robots=True);reader.allow_url('https://example.org/public')
    result=reader.read('https://example.org/public')
    assert result['status']=='complete' and result['results'][0]['details']['content_fetched']
    assert [r.url.path for r in f.requests]==['/robots.txt','/public']


def test_redirect_target_robots_is_checked_before_target_document():
    def handle(request):
        if request.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nDisallow: /denied',headers={'content-type':'text/plain'})
        assert request.url.path=='/start'
        return httpx.Response(302,headers={'location':'https://example.org/denied'})
    f=Fixture(handle);reader=f.reader(respect_robots=True);reader.allow_url('https://example.org/start')
    assert reader.read('https://example.org/start')['error']=='robots_disallowed'
    assert [r.url.path for r in f.requests]==['/robots.txt','/start']
