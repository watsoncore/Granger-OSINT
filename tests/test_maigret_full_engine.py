"""Offline contracts and owned process fixtures; these tests never query a site."""
import asyncio
from contextlib import nullcontext
import json
from pathlib import Path
import ssl
import sys
import threading
from types import SimpleNamespace as NS

import pytest

from grangerpet.engine import maigret_bridge as bridge, runtime
from grangerpet.engine.maigret_contracts import INPUT_SCHEMA, normalize_options
from grangerpet.tool_inputs import validate_object


def site(name="One", **changes):
    values = dict(name=name, url="{urlMain}/{username}", url_main="https://example.com", url_subpath="",
        url_probe=None, similar_search=False, protection=[], protocol="", activation=None,
        request_method="GET", request_payload=None, tags=[])
    return NS(**(values | changes))


class Database:
    def __init__(self, sites):
        self.sites = list(sites.values())
        self.rows = sites

    def ranked_sites_dict(self, **kwargs):
        rows = self.rows
        if kwargs.get("names"):
            rows = {k: v for k, v in rows.items() if k in kwargs["names"]}
        return dict(list(rows.items())[:kwargs.get("top", len(rows))])


def check(state="CLAIMED", **changes):
    return NS(**(dict(status=NS(name=state), error=None, ids_data={}, tags=[]) | changes))


def test_modes_do_not_turn_site_count_into_result_limit():
    database = Database({str(n): site(str(n)) for n in range(9001)})
    full = normalize_options({"mode": "full"})
    selected, eligible, skipped = bridge.select_sites(database, "тест", full)
    assert len(selected) == len(eligible) == 9001 and not skipped
    standard = normalize_options({"mode": "standard"})
    assert len(bridge.select_sites(database, "тест", standard, {"top_sites_count": 500})[0]) == 500
    custom = validate_object({"username": "тест", "mode": "custom", "site_count": 9001}, INPUT_SCHEMA)
    assert normalize_options(custom)["site_count"] == 9001
    with pytest.raises(ValueError):
        normalize_options({"mode": "full", "site_count": 20})
    with pytest.raises(ValueError):
        normalize_options({"concurrency": True})


def test_template_urls_and_all_policy_exclusions_are_explicit():
    assert not bridge.skip_reason(site(), "тест")
    assert "%D1%82" in bridge.formatted_url(site(), "тест")
    cases = [({"protection": ["tls_fingerprint"]}, "protected"),
        ({"activation": {"method": "login"}}, "activation"),
        ({"headers": {"Authorization": "fixture"}}, "credential_headers"),
        ({"url_probe": "http://example.com/{username}"}, "non_public_https"),
        ({"url_main": "https://127.0.0.1"}, "non_public_https"),
        ({"request_method": "POST"}, "non_read_method"),
        ({"similar_search": True}, "similar_search"),
        ({"protocol": "tor"}, "unsupported_protocol:tor")]
    for changes, reason in cases:
        assert bridge.skip_reason(site(**changes), "fixture") == reason


@pytest.mark.parametrize("state,http,error,expected", [
    ("CLAIMED", 200, None, "found"), ("AVAILABLE", 404, None, "not_found"),
    ("CLAIMED", 403, None, "blocked"), ("AVAILABLE", 429, None, "blocked"),
    ("AVAILABLE", 503, None, "unavailable"), ("UNKNOWN", 0, "Request timeout", "unavailable"),
    ("UNKNOWN", 200, "CAPTCHA", "blocked"), ("UNKNOWN", 200, None, "unknown"),
    ("UNKNOWN", 0, "Unexpected", "errors"), ("ILLEGAL", 0, "Unsupported username format", "skipped")])
def test_unknown_access_restrictions_and_negative_results_are_distinct(state, http, error, expected):
    assert bridge.classify({"status": check(state, error=NS(type=error) if error else None), "http_status": http}) == expected


