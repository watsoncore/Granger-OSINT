"""Settings tests use explicit fake DeepSeek transport; no live API or user vault."""
import json
import os
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QLineEdit

from grangerpet.ai import AIError
from grangerpet.ai_keys import DEFAULT_DEEPSEEK_MODEL
from grangerpet.config import Settings, SettingsStore
from grangerpet.connections import ConnectionsPane
from grangerpet.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if not QFontDatabase.families():
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / name))
    return app


@pytest.fixture
def pane(app, monkeypatch):
    values = {}
    for module in ("grangerpet.credentials", "grangerpet.connections", "grangerpet.ai_keys"):
        monkeypatch.setattr(module + ".get_secret", lambda name: values.get(name, ""))
    monkeypatch.setattr("grangerpet.connections.set_secret", lambda name, value: values.__setitem__(name, value))
    monkeypatch.setattr("grangerpet.connections.delete_secret", lambda name: values.pop(name, None))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    widget = ConnectionsPane(Settings(ai_provider="deepseek"))
    widget._fake_vault = values
    yield widget
    widget.shutdown()
    widget.close()
    widget.deleteLater()
    app.processEvents()


def wait(app, predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    pytest.fail("Settings worker did not finish")


def test_default_deepseek_form_is_compact_masked_and_unverified_without_auto_request(pane, monkeypatch):
    calls = []
    monkeypatch.setattr("grangerpet.connections.DeepSeekClient", lambda *args, **kwargs: calls.append(args))
    assert pane.selected_model() == DEFAULT_DEEPSEEK_MODEL
    assert pane.model.currentText() == "DeepSeek V4 Flash"
    assert pane.deepseek_key.echoMode() == QLineEdit.EchoMode.Password
    assert not pane.deepseek_verified
    assert pane.ai_status.text() == "ИИ не настроен"
    assert "API-квоту" in pane.deepseek_notice.text()
    pane.deepseek_key.setText("explicit-fixture-key")
    assert not calls and not pane._jobs
    pane.deepseek_reveal.click()
    assert pane.deepseek_key.echoMode() == QLineEdit.EchoMode.Normal
    pane.deepseek_reveal.click()
    assert pane.deepseek_key.echoMode() == QLineEdit.EchoMode.Password


def test_connection_requires_actual_fake_generation_and_save_keeps_same_verified_identity(pane, app, monkeypatch):
    calls = []
    class FakeSDKClient:
        def __init__(self, key):
            calls.append(("client", key))
        def test_connection(self, model, cancel_event):
            calls.append(("fake_generate", model, cancel_event.is_set()))
            return {"connected": True, "model": model, "text": "Explicit fixture response"}
    monkeypatch.setattr("grangerpet.connections.DeepSeekClient", FakeSDKClient)
    states = []
    pane.ai_connection_changed.connect(states.append)
    pane.deepseek_key.setText("fixture-user-key")
    assert not calls
    pane.check.click()
    wait(app, lambda: not pane._jobs)
    assert calls == [("client", "fixture-user-key"), ("fake_generate", DEFAULT_DEEPSEEK_MODEL, False)]
    assert pane.deepseek_verified and states[-1] is True
    assert pane.ai_status.text() == "Подключение проверено · Сохраните настройки"
    assert not pane.ai_state.snapshot()["configuration_saved"]
    pane.save()
    assert pane._fake_vault["deepseek_api_key"] == "fixture-user-key"
    assert pane.deepseek_key.text() == ""
    assert pane.deepseek_verified
    assert pane.ai_state.snapshot()["connection_status"] == "connected"
    assert pane.ai_status.text() == "DeepSeek V4 Flash · Подключено"
    pane.deepseek_key.setText("fixture-replacement-key")
    assert not pane.deepseek_verified
    assert "Сохраните" in pane.ai_status.text()


@pytest.mark.parametrize('tool_status,round_trip,expected_status', [('supported', True, 'supported'), ('unverified', False, 'unverified'), ('supported', False, 'unverified')])
def test_safe_tool_probe_metadata_is_bound_to_the_checked_key_without_extra_ui(pane, app, monkeypatch, tool_status, round_trip, expected_status):
    class FakeClient:
        def __init__(self, key):
            pass
        def test_connection(self, model, cancel_event):
            return {'connected': True, 'model': model, 'text': 'Explicit fixture response',
                    'tool_calls': {'status': tool_status, 'round_trip': round_trip,
                                   'reason': 'raw-provider-fixture-secret'}}
    monkeypatch.setattr('grangerpet.connections.DeepSeekClient', FakeClient)
    pane.deepseek_key.setText('fixture-checked-key')
    pane.check.click()
    wait(app, lambda: not pane._jobs)
    assert pane.deepseek_verified
    assert pane.connection_details == {'model': DEFAULT_DEEPSEEK_MODEL,
        'tool_calls': {'status': expected_status, 'round_trip': round_trip}}
    assert 'raw-provider-fixture-secret' not in repr(pane.connection_details)
    assert pane.tabs.count() == 4
    assert pane.save()
    assert pane.ai_status.text() == 'DeepSeek V4 Flash · Подключено'
    assert pane.connection_details['tool_calls']['status'] == expected_status
    pane.deepseek_key.setText('fixture-replacement-key')
    assert pane.connection_details == {}
    assert 'не подтверждена' in pane.ai_status.toolTip()


def test_environment_and_legacy_gemini_keys_never_configure_unrelated_gateway(pane, tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-development-key")
    monkeypatch.setenv("GEMINI_API_KEY", "legacy-fixture-key")
    pane._fake_vault["gemini_api_key"] = "legacy-fixture-key"
    pane.store = SettingsStore(tmp_path / "settings.json")
    pane.set_settings(Settings(ai_provider="deepseek"))
    assert pane.deepseek_key.text() == ""
    assert "Введите" in pane.key_source.text()
    assert not pane.ai_state.can_send
    pane.save()
    assert "deepseek_api_key" not in pane._fake_vault
    serialized = pane.store.path.read_text(encoding="utf-8")
    assert "fixture-development-key" not in serialized
    assert "legacy-fixture-key" not in serialized
    assert pane._fake_vault["gemini_api_key"] == "legacy-fixture-key"
    assert json.loads(serialized)["deepseek_model"] == DEFAULT_DEEPSEEK_MODEL


@pytest.mark.parametrize("code,status,message", [("invalid_key", 401, "Недействительный API-ключ"), ("payment_required", 402, "Требуется оплата"), ("access_denied", 403, "Нет доступа к DeepSeek API"), ("model_not_found", 404, "Модель недоступна"), ("timeout", None, "Время ожидания истекло"), ("empty_response", None, "Модель не вернула текст")])
def test_connection_errors_are_visible_and_do_not_claim_connected(pane, app, monkeypatch, code, status, message):
    class FakeSDKClient:
        def __init__(self, key):
            pass
        def test_connection(self, **kwargs):
            raise AIError(message, code=code, http_status=status)
    monkeypatch.setattr("grangerpet.connections.DeepSeekClient", FakeSDKClient)
    pane.deepseek_key.setText("fixture-key-never-in-status")
    pane.check.click()
    wait(app, lambda: not pane._jobs)
    expected = {"invalid_key":"Не удалось подтвердить API-ключ", "access_denied":"Нет доступа к DeepSeek API",
                "payment_required":"Недостаточно средств или требуется оплата у поставщика API (HTTP 402)",
                "model_not_found":"Выбранная модель DeepSeek недоступна", "timeout":"Время ожидания ответа DeepSeek истекло",
                "empty_response":"DeepSeek не вернул текст ответа"}
    assert pane.ai_status.text() == expected[code]
    assert not pane.deepseek_verified and pane.check.isEnabled()
    assert "fixture-key-never-in-status" not in pane.ai_status.text()


def test_retry_after_blocks_early_recheck_without_any_automatic_retry(pane, app, monkeypatch):
    calls = []
    class FakeSDKClient:
        def __init__(self, key):
            pass
        def test_connection(self, **kwargs):
            calls.append("explicit-fixture-request")
            raise AIError("Лимит DeepSeek API достигнут", code="quota", http_status=429, retry_after=.4)
    monkeypatch.setattr("grangerpet.connections.DeepSeekClient", FakeSDKClient)
    pane.deepseek_key.setText("fixture-key")
    pane.check.click()
    wait(app, lambda: not pane._jobs)
    assert not pane.check.isEnabled() and "Повторить через" in pane.check.text()
    pane.check_connection()
    assert len(calls) == 1
    wait(app, pane.check.isEnabled)
    assert len(calls) == 1 and not pane.deepseek_verified


def test_cancellation_passes_real_event_and_never_overwrites_status_later(pane, app, monkeypatch):
    observed = threading.Event()
    class FakeSDKClient:
        def __init__(self, key):
            pass
        def test_connection(self, *, model, cancel_event):
            observed.set()
            cancel_event.wait(2)
            return {"connected": True, "model": model}
    monkeypatch.setattr("grangerpet.connections.DeepSeekClient", FakeSDKClient)
    pane.deepseek_key.setText("fixture-key")
    pane.check.click()
    wait(app, observed.is_set)
    job = pane._jobs[0]
    pane.cancel_check.click()
    assert job.cancelled.is_set() and not pane._jobs
    assert pane.ai_status.text() == "Проверка отменена"
    QTest.qWait(100)
    app.processEvents()
    assert not pane.deepseek_verified and pane.ai_status.text() == "Проверка отменена"


def test_switch_provider_preserves_existing_ollama_and_model_choice(pane, app, monkeypatch):
    monkeypatch.setattr("grangerpet.connections.OllamaClient", lambda address: type("FakeOllama", (), {"list_models": lambda self: ["fixture-local:latest"]})())
    pane.ollama_url.setText("http://localhost:11434")
    pane.provider.setCurrentIndex(pane.provider.findData("ollama"))
    pane.check.click()
    wait(app, lambda: not pane._jobs)
    assert pane.selected_model() == "fixture-local:latest"
    assert "локальных моделей: 1" in pane.ai_status.text()
    pane.save()
    assert pane.settings.ollama_model == "fixture-local:latest"
    pane.provider.setCurrentIndex(pane.provider.findData("deepseek"))
    assert pane.selected_model() == DEFAULT_DEEPSEEK_MODEL


def test_settings_dialog_forwards_verified_state_and_hides_unchecked_source_table(pane, app):
    dialog = SettingsDialog(Settings(ai_provider="deepseek"))
    try:
        states = []
        dialog.ai_connection_changed.connect(states.append)
        dialog.connections.ai_connection_changed.emit(True)
        assert states == [True]
        assert not dialog.readiness.isVisible()
        assert dialog.readiness.rowCount() == 0
        assert not dialog.deepseek_verified
        dialog.connections.deepseek_key.setText("fixture-deepseek-excluded-from-source-probes")
        dialog.connections.google_key.setText("fixture-google-source-key")
        options = dialog.options()
        assert "deepseek_api_key" not in options
        assert options["google_api_key"] == "fixture-google-source-key"
    finally:
        dialog.shutdown()
        dialog.deleteLater()
        app.processEvents()


def test_minimum_settings_window_keeps_key_and_save_actions_accessible(pane, app):
    from grangerpet.theme import STYLE
    dialog = SettingsDialog(Settings(ai_provider="deepseek"))
    dialog.setStyleSheet(STYLE)
    try:
        dialog.resize(460, 420)
        dialog.connections.tabs.setCurrentIndex(2)
        dialog.show()
        app.processEvents()
        QTest.qWait(60)
        assert (dialog.width(), dialog.height()) == (460,420)
        dialog.ai_state.changed.emit(dialog.ai_state.snapshot())
        app.processEvents();QTest.qWait(30)
        assert (dialog.width(), dialog.height()) == (460,420)
        assert not dialog.connections.tabs.hasHeightForWidth()
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.header.isVisible()
        save = dialog.connections.save_button
        assert save.isVisible()
        assert dialog.rect().contains(save.mapTo(dialog, save.rect().bottomRight()))
        tab = dialog.connections.tabs.currentWidget()
        assert tab.horizontalScrollBar().maximum() == 0
        # The content may scroll vertically, while the explicit save action
        # stays in the one compact footer at the minimum window size.
        assert dialog.connections.deepseek_key.width() > 100
        assert dialog.connections.model.width() > 150
    finally:
        dialog.shutdown()
        dialog.deleteLater()
        app.processEvents()
