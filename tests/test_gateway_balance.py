import json

import httpx
import pytest

from grangerpet.gateway_balance import BALANCE_URL, GatewayBalance, fetch_balance


def transport(payload=None, status=200):
    def request(req):
        assert str(req.url) == BALANCE_URL
        assert req.method == 'GET'
        assert req.headers['Authorization'] == 'Bearer fixture-secret'
        assert 'fixture-secret' not in str(req.url)
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(request)


def test_real_field_keeps_unknown_units_and_utf8():
    row = fetch_balance('fixture-secret', transport=transport({'object': 'balance', 'token_balance': '12345.67'}))
    assert row['amount'] == '12345.67'
    assert row['unit'] == 'gateway_units'
    assert row['updated_at']
    assert 'не документировано' in row['message']


@pytest.mark.parametrize('status', [301, 401, 402, 403, 404, 429, 500])
def test_errors_never_echo_vendor_body_or_key(status):
    row = fetch_balance('fixture-secret', transport=transport({'error': 'fixture-secret'}, status))
    assert row['status'] == 'unavailable'
    assert 'fixture-secret' not in json.dumps(row)
    assert row['http_status'] == status


@pytest.mark.parametrize('value', [None, True, {}, -1, 'NaN', 'Infinity', 'fixture-secret', '1e100',
                                 '1e-1000000000','0e-999999999'])
def test_untrusted_amounts_are_not_accepted(value):
    row = fetch_balance('fixture-secret', transport=transport({'token_balance': value}))
    assert row['status'] == 'invalid_response'
    assert row['amount'] is None


def test_missing_credential_does_not_call_network():
    assert fetch_balance('', transport=httpx.MockTransport(lambda _: pytest.fail('network')))['status'] == 'not_configured'


def test_cache_is_independent_and_keeps_last_success_stale():
    cache = GatewayBalance()
    assert cache.prepare('fixture-secret')
    assert not cache.prepare('fixture-secret', force=True)
    cache.finish({'status': 'available', 'amount': '12', 'updated_at': 'time', 'unit': 'gateway_units'})
    cache._requested_at = 0
    assert cache.prepare('fixture-secret', force=True)
    cache.finish({'status': 'unavailable', 'error': 'failure'})
    assert cache.snapshot()['stale'] is True
    assert cache.snapshot()['amount'] == '12'
    assert cache.prepare('changed-secret')
    assert cache.snapshot()['amount'] is None


def test_cancelled_pending_request_can_be_retried_with_same_key():
    cache=GatewayBalance()
    assert cache.prepare('fixture-secret')
    cache.cancel_pending()
    assert cache.snapshot()['status']!='checking'
    assert cache.prepare('fixture-secret',force=True)
