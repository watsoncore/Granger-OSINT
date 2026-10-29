"""Local transport fixtures exercise adapters; these are not live API proofs."""
import asyncio
import json
import logging
import threading
import time

import httpx
import pytest

from grangerpet import public_integrations as public


SHA = 'a' * 64
KEY = 'SYNTHETIC-VIRUSTOTAL-KEY-NOT-REAL'


@pytest.fixture(autouse=True)
def isolated_rate_and_cache(monkeypatch):
    monkeypatch.setattr(public, '_NEXT', {})
    monkeypatch.setattr(public, '_CACHE', {})


class TransportFixture:
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


def github_data(**overrides):
    return {'full_name': 'octocat/Hello-World', 'private': False, 'description': 'Публичный тестовый репозиторий',
            'language': 'Python', 'stargazers_count': 12, 'forks_count': 2, 'private_body': 'must not be copied', **overrides}


def test_github_reads_only_fixed_official_endpoint_and_bounded_public_fields():
    fixture = TransportFixture(lambda _: httpx.Response(200, json=github_data()))
    result = public.execute('github_repository', 'octocat/Hello-World', client_factory=fixture.factory)
    assert result['status'] == 'complete' and len(result['results']) == 1
    row = result['results'][0]
    assert row['title'] == 'octocat/Hello-World'
    assert row['details']['description'] == 'Публичный тестовый репозиторий'
    assert row['details']['acquisition'] == 'official_api'
    assert 'must not be copied' not in json.dumps(result)
    assert str(fixture.requests[0].url) == 'https://api.github.com/repos/octocat/Hello-World'
    assert all(client.is_closed for client in fixture.clients)


@pytest.mark.parametrize('value', ['https://github.com/octocat/Hello-World', '../secret', 'owner/..',
                                  'owner/repo/extra', 'owner/repo?token=x', 'owner/repo\n', 1])
def test_invalid_repository_never_reaches_network(value):
    fixture = TransportFixture(lambda _: pytest.fail('Unexpected request'))
    result = public.execute('github_repository', value, client_factory=fixture.factory)
    assert result['status'] == 'invalid_arguments' and not fixture.requests


@pytest.mark.parametrize('body', [[], {'private': True, 'full_name': 'hidden/repo'}, {'private': False}])
def test_unknown_or_private_github_response_is_not_success(body):
    fixture = TransportFixture(lambda _: httpx.Response(200, json=body))
    result = public.execute('github_repository', 'octocat/Hello-World', client_factory=fixture.factory)
    assert result['status'] != 'complete' and result['results'] == []
    assert result['error_code'] == 'invalid_response'


def test_feodo_returns_observation_and_not_false_safety_for_nonmatch():
    fixture = TransportFixture(lambda _: httpx.Response(200, json=[
        {'ip_address': '8.8.8.8', 'port': 443, 'status': 'online', 'malware': 'SYNTHETIC-FIXTURE'}]))
    found = public.execute('threat_feodo', '8.8.8.8', client_factory=fixture.factory)
    assert found['results'][0]['details']['matched'] is True
    assert found['results'][0]['details']['matches'][0]['malware'] == 'SYNTHETIC-FIXTURE'
    public._NEXT.clear()
    missing = public.execute('threat_feodo', '1.1.1.1', client_factory=fixture.factory)
    assert missing['status'] == 'complete' and missing['results'][0]['details']['matched'] is False
    assert 'не означает безопасность' in missing['results'][0]['description']
    assert all(r.url.host == 'feodotracker.abuse.ch' for r in fixture.requests)


@pytest.mark.parametrize('value', ['127.0.0.1', '10.0.0.1', '::1', '169.254.169.254', '224.0.0.1', 'x.example'])
def test_feodo_private_invalid_or_multicast_targets_rejected(value):
    fixture = TransportFixture(lambda _: pytest.fail('Unexpected request'))
    result = public.execute('threat_feodo', value, client_factory=fixture.factory)
    assert result['status'] == 'invalid_arguments' and not fixture.requests


def test_virustotal_uses_header_only_no_upload_and_drops_unneeded_fields(caplog):
    fixture = TransportFixture(lambda _: httpx.Response(200, json={'data': {'id': SHA, 'attributes': {
        'sha256': SHA, 'size': 10, 'type_description': 'Fixture file',
        'last_analysis_stats': {'malicious': 1, 'undetected': 2}, 'raw_extra': 'not retained'}}}))
    with caplog.at_level(logging.INFO, logger='httpx'):
        result = public.execute('hash_virustotal', SHA.upper(), secret=KEY, client_factory=fixture.factory)
    assert result['status'] == 'complete'
    assert fixture.requests[0].method == 'GET' and fixture.requests[0].content == b''
    assert fixture.requests[0].headers['x-apikey'] == KEY
    assert KEY not in str(fixture.requests[0].url) and KEY not in json.dumps(result) and KEY not in caplog.text
    assert 'not retained' not in json.dumps(result)
    assert result['results'][0]['details']['last_analysis_stats']['malicious'] == 1
    assert all(client.is_closed for client in fixture.clients)


