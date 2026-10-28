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


HTML = '''<!doctype html><html><body>
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fprofile">Example <b>public</b> profile</a>
<a class="result__snippet">Actual indexed description<br> with кириллица.</a></div>
<a class="result__a" href="javascript:alert(1)">Invalid URL</a>
<a class="result__a" href="https://127.0.0.1/admin">Private destination</a>
<a class="result__a" href="https://example.org/profile">Duplicate</a>
</body></html>'''


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


def test_keyless_search_parses_real_markup_urls_snippets_and_deduplicates():
    fixture = Fixture(lambda _: httpx.Response(200, text=HTML))
    provider = WebSearchProvider(client_factory=fixture.factory)
    assert provider.availability()['state'] == 'unverified'
    result = provider.search('solvnox', limit=5)
    assert result['status'] == 'complete' and len(result['results']) == 1
    row = result['results'][0]
    assert row['url'] == 'https://example.org/profile'
    assert row['title'] == 'Example public profile'
    assert 'Actual indexed description' in row['description'] and 'кириллица' in row['description']
    assert row['details']['query'] == 'solvnox' and row['date']
    assert Result.from_dict(row).confirmed
    assert len(fixture.requests) == 1 and fixture.requests[0].url.host == 'html.duckduckgo.com'
    assert fixture.requests[0].url.params['q'] == 'solvnox'
    assert all(client.is_closed for client in fixture.clients)


@pytest.mark.parametrize('status,body', [(202, ''), (403, ''), (429, ''), (200, '<form action="anomaly.js">Challenge</form>')])
def test_challenges_are_unavailable_without_retry_or_endpoint_bypass(status, body):
    fixture = Fixture(lambda _: httpx.Response(status, text=body))
    provider = WebSearchProvider(client_factory=fixture.factory)
    first, second = provider.search('one'), provider.search('two')
    assert first['status'] == second['status'] == 'unavailable'
    assert first['results'] == second['results'] == []
    assert not provider.availability()['available']
    assert len(fixture.requests) == 1


def test_unknown_html_is_not_false_empty_search():
    fixture = Fixture(lambda _: httpx.Response(200, text='<html>Maintenance</html>'))
    result = WebSearchProvider(client_factory=fixture.factory).search('test')
    assert result['status'] == 'unavailable' and result['error_code'] == 'unrecognized_search_response'


def test_explicit_no_results_is_honest_empty():
    fixture = Fixture(lambda _: httpx.Response(200, text='<div class="no-results">No results found</div>'))
    result = WebSearchProvider(client_factory=fixture.factory).search('no-match')
    assert result['status'] == 'empty' and result['results'] == []


def test_configured_google_cse_is_used_without_automatic_provider_fallback(caplog):
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
    result = WebSearchProvider(SimpleNamespace(api_key=secret, api_cx='fixture-cx'), client_factory=failed.factory).search('one')
    assert result['status'] == 'unavailable' and len(failed.requests) == 1
    assert secret not in json.dumps(result)


@pytest.mark.parametrize('query,limit', [('', 1), ('x'*301, 1), ('x\nsecret', 1), ('ok', 0), ('ok', 11), ('ok', True)])
def test_search_validation_precedes_network(query, limit):
    fixture = Fixture(lambda _: (_ for _ in ()).throw(AssertionError('Unexpected HTTP')))
    result = WebSearchProvider(client_factory=fixture.factory).search(query, limit=limit)
    assert result['status'] == 'invalid_arguments' and not fixture.requests


def test_search_cancellation_and_timeout_close_http_and_stop_waiting():
    cancelled = threading.Event()
    async def pending(_):
        cancelled.set()
        await asyncio.sleep(10)
        return httpx.Response(200, text=HTML)
    fixture = Fixture(pending)
    start = time.monotonic()
    result = WebSearchProvider(client_factory=fixture.factory).search('test', cancel_event=cancelled)
    assert result['status'] == 'cancelled' and time.monotonic()-start < 1
    assert all(client.is_closed for client in fixture.clients)
    fixture = Fixture(pending)
    result = WebSearchProvider(client_factory=fixture.factory).search('test', deadline=time.monotonic()-.01)
    assert result['status'] == 'timeout' and not fixture.requests


def test_search_response_size_bound():
    fixture = Fixture(lambda _: httpx.Response(200, content=b'x'*2_000_001))
    result = WebSearchProvider(client_factory=fixture.factory).search('test')
    assert result['status'] == 'unavailable' and result['error_code'] == 'response_too_large'


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
