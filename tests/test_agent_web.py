"""Local HTTP transport fixtures; not evidence of live search availability."""
import asyncio
import json
import logging
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from grangerpet.agent_web import WebSearchProvider, lookup_domain, lookup_ip
from grangerpet.engine.models import Result


class Fixture:
    def __init__(self, handler):
        self.handler, self.requests, self.clients = handler, [], []

    def factory(self, **kwargs):
        async def handle(request):
            self.requests.append(request)
            response = self.handler(request)
            return await response if hasattr(response, '__await__') else response
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle), **kwargs)
        self.clients.append(client)
        return client


def test_keyless_provider_dispatches_to_documented_public_sources(monkeypatch):
    from grangerpet import public_sources
    calls=[]
    def search(query,**kwargs):
        calls.append((query,kwargs))
        return {'tool':'web_search','status':'partial','results':[],
                'limitations':['Fixture: public source unreachable'],'source_attempts':[{'source':'github_users','status':'unavailable'}]}
    monkeypatch.setattr(public_sources,'search',search)
    provider=WebSearchProvider()
    result=provider.search('solvnox',limit=3)
    assert provider.provider=='public_sources' and provider.availability()['available']
    assert calls[0][0]=='solvnox' and calls[0][1]['limit']==3
    assert result['source_attempts'][0]['source']=='github_users'


def test_optional_google_cse_success_and_safe_public_fallback_on_failure(caplog,monkeypatch):
    secret = 'LOCAL-TRANSPORT-ONLY-CSE-FIXTURE'
    fixture = Fixture(lambda _: httpx.Response(200, json={'items': [
        {'title': 'Источник', 'link': 'https://example.org/fact', 'snippet': 'Настоящий фрагмент фикстуры'}]}))
    provider = WebSearchProvider(SimpleNamespace(api_key=secret, api_cx='fixture-cx'), client_factory=fixture.factory)
    with caplog.at_level(logging.INFO, logger='httpx'):
        result = provider.search('русский текст', limit=3)
    assert provider.availability()['state'] == 'configured'
    assert result['results'][0]['platform'] == 'google_cse'
    assert fixture.requests[0].url.host == 'www.googleapis.com'
    assert fixture.requests[0].url.params['key'] == secret
    assert fixture.requests[0].url.params['num'] == '3'
    assert secret not in caplog.text and secret not in json.dumps(result)
    failed = Fixture(lambda _: httpx.Response(403, json={'error': {'message': secret}}))
    forwarded=[]
    def public(query,**kwargs):
        forwarded.append(kwargs)
        return {'tool':'web_search','status':'empty','results':[],'limitations':[]}
    monkeypatch.setattr('grangerpet.public_sources.search',public)
    result = WebSearchProvider(SimpleNamespace(api_key=secret, api_cx='fixture-cx'), client_factory=failed.factory).search('one')
    assert result['status'] == 'empty' and len(failed.requests) == 1 and forwarded
    assert secret not in json.dumps(result)
    assert secret not in repr(forwarded)


@pytest.mark.parametrize('query,limit', [('',1),('x'*301,1),('x\nsecret',1),('ok',0),('ok',11),('ok',True)])
def test_search_validation_precedes_any_public_dispatch(query,limit,monkeypatch):
    monkeypatch.setattr('grangerpet.public_sources.search',lambda *a,**k:pytest.fail('No public request permitted'))
    assert WebSearchProvider().search(query,limit=limit)['status']=='invalid_arguments'


def test_configured_api_cancellation_timeout_and_response_limit(monkeypatch):
    event=threading.Event()
    async def pending(_):
        event.set();await asyncio.sleep(5);return httpx.Response(200,json={})
    fixture=Fixture(pending);provider=WebSearchProvider(SimpleNamespace(api_key='SYNTHETIC-CSE-KEY',api_cx='fixture-cx'),client_factory=fixture.factory)
    start=time.monotonic();result=provider.search('test',cancel_event=event)
    assert result['status']=='cancelled' and time.monotonic()-start<1
    assert all(client.is_closed for client in fixture.clients)
    assert provider.search('test',deadline=time.monotonic()-.1)['status']=='timeout'
    monkeypatch.setattr('grangerpet.public_sources.search',lambda *a,**k:{'status':'empty','results':[],'limitations':[]})
    large=Fixture(lambda _:httpx.Response(200,content=b'x'*2_000_001))
    result=WebSearchProvider(SimpleNamespace(api_key='SYNTHETIC-CSE-KEY',api_cx='fixture-cx'),client_factory=large.factory).search('test')
    assert any('response_too_large' in warning for warning in result['limitations'])


