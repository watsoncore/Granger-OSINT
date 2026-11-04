"""Strict adapter/runner boundary, compatible with the existing results API."""
from __future__ import annotations
import logging
from .agent_evidence import redact, sanitize_evidence, safe_maigret_diagnostics, MAIGRET_DATABASE_ROW_LIMIT
from .engine.models import Result

STATUSES = frozenset(('complete', 'completed', 'partial', 'empty', 'error', 'timeout', 'cancelled',
    'unavailable', 'auth_required', 'blocked', 'limit_reached', 'rate_limited', 'invalid_arguments',
    'approval_required', 'approval_denied', 'unknown_tool', 'duplicate_skipped', 'interrupted', 'disabled',
    'configuration_error', 'missing_runtime', 'missing_dependency', 'not_installed', 'unverified'))


class ToolContractError(ValueError):
    code = 'invalid_tool_output'
    def __init__(self, path, expected, value):
        self.path, self.expected, self.actual_type = path, expected, type(value).__name__
        super().__init__(f'{self.code}: {path}; expected {expected}, received {self.actual_type}')
    def diagnostic(self):
        return {'code': self.code, 'path': self.path, 'expected': self.expected, 'actual_type': self.actual_type}


def validate_outcome(value):
    if not isinstance(value, dict):
        raise ToolContractError('outcome', 'object', value)
    status = value.get('status')
    if not isinstance(status, str) or status not in STATUSES:
        raise ToolContractError('outcome.status', 'execution status', status)
    if 'results' not in value and status in ('complete', 'completed', 'partial', 'empty'):
        raise ToolContractError('outcome.results', 'list', None)
    if 'results' in value and not isinstance(value['results'], list):
        raise ToolContractError('outcome.results', 'list', value['results'])
    if 'limitations' in value:
        notes = value['limitations']
        if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
            raise ToolContractError('outcome.limitations', 'list of strings', notes)
    return value


def sanitize_outcome(value, secrets=()):
    """No payload can consume the envelope's status/origin/record budgets."""
    validate_outcome(value)
    maigret=value.get('tool')=='username_maigret'
    if maigret and len(value.get('results',[]))>MAIGRET_DATABASE_ROW_LIMIT:
        raise ToolContractError('outcome.results','at most 10000 original database rows',value['results'])
    safe = redact({key: item for key, item in value.items() if key != 'results' and
                   not (maigret and key in ('source_diagnostics','data','evidence_ids'))}, secrets)
    safe['results'] = []
    for index, row in enumerate(value.get('results', [])):
        try:
            candidate = sanitize_evidence(row, secrets)
            Result.from_dict(candidate)
        except (ValueError, TypeError):
            raise ToolContractError(f'outcome.results[{index}]', 'finding object', row) from None
        safe['results'].append(candidate)
    if maigret:
        from copy import deepcopy
        if 'source_diagnostics' in value:
            safe['source_diagnostics']=safe_maigret_diagnostics(value['source_diagnostics'],secrets)
        if 'data' in value:
            if not isinstance(value['data'],dict):raise ToolContractError('outcome.data','object',value['data'])
            safe['data']=redact({k:v for k,v in value['data'].items() if k!='results'},secrets)
            safe['data']['results']=deepcopy(safe['results'])
        if 'evidence_ids' in value:
            safe['evidence_ids']=[row['evidence_id'] for row in safe['results'] if row.get('evidence_id')]
    return safe


def log_contract(error, tool):
    logging.getLogger(__name__).warning('Tool output rejected tool=%s code=%s path=%s expected=%s actual_type=%s',
        tool, error.code, error.path, error.expected, error.actual_type)


def execution_status(status):
    if status in ('complete', 'completed'):
        return 'success'
    if status in ('empty', 'partial', 'timeout', 'cancelled'):
        return status
    if status in ('blocked', 'auth_required', 'approval_required', 'approval_denied'):
        return 'blocked'
    if status in ('unavailable', 'disabled', 'configuration_error', 'missing_runtime', 'missing_dependency', 'not_installed'):
        return 'unavailable'
    return 'failed'
