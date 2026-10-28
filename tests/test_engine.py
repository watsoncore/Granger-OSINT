import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.engine import Result, SearchController, SearchQuery, classify
from grangerpet.engine.models import ResultIndex, canonical_url
from grangerpet.engine import runtime


class ClassificationTests(unittest.TestCase):
    def test_routes_actual_identifier_types(self):
        cases = {"octocat": "auto", "@octocat": "auto", "example.org": "web", "user@example.org": "email", "+44 20 8366 1177": "phone",
                 "https://t.me/telegram": "telegram", "https://vk.com/id1": "vk", "https://instagram.com/instagram/": "instagram",
                 "https://example.org/": "web", 'site:example.org "annual report"': "dork",
                 "0x0000000000000000000000000000000000000000": "blockchain", "several words": "dork"}
        for text, kind in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify(text), kind)

    def test_query_limits_and_invalid_input(self):
        query = SearchQuery(" @octocat ", kind="username", limit=1000, timeout=1000).normalized()
        self.assertEqual((query.text, query.kind, query.limit, query.timeout), ("octocat", "username", 50, 90))
        self.assertEqual(SearchQuery("+44 (20) 8366-1177").normalized().text, "+442083661177")
        for query in (SearchQuery(""), SearchQuery("x\ny"), SearchQuery("x", kind="invalid"), SearchQuery("with space", kind="username")):
            with self.assertRaises(ValueError):
                query.normalized()

    def test_blockchain_routes_all_supplied_gansar_families(self):
        values = ["EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c", "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ", "0:" + "a" * 64,
                  "T" + "a" * 33, "D" + "a" * 32, "9" + "a" * 42, "vitalik.eth"]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(classify(value), "blockchain")
        # A user can explicitly choose Username for an ambiguous long base58 name.
        self.assertEqual(SearchQuery("a" * 32, kind="username").normalized().kind, "username")

    def test_resource_dedup_keeps_attribution_not_identity_merges(self):
        index = ResultIndex()
        first = Result("alice", "A", "profile", "GitHub", "https://GITHUB.com/Alice/?utm_source=x", sources=["maigret"])
        duplicate = Result("other-id", "A", "profile", "GitHub", "https://github.com/Alice", sources=["blackbird"])
        second_platform = Result("alice", "A", "profile", "GitLab", "https://gitlab.com/Alice", sources=["maigret"])
        self.assertTrue(index.add(first)[1])
        merged, new, changed = index.add(duplicate)
        self.assertFalse(new)
        self.assertTrue(changed)
        self.assertEqual(merged.sources, ["maigret", "blackbird"])
        self.assertTrue(index.add(second_platform)[1])
        self.assertEqual(len(index.items), 2)

    def test_untrusted_urls_are_not_actionable(self):
        for url in ("javascript:alert(1)", "file:///secret", "https://user:pass@example.org", "https://["):
            self.assertEqual(canonical_url(url), "")
        self.assertEqual(canonical_url("https://EXAMPLE.org/a?utm_source=x&b=2#section"), "https://example.org/a?b=2")

    def test_distinct_blockchain_observations_keep_same_explorer_url(self):
        index = ResultIndex()
        url = "https://explorer.example.org/address/abc"
        for identifier, kind in (("abc:balance", "balance"), ("abc:label", "label"), ("tx1", "transaction"), ("tx2", "transaction")):
            result = Result(identifier, identifier, kind, "BTC", url, sources=["blockchain"])
            self.assertTrue(index.add(result)[1])
        self.assertEqual(len(index.items), 4)

    def test_final_observation_updates_partial_details_without_mutating_payload(self):
        index = ResultIndex()
        initial = {"id": "a:balance", "type": "balance", "platform": "BTC", "title": "Partial", "details": {"coverage": "partial"}, "sources": ["blockchain"]}
        first = Result.from_dict(initial)
        index.add(first)
        final = Result("a:balance", "Final", "balance", "BTC", details={"coverage": "complete", "amount": "1.0"}, sources=["blockchain"])
        merged, new, changed = index.add(final)
        self.assertFalse(new)
        self.assertTrue(changed)
        self.assertEqual(merged.details["coverage"], "complete")
        self.assertEqual(merged.details["amount"], "1.0")
        self.assertEqual(merged.title, "Final")
        self.assertEqual(initial["details"], {"coverage": "partial"})
        json.dumps(merged.to_dict())  # No self-referential confirmations graph.


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wait(self, controller):
        for _ in range(150):
            QTest.qWait(20)
            if not controller.running:
                self.app.processEvents()
                return
        self.fail("Controller did not finish")

    def test_partial_results_dedup_failure_isolation_and_global_state(self):
        @dataclass
        class Adapter:
            id: str
            label: str = "Profiles"
            kinds: tuple = ("username",)
            def run(self, query, context):
                if self.id == "broken":
                    raise RuntimeError("SECRET query must never leak")
                result = {"id": "same", "title": "Fixture", "type": "profile", "platform": "Example",
                          "url": "https://example.org/u", "status": "detected", "sources": [self.id]}
                context.event({"event": "result", "result": result})
                return {"status": "complete", "results": [result], "checked": 1}
        controller = SearchController(adapters=[Adapter("one"), Adapter("two"), Adapter("broken")])
        states, results, summaries, statuses = [], [], [], []
        controller.state.connect(states.append)
        controller.result.connect(results.append)
        controller.finished.connect(summaries.append)
        controller.source_status.connect(statuses.append)
        self.assertTrue(controller.start(SearchQuery("octocat", kind="username")))
        self._wait(controller)
        self.assertEqual(states, ["thinking", "working", "happy"])
        self.assertEqual(summaries[0].result_count, 1)
        self.assertEqual(set(results[-1].sources), {"one", "two"})
        self.assertTrue(any(item.source == "broken" and item.state == "error" for item in statuses))
        self.assertFalse(any("SECRET" in item.message for item in statuses))

    def test_empty_is_idle_not_happy(self):
        class Empty:
            id, label, kinds = "empty", "Empty", ("username",)
            def run(self, query, context):
                return {"status": "empty", "results": []}
        controller = SearchController(adapters=[Empty()])
        states = []
        controller.state.connect(states.append)
        controller.start(SearchQuery("octocat", kind="username"))
        self._wait(controller)
        self.assertEqual(states[-1], "idle")
        self.assertNotIn("happy", states)

    def test_confirmation_arriving_at_result_cap_is_still_merged(self):
        class Source:
            label, kinds = "Profile", ("username",)
            def __init__(self, name): self.id = name
            def run(self, query, context):
                if self.id == "second": time.sleep(.04)
                return {"status": "complete", "results": [{"id": "account", "title": "Account", "type": "profile",
                    "platform": "GitHub", "url": "https://github.com/octocat", "sources": [self.id]}]}
        controller = SearchController(adapters=[Source("first"), Source("second")])
        results, summaries = [], []
        controller.result.connect(results.append)
        controller.finished.connect(summaries.append)
        controller.start(SearchQuery("octocat", kind="username", limit=1))
        self._wait(controller)
        self.assertEqual(summaries[0].result_count, 1)
        self.assertEqual(set(results[-1].sources), {"first", "second"})

    def test_cancel_cooperative_sources_and_replacement_search(self):
        class Slow:
            id, label, kinds = "slow", "Slow", ("username",)
            def run(self, query, context):
                while not context.cancelled.wait(.02):
                    pass
                return {"status": "cancelled", "results": []}
        controller = SearchController(adapters=[Slow()])
        summaries = []
        controller.finished.connect(summaries.append)
        self.assertTrue(controller.start(SearchQuery("octocat", kind="username")))
        self.assertTrue(controller.start(SearchQuery("other", kind="username")))
        controller.cancel()
        self._wait(controller)
        self.assertTrue(summaries[0].cancelled)
        self.assertEqual(summaries[0].result_count, 0)

    def test_concurrency_never_more_than_two_sources(self):
        lock = threading.Lock()
        counts = {"active": 0, "peak": 0}
        class Source:
            label, kinds = "Profile", ("username",)
            def __init__(self, name): self.id = name
            def run(self, query, context):
                with lock:
                    counts["active"] += 1
                    counts["peak"] = max(counts["peak"], counts["active"])
                time.sleep(.05)
                with lock: counts["active"] -= 1
                return {"status": "empty", "results": []}
        controller = SearchController(adapters=[Source(str(i)) for i in range(6)])
        controller.start(SearchQuery("octocat", kind="username"))
        self._wait(controller)
        self.assertEqual(counts["peak"], 2)


