"""Validated persistence boundaries for v1 investigations.

Recovery is an in-memory view: a malformed public row is quarantined, while
private execution state is rejected rather than partially replayed. Diagnostics
contain field paths and types, never decrypted values or model arguments.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math


class InvestigationContractError(ValueError):
    code = 'invalid_investigation_data'

    def __init__(self, path, expected, value):
        self.path, self.expected, self.actual_type = path, expected, type(value).__name__
        super().__init__(f'{path}: expected {expected}, received {self.actual_type}')

    def diagnostic(self):
        return {'code': self.code, 'path': self.path, 'expected': self.expected,
                'actual_type': self.actual_type}


def _expect(value, expected, path):
    if not isinstance(value, expected):
        raise InvestigationContractError(path, expected.__name__, value)
    return value


def _fields(value, names, expected, path, *, nullable=False):
    for key in names:
        if key in value and not (nullable and value[key] is None):
            _expect(value[key], expected, path + '.' + key)


def _integer(value, path):
    if type(value) is not int or value < 0:
        raise InvestigationContractError(path, 'nonnegative integer', value)


def _string_list(value, path):
    for index, item in enumerate(_expect(value, list, path)):
        _expect(item, str, f'{path}[{index}]')


def _record(value, path):
    _expect(value, dict, path)
    _fields(value, ('id', 'goal', 'conversation_id', 'status', 'stop_reason',
                   'started_at', 'finished_at', 'updated_at', 'provider', 'model'), str, path, nullable=True)
    for key in ('steps', 'tool_calls', 'resume_count', 'context_compactions',
                'no_progress_rounds', 'checkpoint_revision', 'budget_reserved_tokens'):
        if key in value:
            _integer(value[key], path + '.' + key)
    if 'elapsed_seconds' in value:
        elapsed = value['elapsed_seconds']
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise InvestigationContractError(path + '.elapsed_seconds', 'finite nonnegative number', elapsed)
    _fields(value, ('limits', 'usage', 'api_error'), dict, path, nullable=True)
    if 'resumable' in value:
        _expect(value['resumable'], bool, path + '.resumable')
    if 'calls' in value:
        _argument_rows(value['calls'], path + '.calls')


def _evidence(value, path, *, require_provenance=True):
    _expect(value, dict, path)
    _fields(value, ('details', 'provenance', 'page_content', 'structured_record',
                    'geoint_result', 'graph'), dict, path)
    _fields(value, ('id', 'title', 'type', 'platform', 'url', 'description', 'date',
                   'status', 'evidence_id', 'resource_id', 'verification'), str, path)
    if 'sources' in value:
        _string_list(value['sources'], path + '.sources')
    if 'observations' in value:
        for index, observation in enumerate(_expect(value['observations'], list, path + '.observations')):
            _expect(observation, dict, f'{path}.observations[{index}]')
            _fields(observation, ('details', 'provenance'), dict, f'{path}.observations[{index}]')
    if 'provenance' in value:
        _fields(value['provenance'], ('tool', 'query', 'obtained_at', 'source_url', 'source_status',
                                      'basis', 'acquisition'), str, path + '.provenance', nullable=True)
    # Old public reports may contain skeletal observations. A row claiming an
    # evidence identity must satisfy the stronger provenance-bearing contract.
    if require_provenance and value.get('evidence_id'):
        from .agent_evidence import validate_saved_evidence
        try:
            validate_saved_evidence(value)
        except ValueError:
            raise InvestigationContractError(path, 'valid provenance-bearing evidence', value) from None


def _execution(value, path):
    _expect(value, dict, path)
    _fields(value, ('tool', 'status', 'query', 'obtained_at', 'error'), str, path, nullable=True)
    if 'limitations' in value:
        _string_list(value['limitations'], path + '.limitations')


def validate_public_evidence(value, path='evidence'):
    """Validate one public row without converting legacy observations to facts."""
    _evidence(value, path)
    return value


def _envelope(value, path, *, compact=False):
    _execution(value, path)
    if 'results' in value:
        for index, item in enumerate(_expect(value['results'], list, path + '.results')):
            _evidence(item, f'{path}.results[{index}]', require_provenance=not compact)
    _fields(value, ('context_selection', 'page_budget'), dict, path)
    if 'context_selection' in value:
        selection = value['context_selection']
        for key in ('offset', 'length'):
            if key in selection:
                _integer(selection[key], path + '.context_selection.' + key)
        _fields(selection, ('focus',), str, path + '.context_selection')


def _argument_rows(value, path):
    for index, item in enumerate(_expect(value, list, path)):
        row_path = f'{path}[{index}]'
        _expect(item, dict, row_path)
        _fields(item, ('tool', 'name', 'status', 'obtained_at'), str, row_path, nullable=True)
        _fields(item, ('arguments',), dict, row_path)


def _messages(value, path):
    for index, message in enumerate(_expect(value, list, path)):
        row_path = f'{path}[{index}]'
        _expect(message, dict, row_path)
        if message.get('role') not in ('system', 'user', 'assistant', 'tool'):
            raise InvestigationContractError(row_path + '.role', 'protocol role', message.get('role'))
        _fields(message, ('content',), str, row_path, nullable=True)
        if message['role'] == 'tool':
            _expect(message.get('tool_call_id'), str, row_path + '.tool_call_id')
            try:
                payload = json.loads(message.get('content', ''))
            except (ValueError, TypeError, RecursionError):
                raise InvestigationContractError(row_path + '.content', 'JSON tool object', message.get('content')) from None
            _envelope(payload, row_path + '.content', compact=True)
        if 'tool_calls' in message:
            for call_index, call in enumerate(_expect(message['tool_calls'], list, row_path + '.tool_calls')):
                call_path = f'{row_path}.tool_calls[{call_index}]'
                _expect(call, dict, call_path)
                _expect(call.get('id'), str, call_path + '.id')
                function = _expect(call.get('function'), dict, call_path + '.function')
                _expect(function.get('name'), str, call_path + '.function.name')
                try:
                    arguments = json.loads(function.get('arguments', ''))
                except (ValueError, TypeError, RecursionError):
                    raise InvestigationContractError(call_path + '.function.arguments', 'JSON object', function.get('arguments')) from None
                _expect(arguments, dict, call_path + '.function.arguments')


def validate_checkpoint(value, identifier=None):
    """Validate present v1 fields without mutating their encrypted source."""
    _expect(value, dict, 'checkpoint')
    if type(value.get('version')) is not int or value['version'] != 1:
        raise InvestigationContractError('checkpoint.version', 'version 1', value.get('version'))
    _expect(value.get('id'), str, 'checkpoint.id')
    if identifier is not None and value['id'] != identifier:
        raise InvestigationContractError('checkpoint.id', 'matching identifier', value['id'])
    record = value.get('record')
    _record(record, 'checkpoint.record')
    if record.get('id') != value['id']:
        raise InvestigationContractError('checkpoint.record.id', 'matching identifier', record.get('id'))
    for key in ('messages', 'protocol_archive'):
        if key in value:
            _messages(value[key], 'checkpoint.' + key)
    for key, checker in (('evidence', _evidence), ('executions', _execution)):
        if key in value:
            for index, row in enumerate(_expect(value[key], list, 'checkpoint.' + key)):
                checker(row, f'checkpoint.{key}[{index}]')
    if 'pending_calls' in value:
        for index, call in enumerate(_expect(value['pending_calls'], list, 'checkpoint.pending_calls')):
            path = f'checkpoint.pending_calls[{index}]'
            _expect(call, dict, path)
            for key in ('id', 'name', 'fingerprint'):
                _expect(call.get(key), str, path + '.' + key)
            _expect(call.get('arguments'), dict, path + '.arguments')
            _fields(call, ('dispatched',), bool, path)
    if 'pending_outcomes' in value:
        for index, outcome in enumerate(_expect(value['pending_outcomes'], dict, 'checkpoint.pending_outcomes').values()):
            _envelope(outcome, f'checkpoint.pending_outcomes[{index}]')
    if 'call_cache' in value:
        for index, cached in enumerate(_expect(value['call_cache'], dict, 'checkpoint.call_cache').values()):
            path = f'checkpoint.call_cache[{index}]'
            _expect(cached, dict, path)
            _envelope(cached.get('outcome'), path + '.outcome')
            if 'resume_count' in cached:
                _integer(cached['resume_count'], path + '.resume_count')
    for key in ('seen_call_ids',):
        if key in value:
            _string_list(value[key], 'checkpoint.' + key)
    for key in ('failures', 'tried_queries'):
        if key in value:
            _argument_rows(value[key], 'checkpoint.' + key)
    if 'completed_steps' in value:
        for index, step in enumerate(_expect(value['completed_steps'], list, 'checkpoint.completed_steps')):
            path = f'checkpoint.completed_steps[{index}]'
            _expect(step, dict, path)
            if 'step' in step:
                _integer(step['step'], path + '.step')
            if 'calls' in step:
                _argument_rows(step['calls'], path + '.calls')
    for key in ('context_memory', 'pending_work'):
        if key in value:
            for index, item in enumerate(_expect(value[key], list, 'checkpoint.' + key)):
                if not isinstance(item, dict) and not (key == 'pending_work' and isinstance(item, str)):
                    raise InvestigationContractError(f'checkpoint.{key}[{index}]', 'object or work item', item)
    _fields(value, ('plan',), str, 'checkpoint')
    for key in ('active_focus','followup_request'):
        if key in value:
            focus=_expect(value[key],dict,'checkpoint.'+key)
            if (set(focus)-{'text','context','intent'} or not isinstance(focus.get('text'),str)
                    or not 0<len(focus['text'])<=4000 or not isinstance(focus.get('context'),dict)
                    or focus.get('intent') not in ('explain','investigate','compare')
                    or len(json.dumps(focus,ensure_ascii=False))>20000):
                raise InvestigationContractError('checkpoint.'+key,'bounded graph followup',focus)
    for key in ('budget_reserved_tokens',):
        if key in value:
            _integer(value[key], 'checkpoint.' + key)
    if 'usage_requests' in value:
        for index, request in enumerate(_expect(value['usage_requests'], dict, 'checkpoint.usage_requests').values()):
            path = f'checkpoint.usage_requests[{index}]'
            _expect(request, dict, path)
            _fields(request, ('usage',), dict, path)
            for key in ('budget_reservation',):
                if key in request:
                    _integer(request[key], path + '.' + key)
    if 'sent_content' in value:
        _string_list(list(_expect(value['sent_content'], dict, 'checkpoint.sent_content').values()), 'checkpoint.sent_content')
    if 'registry_state' in value:
        registry = _expect(value['registry_state'], dict, 'checkpoint.registry_state')
        if 'page_count' in registry:
            _integer(registry['page_count'], 'checkpoint.registry_state.page_count')
        if 'downloaded_bytes' in registry:
            _integer(registry['downloaded_bytes'], 'checkpoint.registry_state.downloaded_bytes')
        if 'attachment_ids' in registry:
            _string_list(registry['attachment_ids'], 'checkpoint.registry_state.attachment_ids')
        if 'known' in registry:
            for index, origin in enumerate(_expect(registry['known'], list, 'checkpoint.registry_state.known')):
                path = f'checkpoint.registry_state.known[{index}]'
                _expect(origin, dict, path)
                _fields(origin, ('url', 'parent_url'), str, path)
                if 'depth' in origin:
                    _integer(origin['depth'], path + '.depth')
    return value


def recover_public_snapshot(value, identifier, *, stop_running=True):
    """Return usable rows plus explicit safe diagnostics; never edit disk."""
    _expect(value, dict, 'investigation')
    if value.get('id') != identifier:
        raise InvestigationContractError('investigation.id', 'matching identifier', value.get('id'))
    result = deepcopy(value)
    warnings = []
    # The former snapshot-wide redaction budget could damage late scalar
    # metadata too. Optional counters must not make intact evidence unreadable,
    # nor may an unknown counter be silently replaced by a fabricated zero.
    metadata = ('goal', 'conversation_id', 'status', 'stop_reason', 'started_at',
                'finished_at', 'updated_at', 'provider', 'model', 'steps', 'tool_calls',
                'resume_count', 'context_compactions', 'no_progress_rounds',
                'checkpoint_revision', 'budget_reserved_tokens', 'elapsed_seconds',
                'limits', 'usage', 'api_error', 'resumable', 'calls')
    for key in metadata:
        if key not in result:
            continue
        try:
            _record({'id': identifier, key: result[key]}, 'investigation')
        except InvestigationContractError as error:
            warnings.append(error.diagnostic())
            del result[key]
    metadata_issues = len(warnings)
    for key, checker in (('evidence', _evidence), ('executions', _execution)):
        rows = result.get(key, [])
        if not isinstance(rows, list):
            warnings.append(InvestigationContractError('investigation.' + key, 'list', rows).diagnostic())
            rows = []
        accepted = []
        for index, row in enumerate(rows):
            try:
                checker(row, f'investigation.{key}[{index}]')
            except InvestigationContractError as error:
                warnings.append(error.diagnostic())
            else:
                accepted.append(row)
        if key in result:
            result[key] = accepted
    if warnings:
        result['validation_warnings'] = warnings[:100]
        result['quarantined_records'] = len(warnings) - metadata_issues
        result['validation_issue_count'] = len(warnings)
    if stop_running and result.get('status') == 'running':
        result.update(status='interrupted', stop_reason='interrupted', resumable=True)
    return result
