"""Actual finite Qt reply/canvas/media paths over isolated temporary stores."""
import base64
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PIL import Image
from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.agent_journal import InvestigationJournal
from grangerpet.async_reply import DeferredReply
from grangerpet.canvas_media import request_media
from grangerpet.credentials import CredentialsStore
from grangerpet.desktop_bridge import DesktopBridge
from grangerpet.geoint.images import AttachmentStore
from grangerpet.research_canvas import apply, new_document, CanvasConflict
from grangerpet.research_canvas_bridge import ResearchCanvasBridge


class FiniteBridge(QObject):
    response = Signal(str, str)
    def __init__(self, journal, images):
        super().__init__()
        self.host = NS(chat_widget=NS(_journal=journal))
        self._closed = False
        self._raw_sources = {}
        self._graph_data = {}
        self._images = lambda: images
        self._canvas_media_jobs = set()
        self.dirty = 0
        self.launched = []
        self._run_tool = lambda *args, **kwargs: self.launched.append((args, kwargs))
        self._research_canvas = ResearchCanvasBridge(self)

    def mark_dirty(self):
        self.dirty += 1

    def _json(self, value):
        return json.dumps(value, ensure_ascii=False)

    def dispatch(self, action, payload):
        if action.startswith("research_canvas_"):
            return self._research_canvas.action(action, payload)
        if action in ("canvas_media_view", "canvas_media_open"):
            return request_media(self, action, payload)
        raise ValueError("Unknown finite action")

    request = DesktopBridge.request


