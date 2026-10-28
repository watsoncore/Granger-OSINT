"""Explicit bounded live checks of the two requested public search scenarios.

No preset number of hits is expected. This does not verify account-required
Telegram/VK/Instagram or AI providers, and never substitutes fixtures.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from grangerpet.engine import SearchController, SearchQuery
from grangerpet.engine.router import detect_query


def main():
    app = QCoreApplication([])
    output = ROOT / "output/search-overhaul-qa/router-live.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    results = {"method": "Actual SearchController → existing local source processes; no network mocks", "checks": []}
    cases = [("solvnox", "username", 20, 25), ("EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c", None, 12, 35)]
    for text, chosen, limit, timeout in cases:
        detection = detect_query(text, chosen)
        assert detection.valid and not detection.requires_clarification, detection.error
        controller = SearchController()
        hits, stages, summaries, executions = {}, [], [], []
        def event(generation, kind, value):
            if kind == "result":
                from grangerpet.engine.models import result_key
                hits[result_key(value)] = value.to_dict()
            elif kind == "execution":
                executions.append(value.to_dict())
            elif kind == "stage":
                stages.append(value)
            elif kind == "finished":
                summaries.append(value)
        controller.search_event.connect(event)
        options = {"source_root": str(ROOT), "request_limit": limit}
        if detection.chain:
            options["chain"] = detection.chain
        query = SearchQuery(detection.text, detection.kind, limit=limit, timeout=timeout, options=options)
        start = time.monotonic()
        assert controller.start(query)
        while not summaries and time.monotonic() - start < timeout + 20:
            app.processEvents()
            QTest.qWait(15)
        if not summaries:
            controller.cancel()
            raise RuntimeError("Actual source request exceeded this verification's deadline")
        summary = summaries[0]
        entry = {"input": text, "kind": detection.kind, "chain": detection.chain,
                 "normalized": detection.text, "elapsed_seconds": round(time.monotonic() - start, 3),
                 "summary": summary.to_dict(), "findings": list(hits.values()), "stages": stages,
                 "only_expected_sources": all(item.source in detection.adapter_ids for item in summary.statuses),
                 "counter_matches_unique_findings": len(hits) == summary.result_count}
        assert entry["only_expected_sources"] and entry["counter_matches_unique_findings"]
        assert all(item.get("type") not in {"status", "execution"} for item in hits.values())
        results["checks"].append(entry)
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"kind": detection.kind, "sources": [item.source for item in summary.statuses],
                          "phase": summary.phase, "unique_findings": summary.result_count,
                          "confirmed": summary.confirmed_count, "elapsed": entry["elapsed_seconds"]}), flush=True)
        controller.shutdown()
        controller.deleteLater()
        app.processEvents()
    print(str(output))


if __name__ == "__main__":
    main()