def test_virustotal_missing_key_and_wrong_sha_do_not_request():
    fixture = TransportFixture(lambda _: pytest.fail('Unexpected request'))
    assert public.execute('hash_virustotal', SHA, client_factory=fixture.factory)['status'] == 'auth_required'
    assert public.execute('hash_virustotal', 'sha1', secret=KEY, client_factory=fixture.factory)['status'] == 'invalid_arguments'
    assert not fixture.requests


@pytest.mark.parametrize('code,status', [(401, 'auth_required'), (402, 'auth_required'), (403, 'blocked'),
                                       (404, 'empty'), (429, 'rate_limited'), (503, 'unavailable')])
def test_api_errors_are_not_success_and_do_not_expose_response_bodies(code, status):
    fixture = TransportFixture(lambda _: httpx.Response(code, text=KEY + ' PRIVATE RESPONSE'))
    result = public.execute('hash_virustotal', SHA, secret=KEY, client_factory=fixture.factory)
    assert result['status'] == status and result['results'] == []
    assert result['error_code'] == 'http_' + str(code)
    assert KEY not in json.dumps(result) and 'PRIVATE RESPONSE' not in json.dumps(result)
    assert len(fixture.requests) == 1


def test_stream_cancellation_and_expired_deadline_close_clients():
    cancel = threading.Event()
    async def pending(_):
        cancel.set()
        await asyncio.sleep(10)
        return httpx.Response(200, json=github_data())
    fixture = TransportFixture(pending)
    started = time.monotonic()
    result = public.execute('github_repository', 'octocat/Hello-World', cancel_event=cancel, client_factory=fixture.factory)
    assert result['status'] == 'cancelled' and time.monotonic() - started < 1
    assert all(client.is_closed for client in fixture.clients)
    result = public.execute('github_repository', 'octocat/Hello-World', deadline=time.monotonic() - 1, client_factory=fixture.factory)
    assert result['status'] == 'timeout' and len(fixture.requests) == 1


def test_cancel_during_rate_wait_and_no_slot_leak():
    cancel = threading.Event()
    public._NEXT['github_repository'] = time.monotonic() + 20
    timer = threading.Timer(.05, cancel.set)
    fixture = TransportFixture(lambda _: pytest.fail('Unexpected request'))
    timer.start()
    try:
        result = public.execute('github_repository', 'octocat/Hello-World', cancel_event=cancel, client_factory=fixture.factory)
    finally:
        timer.join()
    assert result['status'] == 'cancelled' and not fixture.requests
    assert public._SLOTS.acquire(blocking=False)
    assert public._SLOTS.acquire(blocking=False)
    public._SLOTS.release(); public._SLOTS.release()


def test_response_limit_and_malformed_json():
    for content, expected in [(b'x' * 2_000_001, 'response_too_large'), (b'{broken', 'invalid_response')]:
        fixture = TransportFixture(lambda _: httpx.Response(200, content=content))
        public._NEXT.clear()
        result = public.execute('github_repository', 'octocat/Hello-World', client_factory=fixture.factory)
        assert result['status'] != 'complete' and result['error_code'] == expected


def test_cache_is_key_scoped_deep_copied_and_still_obeys_cancellation():
    fixture = TransportFixture(lambda _: httpx.Response(200, json={'data': {'id': SHA, 'attributes': {'size': 1}}}))
    first = public.execute('hash_virustotal', SHA, secret=KEY, client_factory=fixture.factory)
    first['results'].clear()
    cached = public.execute('hash_virustotal', SHA, secret=KEY, client_factory=fixture.factory)
    assert cached['results'] and len(fixture.requests) == 1
    assert 'Кэш' in cached['limitations'][-1]
    public._NEXT.clear()
    public.execute('hash_virustotal', SHA, secret='OTHER-SYNTHETIC-KEY', client_factory=fixture.factory)
    assert len(fixture.requests) == 2
    cancel = threading.Event(); cancel.set()
    assert public.execute('hash_virustotal', SHA, secret=KEY, cancel_event=cancel)['status'] == 'cancelled'
    assert public.execute('hash_virustotal', SHA, secret=KEY, deadline=time.monotonic() - 1)['status'] == 'timeout'
