"""Regressions for shape-changing redaction and damaged persisted evidence.

All data is synthetic. No user journals, vaults, network or model runtime.
"""
from copy import deepcopy

import pytest

from grangerpet.agent_evidence import (EvidenceContractError, EvidenceStore,
                                      normalize_evidence, redact, sanitize_evidence,
                                      validate_saved_evidence)
from grangerpet.investigation import InvestigationEvidence


def finding(**changes):
    value = {'id': 'synthetic', 'title': 'Synthetic source', 'type': 'web',
             'platform': 'fixture', 'url': 'https://example.org/',
             'details': {}, 'status': 'verified', 'sources': ['fixture']}
    value.update(changes)
    return value


def large_details():
    return {'rows': [{'k' + str(k): 'x' for k in range(60)} for _ in range(150)]}


def test_large_adapter_data_never_erases_identity_status_or_generated_provenance():
    record = normalize_evidence(finding(details=large_details()), 'web_read', 'synthetic')
    assert record['status'] == 'verified'
    assert record['verification'] == 'source_reported'
    assert record['id'] == 'synthetic'
    assert record['provenance']['tool'] == 'web_read'
    assert validate_saved_evidence(record)['evidence_id'] == record['evidence_id']


def test_evidence_sanitizer_preserves_late_metadata_and_secrets_are_still_removed():
    record = normalize_evidence(finding(details=large_details()), 'web_read', 'synthetic')
    record['provenance']['basis'] = 'safe excerpt with NOT-REAL-KEY'
    safe = sanitize_evidence(record, ('NOT-REAL-KEY',))
    assert safe['evidence_id'] == record['evidence_id']
    assert safe['resource_id'] == record['resource_id']
    assert safe['provenance']['tool'] == 'web_read'
    assert 'NOT-REAL-KEY' not in str(safe)


def test_observation_sanitizer_cannot_recurse_into_another_observation_ledger():
    observation = {'details': {}, 'provenance': {}}
    observation['observations'] = [observation]
    assert sanitize_evidence({'observations': [observation]}) == {
        'observations': [{'details': {}, 'provenance': {}}]}


def test_large_real_source_projection_does_not_reproduce_str_get():
    # This exact path failed at source_view:53 before the correction: redact's
    # global node budget changed provenance from a dict to '[ограничено]'.
    from grangerpet.desktop_bridge import source_view
    record = normalize_evidence(finding(details=large_details()), 'web_read', 'synthetic')
    assert isinstance(redact(record)['provenance'], dict)
    view = source_view(record)
    assert view['evidence_id'] == record['evidence_id']
    assert view['provenance']['tool'] == 'web_read'


@pytest.mark.parametrize('value,expected', [({}, dict), ([], list), ((1, 2), list)])
def test_node_budget_never_changes_container_type(value, expected):
    assert isinstance(redact(value, _budget=[0]), expected)


def test_depth_limit_preserves_object_and_array_schema():
    assert redact({'key': 'value'}, _depth=13) == {}
    assert redact([{'key': 'value'}], _depth=13) == []


@pytest.mark.parametrize('field,bad', [('details', 'private-source-content'),
                                     ('provenance', 'private-source-content'),
                                     ('sources', None)])
def test_adapter_boundary_rejects_wrong_field_types_with_metadata_only(field, bad):
    with pytest.raises(EvidenceContractError) as captured:
        normalize_evidence(finding(**{field: bad}), 'web_read', 'synthetic')
    assert captured.value.path == 'record.' + field
    assert 'private-source-content' not in str(captured.value)
    assert set(captured.value.diagnostic()) == {'code', 'path', 'actual_type'}


@pytest.mark.parametrize('bad', ['raw-error', None, [], {'error': 'private-source-content'}])
def test_saved_provenance_is_never_invented_to_make_damaged_row_valid(bad):
    record = normalize_evidence(finding(), 'web_read', 'synthetic')
    record['provenance'] = bad
    with pytest.raises(EvidenceContractError):
        validate_saved_evidence(record)


def test_restore_keeps_valid_neighbor_and_reports_damaged_rows_idempotently(caplog):
    good = normalize_evidence(finding(), 'web_read', 'synthetic', '2026-10-30T00:00:00Z')
    broken = deepcopy(good)
    broken['provenance'] = 'PRIVATE-ERROR-CONTENT'
    original = deepcopy([broken, good])
    store = InvestigationEvidence()
    diagnostics = store.restore(original, ['PRIVATE-ERROR-CONTENT', {'tool': 'web_read', 'status': 'empty'}])
    assert store.records() == [good]
    assert store.executions() == [{'tool': 'web_read', 'status': 'empty'}]
    assert store.restore(original, store.executions()) == diagnostics
    assert store.records() == [good]
    assert original == [broken, good]
    assert 'PRIVATE-ERROR-CONTENT' not in str(diagnostics) + caplog.text
    assert len(diagnostics) == 2


def test_valid_saved_contradictory_observations_keep_timestamp_and_semantics():
    store = EvidenceStore()
    for status in ('verified', 'check'):
        store.add({'tool': 'web_read', 'query': 'synthetic', 'status': 'complete',
                   'results': [finding(status=status)]})
    saved = store.records()[0]
    restored = InvestigationEvidence()
    assert restored.restore([saved], []) == []
    assert restored.records() == [saved]


@pytest.mark.parametrize('bad', ['html-error', None, {}, 123])
def test_invalid_result_collection_does_not_become_execution_or_fact(bad):
    store = EvidenceStore()
    assert store.add({'tool': 'web_read', 'results': bad}) == []
    assert store.records() == []
    assert store.executions() == []
    assert store.diagnostics()[0]['path'] == 'envelope.results'


def test_bad_result_rows_are_isolated_without_erasing_good_facts():
    store = EvidenceStore()
    ids = store.add({'tool': 'web_read', 'query': 'synthetic',
                     'results': ['raw server error', finding()]})
    assert len(ids) == len(store.records()) == 1
    assert store.diagnostics()[0]['path'] == 'envelope.results[]'
