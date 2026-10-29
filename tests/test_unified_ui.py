"""UI/AI integration checks with explicit local fixture evidence."""
import json
import os
import time
from unittest.mock import Mock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog
from grangerpet.config import Settings,SettingsStore
from grangerpet.connections import ConnectionsPane
from grangerpet.credentials import CredentialError
from grangerpet.engine import Result
from grangerpet.launcher import Launcher
from grangerpet.panel import OsintPanel

@pytest.fixture(scope='module')
def app():
    value=QApplication.instance()or QApplication([]);value.setQuitOnLastWindowClosed(False);return value

@pytest.fixture
def vault(monkeypatch):
    values={}
    for module in ('grangerpet.credentials','grangerpet.connections','grangerpet.panel','grangerpet.ai_keys'):
        monkeypatch.setattr(module+'.get_secret',lambda name:values.get(name,''))
    for module in ('grangerpet.credentials','grangerpet.connections'):
        monkeypatch.setattr(module+'.set_secret',lambda name,value:values.__setitem__(name,value))
        monkeypatch.setattr(module+'.delete_secret',lambda name:values.pop(name,None))
    return values

def wait(app,predicate):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        QTest.qWait(10)
    pytest.fail('Qt task did not finish')

def test_explicit_provider_named_deepseek_action_uses_evidence_only(app,vault,monkeypatch):
    network=Mock(return_value='Fixture model explanation')
    vault['deepseek_api_key']='fixture-key'
    monkeypatch.setattr('grangerpet.chat.explain_evidence',network)
    monkeypatch.setattr('grangerpet.chat.EvidenceSelection.exec',lambda self:QDialog.DialogCode.Accepted)
    panel=OsintPanel(Settings(ai_provider='deepseek',deepseek_model='fixture-model'))
    try:
        panel._engine_result(Result('one','Public fixture evidence','web','Example','https://example.org/'))
        app.processEvents();network.assert_not_called()
        assert panel.analyze.text()=='Объяснить с помощью Гермионы'
        panel.analyze.click();wait(app,lambda:not panel.chat_widget._busy)
        network.assert_called_once()
        assert network.call_args.kwargs['external_consent']is True
        assert network.call_args.args[2][0]['id']=='one'
        assert 'Fixture model explanation'in panel.chat_widget.history.toPlainText()
        assert panel.mode_tabs.currentWidget()is panel.chat_widget
        assert panel.result_model.rowCount()==1
        panel.show_search();assert panel.result_model.rowCount()==1
    finally:panel.shutdown();panel.deleteLater()

def test_same_source_url_preserves_distinct_blockchain_observations(app,vault):
    panel=OsintPanel(Settings())
    try:
        url='https://example.org/address/one'
        panel._engine_result(Result('one','Balance','balance','Ethereum',url,details={'amount':'1'}))
        panel._engine_result(Result('one','Service label','label','Ethereum',url,details={'label':'Fixture'},status='check'))
        assert len(panel._records)==panel.result_model.rowCount()==2
    finally:panel.shutdown();panel.deleteLater()

def test_unavailable_secret_backend_does_not_disable_keyless_public_search(app,vault,monkeypatch):
    def unavailable(name):raise CredentialError('Vault unavailable')
    monkeypatch.setattr('grangerpet.connections.get_secret',unavailable)
    monkeypatch.setattr('grangerpet.panel.get_secret',unavailable)
    monkeypatch.setattr('grangerpet.ai_keys.get_secret',unavailable)
    opened=Mock(return_value=True);monkeypatch.setattr('grangerpet.panel.QDesktopServices.openUrl',opened)
    panel=OsintPanel(Settings(ai_provider='deepseek',deepseek_model='fixture'))
    try:
        dispatched=[]
        monkeypatch.setattr(panel.controller,'start',lambda query,options:dispatched.append((query,options)) or False)
        panel.text.setText('site:example.org report');panel.start_search()
        opened.assert_not_called()
        assert len(dispatched)==1 and dispatched[0][0].kind=='dork'
        assert not dispatched[0][1].get('google_api_key')
        assert not panel._has_api()
        panel._engine_result(Result('one','Evidence','web','Example','https://example.org/'))
        monkeypatch.setattr(panel,'open_settings',lambda *args:None)
        panel.analyze_current_results()
        assert not panel.chat_widget._busy
        assert not panel.ai_state.snapshot()['credential_available']
        assert panel.chat_widget.provider_status.text() == panel.ai_state.status_text()
    finally:panel.shutdown();panel.deleteLater()

def test_connections_store_only_preferences_in_json_and_secrets_in_vault(app,vault,tmp_path):
    store=SettingsStore(tmp_path/'settings.json');pane=ConnectionsPane(Settings(),store)
    try:
        pane.google_key.setText('fixture-google-secret');pane.deepseek_key.setText('fixture-deepseek-secret');pane.google_cx.setText('fixture-cx');pane.save()
        payload=store.path.read_text(encoding='utf-8')
        assert 'fixture-google-secret'not in payload and'fixture-deepseek-secret'not in payload
        assert 'api_key'not in json.loads(payload)and json.loads(payload)['api_cx']=='fixture-cx'
        assert vault['google_api_key']=='fixture-google-secret'and vault['deepseek_api_key']=='fixture-deepseek-secret'
        assert pane.google_key.text()==pane.deepseek_key.text()==''
    finally:pane.shutdown();pane.deleteLater()

