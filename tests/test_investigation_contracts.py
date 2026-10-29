"""Malformed persistence must be stopped at its read/write boundary."""
from copy import deepcopy
import json

import pytest

from grangerpet.agent_evidence import normalize_evidence
from grangerpet.agent_journal import InvestigationJournal
from grangerpet.investigation_contracts import (InvestigationContractError,
                                               recover_public_snapshot,
                                               validate_checkpoint)


IDENTIFIER = 'a' * 32


def evidence():
    return normalize_evidence({'id': 'public', 'type': 'web', 'title': 'Публичная страница',
        'platform': 'Example', 'url': 'https://example.org/public', 'status': 'indexed'},
        'web_read', 'https://example.org/public', '2026-10-30T00:00:00Z')


def checkpoint():
    row = evidence()
    outcome = {'tool': 'web_read', 'query': row['url'], 'status': 'complete',
               'results': [row], 'limitations': []}
    return {'version': 1, 'id': IDENTIFIER,
        'record': {'id': IDENTIFIER, 'status': 'paused', 'checkpoint_revision': 1},
        'messages': [{'role': 'system', 'content': 'Система'}, {'role': 'user', 'content': 'Проверка'}],
        'evidence': [row], 'executions': [{'tool': 'web_read', 'status': 'complete'}],
        'pending_calls': [{'id': 'c1', 'name': 'web_read', 'arguments': {'url': row['url']},
                           'fingerprint': 'abc', 'dispatched': True}],
        'pending_outcomes': {'c1': outcome},
        'call_cache': {'abc': {'outcome': outcome, 'resume_count': 0}},
        'seen_call_ids': ['c1'], 'failures': [], 'completed_steps': [], 'tried_queries': [],
        'pending_work': ['Продолжить'], 'plan': 'Проверить источник', 'context_memory': [],
        'registry_state': {'page_count': 1, 'known': [{'url': row['url'], 'depth': 0, 'parent_url': ''}],
                           'attachment_ids': []},
        'usage_requests': {'r1': {'status': 'success', 'usage': {'total_tokens': 10}}},
        'sent_content': {'hash': row['evidence_id']}, 'budget_reserved_tokens': 10}


@pytest.mark.parametrize('key,bad', [
    ('messages', ['SERVER ERROR PRIVATE']), ('messages', [{'role': 'tool', 'content': '"PRIVATE"', 'tool_call_id': 'c'}]),
    ('pending_calls', ['PRIVATE']), ('pending_calls', [{'id': 'c', 'name': 'web_read', 'arguments': []}]),
    ('pending_outcomes', {'c': 'PRIVATE'}), ('call_cache', {'hash': 'PRIVATE'}),
    ('call_cache', {'hash': {'outcome': {'results': ['PRIVATE']}}}),
    ('usage_requests', {'r': 'PRIVATE'}), ('usage_requests', {'r': {'usage': 'PRIVATE'}}),
    ('registry_state', 'PRIVATE'), ('registry_state', {'known': ['PRIVATE']}),
    ('context_memory', ['PRIVATE']), ('evidence', ['PRIVATE']),
    ('executions', ['PRIVATE']), ('record', 'PRIVATE'), ('completed_steps', ['PRIVATE']),
    ('failures', ['PRIVATE']), ('seen_call_ids', [{}]), ('sent_content', {'hash': {}}),
])
def test_checkpoint_rejects_nested_contract_before_replay(key, bad):
    value = checkpoint()
    value[key] = bad
    with pytest.raises(InvestigationContractError) as caught:
        validate_checkpoint(value)
    assert caught.value.code == 'invalid_investigation_data'
    assert 'PRIVATE' not in str(caught.value)
    assert 'PRIVATE' not in str(caught.value.diagnostic())


def test_real_runner_checkpoint_satisfies_contract():
    from tests.test_agent_lifecycle import Client, Registry, HISTORY, response, tool
    from grangerpet.agent import AgentRunner, AgentLimits
    runner = AgentRunner(Client([response(tool())]), Registry(), limits=AgentLimits(max_steps=1))
    runner.run('fixture', HISTORY)
    value = runner.checkpoint()
    assert validate_checkpoint(value) is value


def test_corrupt_public_row_is_quarantined_without_discarding_other_rows_or_rewriting(tmp_path, caplog):
    store = InvestigationJournal(tmp_path)
    good = evidence()
    bad = deepcopy(good)
    bad['provenance'] = 'PRIVATE WRONG DATA'
    original = {'id': IDENTIFIER, 'status': 'running', 'evidence': [good, bad],
                'executions': [{'tool': 'web_read', 'status': 'complete'}, 'PRIVATE WRONG DATA']}
    path = tmp_path / (IDENTIFIER + '.json')
    encoded = json.dumps(original, ensure_ascii=False).encode('utf-8')
    path.write_bytes(encoded)
    first = store.load(IDENTIFIER)
    second = store.load(IDENTIFIER)
    assert first == second and first['status'] == 'interrupted'
    assert first['evidence'] == [good] and len(first['executions']) == 1
    assert first['quarantined_records'] == 2
    assert first['validation_warnings'][0]['path'] == 'investigation.evidence[1].provenance'
    assert path.read_bytes() == encoded and not list(tmp_path.glob('*.tmp'))
    assert 'PRIVATE WRONG DATA' not in caplog.text
    assert caplog.text.count('Investigation data quarantined') == 2


def test_public_invalid_container_has_explicit_recovery_diagnostic():
    result = recover_public_snapshot({'id': IDENTIFIER, 'evidence': 'PRIVATE', 'executions': []}, IDENTIFIER)
    assert result['evidence'] == [] and result['quarantined_records'] == 1
    assert result['validation_warnings'][0]['actual_type'] == 'str'


