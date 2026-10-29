"""Real encrypted temporary profiles behind the actual Qt bridge; no real keys."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtTest import QTest
import time

from grangerpet import credentials
from grangerpet.chat_archive import ChatArchive
from grangerpet.config import Settings, SettingsStore
from grangerpet.desktop_bridge import DesktopBridge
from grangerpet.panel import OsintPanel
from grangerpet.portable_vault import ARTIFACT_MAGIC


PASSWORD = 'Синтетическая фраза bridge 2026'


@pytest.fixture
def vault_bridge(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = credentials.CredentialsStore(prefix='GrangerPet/Tests/VaultBridgeFixture',
                                        directory=tmp_path/'vault', data_root=tmp_path)
    monkeypatch.setattr(credentials, '_STORE', store)
    credentials.create_portable_vault(PASSWORD, migrate=False)
    host = OsintPanel(Settings(), SettingsStore(tmp_path/'settings.json'))
    bridge = DesktopBridge(host)
    yield bridge
    if not credentials.portable_unlocked():
        credentials.unlock_portable_vault(PASSWORD)
    bridge.shutdown(); host.shutdown(); host.deleteLater(); app.processEvents()


def unlock_dialog(monkeypatch):
    class UnlockDialog:
        def __init__(self, operation, host):
            assert operation == 'unlock'
        def exec(self):
            credentials.unlock_portable_vault(PASSWORD)
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr('grangerpet.vault_dialog.VaultDialog', UnlockDialog)


def test_lock_flushes_dirty_canvas_and_history_then_unlock_restores_disk_data(vault_bridge, monkeypatch):
    bridge = vault_bridge
    chat = bridge.host.chat_widget
    chat._append('user', 'Личный синтетический вопрос')
    chat._append('model', '# Синтетический отчёт\n\nИсходный текст')
    message_id = chat.messages[-1]['id']
    bridge.dispatch('canvas_open', {'message_id':message_id})
    canvas = bridge.host.canvas
    canvas.editor.setPlainText('# Синтетический отчёт\n\nНесохранённое изменение')
    assert canvas._dirty and canvas._save_timer.isActive()
    document_path = canvas.directory / (canvas.document_id+'.md')
    bridge.snapshot()  # Populate plaintext render and title caches.
    before = list(chat.messages)
    result = bridge.dispatch('vault_manage', {'operation':'lock'})
    assert result['completed'] and result['enabled'] and not result['unlocked']
    assert chat.messages == [] and chat._context == [] and chat._library._metadata_cache == {}
    assert canvas.editor.toPlainText() == '' and canvas.preview.toPlainText() == ''
    assert canvas._documents == {} and canvas._original_source == ''
    assert not canvas._dirty and not canvas._save_timer.isActive() and not canvas._preview_timer.isActive()
    assert document_path.read_bytes().startswith(ARTIFACT_MAGIC)
    assert bridge.snapshot()['history'] == [] and bridge.snapshot()['messages'] == []
    unlock_dialog(monkeypatch)
    result = bridge.dispatch('vault_manage', {'operation':'unlock'})
    assert result['unlocked'] and chat.messages == before and not chat.archive_error
    assert 'Несохранённое изменение' in credentials.open_bytes(document_path.read_bytes()).decode('utf-8')
    assert ChatArchive(chat._archive._path).load()['messages'] == before


def test_failed_canvas_save_prevents_lock_and_preserves_open_document(vault_bridge, monkeypatch):
    bridge = vault_bridge
    chat = bridge.host.chat_widget
    chat._append('model','# Отчёт')
    bridge.dispatch('canvas_open', {'message_id':chat.messages[-1]['id']})
    canvas = bridge.host.canvas
    canvas.editor.setPlainText('Важное несохранённое изменение')
    monkeypatch.setattr(canvas,'save_document',lambda:None)
    with pytest.raises(ValueError, match='Canvas'):
        bridge._vault_manage('lock')
    assert credentials.portable_unlocked() and canvas.editor.toPlainText() == 'Важное несохранённое изменение'
    canvas._dirty = False  # The deliberately failed fixture must not auto-save in teardown.


def test_failed_history_save_does_not_lock_or_clear_conversation(vault_bridge, monkeypatch):
    chat = vault_bridge.host.chat_widget
    chat._append('user','Несохранённый вопрос')
    monkeypatch.setattr(chat,'_save_archive',lambda:False)
    chat.archive_error = 'Synthetic archive write failure'
    with pytest.raises(ValueError,match='Synthetic'):
        vault_bridge._vault_manage('lock')
    assert credentials.portable_unlocked() and chat.messages[-1]['text']=='Несохранённый вопрос'


@pytest.mark.parametrize('attribute', ['_manual_job','_balance_job','_models_job','_tools_job','_attachment_job'])
def test_active_bridge_jobs_prevent_vault_transition(vault_bridge, monkeypatch, attribute):
    with monkeypatch.context() as patch:
        patch.setattr(vault_bridge, attribute, object(), raising=False)
        with pytest.raises(ValueError,match='текущих запросов'):
            vault_bridge._vault_manage('lock')
        assert credentials.portable_unlocked()


def test_connection_check_and_search_and_chat_prevent_vault_transition(vault_bridge, monkeypatch):
    for target, attribute, value in [(vault_bridge.host.settings_dialog.connections,'_jobs',[object()]),
                                     (vault_bridge.host,'_busy',True),
                                     (vault_bridge.host.chat_widget,'_busy',True)]:
        with monkeypatch.context() as patch:
            patch.setattr(target,attribute,value)
            with pytest.raises(ValueError,match='текущих запросов'):
                vault_bridge._vault_manage('lock')
            assert credentials.portable_unlocked()


def test_password_fields_are_rejected_by_renderer_protocol(vault_bridge):
    with pytest.raises(ValueError,match='защищённом окне'):
        vault_bridge.dispatch('vault_manage', {'operation':'unlock','password':'must never cross renderer'})
    assert credentials.portable_unlocked()


def test_cancelled_native_dialog_leaves_state_and_history_unchanged(vault_bridge, monkeypatch):
    chat = vault_bridge.host.chat_widget
    chat._append('user','Исходная переписка')
    before = list(chat.messages)
    class CancelDialog:
        def __init__(self,*args): pass
        def exec(self): return QDialog.DialogCode.Rejected
    monkeypatch.setattr('grangerpet.vault_dialog.VaultDialog',CancelDialog)
    result = vault_bridge._vault_manage('change')
    assert result == {'completed':False} and credentials.portable_unlocked()
    assert chat.messages == before


def test_native_passphrase_dialog_unlocks_asynchronously_and_clears_input(vault_bridge):
    from grangerpet.vault_dialog import VaultDialog
    credentials.lock_portable_vault()
    dialog = VaultDialog('unlock', vault_bridge.host)
    dialog.fields['password'].setText(PASSWORD)
    dialog.submit()
    assert dialog._job is not None and dialog.fields['password'].text() == ''
    assert not dialog.fields['password'].isEnabled()
    deadline = time.monotonic() + 4
    while dialog._job is not None and time.monotonic() < deadline:
        QTest.qWait(20)
    assert dialog._job is None and credentials.portable_unlocked()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert all(field.text() == '' for field in dialog.fields.values())
    dialog.deleteLater()


def test_native_wrong_passphrase_never_modifies_container_or_exposes_password(vault_bridge):
    from grangerpet.vault_dialog import VaultDialog
    path = credentials._STORE.portable.path
    original = path.read_bytes()
    credentials.lock_portable_vault()
    dialog = VaultDialog('unlock', vault_bridge.host)
    wrong = 'Wrong synthetic password 2026'
    dialog.fields['password'].setText(wrong)
    dialog.submit()
    deadline = time.monotonic() + 4
    while dialog._job is not None and time.monotonic() < deadline:
        QTest.qWait(20)
    assert dialog._job is None and not credentials.portable_unlocked()
    assert path.read_bytes() == original and dialog.status.text()
    assert wrong not in dialog.status.text() and PASSWORD not in dialog.status.text()
    assert dialog.fields['password'].text() == '' and dialog.fields['password'].isEnabled()
    dialog.reject();dialog.deleteLater()


def test_vault_operations_cannot_claim_legacy_profile_is_locked(vault_bridge, monkeypatch):
    from grangerpet.portable_vault import PortableVault
    chat = vault_bridge.host.chat_widget
    chat._append('user', 'Сохранить этот вопрос')
    with monkeypatch.context() as patch:
        patch.setattr(credentials._STORE, 'portable', PortableVault(credentials._STORE.directory/'not-created.gpx'))
        with pytest.raises(ValueError,match='Сначала создайте'):
            vault_bridge._vault_manage('lock')
        assert chat.messages[-1]['text'] == 'Сохранить этот вопрос'


def test_existing_vault_cannot_be_recreated_and_password_change_requires_unlock(vault_bridge):
    with pytest.raises(ValueError,match='уже существует'):
        vault_bridge._vault_manage('create')
    credentials.lock_portable_vault()
    with pytest.raises(ValueError,match='Сначала разблокируйте'):
        vault_bridge._vault_manage('change')
