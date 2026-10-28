import pytest
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
