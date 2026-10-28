import sys
import pytest
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
