import json

from grangerpet.usage import UsageLedger


def test_request_conversation_and_investigation_totals_use_only_actual_usage(tmp_path):
    ledger = UsageLedger(tmp_path / 'usage.sqlite3')
    usage = {'usage': {'prompt_tokens': 17, 'completion_tokens': 4, 'total_tokens': 21},
             'headers': {'Authorization': 'DO-NOT-SAVE'}, 'text': 'Private conversation'}
    ledger.record_response(usage, provider='deepseek', model='deepseek-v4-flash', conversation_id='chat_1', investigation_id='case_1', request_id='req_1')
    ledger.record_response({'usage': {'prompt_tokens': 8, 'completion_tokens': 2, 'total_tokens': 10}}, conversation_id='chat_1', request_id='req_2')
    ledger.record_response({}, conversation_id='chat_2', request_id='req_3')
    assert ledger.snapshot('chat_1')['totals']['total_tokens'] == 31
    assert ledger.snapshot(investigation_id='case_1')['totals']['total_tokens'] == 21
    assert ledger.snapshot('chat_2')['totals']['total_tokens'] is None
    assert ledger.snapshot()['provider_balance']['status'] == 'unknown'
    assert ledger.snapshot()['context_window'] is None
    payload = (tmp_path / 'usage.sqlite3').read_bytes()
    assert b'DO-NOT-SAVE' not in payload and b'Private conversation' not in payload


def test_stable_request_id_prevents_double_counting_or_late_timeout_overwriting_usage(tmp_path):
    ledger = UsageLedger(tmp_path / 'usage.sqlite3')
    ledger.record_error(request_id='req_1', status='timeout', error_code='timeout')
    metadata = {'usage': {'prompt_tokens': 30, 'completion_tokens': 5, 'total_tokens': 35}}
    ledger.record_response(metadata, request_id='req_1')
    ledger.record_response(metadata, request_id='req_1')
    ledger.record_error(request_id='req_1', status='timeout', error_code='timeout')
    result = UsageLedger(tmp_path / 'usage.sqlite3').snapshot()
    assert result['totals']['requests'] == 1 and result['totals']['total_tokens'] == 35
    assert result['last_request']['status'] == 'success'


def test_invalid_or_partial_usage_is_not_filled_with_estimates(tmp_path):
    ledger = UsageLedger(tmp_path / 'usage.sqlite3')
    ledger.record_response({'usage': {'prompt_tokens': 10, 'completion_tokens': True, 'total_tokens': -1}}, request_id='partial')
    snapshot = ledger.snapshot()
    assert snapshot['totals']['prompt_tokens'] == 10 and snapshot['totals']['completion_tokens'] is None
    assert snapshot['totals']['total_tokens'] is None and snapshot['totals']['partial_usage']
    assert set(snapshot['last_request']['usage']) == {'prompt_tokens'}


def test_real_zero_usage_is_distinct_from_missing_usage(tmp_path):
    ledger = UsageLedger(tmp_path / 'usage.sqlite3')
    ledger.record_response({'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}})
    totals = ledger.snapshot()['totals']
    assert totals['total_tokens'] == 0 and totals['usage_reported_requests'] == 1
    assert not totals['partial_usage']


def test_reading_empty_ledger_does_not_create_files(tmp_path):
    path = tmp_path / 'unused' / 'usage.sqlite3'
    assert UsageLedger(path).snapshot()['totals']['requests'] == 0
    assert not path.exists()
