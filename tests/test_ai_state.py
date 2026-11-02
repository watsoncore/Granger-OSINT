"""Secret-free shared AI lifecycle using only isolated fake vault values."""
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from grangerpet.ai_state import AIState
from grangerpet.config import Settings, SettingsStore
from grangerpet.connections import ConnectionsPane
from grangerpet.settings_dialog import SettingsDialog


@pytest.fixture
def isolated(monkeypatch):
    app = QApplication.instance() or QApplication([])
    vault = {}
    for module in ("grangerpet.credentials", "grangerpet.connections", "grangerpet.ai_keys"):
        monkeypatch.setattr(module+".get_secret", lambda name: vault.get(name, ""))
    monkeypatch.setattr("grangerpet.connections.set_secret", lambda name,value: vault.__setitem__(name,value))
    monkeypatch.setattr("grangerpet.connections.delete_secret", lambda name: vault.pop(name,None))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    return app, vault


def test_verified_connection_stays_connected_while_generating(isolated):
    _,vault=isolated
    vault['deepseek_api_key']='isolated-test-credential'
    settings=Settings(ai_provider='deepseek')
    state=AIState(settings)
    state.request_started('deepseek','deepseek-v4-flash')
    state.request_succeeded('deepseek','deepseek-v4-flash')
    state.request_started('deepseek','deepseek-v4-flash')
    assert state.snapshot()['connection_status']=='connected' and state.can_send


def test_checked_draft_never_unlocks_unconfigured_committed_chat(isolated):
    _, vault = isolated
    state=AIState(Settings())
    token=state.begin_check("deepseek", "deepseek-v4-flash", "explicit-fixture-key")
    assert state.snapshot()["connection_status"] == "checking"
    assert state.finish_check(token)
    assert state.snapshot()["connection_status"] == "verified_unsaved"
    assert not state.snapshot()["configuration_saved"]
    assert not state.can_send
    assert "Сохраните" in state.status_text()
    assert "explicit-fixture-key" not in repr(state.snapshot())
    vault["deepseek_api_key"]="explicit-fixture-key"
    settings=Settings(ai_provider="deepseek",deepseek_model="deepseek-v4-flash")
    state.commit(settings)
    assert state.can_send and state.snapshot()["connection_status"] == "connected"
    state.set_settings(deepcopy(settings))
    assert state.snapshot()["connection_status"] == "connected"
    restarted=AIState(settings)
    assert restarted.can_send
    assert restarted.snapshot()["connection_status"] == "configured_unverified"


def test_key_replacement_and_stale_callbacks_cannot_verify_wrong_config(isolated):
    _, vault=isolated
    vault["deepseek_api_key"]="old-fixture-key"
    settings=Settings(ai_provider="deepseek",deepseek_model="deepseek-v4-flash")
    state=AIState(settings)
    old=state.begin_check()
    state.update_draft("deepseek","deepseek-v4-flash","new-fixture-key")
    assert not state.finish_check(old)
    fresh=state.begin_check()
    assert state.finish_check(fresh)
    assert state.snapshot()["connection_status"]=="verified_unsaved"
    vault["deepseek_api_key"]="new-fixture-key"
    state.commit(settings)
    assert state.snapshot()["connection_status"]=="connected"


def test_discarding_another_checked_draft_keeps_previously_verified_saved_connection(isolated):
    _,vault=isolated;vault["deepseek_api_key"]="saved-key"
    state=AIState(Settings(ai_provider="deepseek",deepseek_model="deepseek-v4-flash"))
    state.finish_check(state.begin_check())
    before=state.snapshot()["last_verified_at"]
    state.finish_check(state.begin_check("deepseek","deepseek-v4-flash","different-key"))
    assert state.snapshot()["connection_status"]=="verified_unsaved"
    state.discard_draft()
    assert state.snapshot()["connection_status"]=="connected"
    assert state.snapshot()["last_verified_at"]==before


@pytest.mark.parametrize("code,http_status,status",[("auth",401,"authentication_failed"),("payment_required",402,"payment_required"),("forbidden",403,"permission_denied"),
    ("quota",429,"quota_exceeded"),("model_not_found",404,"model_unavailable"),("network",None,"network_error")])
