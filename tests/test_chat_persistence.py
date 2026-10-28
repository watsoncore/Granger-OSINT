"""Disk failures cannot silently discard the currently visible conversation."""
from copy import deepcopy
import os
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.chat import ChatWidget
from grangerpet.chat_archive import ChatArchive
from grangerpet.config import Settings, SettingsStore


@pytest.fixture
def persisted_chat(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    previous=app.property('web_desktop');app.setProperty('web_desktop',False)
    monkeypatch.setattr('grangerpet.chat.resolve_deepseek_key',lambda:'')
    chat=ChatWidget(Settings(),SettingsStore(tmp_path/'settings.json'))
    chat._append('user','Original question');chat._append('model','Original answer')
    chat._context=[{'role':'user','text':'Original question'},{'role':'model','text':'Original answer'}]
    assert chat._save_archive()
    yield app,chat
    chat._archive_timer.stop();chat.close();chat.deleteLater();app.processEvents()
    app.setProperty('web_desktop',previous)


def fail_write(*args,**kwargs):
    raise OSError('Controlled unavailable storage')


@pytest.mark.parametrize('operation',['new','load'])
def test_failed_current_save_aborts_new_or_load_without_changing_memory_id_or_files(persisted_chat,monkeypatch,operation):
    _,chat=persisted_chat
    chat._append('user','Unsaved new requirement')
    original=deepcopy(chat.messages);identifier=chat.conversation_id
    ciphertext=chat._archive.path.read_bytes();pointer=chat._library.pointer.read_bytes()
    changed=[];chat.state_changed.connect(lambda:changed.append(chat.archive_error))
    monkeypatch.setattr(chat._archive,'save',fail_write)
    with pytest.raises(ValueError,match='Не удалось сохранить'):
        chat.new_conversation() if operation=='new' else chat.load_conversation('a'*32)
    assert chat.messages==original and chat.conversation_id==chat._library.current_id==identifier
    assert chat._archive.path.read_bytes()==ciphertext and chat._library.pointer.read_bytes()==pointer
    assert chat.archive_error and changed[-1]==chat.archive_error
    assert 'Unsaved new requirement' in chat.history.toPlainText()


def test_real_archive_size_guard_keeps_unsaved_messages_and_old_conversation(persisted_chat,monkeypatch):
    _,chat=persisted_chat
    chat._append('user','Large unsaved input '*100)
    original=deepcopy(chat.messages);ciphertext=chat._archive.path.read_bytes();identifier=chat.conversation_id
    monkeypatch.setattr('grangerpet.chat_archive.MAX_ARCHIVE_BYTES',200)
    with pytest.raises(ValueError):chat.new_conversation()
    assert chat.messages==original and chat.conversation_id==identifier
    assert chat._archive.path.read_bytes()==ciphertext and '64 МиБ' in chat.archive_error


def test_explicit_clear_does_not_pretend_it_was_saved_if_replacement_write_fails(persisted_chat,monkeypatch):
    _,chat=persisted_chat
    messages=deepcopy(chat.messages);context=deepcopy(chat._context);ciphertext=chat._archive.path.read_bytes()
    original_status=chat.status.text()
    monkeypatch.setattr(chat._archive,'save',fail_write)
    assert chat.clear_history() is False
    assert chat.messages==messages and chat._context==context
    assert chat._archive.path.read_bytes()==ciphertext and chat.status.text()==original_status
    assert chat.archive_error


def test_archive_error_clears_after_successful_retry_and_then_allows_new_dialog(persisted_chat,monkeypatch):
    _,chat=persisted_chat
    save=chat._archive.save
    monkeypatch.setattr(chat._archive,'save',fail_write)
    assert chat._save_archive() is False and chat.archive_error
    monkeypatch.setattr(chat._archive,'save',save)
    states=[];chat.state_changed.connect(lambda:states.append(chat.archive_error))
    assert chat._save_archive() is True and not chat.archive_error
    assert states[-1]==''
    previous=chat.conversation_id
    chat.new_conversation()
    assert chat.conversation_id!=previous and chat.messages==[]
    saved=ChatArchive(chat._library.directory/(previous+'.dpapi')).load()
    assert saved['messages'][0]['text']=='Original question'


def test_second_write_failure_during_new_dialog_preserves_memory_and_restores_current_id(persisted_chat,monkeypatch):
    _,chat=persisted_chat
    previous=chat.conversation_id;original=deepcopy(chat.messages);pointer=chat._library.pointer.read_bytes()
    save=chat._archive.save;calls=[]
    def fail_empty(messages,context,**kwargs):
        calls.append(len(messages))
        if not messages:raise OSError('Controlled new archive creation failure')
        return save(messages,context,**kwargs)
    monkeypatch.setattr(chat._archive,'save',fail_empty)
    with pytest.raises(ValueError):chat.new_conversation()
    assert calls==[2,0]
    assert chat.messages==original and chat.conversation_id==chat._library.current_id==previous
    assert chat._library.pointer.read_bytes()==pointer


def test_named_archive_copy_failure_blocks_switch_while_current_ciphertext_keeps_new_messages(persisted_chat,monkeypatch):
    _,chat=persisted_chat
    chat._append('user','Keep this latest unsaved requirement')
    original=deepcopy(chat.messages);identifier=chat.conversation_id
    monkeypatch.setattr(chat._library,'seal',fail_write)
    with pytest.raises(ValueError):chat.new_conversation()
    assert chat.messages==original and chat.conversation_id==chat._library.current_id==identifier
    assert ChatArchive(chat._archive.path).load()['messages'][-1]['text']=='Keep this latest unsaved requirement'


def test_new_pointer_write_failure_keeps_current_conversation_and_saved_data(persisted_chat,monkeypatch):
    _,chat=persisted_chat
    identifier=chat.conversation_id;original=deepcopy(chat.messages);pointer=chat._library.pointer.read_bytes()
    monkeypatch.setattr(chat._library,'_write_pointer',fail_write)
    with pytest.raises(ValueError,match='создать новый диалог'):chat.new_conversation()
    assert chat.messages==original and chat.conversation_id==chat._library.current_id==identifier
    assert chat._library.pointer.read_bytes()==pointer and chat.archive_error


def test_web_bulk_restore_does_not_create_hidden_native_bubbles_and_next_stream_keeps_indices(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    previous=app.property('web_desktop');app.setProperty('web_desktop',True)
    monkeypatch.setattr('grangerpet.chat.resolve_deepseek_key',lambda:'')
    rows=[{'id':str(index),'role':'user' if index%2==0 else'model','text':'Stored line '+str(index)}for index in range(1000)]
    rows[1].update(investigation_id='a'*32,evidence_ids=['ev_'+'b'*20])
    archive=ChatArchive(tmp_path/'chat-history.dpapi');archive.save(rows,[])
    chat=ChatWidget(Settings(),SettingsStore(tmp_path/'settings.json'))
    try:
        assert len(chat.messages)==1000 and len(chat.history.bubbles)==0
        assert chat.messages[1]['evidence_ids']==rows[1]['evidence_ids']
        chat._busy=True;chat._generation=7
        chat._on_agent_progress(7,{'type':'text','text':'Stream start'})
        chat._on_agent_progress(7,{'type':'text','text':'Stream complete'})
        assert chat._stream_index==1000 and len(chat.history.bubbles)==1
        assert chat.messages[1000]['text']=='Stream complete' and chat.messages[0]['text']=='Stored line 0'
        chat.history.update_message(chat._stream_bubble,'Stream final')
        chat.history.flush_updates()
        chat.messages[1000]['text']='Stream final'
        assert chat.history._records[0]['text']=='Stream final'
        assert chat._save_archive()
        restored=archive.load()['messages']
        assert len(restored)==1001 and restored[0]['text']=='Stored line 0' and restored[-1]['text']=='Stream final'
    finally:
        chat._busy=False;chat._archive_timer.stop();chat.close();chat.deleteLater();app.processEvents()
        app.setProperty('web_desktop',previous)
