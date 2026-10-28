import sys
import pytest
import json
from grangerpet.chat_archive import ChatArchive


@pytest.mark.skipif(sys.platform!='win32', reason='DPAPI requires Windows')
def test_archive_encrypts_real_unicode_and_redacts_key_before_storage(tmp_path):
    archive=ChatArchive(tmp_path/'history.dpapi')
    source=[{'role':'user','text':'Привет, Гермиона! private-test-key'},{'role':'model','text':'Привет!'}]
    archive.save(source,source,secrets=('private-test-key',))
    encoded=archive.path.read_bytes()
    assert 'Привет'.encode('utf-8') not in encoded and b'private-test-key' not in encoded
    loaded=archive.load()
    assert loaded['messages'][0]['text']=='Привет, Гермиона! [скрытый ключ]'
    assert loaded['context'][-1]['text']=='Привет!'


def test_corrupt_or_missing_archive_does_not_erase_current_runtime(tmp_path):
    archive=ChatArchive(tmp_path/'history.dpapi')
    assert archive.load()=={}
    archive.path.write_bytes(b'corrupted')
    assert archive.load()=={}


@pytest.mark.skipif(sys.platform!='win32', reason='Actual DPAPI migration')
def test_full_history_no_longer_silently_drops_older_messages_or_large_text(tmp_path):
    archive=ChatArchive(tmp_path/'history.dpapi')
    messages=[{'id':str(index),'role':'user' if index%2==0 else'model','text':str(index)+' Пример. '*600}
              for index in range(620)]
    messages[0]['text']='Сохранить это требование. '+'д'*130000
    messages[1].update(investigation_id='a'*32,evidence_ids=['ev_'+format(index,'020x')for index in range(250)])
    archive.save(messages,messages)
    restored=archive.load()
    assert len(restored['messages'])==len(restored['context'])==620
    assert restored['messages'][0]['text']==messages[0]['text']
    assert restored['messages'][1]['evidence_ids']==messages[1]['evidence_ids']
    assert restored['messages'][-1]['id']=='619'


@pytest.mark.skipif(sys.platform!='win32', reason='Actual DPAPI migration')
def test_legacy_ciphertext_is_backed_up_before_first_v2_write(tmp_path):
    from grangerpet.credentials import CredentialsStore
    archive=ChatArchive(tmp_path/'history.dpapi')
    legacy={'messages':[{'role':'user','text':'Исходная история'}],'context':[]}
    original=CredentialsStore._protect(json.dumps(legacy).encode())
    archive.path.write_bytes(original)
    assert archive.load()==legacy
    archive.save(legacy['messages'],[])
    backup=archive.path.with_name('history.dpapi.v1-backup')
    assert backup.read_bytes()==original and archive.load()==legacy
    archive.save(legacy['messages']+[{'role':'model','text':'Ответ'}],[])
    assert backup.read_bytes()==original


@pytest.mark.skipif(sys.platform!='win32', reason='Actual DPAPI storage preservation')
def test_storage_policy_error_preserves_previous_ciphertext_instead_of_trimming(tmp_path,monkeypatch):
    archive=ChatArchive(tmp_path/'history.dpapi');archive.save([{'role':'user','text':'Previous'}],[])
    previous=archive.path.read_bytes()
    monkeypatch.setattr('grangerpet.chat_archive.MAX_ARCHIVE_BYTES',200)
    with pytest.raises(ValueError):archive.save([{'role':'user','text':'x'*1000}],[])
    assert archive.path.read_bytes()==previous


@pytest.mark.skipif(sys.platform!='win32', reason='Actual DPAPI named-conversation migration')
def test_legacy_named_conversation_backup_survives_new_current_archive_write(tmp_path):
    from grangerpet.credentials import CredentialsStore
    from grangerpet.conversations import ConversationLibrary
    archive=ChatArchive(tmp_path/'history.dpapi');archive.save([{'role':'user','text':'Current'}],[])
    library=ConversationLibrary(archive)
    identifier='c'*32
    legacy={'messages':[{'role':'user','text':'Legacy saved history'}],'context':[]}
    original=CredentialsStore._protect(json.dumps(legacy).encode())
    source=library.directory/(identifier+'.dpapi');source.write_bytes(original)
    assert library.load(identifier)==legacy
    backup=source.with_name(source.name+'.v1-backup')
    archive.save(legacy['messages']+[{'role':'model','text':'New reply'}],[]);library.seal()
    assert backup.read_bytes()==original and source.read_bytes()!=original
    assert archive.load()['messages'][0]['text']=='Legacy saved history'
