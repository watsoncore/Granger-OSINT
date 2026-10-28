"""Generation-scoped incremental search, separate findings and source executions."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import queue
import threading
import time

from PySide6.QtCore import QObject, Signal

from .adapters import default_adapters, select_adapters
from .models import Result, ResultIndex, SearchQuery, SearchSummary, SourceExecution, is_confirmed
from .router import detect_query


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Context:
    cancelled: threading.Event
    options: dict
    event: object

    def checkpoint(self):
        if self.cancelled.is_set():
            raise InterruptedError("cancelled")


class SearchController(QObject):
    result = Signal(object)
    source_status = Signal(object)
    progress = Signal(int, int)
    finished = Signal(object)
    state = Signal(str)  # Existing Pet activity contract.
    phase = Signal(str)
    stage = Signal(object)
    error = Signal(str)
    # Do not shadow QObject.event. UI filters the generation again at delivery,
    # because Qt may still have queued an old event just before cancellation.
    search_event = Signal(int, str, object)

    def __init__(self, parent=None, adapters=None):
        super().__init__(parent)
        self.adapters = adapters
        self._cancel = threading.Event()
        self._thread = None
        self._generation = 0
        self._closed = False
        self._source_slots = threading.BoundedSemaphore(2)

    @property
    def generation(self):
        return self._generation

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def _emit(self, generation, kind, payload):
        if self._closed or generation != self._generation:
            return
        try:
            # Queued payloads must not mutate when the next source adds proof.
            payload = copy.deepcopy(payload)
            self.search_event.emit(generation, kind, payload)
            if kind == "progress":
                self.progress.emit(*payload)
            else:
                signals = {"result": self.result, "execution": self.source_status,
                           "finished": self.finished, "phase": self.phase,
                           "stage": self.stage, "error": self.error, "state": self.state}
                signal = signals.get(kind)
                if signal:
                    signal.emit(payload)
        except RuntimeError:
            pass  # Qt lifetime ended while a daemon was completing.

    def start(self, query, options=None):
        if self._closed:
            return False
        candidate = SearchQuery(query) if isinstance(query, str) else query
        merged = {**getattr(candidate, "options", {}), **(options or {})}
        try:
            # Validation sees source_root so it can call this checkout's exact
            # Gansar validator (or the frozen copy of the same file).
            candidate = SearchQuery(candidate.text, candidate.kind, candidate.limit, candidate.timeout, merged)
            normalized = candidate.normalized()
        except (ValueError, TypeError, AttributeError) as exc:
            self._emit(self._generation, "error", str(exc))
            detection = detect_query(getattr(candidate, "text", ""), getattr(candidate, "kind", "auto"), merged)
            self._emit(self._generation, "phase", "needs_clarification" if detection.requires_clarification else "failed")
            self._emit(self._generation, "state", "idle" if detection.requires_clarification else "error")
            return False
        # Replacing a query cancels its children and starts a fresh generation.
        # One shared semaphore limits old+new active source processes together.
        self._cancel.set()
        self._generation += 1
        generation = self._generation
        self._cancel = threading.Event()
        self._emit(generation, "phase", "detecting")
        self._emit(generation, "state", "thinking")
        self._thread = threading.Thread(target=self._run,
            args=(normalized, normalized.options, generation, self._cancel), daemon=True,
            name="GrangerPetSearchController")
        self._thread.start()
        return True

    def _run(self, query, options, generation, cancelled):
        started = time.monotonic()
        adapters = self.adapters if self.adapters is not None else default_adapters(options)
        jobs = select_adapters(query, options, adapters, verify_runtime=self.adapters is None, cancelled=cancelled)
        if generation != self._generation or self._closed:
            return
        if cancelled.is_set():
            summary = SearchSummary(query, 0, True, [], time.monotonic() - started, phase="cancelled")
            self._emit(generation, "finished", summary)
            self._emit(generation, "phase", "cancelled")
            self._emit(generation, "state", "idle")
            return
        messages, pending = queue.Queue(), queue.Queue()
        index, executions, source_findings = ResultIndex(), {}, {}
        for adapter in jobs:
            pending.put(adapter)
            execution = SourceExecution(adapter.id, "queued", label=adapter.label)
            executions[adapter.id] = execution
            source_findings[adapter.id] = set()
            self._emit(generation, "execution", execution)
        self._emit(generation, "progress", (0, len(jobs)))
        self._emit(generation, "phase", "searching")
        self._emit(generation, "state", "working" if jobs else "idle")

        def worker():
            while not cancelled.is_set() and not self._closed:
                try:
                    adapter = pending.get_nowait()
                except queue.Empty:
                    return
                acquired = False
                while not cancelled.is_set() and not self._closed:
                    if self._source_slots.acquire(timeout=.05):
                        acquired = True
                        break
                if not acquired:
                    return
                try:
                    if cancelled.is_set():
                        return
                    messages.put(("start", adapter, {}))
                    def event(item, current=adapter):
                        if not cancelled.is_set() and isinstance(item, dict):
                            messages.put(("event", current, item))
                    try:
                        context = Context(cancelled, options, event)
                        outcome = adapter.run(query, context)
                        if not isinstance(outcome, dict):
                            raise ValueError("Invalid adapter output")
                    except InterruptedError:
                        outcome = {"status": "cancelled", "results": [], "message": "Поиск отменён."}
                    except Exception:
                        outcome = {"status": "error", "results": [], "message": "Источник не выполнил запрос. Проверьте подключение и зависимости."}
                    messages.put(("done", adapter, outcome))
                finally:
                    self._source_slots.release()

        workers = [threading.Thread(target=worker, daemon=True, name="GrangerPetSource")
                   for _ in range(min(2, len(jobs)))]
        for thread in workers:
            thread.start()
        completed = 0

        def receive(value, adapter):
            if cancelled.is_set():
                return
            try:
                item = Result.from_dict(value, adapter.id)
            except (ValueError, TypeError):
                return
            if len(index.items) >= query.limit and not index.contains(item):
                return
            resource, new, changed = index.add(item)
            source_findings[adapter.id].add(index.key(item))
            if new or changed:
                self._emit(generation, "result", resource)
                self._emit(generation, "phase", "partial_results")

        while completed < len(jobs) and not self._closed and generation == self._generation:
            if cancelled.is_set():
                # Built-in workers observe cancellation every60ms and kill their
                # source process. No further findings are accepted meanwhile.
                break
            try:
                kind, adapter, payload = messages.get(timeout=.05)
            except queue.Empty:
                continue
            execution = executions[adapter.id]
            if kind == "start":
                execution.state, execution.started_at = "running", _timestamp()
                self._emit(generation, "execution", execution)
                continue
            if kind == "event":
                if payload.get("event") == "result":
                    receive(payload.get("result"), adapter)
                elif payload.get("event") == "stage":
                    self._emit(generation, "stage", {"source": adapter.id, **payload})
                continue
            if kind != "done":
                continue
            for value in payload.get("results", [])[:query.limit] if isinstance(payload.get("results", []), list) else []:
                receive(value, adapter)
            completed += 1
            execution.state = str(payload.get("status", "error"))
            execution.message = str(payload.get("message", ""))[:1000]
            try:
                execution.checked = max(0, int(payload.get("checked", 0)))
            except (ValueError, TypeError, OverflowError):
                execution.checked = 0
            execution.found = len(source_findings[adapter.id])
            execution.finished_at = _timestamp()
            execution.error_code = execution.state if execution.state in {"error", "timeout", "unavailable", "auth_required"} else ""
            self._emit(generation, "execution", execution)
            self._emit(generation, "progress", (completed, len(jobs)))
        if self._closed or generation != self._generation:
            return
        if cancelled.is_set():
            for execution in executions.values():
                if execution.state in ("queued", "running"):
                    execution.state, execution.finished_at = "cancelled", _timestamp()
                    execution.message = "Поиск отменён."
                    self._emit(generation, "execution", execution)
        values = list(index.items.values())
        confirmed = sum(is_confirmed(item) for item in values)
        errors = sum(item.state in {"error", "timeout", "unavailable", "auth_required", "partial"} for item in executions.values())
        all_failed = bool(executions) and all(item.state in {"error", "timeout", "unavailable"} for item in executions.values())
        phase = ("cancelled" if cancelled.is_set() else "failed" if all_failed and not values
                 else "completed_with_errors" if errors else "completed" if values else "completed_empty")
        summary = SearchSummary(query, len(values), cancelled.is_set(), list(executions.values()),
            time.monotonic() - started, phase=phase, confirmed_count=confirmed,
            uncertain_count=len(values) - confirmed,
            checked_sources=sum(item.started_at is not None for item in executions.values()))
        self._emit(generation, "finished", summary)
        self._emit(generation, "phase", phase)
        self._emit(generation, "state", "happy" if confirmed and not cancelled.is_set() else "error" if phase == "failed" else "idle")

    def cancel(self):
        self._cancel.set()

    def shutdown(self):
        self._closed = True
        self._cancel.set()
