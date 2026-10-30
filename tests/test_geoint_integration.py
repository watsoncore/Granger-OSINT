"""Production bridge/runner/tools with real pixels and an explicit LLM fixture.

These tests do not authenticate to a gateway. The transport fixture chooses
functions; AttachmentStore, OCR, metadata, evidence, Qt UiJob and encrypted
checkpoints are the actual application implementations.
"""
from copy import deepcopy
import base64
import io
import json
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet import credentials
from grangerpet.agent import AgentLimits, AgentRunner
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings, SettingsStore
from grangerpet.desktop_bridge import DesktopBridge
from grangerpet.panel import OsintPanel


class PixelContractGateway:
    """An explicit protocol fixture, never presented as a live API result."""
    instances = []
    def __init__(self):
        self.requests = []
        self.__class__.instances.append(self)

    def complete_turn(self, model, messages, **options):
        self.requests.append(deepcopy(messages))
        encoded = json.dumps(messages, ensure_ascii=False)
        assert "data:image/" not in encoded and "base64" not in encoded
        assert "C:\\" not in encoded and "file:///" not in encoded
        tools = [row for row in messages if row.get("role") == "tool"]
        # The deterministic literal-image route may already have read metadata
        # before asking the planner. Request only the missing OCR operation.
        ocr_done=any(row.get('name')=='image_ocr' or '"tool":"image_ocr"' in row.get('content','') for row in tools)
        if not ocr_done:
            import re
            identifier = re.search(r"img_[a-f0-9]{64}", encoded).group(0)
            names = {row["function"]["name"] for row in options["tools"]}
            assert {"image_metadata", "image_ocr"} <= names
            calls = [{"id": "fixture_" + name, "type": "function", "function": {
                "name": name, "arguments": json.dumps({"attachment_id": identifier})}}
                for name in (("image_ocr",) if tools else ("image_metadata", "image_ocr"))]
            message = {"role": "assistant", "content": "Проверяю реальные локальные метаданные и надписи.", "tool_calls": calls}
        else:
            content = "\n".join(row["content"] for row in tools)
            assert "МОСКВА" in content
            assert "no_gps_metadata" in content
            message = {"role": "assistant", "content": "На тестовом изображении распознано «МОСКВА УЛИЦА МИРА». GPS EXIF отсутствует; место съёмки не установлено."}
        return {"message": message, "metadata": {"usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}}}


def wait_until(app, predicate, timeout=8):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def production_bridge(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    profile = tmp_path / "GrangerPet"
    monkeypatch.setenv("APPDATA", str(tmp_path))
    isolated = credentials.CredentialsStore(prefix="Granger-Geoint-Integration-Fixture", directory=profile / "vault", data_root=profile)
    isolated.portable.create("Synthetic integration passphrase", secrets={"deepseek_api_key": "NOT-A-REAL-GATEWAY-KEY"})
    monkeypatch.setattr(credentials, "_STORE", isolated)
    monkeypatch.setattr("grangerpet.chat.DeepSeekClient", PixelContractGateway)
    original_registry = ToolRegistry
    def registry(*args, **kwargs):
        kwargs["readiness"] = lambda *a, **k: {"runtime_ready": False, "state": "not_installed", "message": "Unrelated CLI probe disabled in image integration fixture"}
        return original_registry(*args, **kwargs)
    monkeypatch.setattr("grangerpet.chat.ToolRegistry", registry)
    PixelContractGateway.instances.clear()
    settings = Settings(ai_provider="deepseek", agent_steps=3, agent_calls=3, agent_timeout=30)
    host = OsintPanel(settings, SettingsStore(profile / "settings.json"))
    bridge = DesktopBridge(host)
    yield app, host, bridge
    bridge.shutdown()
    host.shutdown()
    host.close()
    host.deleteLater()
    app.processEvents()


def russian_pixels():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    font = ImageFont.truetype(str(root / "frontend/public/fonts/Manrope-Variable.ttf"), 70)
    image = Image.new("RGB", (1800, 250), "white")
    ImageDraw.Draw(image).text((40, 65), "МОСКВА УЛИЦА МИРА", font=font, fill="black")
    raw = io.BytesIO()
    image.save(raw, "PNG")
    return raw.getvalue()


def import_pixels(app, bridge):
    data = russian_pixels()
    start = time.monotonic()
    result = bridge.dispatch("attachment_import", {"name": "Русская тестовая надпись.png", "base64": base64.b64encode(data).decode("ascii")})
    assert result == {"started": True} and time.monotonic() - start < .2
    wait_until(app, lambda: bridge._attachment_job is None)
    assert not bridge._attachment_error
    return bridge.snapshot()["attachments"][0]


def test_real_pixels_through_bridge_chat_runner_ocr_evidence_and_encrypted_checkpoint(production_bridge):
    app, host, bridge = production_bridge
    record = import_pixels(app, bridge)
    assert record["preview"].startswith("data:image/") and record["mime"] == "image/png"
    bridge.dispatch("chat_send", {"text": "Исследуй надпись на выбранном изображении. Только локальные метаданные и OCR, без внешних источников.", "attachment_ids": [record["id"]]})
    wait_until(app, lambda: not host.chat_widget.busy, timeout=12)
    chat = host.chat_widget
    assert len(PixelContractGateway.instances) == 1
    assert len(PixelContractGateway.instances[0].requests) == 2
    assert chat.messages[-1]["role"] == "model" and "МОСКВА" in chat.messages[-1]["text"]
    assert "место съёмки не установлено" in chat.messages[-1]["text"]
    assert chat.messages[0]["attachments"][0]["id"] == record["id"]
    assert "preview" not in chat.messages[0]["attachments"][0]
    assert bridge._attachments == []
    assert chat._last_investigation["status"] == "completed"
    assert {row["provenance"]["tool"] for row in chat._last_investigation["evidence"]} == {"image_metadata", "image_ocr"}
    checkpoint = chat._journal.load_checkpoint(chat._last_investigation["id"])
    assert record["id"] in checkpoint["registry_state"]["attachment_ids"]
    checkpoint_path = next(chat._journal.directory.glob("*.checkpoint.dpapi"))
    assert "МОСКВА".encode() not in checkpoint_path.read_bytes()
    assert b"NOT-A-REAL-GATEWAY-KEY" not in checkpoint_path.read_bytes()
    snapshot = bridge.snapshot()
    assert len(snapshot["evidence"]) == 2
    assert all(row["url"] == "" for row in snapshot["evidence"])


def test_bridge_rejects_unselected_attachment_and_source_path(production_bridge):
    app, host, bridge = production_bridge
    for identifier in ("img_" + "a" * 64, "../../secret.env", "C:\\private\\image.jpg"):
        with pytest.raises(ValueError):
            bridge.dispatch("chat_send", {"text": "Проверь изображение", "attachment_ids": [identifier]})
    assert not host.chat_widget.messages


def test_registry_enforces_task_attachment_scope_even_with_valid_saved_image(production_bridge):
    app, host, bridge = production_bridge
    record = import_pixels(app, bridge)
    registry = ToolRegistry(host.settings, image_store=bridge._images())
    denied = registry.execute("image_metadata", {"attachment_id": record["id"]})
    assert denied["status"] == "invalid_arguments" and not denied["results"]
    registry.allow_attachments([record["id"]])
    allowed = registry.execute("image_metadata", {"attachment_id": record["id"]})
    assert allowed["status"] == "complete" and len(allowed["evidence_ids"]) == 1
    assert allowed["results"][0]["details"]["metadata"]["gps"] is None


def test_bad_attachment_async_error_is_not_reported_as_success(production_bridge):
    app, host, bridge = production_bridge
    bridge.dispatch("attachment_import", {"name": "corrupt.png", "base64": base64.b64encode(b"\x89PNG\r\n\x1a\nBROKEN").decode("ascii")})
    wait_until(app, lambda: bridge._attachment_job is None)
    assert bridge._attachment_error and not bridge._attachments
    assert not host.chat_widget.messages


def test_cancelled_async_import_ignores_late_result(production_bridge, monkeypatch):
    app, host, bridge = production_bridge
    store = bridge._images()
    original = store.import_bytes
    begun, finished = threading.Event(), threading.Event()
    def slow(data, name, cancel_event=None):
        begun.set()
        try:
            cancel_event.wait(3)
            return original(data, name, cancel_event)
        finally:
            finished.set()
    monkeypatch.setattr(store, "import_bytes", slow)
    bridge.dispatch("attachment_import", {"name": "cancelled.png", "base64": base64.b64encode(russian_pixels()).decode("ascii")})
    assert begun.wait(1)
    bridge.dispatch("attachment_cancel", {})
    assert bridge._attachment_job is None
    wait_until(app, finished.is_set)
    assert bridge._attachments == [] and not bridge._attachment_error
    assert not store.root.exists()


def test_new_dialog_does_not_inherit_attachment_permissions(production_bridge):
    app, host, bridge = production_bridge
    record = import_pixels(app, bridge)
    chat = host.chat_widget
    chat._agent_registry = ToolRegistry(host.settings, image_store=bridge._images(), attachment_ids=[record["id"]])
    bridge.dispatch("chat_new", {})
    assert chat._agent_registry is None


def test_agent_resume_restores_attachment_scope_before_initial_checkpoint(production_bridge):
    app, host, bridge = production_bridge
    record = import_pixels(app, bridge)
    class PauseGateway:
        def complete_turn(self, *args, **kwargs):
            return {"message": {"role": "assistant", "content": "Пауза теста", "tool_calls": []}, "metadata": {}}
    registry = ToolRegistry(host.settings, image_store=bridge._images(), attachment_ids=[record["id"]],
                            readiness=lambda *a, **k: {"runtime_ready": False, "state": "not_installed"})
    runner = AgentRunner(PauseGateway(), registry, limits=AgentLimits(max_steps=1, max_tool_calls=2, timeout=10))
    runner.run("fixture-model", [{"role": "user", "text": "Проверь изображение " + record["id"]}])
    checkpoint = runner.checkpoint()
    checkpoint["record"].update(status="paused", resumable=True)
    fresh_registry = ToolRegistry(host.settings, image_store=bridge._images(), readiness=lambda *a, **k: {"runtime_ready": False, "state": "not_installed"})
    assert not fresh_registry._attachment_ids
    checkpoints = []
    resumed = AgentRunner(PauseGateway(), fresh_registry, limits=AgentLimits(max_steps=2, max_tool_calls=2, timeout=15))
    resumed.run("fixture-model", [], resume_state=checkpoint, checkpoint_callback=checkpoints.append)
    assert record["id"] in fresh_registry._attachment_ids
    assert checkpoints and record["id"] in checkpoints[0]["registry_state"]["attachment_ids"]


def test_compact_context_retains_actual_gps_semantics_under_budget_and_excludes_image_buffers(production_bridge):
    app, host, bridge = production_bridge
    record = import_pixels(app, bridge)
    registry = ToolRegistry(host.settings, image_store=bridge._images(), attachment_ids=[record["id"]])
    envelope = registry.execute("image_metadata", {"attachment_id": record["id"]})
    # An accidental future adapter field must not silently send pixels or paths.
    details = envelope["results"][0]["details"]
    details.update(preview="data:image/png;base64,DO-NOT-SEND", local_path="C:\\private\\image.png")
    details["metadata"]["text_metadata"] = {"description": "Untrusted metadata " * 3000}
    runner = AgentRunner(PixelContractGateway(), registry, limits=AgentLimits(max_tool_result_chars=2500))
    runner._record = {"goal": "Исследуй изображение"}
    runner._state = {}
    compact = runner._compact(envelope)
    parsed = json.loads(compact)
    assert len(compact) <= 2500
    assert "DO-NOT-SEND" not in compact and "base64" not in compact and "local_path" not in compact
    assert parsed["results"][0]["evidence_id"] == envelope["results"][0]["evidence_id"]
    metadata = parsed["results"][0]["geoint_result"]["metadata"]
    assert metadata["status"] == "no_gps_metadata" and metadata["gps"] is None
    assert len(details["metadata"]["text_metadata"]["description"]) > 2500


def test_compact_ocr_shows_real_boxes_without_sending_all_words(production_bridge):
    app, host, bridge = production_bridge
    record = import_pixels(app, bridge)
    registry = ToolRegistry(host.settings, image_store=bridge._images(), attachment_ids=[record["id"]])
    envelope = registry.execute("image_ocr", {"attachment_id": record["id"]})
    details = envelope["results"][0]["details"]
    original = deepcopy(details["segments"])
    details["segments"] = original * 100
    runner = AgentRunner(PixelContractGateway(), registry, limits=AgentLimits(max_tool_result_chars=3000))
    runner._record, runner._state = {"goal": "Прочитай надпись"}, {}
    parsed = json.loads(runner._compact(envelope))
    actual = parsed["results"][0]["geoint_result"]
    assert "МОСКВА" in actual["text"]
    assert actual["segments"][0] == original[0]
    assert actual["segments_total"] == 300
    assert len(actual["segments"]) < 300


def test_mapping_manifests_have_actual_official_api_origins():
    from grangerpet.agent_tools import _BY_NAME
    from grangerpet.tool_manifest import manifest
    assert manifest(_BY_NAME["map_wikimedia"]).access_mode == "OFFICIAL_API"
    assert "mediawiki.org" in manifest(_BY_NAME["map_wikimedia"]).documentation_url
    assert manifest(_BY_NAME["map_geocode"]).access_mode == "OFFICIAL_API"
    assert "nominatim.org" in manifest(_BY_NAME["map_geocode"]).documentation_url


def test_invalid_mapping_coordinates_return_a_typed_invocation_without_network():
    registry=ToolRegistry(Settings(),secret_getter=lambda name:'')
    for value in ('91,0','NaN,0','not-coordinates'):
        result=registry.execute('map_wikimedia',{'coordinates':value},approved=True)
        assert result['status']=='invalid_arguments' and result['results']==[]
        assert result['invocation_id'] and result['tool_id']=='map_wikimedia'