def test_damaged_optional_report_metadata_does_not_discard_intact_evidence():
    original = {'id': IDENTIFIER, 'status': 'paused', 'evidence': [evidence()],
                'executions': [], 'context_compactions': '[ограничено]',
                'elapsed_seconds': None, 'usage': 'damaged'}
    result = recover_public_snapshot(original, IDENTIFIER)
    assert result['evidence'] == original['evidence']
    assert result['status'] == 'paused'
    assert all(key not in result for key in ('context_compactions', 'elapsed_seconds', 'usage'))
    assert result['quarantined_records'] == 0 and result['validation_issue_count'] == 3
    assert result['validation_warnings'][0]['path'] == 'investigation.context_compactions'
    assert original['context_compactions'] == '[ограничено]'


def test_public_save_validates_unexpected_rows_and_preserves_all_valid_rows(tmp_path):
    store = InvestigationJournal(tmp_path)
    value = {'id': IDENTIFIER, 'status': 'running', 'evidence': [evidence(), 'PRIVATE'],
             'executions': [{'tool': 'web_read', 'status': 'complete'}]}
    path = store.save(value)
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['status'] == 'running' and len(saved['evidence']) == 1
    assert saved['quarantined_records'] == 1 and 'PRIVATE' not in path.read_text(encoding='utf-8')


def test_large_public_record_keeps_identity_and_origin_beyond_details_budget(tmp_path):
    row = evidence()
    row['details']['large_parser_result'] = [{str(index): 'value' for index in range(60)} for _ in range(150)]
    store = InvestigationJournal(tmp_path)
    path = store.save({'id': IDENTIFIER, 'status': 'paused', 'evidence': [row]})
    saved = store.load(IDENTIFIER)
    assert len(saved['evidence']) == 1
    assert saved['evidence'][0]['evidence_id'] == row['evidence_id']
    assert saved['evidence'][0]['provenance'] == row['provenance']
    assert 'quarantined_records' not in saved
    assert json.loads(path.read_text(encoding='utf-8'))['evidence'][0]['provenance'] == row['provenance']


def test_checkpoint_save_rejects_malformed_state_without_replacing_previous_ciphertext(tmp_path):
    store = InvestigationJournal(tmp_path)
    value = checkpoint()
    path = store.save_checkpoint(value)
    previous = path.read_bytes()
    value['call_cache']['abc'] = 'PRIVATE'
    with pytest.raises(InvestigationContractError):
        store.save_checkpoint(value)
    assert path.read_bytes() == previous


def test_checkpoint_load_rejects_malformed_state_without_mutating_ciphertext(tmp_path):
    from grangerpet.credentials import CredentialsStore
    store = InvestigationJournal(tmp_path)
    value = checkpoint()
    value['pending_outcomes']['c1']['results'] = 'PRIVATE'
    encoded = CredentialsStore._protect(json.dumps(value).encode('utf-8'))
    path = tmp_path / (IDENTIFIER + '.checkpoint.dpapi')
    path.write_bytes(encoded)
    with pytest.raises(InvestigationContractError):
        store.load_checkpoint(IDENTIFIER)
    assert path.read_bytes() == encoded


def test_public_provenance_recovers_only_matching_validated_checkpoint_rows_without_rewrites(tmp_path):
    store = InvestigationJournal(tmp_path)
    private = checkpoint()
    private_path = store.save_checkpoint(private)
    private_bytes = private_path.read_bytes()
    good = private['evidence'][0]
    damaged = deepcopy(good)
    damaged['provenance'] = '[ограничено]'
    unrelated = deepcopy(damaged)
    unrelated['evidence_id'] = 'ev_different'
    original = {'id': IDENTIFIER, 'status': 'running', 'evidence': [damaged, unrelated], 'executions': []}
    encoded = json.dumps(original, ensure_ascii=False).encode('utf-8')
    public_path = tmp_path / (IDENTIFIER + '.json')
    public_path.write_bytes(encoded)
    result = store.load(IDENTIFIER)
    assert result['evidence'] == [good]
    assert result['recovered_records'] == 1 and result['quarantined_records'] == 1
    assert result['checkpoint_recovery'] == 'validated_matching_evidence_ids'
    assert result['status'] == 'interrupted'
    assert 'messages' not in result and 'pending_calls' not in result
    assert private_path.read_bytes() == private_bytes and public_path.read_bytes() == encoded


def test_compact_protocol_provenance_is_validated_without_requiring_full_saved_row():
    value = checkpoint()
    compact = {'tool': 'web_read', 'status': 'complete', 'results': [
        {'evidence_id': value['evidence'][0]['evidence_id'], 'title': 'Page',
         'provenance': {'tool': 'web_read', 'obtained_at': '2026-10-30'}}]}
    value['messages'].append({'role': 'tool', 'tool_call_id': 'c1', 'content': json.dumps(compact)})
    assert validate_checkpoint(value)


def test_checkpoint_redacts_json_escaped_secret_before_encryption(tmp_path):
    value = checkpoint()
    secret = 'SYNTHETIC-"-ESCAPED\nSECRET'
    value['messages'][1]['content'] += secret
    store = InvestigationJournal(tmp_path)
    store.save_checkpoint(value, secrets=(secret,))
    restored = store.load_checkpoint(IDENTIFIER)
    assert secret not in restored['messages'][1]['content']
    assert '[скрытый ключ]' in restored['messages'][1]['content']


def test_identifier_never_coerces_nonstring_into_path(tmp_path):
    with pytest.raises(ValueError):
        InvestigationJournal(tmp_path).load(int('1' * 32))
