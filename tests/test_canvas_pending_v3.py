"""Bounded native shutdown and inert encrypted recovery, without a real profile."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace as NS

import pytest
from PySide6.QtCore import QTimer

from test_master_v3_bridge import finite, wait_until, send, responses
from grangerpet.canvas_pending import MAX_INTENTS, MAX_PENDING_BYTES, PendingCanvasStore, flush_canvas_pending, validate_snapshot
from grangerpet.desktop_surface import DesktopSurface
from grangerpet.research_canvas import apply, new_document


def intent(token="a", label="Заметка", target=None):
    return {"op": "edit", "payload": {"operation": "node", "arguments": {"type": "analyst_note", "label": label}},
        "token": token * 32, **({"target": target} if target else {})}


def recovery(finite, action='research_canvas_queue_recovery'):
    replies=[]
    deferred=finite.dispatch(action,{})
    deferred.subscribe(lambda value,error:replies.append((value,error)))
    wait_until(lambda:bool(replies))
    assert replies[0][1] is None
    return replies[0][0]


def test_pending_queue_is_encrypted_validated_and_never_runs_tools_on_read(finite):
    controller = finite._research_canvas
    controller.document = controller.store.save(new_document(), 0)
    target = controller.document["id"]
    snapshot = {"intents": [intent(target=target), {"op": "tool", "payload": {"entity_id": "x", "tool": "username_maigret",
        "arguments": {"username": "solvnox", "mode": "full"}}, "target": target, "token": "b" * 32}],
        "current": {"id": target, "revision": 1}, "error": "Явный повтор"}
    store = PendingCanvasStore(controller.store)
    identifier = store.save(snapshot)
    ciphertext = store._path(identifier).read_bytes()
    assert "Заметка".encode() not in ciphertext and b"solvnox" not in ciphertext
    loaded = recovery(finite)
    assert loaded["draft_id"] == identifier and loaded["intents"] == snapshot["intents"]
    assert not finite.launched and not controller.document["entities"]
    finite.dispatch("research_canvas_queue_clear", {"draft_id": identifier})
    assert recovery(finite,'research_canvas_queue_read') is None
    with pytest.raises(ValueError):
        finite.dispatch("research_canvas_queue_clear", {"draft_id": "../../outside"})


@pytest.mark.parametrize("change", [
    {"intents": [intent() | {"op": "shell"}]},
    {"intents": [intent() | {"payload": {"path": "C:/private"}}]},
    {"intents": [intent() | {"payload": {"operation": "node", "arguments": {"api_key": "SECRET"}}}]},
    {"intents": [intent() | {"payload": {"operation": "positions", "arguments": {"x": float("nan")}}}]},
    {"intents": [intent()] * 1025}, {"intents": [intent(), intent()]},
    {"current": {"id": "../../outside", "revision": 1}},
])
def test_pending_queue_rejects_paths_credentials_nonfinite_and_unbounded_data(change):
    with pytest.raises(ValueError):
        validate_snapshot({"intents": [intent()], "error": ""} | change)


def test_shutdown_draft_budget_covers_all_300_unicode_notes_and_1024_unique_intents():
    assert MAX_INTENTS == 1024 and MAX_PENDING_BYTES == 32_000_000
    rows = [{**intent(), "token": f"{i:032x}"} for i in range(MAX_INTENTS)]
    for row in rows[:300]:
        row["payload"] = {"operation": "annotate", "arguments": {"entity_id": "ent_" + "b" * 24,
            "annotation": {"label": "Юникод", "markdown": "漢" * 20_000}}}
    assert len(validate_snapshot({"intents": rows})["intents"]) == MAX_INTENTS
    with pytest.raises(ValueError, match="1024"):
        validate_snapshot({"intents": rows + [{**intent(), "token": "f" * 32}]})
    with pytest.raises(ValueError, match="32 MB"):
        validate_snapshot(" " * (MAX_PENDING_BYTES + 1))


class QueuePage:
    def __init__(self, finite, values):
        self.finite = finite
        self.values = values
        self.frozen = False
        self.last = []

    def runJavaScript(self, script, callback):
        if "prepareShutdown" in script:
            self.frozen = True
        self.last.append(script)
        QTimer.singleShot(0, lambda: callback(json.dumps(self.values(), ensure_ascii=False)))


def test_unsaved_editor_text_is_encrypted_at_shutdown_and_remains_inert_until_explicit_retry(finite):
    controller = finite._research_canvas
    controller.document = controller.store.save(apply(new_document(), "node", {"type": "analyst_note", "label": "Основание"}), 0)
    target = controller.document["id"]
    entity_id = controller.document["entities"][0]["id"]
    original = deepcopy(controller.store.load(target))
    pending = {"op": "edit", "target": target, "token": "e" * 32, "payload": {"operation": "annotate",
        "arguments": {"entity_id": entity_id, "annotation": {"label": "Мой черновик", "markdown": "**Русская гипотеза** — ещё не сохранена 漢"}}}}
    page = QueuePage(finite, lambda: {"intents": [pending], "current": {"id": target, "revision": 1}, "error": ""})
    result = flush_canvas_pending(NS(bridge=finite, trusted_page=page), timeout_ms=30)
    assert result["pending"] == 1 and not result["drained"] and page.frozen
    store = PendingCanvasStore(controller.store)
    encrypted = store._path(result["draft_id"]).read_bytes()
    assert "Русская гипотеза".encode() not in encrypted
    recovered = recovery(finite)
    assert recovered["intents"] == [pending] and controller.store.load(target) == original
    assert finite.launched == []
    replies = responses(finite)
    send(finite, "explicit-open", "research_canvas_open", {"id": target, "await_commit": True, "mutation_id": "f" * 32})
    wait_until(lambda: len(replies) == 1)
    assert controller.document["revision"] == 1  # Opening recovered text does not apply it.
    payload = {"id": target, "revision": 1, **pending["payload"], "await_commit": True, "mutation_id": pending["token"]}
    send(finite, "explicit-retry", "research_canvas_edit", payload)
    wait_until(lambda: len(replies) == 2)
    assert replies[-1][1]["ok"] and controller.document["revision"] == 2
    assert controller.document["annotations"][entity_id] == pending["payload"]["arguments"]["annotation"]
    send(finite, "receipt-replay", "research_canvas_edit", payload)
    assert replies[-1][1]["ok"] and controller.document["revision"] == 2
    assert store.recovery() is None and store._path(result["draft_id"]).read_bytes() == encrypted


def test_actual_surface_shutdown_drains_accepted_commit_before_channel_is_closed(finite):
    controller = finite._research_canvas
    controller.document = controller.store.save(new_document(), 0)
    target = controller.document["id"]
    values = responses(finite)
    pending = intent(target=target)
    send(finite, "save", "research_canvas_edit", {"id": target, "revision": 1,
        **pending["payload"], "await_commit": True, "mutation_id": pending["token"]})
    page = QueuePage(finite, lambda: {"intents": [] if values else [pending], "current": {"id": target, "revision": 1}, "error": ""})
    stopped = []
    class Surface:
        _closing = False
        bridge = finite
        trusted_page = page
        host = NS(removeEventFilter=lambda value: stopped.append("event_filter"))
        def stop(self):
            stopped.append("stop")
    surface = Surface()
    page.setWebChannel = lambda value: stopped.append("channel")
    def close_bridge():
        assert values and controller.job is None
        finite._closed = True
        stopped.append("bridge")
    finite.shutdown = close_bridge
    DesktopSurface.shutdown(surface)
    assert surface.canvas_shutdown == {"drained": True, "pending": 0}
    assert page.frozen and stopped == ["event_filter", "bridge", "stop", "channel"]
    restored = controller.store.load(target)
    assert len(restored["entities"]) == 1 and restored["mutation_receipts"] == ["a" * 32]


def test_deadline_persists_late_commit_and_recovery_filters_durable_receipt(finite, monkeypatch):
    controller = finite._research_canvas
    controller.document = controller.store.save(new_document(), 0)
    target = controller.document["id"]
    pending = intent(target=target)
    original_save = controller.store.save
    release = threading.Event()
    entered = threading.Event()
    def delayed(*args, **kwargs):
        entered.set();release.wait(3)
        return original_save(*args, **kwargs)
    monkeypatch.setattr(controller.store, "save", delayed)
    values = responses(finite)
    send(finite, "save", "research_canvas_edit", {"id": target, "revision": 1,
        **pending["payload"], "await_commit": True, "mutation_id": pending["token"]})
    assert entered.wait(1)
    page = QueuePage(finite, lambda: {"intents": [pending], "current": {"id": target, "revision": 1}, "error": ""})
    started = time.monotonic()
    result = flush_canvas_pending(NS(bridge=finite, trusted_page=page), timeout_ms=60)
    assert time.monotonic() - started < 1
    assert not result["drained"] and result["pending"] == 1 and not values
    draft = PendingCanvasStore(controller.store)
    assert draft.recovery()["intents"] == [pending]
    release.set()
    wait_until(lambda: bool(values))
    assert controller.store.load(target)["mutation_receipts"] == [pending["token"]]
    assert draft.recovery() is None
    assert controller.store.load(target)["revision"] == 2


def test_new_document_late_receipt_prevents_recreating_canvas_from_unbound_draft(finite):
    controller = finite._research_canvas
    values = responses(finite)
    payload = {"title": "Ровно один проект", "await_commit": True, "mutation_id": "c" * 32}
    draft = PendingCanvasStore(controller.store)
    identifier = draft.save({"intents": [{"op": "new", "payload": {"title": payload["title"]}, "token": payload["mutation_id"]}], "error": ""})
    send(finite, "new", "research_canvas_new", payload)
    wait_until(lambda: bool(values))
    assert draft.recovery() is None and len(controller.store.list()) == 1
    assert controller.document["mutation_receipts"] == [payload["mutation_id"]]


def test_receipt_window_preserves_recent_ids_across_undo_values_without_mutating_inputs(finite):
    controller=finite._research_canvas
    previous=new_document();previous['mutation_receipts']=[f'{n:032x}' for n in range(128)]
    old_revision=deepcopy(previous);old_revision['mutation_receipts']=previous['mutation_receipts'][:10]
    controller._active_receipt={'mutation_id':'f'*32}
    saved=controller._with_receipt(old_revision,previous=previous)
    assert len(saved['mutation_receipts'])==128 and saved['mutation_receipts'][-1]=='f'*32
    assert f'{0:032x}' not in saved['mutation_receipts'] and f'{127:032x}' in saved['mutation_receipts']
    assert len(previous['mutation_receipts'])==128 and len(old_revision['mutation_receipts'])==10
    controller._active_receipt=None


def test_recovery_reply_is_asynchronous_and_duplicate_reads_share_one_job(finite):
    first=finite.dispatch('research_canvas_queue_recovery',{})
    second=finite.dispatch('research_canvas_queue_read',{})
    assert first is second and not first.finished
    wait_until(lambda:first.finished)
    assert first.value is None and first.error is None