def fake_engine(monkeypatch, coroutine, count=55):
    database = Database({str(n): site(str(n)) for n in range(count)})
    checking = NS(maigret=coroutine)
    monkeypatch.setattr(bridge, "load_engine", lambda root: (checking, database, {},
        {"engine_version": "fixture", "database_sha256": "a" * 64, "database_total": count, "enabled_username": count}))
    monkeypatch.setattr(bridge, "verified_transport", lambda module: nullcontext())


def test_original_output_container_streams_all_findings_and_actual_unicode_metadata(monkeypatch):
    events = []
    async def original(username, sites, logger, **kwargs):
        for name in sites:
            kwargs["output_container"][name] = {"status": check(ids_data={"fullname": "Имя", "bio": "Привет", "avatar": "https://example.com/a.png"}),
                "url_user": "https://example.com/" + name, "http_status": 200, "ids_links": ["https://example.net/"]}
        await asyncio.sleep(.15)
        assert len([e for e in events if e["event"] == "result"]) == 55
        return kwargs["output_container"]
    fake_engine(monkeypatch, original)
    result = bridge.run_adapter(Path("unused"), {"text": "тест", "limit": 1, "timeout": 5},
        {"maigret": {"mode": "full", "time_budget": 5}, "_emit": events.append})
    assert result["status"] == "complete" and len(result["results"]) == 55
    assert result["results"][0]["details"]["full_name"] == "Имя"
    assert result["results"][0]["details"]["identity_match"] == "unconfirmed"
    assert result["source_diagnostics"]["coverage"]["checked"] == 55
    assert len(result["source_diagnostics"]["site_checks"]) == 55


def test_original_partial_output_survives_internal_deadline(monkeypatch):
    async def original(username, sites, logger, **kwargs):
        kwargs["output_container"]["0"] = {"status": check(), "url_user": "https://example.com/0", "http_status": 200}
        await asyncio.sleep(5)
    fake_engine(monkeypatch, original, 3)
    result = bridge.run_adapter(Path("unused"), {"text": "fixture", "timeout": .65}, {"maigret": {"mode": "full"}})
    assert result["status"] == "timeout" and len(result["results"]) == 1
    assert result["source_diagnostics"]["coverage"]["pending"] == 2
    assert result["source_diagnostics"]["resumption"]["native_durable_resume"] is False


def test_transport_enforces_verified_tls_no_environment_proxy_and_public_redirects(monkeypatch):
    try:
        import aiohttp
    except ImportError:
        # The GUI runtime deliberately has no vendor aiohttp dependency. The
        # constructor contract is also exercised with real aiohttp separately
        # in the installed, isolated Maigret interpreter.
        from types import ModuleType
        aiohttp = ModuleType("aiohttp")
        resolver_module = ModuleType("aiohttp.resolver")
        class Resolver:
            async def resolve(self, *args):
                return [{"host": "93.184.216.34"}]
            async def close(self):
                pass
        resolver_module.ThreadedResolver = Resolver
        aiohttp.TraceConfig = lambda: NS(on_request_start=[], on_request_redirect=[])
        aiohttp.ClientSession = None
        aiohttp.TCPConnector = None
        aiohttp.ClientResponse = object
        monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)
        monkeypatch.setitem(sys.modules, "aiohttp.resolver", resolver_module)
    captured = {}
    class Base:
        cookie_jar = None
        url = "https://example.com/test"
        headers = None
        allow_redirects = True
        timeout = 1
        method = "get"
        logger = None
        payload = None
        async def _make_request(self, session, *args):
            return "Привет", 200, None
    class Session:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(aiohttp, "ClientSession", Session)
    monkeypatch.setattr(aiohttp, "TCPConnector", lambda **kwargs: captured.setdefault("connector_config", kwargs))
    checking = NS(SimpleAiohttpChecker=Base, CheckError=lambda *args: NS(type=args[0]))
    async def run():
        with bridge.verified_transport(checking) as Checker:
            assert await Checker().check() == ("Привет", 200, None)
            config = captured["connector_config"]
            assert config["ssl"].verify_mode == ssl.CERT_REQUIRED and config["ssl"].check_hostname is True
            assert captured["trust_env"] is False
            trace = captured["trace_configs"][0]
            context = NS(redirect_count=0)
            for url in ("http://example.com", "https://127.0.0.1", "https://10.1.2.3", "https://host.local"):
                with pytest.raises(ValueError):
                    await trace.on_request_redirect[0](None, context, NS(url="https://example.com", response=NS(headers={"Location": url})))
                context.redirect_count = 0
            from aiohttp.resolver import ThreadedResolver
            async def private(self, *args):
                return [{"host": "192.168.0.1"}]
            monkeypatch.setattr(ThreadedResolver, "resolve", private)
            with pytest.raises(OSError):
                await config["resolver"].resolve("example.com")
            await config["resolver"].close()
        assert checking.SimpleAiohttpChecker is Base
    asyncio.run(run())


