"""Real Qt controllers behind the finite renderer protocol; no live API claims."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl

from grangerpet.config import Settings, SettingsStore
from grangerpet.panel import OsintPanel
from grangerpet.desktop_bridge import DesktopBridge
from grangerpet.desktop_surface import bundled_url
from grangerpet.chat_archive import ChatArchive
from grangerpet.conversations import ConversationLibrary


@pytest.fixture
def bridge(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    for module in ('grangerpet.panel','grangerpet.connections','grangerpet.ai_keys'):
        monkeypatch.setattr(module+'.get_secret',lambda name:'')
    monkeypatch.setattr('grangerpet.desktop_bridge.resolve_deepseek_key',lambda:'')
    host=OsintPanel(Settings(),SettingsStore(tmp_path/'settings.json'))
    value=DesktopBridge(host)
    yield value
    value.shutdown();host.shutdown();host.deleteLater();app.processEvents()


def test_bridge_reports_only_actual_sources_and_no_secret_settings(bridge):
    bridge.host.chat_widget._append('model','# Actual stored fixture')
    bridge.host._agent_evidence([{'evidence_id':'ev_'+'a'*20,'id':'fixture','title':'Known fixture page','url':'https://example.org/',
        'type':'web','platform':'Example','description':'Fixture body','details':{'reading_method':'direct_http'},'status':'verified'}])
    snapshot=bridge.snapshot()
    assert snapshot['messages'][-1]['text']=='# Actual stored fixture'
    assert snapshot['evidence'][0]['kind']=='page'
    assert 'api_key' not in snapshot['settings'] and snapshot['connection']['balance'] is None
    assert 'не предоставляет' in snapshot['connection']['balanceMessage']


def test_finite_actions_reject_arbitrary_paths_commands_and_secret_fields(bridge,tmp_path):
    for action,payload in [('shell',{'command':'whoami'}),('settings_save',{'values':{'api_key':'forbidden'}}),
        ('open_url',{'url':'file:///C:/Windows/win.ini'}),('open_url',{'url':'javascript:alert(1)'}),
        ('history_load',{'id':'../../outside'}),('tool_run',{'tool':'cmd','query':'whoami'})]:
        with pytest.raises((ValueError,KeyError)):bridge.dispatch(action,payload)
    assert not list(tmp_path.glob('outside*'))


def test_canvas_edit_rejects_stale_document_and_keeps_evidence(bridge):
    row=bridge.host.chat_widget._append('model','# Current report\n\nOriginal')
    identifier=bridge.host.chat_widget.messages[-1]['id']
    bridge.dispatch('canvas_open',{'message_id':identifier})
    canvas=bridge.host.canvas
    with pytest.raises(ValueError):bridge.dispatch('canvas_edit',{'document_id':'wrong','text':'Overwrite'})
    assert 'Original' in canvas.editor.toPlainText()
    bridge.dispatch('canvas_edit',{'document_id':canvas.document_id,'text':'# Edited report'})
    bridge.dispatch('canvas_save',{})
    assert canvas.editor.toPlainText()=='# Edited report'
    assert bridge.host.chat_widget.messages[-1]['text']=='# Current report\n\nOriginal'


def test_stream_delta_transmits_one_changed_message(bridge):
    chat=bridge.host.chat_widget
    chat._append('user','Question');chat._append('model','Initial')
    values=[];bridge.stateChanged.connect(values.append)
    bridge.publish(force=True);chat.messages[-1]['text']='Initial streaming extension';bridge.publish()
    update=json.loads(values[-1])
    assert 'messages' not in update
    assert update['message_updates']==[{'index':1,'message':{**chat.messages[-1],'streaming':False,'sources':[]}}]


def test_asset_origin_cannot_escape_bundle_or_load_remote_content(tmp_path):
    (tmp_path/'index.html').write_text('<html/>')
    assert bundled_url(QUrl('granger://app/index.html'),tmp_path)
    assert bundled_url(QUrl('qrc:///qtwebchannel/qwebchannel.js'),tmp_path)
    for url in ('file:///C:/Windows/win.ini','https://example.org/','granger://attacker/index.html',
                'granger://app/../../Windows/win.ini','qrc:///unrelated/script.js'):
        assert not bundled_url(QUrl(url),tmp_path)


def test_legacy_archive_is_preserved_when_starting_and_switching_conversations(tmp_path):
    archive=ChatArchive(tmp_path/'chat-history.dpapi')
    archive.save([{'role':'user','text':'Первый разговор'},{'role':'model','text':'Первый ответ'}],[])
    original=archive.path.read_bytes();library=ConversationLibrary(archive);first=library.current_id
    second=library.new()
    assert first!=second and (tmp_path/'conversations'/f'{first}.dpapi').read_bytes()==original
    archive.save([{'role':'user','text':'Второй разговор'}],[]);library.seal()
    assert library.load(first)['messages'][0]['text']=='Первый разговор'
    assert library.load(second)['messages'][0]['text']=='Второй разговор'
    assert len(library.list())==2
    assert b'conversation' not in original and 'Первый разговор'.encode() not in original