@pytest.fixture
def finite(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    app = QApplication.instance() or QApplication([])
    images = AttachmentStore(tmp_path / "attachments", seal=CredentialsStore._protect,
        open_sealed=lambda value: CredentialsStore._protect(value, decrypt=True))
    bridge = FiniteBridge(InvestigationJournal(tmp_path / "investigations"), images)
    yield bridge
    end = time.monotonic() + 3
    while (bridge._research_canvas.job or bridge._canvas_media_jobs) and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    bridge._closed = True
    bridge.deleteLater(); app.processEvents()


def wait_until(predicate):
    end = time.monotonic() + 5
    while not predicate() and time.monotonic() < end:
        QApplication.processEvents(); QTest.qWait(5)
    assert predicate(), "Finite reply did not finish"


def send(bridge, identifier, action, payload):
    bridge.request(identifier, action, json.dumps(payload, ensure_ascii=False))


def responses(bridge):
    values = []
    bridge.response.connect(lambda identifier, value: values.append((identifier, json.loads(value))))
    return values


def test_deferred_reply_resolves_once_and_replays_finished_receipt():
    value = DeferredReply(); replies = []
    value.subscribe(lambda data, error: replies.append((data, error)))
    value.resolve({"revision": 2})
    value.resolve({"revision": 3}, {"error": "duplicate"})
    value.subscribe(lambda data, error: replies.append((data, error)))
    assert replies == [({"revision": 2}, None), ({"revision": 2}, None)]


def test_canvas_ack_waits_for_durable_save_and_replay_never_adds_revision(finite):
    values = responses(finite)
    payload = {"title": "Русское расследование", "await_commit": True, "mutation_id": "a" * 32}
    send(finite, "new", "research_canvas_new", payload)
    assert not values
    wait_until(lambda: len(values) == 1)
    receipt = values[0][1]
    assert receipt["ok"] and receipt["result"]["revision"] == 1
    controller = finite._research_canvas
    identifier = controller.document["id"]
    assert controller.store.load(identifier)["revision"] == 1
    mutation = {"id": identifier, "revision": 1, "operation": "rename", "arguments": {"title": "Сохранено"},
        "await_commit": True, "mutation_id": "b" * 32}
    send(finite, "edit", "research_canvas_edit", mutation)
    wait_until(lambda: len(values) == 2)
    assert values[-1][1]["result"]["revision"] == 2
    files = list(controller.store._folder(identifier).glob("r*.dpapi"))
    send(finite, "replay", "research_canvas_edit", mutation)
    assert values[-1][0] == "replay" and values[-1][1] == values[-2][1]
    assert list(controller.store._folder(identifier).glob("r*.dpapi")) == files
    send(finite, "collision", "research_canvas_edit", mutation | {"arguments": {"title": "Другой запрос"}})
    assert values[-1][1]["ok"] is False and controller.store.load(identifier)["title"] == "Сохранено"


def test_conflict_from_actual_store_returns_current_revision_without_overwrite(finite):
    controller = finite._research_canvas
    controller.document = controller.store.save(new_document("Начало"), 0)
    document = controller.document
    external = controller.store.save(apply(document, "rename", {"title": "Другой редактор"}), 1)
    values = responses(finite)
    send(finite, "conflict", "research_canvas_edit", {"id": document["id"], "revision": 1,
        "operation": "rename", "arguments": {"title": "Устаревшее"}, "await_commit": True, "mutation_id": "c" * 32})
    wait_until(lambda: bool(values))
    assert values[0][1]["ok"] is False
    assert values[0][1]["code"] == CanvasConflict.code and values[0][1]["revision"] == external["revision"]
    assert controller.store.load(document["id"])["title"] == "Другой редактор"


def test_synchronous_stale_canvas_conflict_in_finite_protocol_includes_revision(finite):
    controller = finite._research_canvas
    controller.document = controller.store.save(new_document(), 0)
    values = responses(finite)
    send(finite, "stale", "research_canvas_edit", {"id": controller.document["id"], "revision": 0,
        "operation": "rename", "arguments": {"title": "Stale"}})
    assert values[0][1]["ok"] is False and values[0][1]["code"] == CanvasConflict.code
    assert values[0][1]["revision"] == 1


def test_canvas_ip_capability_refuses_gansar_before_any_tool_runner(finite):
    controller = finite._research_canvas
    controller.document = controller.store.save(apply(new_document(), "node", {"type": "infrastructure_asset", "label": "66.249.67.41"}), 0)
    document = controller.document
    node = document["entities"][0]
    payload = {"id": document["id"], "revision": document["revision"], "entity_id": node["id"]}
    result = finite.dispatch("research_canvas_capability", payload)
    assert not next(row for row in result["tools"] if row["id"] == "blockchain_gansar")["compatible"]
    with pytest.raises(ValueError):
        finite.dispatch("research_canvas_tool", payload | {"tool": "blockchain_gansar",
            "arguments": {"address": "0:" + "12" * 32, "chain": "ton", "operation": "profile"}})
    assert finite.launched == []


def image_node(finite):
    stream = io.BytesIO()
    Image.new("RGB", (64, 48), "#a08040").save(stream, "PNG")
    original = stream.getvalue()
    image = finite._images().import_bytes(original, "Исходник.png")
    document = apply(new_document(), "node", {"type": "image", "label": "Исходник"})
    node = document["entities"][0]
    node["attributes"].update(attachment_id=image["id"], original_image=True)
    finite._research_canvas.document = finite._research_canvas.store.save(document, 0)
    return original, image, {"canvas_id": document["id"], "entity_id": node["id"]}


def test_media_finite_async_reply_authorizes_server_node_and_keeps_original_hash(finite, monkeypatch):
    original, image, payload = image_node(finite)
    values, threads = responses(finite), []
    store = finite._images(); read = store.read_bytes
    def observed(*args):
        threads.append(QThread.currentThread() != QApplication.instance().thread())
        return read(*args)
    monkeypatch.setattr(store, "read_bytes", observed)
    send(finite, "view", "canvas_media_view", payload)
    assert not values
    wait_until(lambda: bool(values))
    result = values[0][1]
    assert result["ok"] and result["result"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert result["result"]["width"] == 64 and result["result"]["height"] == 48
    assert threads == [True] and store.read_bytes(image["id"]) == original
    assert base64.b64decode(result["result"]["preview"].split(",", 1)[1]) != original
    assert "original_base64" not in result["result"]
    send(finite, "forged", "canvas_media_view", payload | {"path": "C:/private/photo.png"})
    assert values[-1][1]["ok"] is False
    send(finite, "missing", "canvas_media_view", payload | {"entity_id": "unowned"})
    assert values[-1][1]["ok"] is False


def test_media_integrity_failure_finishes_reply_and_preserves_corrupt_fixture(finite):
    original, image, payload = image_node(finite)
    path = finite._images()._path(image["id"])
    damaged = path.read_bytes()[:-10] + b"damaged!!"
    path.write_bytes(damaged)
    values = responses(finite)
    send(finite, "damaged", "canvas_media_view", payload)
    wait_until(lambda: bool(values))
    assert values[0][1]["ok"] is False and values[0][1]["code"] == "canvas_media_unavailable"
    assert path.read_bytes() == damaged and not finite._canvas_media_jobs