class TransportTests(unittest.TestCase):
    def _run(self, body, *, timeout=2, cancellation=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "maigret-main").mkdir()
            (root / "worker.py").write_text("import json,sys,time\nrequest=json.loads(sys.stdin.readline())\n" + body, encoding="utf-8")
            with patch.object(runtime, "__file__", str(root / "runtime.py")):
                events = []
                result = runtime.run_worker("maigret", {"text": "fixture", "timeout": timeout},
                    {"tools_root": str(root), "runtime_python": sys.executable}, cancellation or threading.Event(), events.append)
            return result, events

    def test_actual_hidden_subprocess_json_and_partial_delivery(self):
        body = 'item={"id":"x","title":"fixture","platform":"test","type":"profile"}\nprint(json.dumps({"event":"result","result":item}),flush=True)\nprint(json.dumps({"event":"final","outcome":{"status":"complete","results":[item]}}),flush=True)\n'
        result, events = self._run(body)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(events[0]["event"], "result")

    def test_timeout_kills_source_and_keeps_partial(self):
        body = 'print(json.dumps({"event":"result","result":{"id":"partial"}}),flush=True)\ntime.sleep(10)\n'
        started = time.monotonic()
        result, _ = self._run(body, timeout=.2)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["results"], [{"id": "partial"}])
        self.assertLess(time.monotonic() - started, 2)

    def test_cancel_terminates_blocked_source(self):
        cancelled = threading.Event()
        timer = threading.Timer(.15, cancelled.set)
        timer.start()
        try:
            result, _ = self._run("time.sleep(10)\n", cancellation=cancelled)
            self.assertEqual(result["status"], "cancelled")
        finally:
            timer.cancel()

    def test_oversized_output_is_bounded(self):
        result, _ = self._run('print("x"*1000001,flush=True)\ntime.sleep(10)\n')
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