def test_launcher_existing_compact_process_controls_unchanged(app,vault,tmp_path):
    launcher=Launcher(SettingsStore(tmp_path/'settings.json'))
    try:
        launcher.show();app.processEvents()
        assert launcher.width()==360 and launcher.height()<=420
        assert not launcher.preview.pixmap().isNull()
        assert(launcher.size_slider.minimum(),launcher.size_slider.maximum(),launcher.size_slider.value())==(100,195,195)
        assert not launcher.reaction_box.isVisible()
        launcher.preferences_toggle.setChecked(True);app.processEvents();assert launcher.reaction_box.isVisible()
        launcher.size_slider.setValue(100);launcher.save_preferences();assert launcher.store.load().size==100
    finally:launcher.close();launcher.deleteLater()


def test_verified_draft_save_updates_open_chat_and_restarted_configuration(app,vault,tmp_path,monkeypatch):
    calls=[]
    class ExplicitFakeDeepSeek:
        def __init__(self,*args,**kwargs):
            pass
        def test_connection(self,model,*,cancel_event=None):
            calls.append(('check',model,vault.get('deepseek_api_key')))
            return {'connected':True,'model':model,'text':'EXPLICIT LOCAL TEST FIXTURE'}
        def chat(self,model,messages,*,cancel_event=None):
            calls.append(('chat',model,vault.get('deepseek_api_key')))
            return 'EXPLICIT LOCAL TEST REPLY'
    monkeypatch.setattr('grangerpet.connections.DeepSeekClient',ExplicitFakeDeepSeek)
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient',ExplicitFakeDeepSeek)
    store=SettingsStore(tmp_path/'settings.json');store.save(Settings())
    panel=OsintPanel(store.load(),store)
    other=None
    try:
        pane=panel.connections
        assert pane.ai_state is panel.ai_state is panel.chat_widget.ai_state
        pane.provider.setCurrentIndex(pane.provider.findData('deepseek'))
        pane.deepseek_key.setText('EXPLICIT-TEST-KEY-ONE')
        pane.check_connection();wait(app,lambda:not pane._jobs)
        assert panel.ai_state.snapshot()['connection_status']=='verified_unsaved'
        assert 'Сохраните' in panel.chat_widget.provider_status.text()
        assert not panel.ai_state.can_send
        assert pane.save()
        assert panel.ai_state.snapshot()['connection_status']=='connected'
        assert panel.settings.ai_provider==panel.chat_widget.settings.ai_provider=='deepseek'
        assert panel.chat_widget.provider_status.toolTip()==pane.ai_status.text()
        assert 'Подключено' in panel.chat_widget.provider_status.toolTip()
        panel.chat_widget.input.setPlainText('Привет — явная тестовая подстановка')
        assert panel.chat_widget.send.isEnabled()
        panel.chat_widget.send.click();wait(app,lambda:not panel.chat_widget.busy)
        assert calls[-1] == ('chat','deepseek-v4-flash','EXPLICIT-TEST-KEY-ONE')
        assert 'EXPLICIT LOCAL TEST REPLY' in panel.chat_widget.history.toPlainText()
        before=len(calls)
        other=OsintPanel(store.load(),store)
        assert len(calls)==before  # Restart never consumes a verification request.
        assert other.ai_state.can_send
        assert other.ai_state.snapshot()['connection_status']=='configured_unverified'
        other.chat_widget.input.setPlainText('Restart test draft')
        assert other.chat_widget.send.isEnabled()
        assert 'EXPLICIT-TEST-KEY-ONE' not in store.path.read_text(encoding='utf-8')
    finally:
        panel.shutdown();panel.deleteLater()
        if other:other.shutdown();other.deleteLater()


def test_panel_close_cancels_pending_chat_without_losing_messages_or_draft(app,vault,monkeypatch):
    import threading
    entered=threading.Event()
    class PendingFixture:
        def chat(self,model,messages,*,cancel_event=None):
            entered.set();cancel_event.wait(2)
            return 'Late fixture must be discarded'
    vault['deepseek_api_key']='explicit-ui-fixture-key'
    monkeypatch.setattr('grangerpet.chat.DeepSeekClient',PendingFixture)
    panel=OsintPanel(Settings(ai_provider='deepseek',deepseek_model='deepseek-v4-flash'))
    try:
        panel.show();panel.show_chat();panel.chat_widget.input.setPlainText('Submitted fixture message')
        panel.chat_widget.send_message();wait(app,entered.is_set)
        panel.chat_widget.input.setPlainText('Draft written while waiting')
        panel.close();app.processEvents()
        assert not panel.chat_widget.busy
        assert panel.chat_widget.input.toPlainText()=='Draft written while waiting'
        assert 'Submitted fixture message' in panel.chat_widget.history.toPlainText()
        QTest.qWait(50);app.processEvents()
        assert 'Late fixture must be discarded' not in panel.chat_widget.history.toPlainText()
    finally:panel.shutdown();panel.deleteLater()