def test_api_error_keeps_saved_configuration_and_can_send_manual_retry(isolated, code,http_status,status):
    _,vault=isolated;vault["deepseek_api_key"]="fixture"
    state=AIState(Settings(ai_provider="deepseek",deepseek_model="deepseek-v4-flash"))
    state.request_started("deepseek","deepseek-v4-flash")
    state.request_failed({"code":code,"http_status":http_status,"raw_secret":"must-not-display"},"deepseek","deepseek-v4-flash")
    assert state.snapshot()["connection_status"]==status
    assert state.snapshot()["configuration_saved"] and state.can_send
    assert "must-not-display" not in str(state.snapshot())
    assert vault["deepseek_api_key"]=="fixture"


@pytest.mark.parametrize('code,message', [
    ('tools_not_enabled', 'Автоматический запуск OSINT не подключён. Используйте ручной поиск и анализ выбранных находок.'),
    ('invalid_request', 'Шлюз DeepSeek отклонил параметры запроса. Проверьте выбранную модель.'),
])
def test_response_contract_errors_are_not_misreported_as_network_errors(isolated, code, message):
    _, vault = isolated
    vault['deepseek_api_key'] = 'isolated-fixture-key'
    state = AIState(Settings(ai_provider='deepseek'))
    state.request_started('deepseek', 'deepseek-v4-flash')
    state.request_failed({'code': code, 'raw_secret': 'must-not-display'}, 'deepseek', 'deepseek-v4-flash')
    snapshot = state.snapshot()
    assert snapshot['connection_status'] == 'response_error'
    assert state.status_text() == message
    assert snapshot['configuration_saved'] and state.can_send
    assert 'must-not-display' not in str(snapshot)
    assert vault['deepseek_api_key'] == 'isolated-fixture-key'


def test_failed_preferences_save_restores_vault_and_keeps_checked_draft(isolated,tmp_path,monkeypatch):
    app,vault=isolated;vault["deepseek_api_key"]="old-key"
    store=SettingsStore(tmp_path/"settings.json")
    store.save(Settings())
    state=AIState(store.load())
    pane=ConnectionsPane(store.load(),store,ai_state=state)
    try:
        pane.provider.setCurrentIndex(pane.provider.findData("deepseek"))
        pane.deepseek_key.setText("new-key")
        token=state.begin_check("deepseek","deepseek-v4-flash","new-key")
        state.finish_check(token)
        monkeypatch.setattr(store,"save",lambda settings:(_ for _ in ()).throw(OSError("explicit fake disk error")))
        assert pane.save() is False
        assert vault["deepseek_api_key"]=="old-key"
        assert pane.deepseek_key.text()=="new-key"
        assert pane.is_dirty()
        assert state.snapshot()["connection_status"]=="verified_unsaved"
        assert not state.snapshot()["configuration_saved"] and not state.can_send
        assert "не сохранены" in pane.ai_status.text()
    finally:
        pane.shutdown();pane.deleteLater();app.processEvents()


def test_done_cancel_keeps_draft_discard_restores_and_always_masks(isolated,monkeypatch):
    app,vault=isolated
    dialog=SettingsDialog(Settings())
    try:
        dialog.show();app.processEvents()
        pane=dialog.connections
        pane.provider.setCurrentIndex(pane.provider.findData("deepseek"))
        pane.deepseek_key.setText("not-persisted-fixture")
        pane.deepseek_reveal.setChecked(True)
        monkeypatch.setattr(dialog,"ask_unsaved_changes",lambda:QMessageBox.StandardButton.Cancel)
        dialog.close();app.processEvents()
        assert dialog.isVisible() and pane.is_dirty()
        assert vault=={}
        monkeypatch.setattr(dialog,"ask_unsaved_changes",lambda:QMessageBox.StandardButton.Discard)
        dialog.close();app.processEvents()
        assert not dialog.isVisible() and not pane.is_dirty()
        assert pane.deepseek_key.text()=="" and not pane.deepseek_reveal.isChecked()
        assert pane.provider.currentData()=="none"
        assert dialog.ai_state.snapshot()["connection_status"]=="not_configured"
    finally:
        dialog.shutdown();dialog.deleteLater();app.processEvents()


def test_deleting_saved_key_is_a_draft_and_discard_never_deletes_vault(isolated):
    app,vault=isolated;vault["deepseek_api_key"]="saved-fixture"
    pane=ConnectionsPane(Settings(ai_provider="deepseek",deepseek_model="deepseek-v4-flash"))
    try:
        pane._pending_deletions.add("deepseek_api_key")
        pane._invalidate_connection()
        assert pane.is_dirty() and vault["deepseek_api_key"]=="saved-fixture"
        pane.discard_changes()
        assert vault["deepseek_api_key"]=="saved-fixture" and not pane.is_dirty()
    finally:
        pane.shutdown();pane.deleteLater();app.processEvents()
