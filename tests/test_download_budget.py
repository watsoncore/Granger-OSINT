import asyncio
import httpx
import pytest
from grangerpet.download_budget import CURRENT, DownloadBudget, DownloadLimit
from grangerpet.agent_web import _fetch
from grangerpet.web_http import fetch_public
from test_agent_tools import Adapter, registry


def test_streamed_http_bytes_are_shared_and_next_request_never_starts_after_limit():
    requests = []
    budget = DownloadBudget(10)
    def reply(request):
        requests.append(request)
        return httpx.Response(200, content=b'123456')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            assert await _fetch(client, 'https://example.org/one') == b'123456'
            with pytest.raises(DownloadLimit):
                await _fetch(client, 'https://example.org/two')
            with pytest.raises(DownloadLimit):
                await _fetch(client, 'https://example.org/three')
    token = CURRENT.set(budget)
    try: asyncio.run(run())
    finally: CURRENT.reset(token)
    assert len(requests) == 2
    assert budget.snapshot()['used_bytes'] == 12


def test_pinned_public_transport_obeys_same_budget():
    requests = []
    budget = DownloadBudget(4)
    async def resolver(host, port): return ['93.184.216.34']
    def factory(**kwargs):
        def reply(request):
            requests.append(request)
            return httpx.Response(200, headers={'content-type': 'text/plain'}, content=b'12345')
        return httpx.AsyncClient(transport=httpx.MockTransport(reply))
    token = CURRENT.set(budget)
    try:
        with pytest.raises(DownloadLimit):
            asyncio.run(fetch_public('https://example.org/', resolver=resolver, client_factory=factory, rate_interval=0))
    finally: CURRENT.reset(token)
    assert len(requests) == 1 and budget.used == 5


def test_registry_turns_limit_into_real_limited_status_and_keeps_budget_after_restore():
    class BudgetAdapter(Adapter):
        def run(self, query, context):
            from grangerpet.download_budget import consume
            consume(11)
    reg, _ = registry(BudgetAdapter())
    reg._download_budget = DownloadBudget(10)
    result = reg.execute('username_maigret', {'username': 'fixture'})
    assert result['status'] == 'limit_reached' and result['error_code'] == 'download_limit'
    assert result['download_budget']['used_bytes'] == 11
    restored, _ = registry()
    restored.restore_investigation([], reg.checkpoint_state())
    assert restored.checkpoint_state()['downloaded_bytes'] == 11
    assert restored._download_budget.snapshot()['legacy_CLI_metered'] is False