def test_domain_lookup_has_real_dns_types_rdap_provenance_and_no_arbitrary_hosts():
    def handle(request):
        if request.url.host == 'dns.google':
            return httpx.Response(200, json={'Status': 0, 'Answer': [{'type': 5, 'TTL': 120, 'data': 'actual-cname.example.org.'}]})
        assert request.url.host == 'rdap.publicinterestregistry.org'
        return httpx.Response(200, json={'objectClassName': 'domain', 'ldhName': 'EXAMPLE.ORG', 'handle': 'actual-fixture-handle', 'status': ['active'],
                                       'entities': [{'vcardArray': ['PRIVATE-CONTACT-NOT-FOR-MODEL']}]})
    fixture = Fixture(handle)
    result = lookup_domain('example.org', client_factory=fixture.factory)
    assert result['status'] == 'complete' and len(result['results']) == 4
    assert all(Result.from_dict(row).type == 'domain' for row in result['results'])
    assert result['results'][0]['details']['record_type'] == 'CNAME'
    assert result['results'][0]['details']['query_type'] == 'A'
    assert 'PRIVATE-CONTACT' not in json.dumps(result)
    assert len(fixture.requests) == 4


def test_domain_negative_dns_is_an_observation_not_registration_claim():
    fixture = Fixture(lambda _: httpx.Response(200, json={'Status': 3}))
    result = lookup_domain('absent.example.edu', client_factory=fixture.factory)
    assert result['status'] == 'partial' and len(result['results']) == 3
    assert all(row['details']['response_code'] == 3 for row in result['results'])
    assert any('RDAP' in text for text in result['limitations'])


@pytest.mark.parametrize('target', ['localhost', 'router.local', '127.0.0.1', 'https://example.org', 'example.org/path', 'user@example.org', 'bad;cmd.com', 'x.invalid', 'x.onion'])
def test_domain_validation_blocks_non_domains_before_network(target):
    fixture = Fixture(lambda _: (_ for _ in ()).throw(AssertionError('Unexpected HTTP')))
    assert lookup_domain(target, client_factory=fixture.factory)['status'] == 'invalid_arguments'
    assert not fixture.requests


def test_domain_cancellation_preserves_already_observed_records():
    cancelled = threading.Event()
    async def handle(request):
        if request.url.params['type'] == 'A':
            return httpx.Response(200, json={'Status': 0, 'Answer': [{'type': 1, 'data': '93.184.215.14'}]})
        cancelled.set()
        await asyncio.sleep(10)
        return httpx.Response(200, json={'Status': 0})
    fixture = Fixture(handle)
    result = lookup_domain('example.edu', client_factory=fixture.factory, cancel_event=cancelled)
    assert result['status'] == 'cancelled' and len(result['results']) == 1
    assert result['results'][0]['details']['value'] == '93.184.215.14'


def test_public_ip_lookup_returns_source_asn_prefix_without_claiming_geolocation():
    fixture = Fixture(lambda _: httpx.Response(200, json={'status': 'ok', 'data': {'asns': ['13335'], 'prefix': '1.1.1.0/24'}}))
    result = lookup_ip('1.1.1.1', client_factory=fixture.factory)
    assert result['status'] == 'complete' and len(result['results']) == 1
    row = result['results'][0]
    assert Result.from_dict(row).type == 'ip'
    assert row['details']['asns'] == ['13335'] and row['details']['prefix'] == '1.1.1.0/24'
    assert fixture.requests[0].url.host == 'stat.ripe.net'
    assert 'Порты не сканировались' in result['limitations'][0]


@pytest.mark.parametrize('target', ['127.0.0.1', '192.168.0.1', '10.0.0.1', '169.254.169.254', '::1', 'fe80::1', '224.0.0.1', '1.1.1.1;cmd', 'http://1.1.1.1', 'fe80::1%eth0'])
def test_ip_lookup_rejects_local_reserved_or_command_arguments(target):
    fixture = Fixture(lambda _: (_ for _ in ()).throw(AssertionError('Unexpected HTTP')))
    assert lookup_ip(target, client_factory=fixture.factory)['status'] == 'invalid_arguments'
    assert not fixture.requests
