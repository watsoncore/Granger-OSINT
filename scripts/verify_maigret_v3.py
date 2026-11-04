"""Offline Maigret V3 verification, with an explicitly requested six-site probe.

Run with .toolenvs/maigret/Scripts/python.exe -I -B. No installation, DB update,
settings write or profile access. Network requests occur ONLY with --live.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import ssl
import sys
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "grangerpet/engine"))
logging.disable(logging.CRITICAL)
import maigret_bridge as bridge

TARGETS = ["GitHub", "YouTube", "TikTok", "Wikipedia", "WordPressOrg", "GooglePlayStore"]


def verify_transport(checking):
    import aiohttp
    captured = {}
    class Session:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    async def make_request(self, session, *args):
        return "Проверка UTF-8", 200, None
    async def run():
        original = checking.SimpleAiohttpChecker
        with bridge.verified_transport(checking) as Checker:
            with patch.object(aiohttp, "ClientSession", Session), patch.object(aiohttp, "TCPConnector",
                    lambda **kwargs: captured.setdefault("connector_arguments", kwargs)), patch.object(Checker, "_make_request", make_request):
                checker = Checker(dns_resolver="threaded")
                checker.prepare("https://example.com/test", timeout=1)
                assert await checker.check() == ("Проверка UTF-8", 200, None)
                context = captured["connector_arguments"]["ssl"]
                assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
                assert captured["trust_env"] is False
                trace = captured["trace_configs"][0]
                refusals = 0
                for url in ("http://example.com", "https://127.0.0.1", "https://10.0.0.1", "https://host.local"):
                    try:
                        await trace.on_request_redirect[0](None, NS(redirect_count=0), NS(url="https://example.com", response=NS(headers={"Location": url})))
                    except ValueError:
                        refusals += 1
                assert refusals == 4
                from aiohttp.resolver import ThreadedResolver
                async def private(*args, **kwargs):
                    return [{"host": "192.168.0.1"}]
                resolver = captured["connector_arguments"]["resolver"]
                with patch.object(ThreadedResolver, "resolve", private):
                    try:
                        await resolver.resolve("example.com")
                    except OSError:
                        pass
                    else:
                        raise AssertionError("Private DNS address accepted")
                await resolver.close()
        assert checking.SimpleAiohttpChecker is original
    asyncio.run(run())
    return {"real_aiohttp": aiohttp.__version__, "tls_verified": True, "trust_env": False,
            "private_dns_refused": True, "unsafe_redirects_refused": 4, "vendor_class_restored": True,
            "network_requests": 0}


def live_comparison(username):
    checking, database, defaults, identity = bridge.load_engine(ROOT / "maigret-main")
    config = bridge.normalize_options({"mode": "custom", "sites": TARGETS, "site_count": 0,
        "include_mirrors": False, "per_site_timeout": 3, "concurrency": 3, "time_budget": 25, "parse_metadata": True})
    selected, eligible, skipped = bridge.select_sites(database, username, config, defaults)
    if len(selected) > 12 or set(selected) != set(eligible) or skipped:
        raise ValueError("Bounded comparison selection changed; inspect the database before network use")
    raw = {}
    async def original():
        with bridge.verified_transport(checking):
            await asyncio.wait_for(checking.maigret(username, eligible, logging.getLogger("maigret.qa"),
                timeout=3, max_connections=3, no_progressbar=True, retries=0, is_parsing_enabled=True,
                is_enrich_enabled=False, check_domains=False, cloudflare_bypass=None,
                dns_resolver="threaded", output_container=raw), timeout=25)
    original_start = datetime.now(timezone.utc).isoformat()
    native_status = "complete"
    try:
        asyncio.run(original())
    except asyncio.TimeoutError:
        native_status = "timeout"
    original_end = datetime.now(timezone.utc).isoformat()
    native_checks = []
    for name, item in raw.items():
        check = item.get("status")
        native_checks.append({"site": name, "native_status": getattr(getattr(check, "status", None), "name", "UNKNOWN"),
            "mapped_status": bridge.classify(item), "http_status": item.get("http_status"),
            "error_type": str(getattr(getattr(check, "error", None), "type", "")),
            "url": item.get("url_user", ""), "metadata_fields": list((getattr(check, "ids_data", None) or {}).keys())})
    events = []
    adapter_start = datetime.now(timezone.utc).isoformat()
    adapter = bridge.run_adapter(ROOT / "maigret-main", {"text": username, "timeout": 25, "limit": 1},
        {"maigret": config | {"username": username}, "_emit": events.append})
    adapter_end = datetime.now(timezone.utc).isoformat()
    original_by_site = {row["site"]: row["mapped_status"] for row in native_checks}
    adapter_by_site = {row["site"]: row["status"] for row in adapter["source_diagnostics"]["site_checks"]}
    return {"kind": "bounded_original_api_vs_granger_adapter", "username": username, **identity,
        "configuration": config, "sites": list(selected),
        "original": {"status": native_status, "start_utc": original_start, "end_utc": original_end, "checks": native_checks},
        "granger": {"start_utc": adapter_start, "end_utc": adapter_end, "outcome": adapter,
            "streamed_findings": sum(e.get("event") == "result" for e in events),
            "progress_events": sum(e.get("event") == "maigret_progress" for e in events)},
        "status_differences": [{"site": name, "original": original_by_site.get(name), "granger": adapter_by_site.get(name)}
            for name in sorted(set(original_by_site) | set(adapter_by_site)) if original_by_site.get(name) != adapter_by_site.get(name)],
        "limitations": ["Both executions use verified public-only HTTPS transport; the vendor default disables TLS verification.",
            "Original core API comparison, not an unmodified original CLI/full-database network parity claim.",
            "Sequential calls share configuration/database/username but remote responses may change between calls.",
            "No recursive username expansion, enrichment, authentication, CAPTCHA or WAF bypass."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Perform exactly the fixed six-site comparison")
    parser.add_argument("--username", default="solvnox")
    args = parser.parse_args()
    checking, _, _, _ = bridge.load_engine(ROOT / "maigret-main")
    result = {"offline_capability": bridge.capability(ROOT / "maigret-main"), "transport_verification": verify_transport(checking)}
    if args.live:
        if not re_username(args.username):
            raise ValueError("Expected a simple public username")
        result["live_comparison"] = live_comparison(args.username)
    print(json.dumps(result, ensure_ascii=False))


def re_username(value):
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value))


if __name__ == "__main__":
    main()
