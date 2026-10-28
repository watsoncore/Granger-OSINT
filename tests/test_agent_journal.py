import pytest
import sys
from copy import deepcopy
from grangerpet.agent_journal import InvestigationJournal


def test_atomic_journal_retains_all_bounded_records_and_no_transport_secrets(tmp_path):
    store=InvestigationJournal(tmp_path)
    record={'id':'a'*32,'status':'cancelled','evidence':[{'id':str(i),'title':'fact','api_key':'secret'} for i in range(200)],
            'executions':[{'tool':'web_search','status':'partial'}], 'messages':[{'content':'private conversation'}],
            'headers':{'Authorization':'secret'},'runtime_python':'C:/private/python.exe'}
    path=store.save(record)
    saved=store.load(record['id'])
    assert len(saved['evidence'])==200
    assert 'secret' not in path.read_text(encoding='utf-8') and 'private conversation' not in str(saved)
    assert 'headers' not in saved and saved['status']=='cancelled'


def test_journal_rejects_model_supplied_paths(tmp_path):
    store=InvestigationJournal(tmp_path)
    with pytest.raises(ValueError):store.save({'id':'../arbitrary','evidence':[{}]})
    with pytest.raises(ValueError):store.load('../arbitrary')


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows DPAPI integration')
def test_private_checkpoint_is_encrypted_and_resumable_across_journal_instances(tmp_path):
    identifier = 'b' * 32
    value = {'version': 1, 'id': identifier, 'record': {'id': identifier, 'goal': 'Личная цель NOT-REAL-SECRET',
        'status': 'paused', 'resumable': True, 'checkpoint_revision': 2},
        'messages': [{'role': 'user', 'content': 'Личная переписка NOT-REAL-SECRET'}],
        'pending_calls': [{'id': 'one', 'name': 'web_search', 'arguments': {'query': 'fixture'}}],
        'call_cache': {'fingerprint': {'status': 'complete'}}, 'headers': {'Authorization': 'not-in-contract'}}
    store = InvestigationJournal(tmp_path)
    path = store.save_checkpoint(value, secrets=('NOT-REAL-SECRET',))
    encoded = path.read_bytes()
    assert 'Личная переписка'.encode('utf-8') not in encoded and b'NOT-REAL-SECRET' not in encoded
    restored_store = InvestigationJournal(tmp_path)
    restored = restored_store.load_checkpoint(identifier)
    assert 'NOT-REAL-SECRET' not in str(restored) and 'headers' not in restored
    assert restored['pending_calls'] == value['pending_calls'] and restored['call_cache'] == value['call_cache']
    assert restored_store.list_resumable()[0]['id'] == identifier
    older = deepcopy(value)
    older['record'].update(checkpoint_revision=1, status='running')
    restored_store.save_checkpoint(older)
    assert restored_store.load_checkpoint(identifier)['record']['status'] == 'paused'


def test_checkpoint_never_falls_back_to_plaintext_when_dpapi_unavailable(tmp_path, monkeypatch):
    from grangerpet.credentials import CredentialsStore, CredentialError
    def unavailable(*args, **kwargs):
        raise CredentialError('Unavailable')
    monkeypatch.setattr(CredentialsStore, '_protect', unavailable)
    store = InvestigationJournal(tmp_path)
    with pytest.raises(CredentialError):
        store.save_checkpoint({'version': 1, 'id': 'c'*32, 'record': {'id': 'c'*32}})
    assert not list(tmp_path.iterdir())