def test_oversized_response_stream_is_never_truncated_into_a_false_negative():
    class Stream:
        def __init__(self,content):self.content=content
        async def read(self,n):
            value=self.content[:min(n,3)];self.content=self.content[len(value):];return value
    async def run():
        normal=bridge.BoundedContent(Stream('Привет'.encode()),{},maximum=100)
        assert await normal.read()== 'Привет'.encode()
        state={}
        excessive=bridge.BoundedContent(Stream(b'x'*21),state,maximum=20)
        with pytest.raises(ValueError):await excessive.read()
        assert state['body_limit_exceeded'] is True
        assert bridge.classify({'status':check('UNKNOWN',error=NS(type='Response size limit'))})=='unavailable'
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["normal", "cancel", "timeout"])
def test_owned_worker_retains_complete_stream_and_coverage_on_stop(tmp_path, monkeypatch, mode):
    (tmp_path / "maigret-main").mkdir()
    worker = tmp_path / "worker.py"
    row = {"id": "one", "type": "profile", "title": "Один", "platform": "fixture", "url": "https://example.com/one"}
    events = [
        {"event": "maigret_plan", "scheduled_sites": ["one", "two"], "configuration": {"mode": "full"}},
        {"event": "result", "result": row},
        {"event": "maigret_checks", "checks": [{"site": "one", "status": "found"}]},
        {"event": "maigret_progress", "progress": {"checked": 1, "found": 1, "pending": 1, "complete": False}},
    ]
    worker.write_text("import json,sys,time\njson.loads(sys.stdin.readline())\n" +
        "\n".join("print(" + repr(json.dumps(e, ensure_ascii=False)) + ",flush=True)" for e in events) + "\n" +
        ("print(" + repr(json.dumps({"event": "final", "outcome": {"source": "maigret", "status": "complete", "results": [], "streamed_result_count": 1}})) + ",flush=True)\n"
         if mode == "normal" else "time.sleep(10)\n"), encoding="utf-8")
    monkeypatch.setattr(runtime, "__file__", str(tmp_path / "runtime.py"))
    stopped = threading.Event()
    def on_event(event):
        if mode == "cancel" and event.get("event") == "maigret_progress":
            stopped.set()
    result = runtime.run_worker("maigret", {"text": "fixture", "timeout": .8 if mode == "timeout" else 3},
        {"tools_root": str(tmp_path), "runtime_python": sys.executable}, stopped, on_event)
    assert result["status"] == {"normal": "complete", "cancel": "cancelled", "timeout": "timeout"}[mode]
    assert result["results"] == [row]
    diag = result["source_diagnostics"]
    assert diag["coverage"]["found"] == 1 and diag["site_checks"][0]["site"] == "one"
    assert diag["resumption"]["remaining_sites"] == ["two"]
