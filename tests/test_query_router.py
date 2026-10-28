"""Deterministic validation and actual adapter dispatch: no live-service claims."""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.engine import SearchController, SearchQuery, SearchResult, SourceExecution
from grangerpet.engine.adapters import default_adapters, select_adapters
from grangerpet.engine.models import Result, ResultIndex, canonical_url, is_confirmed
from grangerpet.engine.router import detect_query, validate_ton


def friendly(tag=0x11, body=bytes(32)):
    payload = bytes([tag, 0]) + body
    return base64.urlsafe_b64encode(payload + binascii.crc_hqx(payload, 0).to_bytes(2, "big")).decode()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_until(app, predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError("Search controller did not complete")


@pytest.mark.parametrize("address", [friendly(), friendly(0x51), "0:" + "ab" * 32, "-1:" + "aB" * 32])
def test_ton_calls_supplied_validator_and_routes_only_existing_gansar(address):
    with patch("grangerpet.engine.router.validate_ton", wraps=validate_ton) as real:
        resolution = detect_query("  " + address + "  ")
    assert real.call_count >= 1
    assert resolution.valid and not resolution.requires_clarification
    assert resolution.kind == "blockchain" and resolution.chain == "ton"
    assert resolution.adapter_ids == ("blockchain",)
    request = SearchQuery(resolution.text, resolution.kind).normalized()
    assert request.options["chain"] == "ton"
    assert [item.id for item in select_adapters(request, {}, default_adapters(), verify_runtime=False)] == ["blockchain"]


@pytest.mark.parametrize("address", [friendly()[:-1] + "A", "EQ" + "A" * 46, "UQ" + "A" * 46, "0:" + "g" * 64])
def test_invalid_ton_never_falls_through_to_profiles(address):
    resolution = detect_query(address)
    assert not resolution.valid
    assert "TON" in resolution.error
    assert resolution.adapter_ids == ()
    with pytest.raises(ValueError):
        SearchQuery(address).normalized()


def test_ton_dns_support_is_not_invented():
    resolution = detect_query("wallet.ton")
    assert not resolution.valid and "нет прямого разрешения" in resolution.error


@pytest.mark.parametrize("tag", [0x91, 0xd1])
def test_testnet_tag_is_not_lost_by_mainnet_raw_normalization(tag):
    resolution = detect_query(friendly(tag))
    assert not resolution.valid and "testnet" in resolution.error
    assert not resolution.adapter_ids


def test_solvnox_requires_per_query_explicit_direction():
    resolution = detect_query("solvnox")
    assert resolution.requires_clarification and resolution.kind == "auto"
    assert dict(resolution.choices) == {"Публичные профили": "username", "Упоминания": "dork"}
    with pytest.raises(ValueError):
        SearchQuery("solvnox").normalized()
    assert detect_query("solvnox", "username").kind == "username"
    assert detect_query("solvnox", "dork").adapter_ids == ("google",)
    assert detect_query("another-name").requires_clarification


@pytest.mark.parametrize("text,kind,adapter,normalized", [
    ("t.me/telegram/1", "telegram", "telegram", "https://t.me/telegram/1"),
    ("https://t.me/s/telegram/20", "telegram", "telegram", "https://t.me/telegram/20"),
    ("m.vk.com/id1", "vk", "vk", "https://vk.com/id1"),
    ("vk.com/public123", "vk", "vk", "https://vk.com/public123"),
    ("club123", "vk", "vk", "https://vk.com/club123"),
    ("instagram.com/instagram", "instagram", "instagram", "https://www.instagram.com/instagram"),
    ("https://example.org/Path", "web", "wayback", "https://example.org/Path"),
    ("example.org", "web", "wayback", "https://example.org/"),
    ("Test@пример.рф", "email", "holehe", "Test@xn--e1afmkfd.xn--p1ai"),
    ("+7 (999) 123-45-67", "phone", "phoneinfoga", "+79991234567"),
])
def test_deterministic_public_inputs_and_single_relevant_adapter(text, kind, adapter, normalized):
    resolution = detect_query(text)
    assert resolution.valid, resolution.error
    assert resolution.kind == kind and resolution.text == normalized
    selected = select_adapters(SearchQuery(resolution.text, kind), {}, default_adapters(), verify_runtime=False)
    assert [item.id for item in selected] == [adapter]


@pytest.mark.parametrize("text", ["person..name@example.org", "bad@host", "+70000000000", "t.me/+private", "https://t.me/c/123/1", "file:///secret"])
def test_invalid_specialized_input_does_not_run_a_random_source(text):
    assert not detect_query(text).valid


def test_dotted_nickname_unknown_tld_asks_instead_of_archiving_arbitrary_text():
    resolution = detect_query("some.nick")
    assert resolution.requires_clarification
    assert detect_query("some.nick", "username").kind == "username"


def test_default_username_plan_avoids_three_duplicate_profile_catalogs():
    def readiness(source, _, cancelled=None):
        return {"runtime_ready": source != "maigret"}
    with patch("grangerpet.engine.readiness.runtime_readiness", side_effect=readiness):
        selected = select_adapters(SearchQuery("solvnox", "username"), {}, default_adapters())
    assert [item.id for item in selected] == ["blackbird"]


def test_execution_objects_and_invalid_profile_rows_can_never_be_hits():
    assert SearchResult is Result
    assert not isinstance(SourceExecution("maigret", "complete"), Result)
    rows = [{"source": "maigret", "status": "complete"}, {"id": "m", "title": "Source done", "type": "execution", "platform": "Profiles"},
            {"id": "account", "title": "Account", "type": "profile", "platform": "GitHub", "url": ""},
            {"id": "account", "title": "Account", "type": "profile", "platform": "GitHub", "url": "https://github.com/test", "status": "complete"}]
    for value in rows:
        with pytest.raises(ValueError):
            Result.from_dict(value)


def test_profile_dedup_aliases_tracking_and_confirmations_without_identity_merge():
    index = ResultIndex()
    raw = {"id": "solvnox", "title": "solvnox", "type": "profile", "platform": "GitHub", "url": "http://www.github.com/SolvNox/?utm_source=a", "status": "heuristic"}
    first = Result.from_dict(raw, "social_analyzer")
    assert index.add(first)[1]
    second = Result.from_dict({**raw, "url": "https://github.com/solvnox", "status": "detected"}, "maigret")
    merged, new, _ = index.add(second)
    assert not new and is_confirmed(merged)
    assert set(merged.sources) == {"social_analyzer", "maigret"}
    assert index.add(Result.from_dict({**raw, "platform": "GitLab", "url": "https://gitlab.com/solvnox", "status": "detected"}, "maigret"))[1]
    assert len(index.items) == 2
    assert canonical_url("https://example.org/Case") != canonical_url("https://example.org/case")
    assert canonical_url("https://github.com/Case/Repo/blob/main/CaseFile") != canonical_url("https://github.com/Case/Repo/blob/main/casefile")
    assert canonical_url("http://www.youtube.com/@SolvNox/about?utm_source=x") == canonical_url("https://youtube.com/@solvnox")


def test_blockchain_confirmation_field_does_not_collide_with_source_evidence():
    for confirmations in (None, 0, 42):
        index = ResultIndex()
        value = {"id": "tx", "title": "Transaction", "type": "transaction", "platform": "TON",
                 "status": "verified", "details": {"confirmations": confirmations}, "sources": ["blockchain"]}
        index.add(Result.from_dict(value))
        merged, new, _ = index.add(Result.from_dict(value))
        assert not new
        assert merged.details["confirmations"] is confirmations
        assert merged.details["source_confirmations"] == {"blockchain": "verified"}


def test_ton_is_actually_dispatched_only_to_gansar_and_real_findings_delivered(app):
    calls, findings, executions, summaries = [], [], [], []
    @dataclass
    class Adapter:
        id: str
        kinds: tuple
        label: str = "Fixture source"
        def run(self, query, context):
            calls.append((self.id, query.text, query.options))
            value = {"id": "ton:balance", "type": "balance", "platform": "TON", "title": "TON · 0", "details": {"amount": "0"}, "status": "verified"}
            return {"status": "complete", "results": [value], "checked": 1}
    controller = SearchController(adapters=[Adapter("blockchain", ("blockchain",)), Adapter("maigret", ("username",)), Adapter("phoneinfoga", ("phone",))])
    controller.result.connect(findings.append)
    controller.source_status.connect(executions.append)
    controller.finished.connect(summaries.append)
    assert controller.start(friendly())
    wait_until(app, lambda: len(summaries) == 1)
    assert [row[0] for row in calls] == ["blockchain"]
    assert calls[0][2]["chain"] == "ton"
    assert len(findings) == summaries[0].result_count == summaries[0].confirmed_count == 1
    assert all(isinstance(item, SourceExecution) for item in executions)


def test_status_only_sources_report_zero_findings_and_separate_execution_count(app):
    class Adapter:
        id, label, kinds = "source", "Profiles", ("username",)
        def run(self, query, context):
            return {"status": "complete", "results": [{"source": "x", "status": "complete"}, {"status": "empty"}], "checked": 3}
    controller = SearchController(adapters=[Adapter()])
    hits, summaries = [], []
    controller.result.connect(hits.append)
    controller.finished.connect(summaries.append)
    controller.start(SearchQuery("solvnox", "username"))
    wait_until(app, lambda: bool(summaries))
    assert hits == []
    assert summaries[0].confirmed_count == summaries[0].result_count == 0
    assert summaries[0].checked_sources == 1
    assert summaries[0].phase == "completed_empty"


def test_cancel_and_replace_drops_late_old_findings_at_both_generation_boundaries(app):
    old_started, release_old = threading.Event(), threading.Event()
    class Adapter:
        id, label, kinds = "source", "Profiles", ("username",)
        def run(self, query, context):
            if query.text == "old":
                old_started.set()
                release_old.wait(2)
                context.event({"event": "result", "result": {"id": "old", "title": "OLD", "type": "profile", "platform": "Example", "url": "https://example.org/old", "status": "verified"}})
            return {"status": "complete", "results": [{"id": query.text, "title": query.text, "type": "profile", "platform": "Example", "url": "https://example.org/" + query.text, "status": "verified"}]}
    controller = SearchController(adapters=[Adapter()])
    events = []
    controller.search_event.connect(lambda *args: events.append(args))
    assert controller.start(SearchQuery("old", "username"))
    wait_until(app, old_started.is_set)
    old_generation = controller.generation
    controller.cancel()
    assert controller.start(SearchQuery("new", "username"))
    new_generation = controller.generation
    release_old.set()
    wait_until(app, lambda: any(g == new_generation and kind == "finished" for g, kind, _ in events))
    assert new_generation > old_generation
    assert [value.title for g, kind, value in events if g == new_generation and kind == "result"] == ["new"]
    assert not any(g == old_generation and kind == "result" for g, kind, _ in events)


def test_cold_readiness_probe_is_cancelled_and_does_not_run_search(app):
    from grangerpet.engine import readiness
    readiness._CACHE.clear()
    probe_started, probe_cancelled = threading.Event(), threading.Event()
    def slow_probe(source, query, options, cancelled, event=None):
        assert options.get("operation") == "probe"
        probe_started.set()
        assert cancelled.wait(2)
        probe_cancelled.set()
        return {"status": "cancelled", "results": []}
    controller = SearchController()
    summaries = []
    controller.finished.connect(summaries.append)
    with patch("grangerpet.engine.readiness.run_worker", side_effect=slow_probe):
        assert controller.start(SearchQuery("solvnox", "username"))
        wait_until(app, probe_started.is_set)
        controller.cancel()
        wait_until(app, lambda: bool(summaries))
    assert probe_cancelled.is_set()
    assert summaries[0].cancelled and summaries[0].result_count == 0
    assert not readiness._CACHE, "A cancelled probe must not cache false unavailability"


def test_readiness_and_searches_share_one_global_two_process_budget():
    from grangerpet.engine import runtime
    active = {"current": 0, "peak": 0}
    lock = threading.Lock()
    def blocked(*args, **kwargs):
        with lock:
            active["current"] += 1
            active["peak"] = max(active["peak"], active["current"])
        time.sleep(.04)
        with lock:
            active["current"] -= 1
        return {"status": "ready", "results": []}
    with patch.object(runtime, "_run_worker", side_effect=blocked):
        threads = [threading.Thread(target=runtime.run_worker, args=("maigret", {}, {"operation": "probe"} if index % 2 else {}, threading.Event())) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
    assert active["peak"] == 2


def test_summary_reports_routing_without_serializing_credentials():
    import json
    from grangerpet.engine.models import SearchSummary
    options = {"source_root": "C:/tools", "chain": "ton", "google_api_key": "SECRET-GOOGLE", "secrets": {"vk_token": "SECRET-VK"},
               "nested": {"telegram_api_hash": "SECRET-HASH", "allowed": True}, "api_key": "SECRET-LEGACY"}
    summary = SearchSummary(SearchQuery("0:" + "ab" * 32, "blockchain", options=options), 0, False, [], .1)
    encoded = json.dumps(summary.to_dict())
    assert "SECRET" not in encoded
    assert summary.to_dict()["query"]["options"] == {"source_root": "C:/tools", "chain": "ton", "nested": {"allowed": True}}
    assert summary.query.options["google_api_key"] == "SECRET-GOOGLE", "Only serialization is redacted; actual adapters still need credentials"


def test_missing_platform_credentials_route_to_auth_required_not_username_search(app):
    from grangerpet.engine.adapters import SourceAdapter
    for text, source in (("t.me/telegram/1", "telegram"), ("vk.com/id1", "vk")):
        controller = SearchController(adapters=default_adapters())
        summaries = []
        controller.finished.connect(summaries.append)
        with patch("grangerpet.engine.adapters.run_worker", side_effect=AssertionError("Must not make an unauthorized request")):
            assert controller.start(text)
            wait_until(app, lambda: bool(summaries))
        assert [item.source for item in summaries[0].statuses] == [source]
        assert summaries[0].statuses[0].state == "auth_required"
        assert summaries[0].result_count == 0
