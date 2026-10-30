"""Atomic evidence journals and encrypted resumable checkpoints.

Legacy .json evidence reports retain their format. Portable mode additionally
encrypts these reports; the .checkpoint.dpapi filename remains compatible while
its ciphertext uses the portable format after explicit vault migration.
"""
from __future__ import annotations

from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import threading

from .agent_evidence import redact, sanitize_evidence, validate_saved_evidence
from .config import data_directory
from .credentials import CredentialsStore, CredentialError, protected_path, portable_enabled
from .investigation_contracts import (InvestigationContractError,
                                      recover_public_snapshot, validate_checkpoint,
                                      validate_public_evidence)


CHECKPOINT_LIMIT = 32_000_000


class InvestigationJournal:
    def __init__(self, directory=None):
        self._directory = Path(directory) if directory is not None else data_directory() / 'investigations'
        self._lock = threading.RLock()
        self._revisions = {}
        self._reported_contracts = set()

    def _report_contracts(self, identifier, warnings):
        """Log a field/type once per journal instance, never the saved value."""
        for warning in warnings:
            fingerprint = (identifier, warning.get('path'), warning.get('actual_type'))
            if fingerprint not in self._reported_contracts:
                self._reported_contracts.add(fingerprint)
                logging.getLogger(__name__).warning(
                    'Investigation data quarantined id=%s path=%s expected=%s actual_type=%s',
                    identifier, warning.get('path'), warning.get('expected'), warning.get('actual_type'))

    def _recover_checkpoint_evidence(self, identifier, original, safe):
        """Repair only exact existing evidence IDs from an intact private copy.

        This never imports a checkpoint's messages, pending work or additional
        findings, and neither original file is rewritten during recovery.
        """
        if not safe.get('quarantined_records') or not isinstance(original.get('evidence'), list):
            return safe
        checkpoint_path = self.directory / (identifier + '.checkpoint.dpapi')
        if not checkpoint_path.is_file():
            return safe
        try:
            checkpoint = self.load_checkpoint(identifier)
        except (OSError, ValueError, UnicodeError, CredentialError):
            return safe  # Valid public rows remain usable; the private file is retained.
        matches = {row['evidence_id']: row for row in checkpoint.get('evidence', [])
                   if isinstance(row, dict) and isinstance(row.get('evidence_id'), str)}
        recovered, rows = 0, []
        for index, row in enumerate(original['evidence']):
            try:
                validate_public_evidence(row, f'investigation.evidence[{index}]')
            except InvestigationContractError:
                pass
            else:
                rows.append(deepcopy(row))
                continue
            evidence_id = row.get('evidence_id') if isinstance(row, dict) else None
            candidate = matches.get(evidence_id) if isinstance(evidence_id, str) else None
            if candidate is not None:
                try:
                    replacement = validate_saved_evidence(candidate)
                except ValueError:
                    continue
                rows.append(replacement)
                recovered += 1
        if recovered:
            safe['evidence'] = rows
            safe['recovered_records'] = recovered
            safe['quarantined_records'] -= recovered
            safe['checkpoint_recovery'] = 'validated_matching_evidence_ids'
        return safe

    @property
    def directory(self):
        return protected_path(self._directory)

    @staticmethod
    def _identifier(identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise ValueError('Invalid investigation identifier')
        return identifier

    def _write(self, target, encoded):
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='journal-', dir=self.directory)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return target

    def save_checkpoint(self, checkpoint, *, secrets=()):
        if not isinstance(checkpoint, dict) or checkpoint.get('version') != 1:
            raise ValueError('Unsupported investigation checkpoint')
        identifier = self._identifier(checkpoint.get('id'))
        # This is an explicit private-state contract, not an arbitrary object
        # dump: runtime options, headers and credentials have no field here.
        allowed = ('version', 'id', 'record', 'messages', 'context_memory', 'pending_calls',
                   'pending_outcomes', 'call_cache', 'seen_call_ids', 'evidence', 'executions',
                   'failures', 'completed_steps', 'tried_queries', 'pending_work', 'plan',
                   'registry_state', 'usage_requests', 'budget_reserved_tokens', 'protocol_archive', 'sent_content',
                   'active_focus','followup_request','focus_budget', 'report_parts', 'report_draft', 'synthesis_reserved_tokens')
        value = {key: checkpoint[key] for key in allowed if key in checkpoint}
        validate_checkpoint(value, identifier)
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        for secret in secrets:
            if isinstance(secret, str) and secret:
                raw = raw.replace(json.dumps(secret, ensure_ascii=False)[1:-1], '[скрытый ключ]')
        encoded = raw.encode('utf-8')
        if len(encoded) > CHECKPOINT_LIMIT:
            raise ValueError('Investigation checkpoint storage limit exceeded')
        protected = CredentialsStore._protect(encoded)
        target = self.directory / (identifier + '.checkpoint.dpapi')
        revision = value.get('record', {}).get('checkpoint_revision', 0)
        if type(revision) is not int or revision < 0:
            raise ValueError('Invalid checkpoint revision')
        with self._lock:
            if identifier not in self._revisions and target.exists():
                self.load_checkpoint(identifier)
            if revision < self._revisions.get(identifier, 0):
                return target  # A slow observer cannot overwrite a newer stage.
            self._write(target, protected)
            self._revisions[identifier] = revision
        return target

    def load_checkpoint(self, identifier):
        identifier = self._identifier(identifier)
        path = self.directory / (identifier + '.checkpoint.dpapi')
        if path.stat().st_size > CHECKPOINT_LIMIT + 65536:
            raise ValueError('Investigation checkpoint storage limit exceeded')
        decoded = CredentialsStore._protect(path.read_bytes(), decrypt=True)
        if len(decoded) > CHECKPOINT_LIMIT:
            raise ValueError('Investigation checkpoint storage limit exceeded')
        try:
            value = json.loads(decoded.decode('utf-8'))
        except RecursionError:
            raise InvestigationContractError('checkpoint', 'bounded JSON nesting', decoded) from None
        try:
            validate_checkpoint(value, identifier)
        except InvestigationContractError as error:
            self._report_contracts(identifier, [error.diagnostic()])
            raise
        revision = value['record'].get('checkpoint_revision', 0)
        if type(revision) is int:
            with self._lock:
                self._revisions[identifier] = max(revision, self._revisions.get(identifier, 0))
        return value

    def list_resumable(self, limit=30):
        if not self.directory.exists():
            return []
        result = []
        paths = sorted(self.directory.glob('*.checkpoint.dpapi'), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths:
            try:
                value = self.load_checkpoint(path.name.split('.')[0])
                record = value['record']
                if record.get('status') == 'completed' or record.get('resumable') is False:
                    continue
                result.append({key: record.get(key) for key in ('id', 'goal', 'conversation_id', 'status',
                    'stop_reason', 'steps', 'tool_calls', 'started_at', 'updated_at', 'finished_at')})
            except (OSError, ValueError, UnicodeError, CredentialError):
                continue
            if len(result) >= max(1, min(100, int(limit))):
                break
        return result

    def save(self, snapshot, *, secrets=()):
        if not isinstance(snapshot, dict):
            raise InvestigationContractError('investigation', 'dict', snapshot)
        if not snapshot.get('evidence') and not snapshot.get('executions'):
            return None
        identifier = str(snapshot.get('id', ''))
        self._identifier(identifier)
        # No raw conversation, options, model reasoning, headers or runtime paths.
        safe = redact({key: snapshot[key] for key in
            ('id', 'started_at', 'finished_at', 'status', 'stop_reason', 'steps', 'tool_calls',
             'accounted_tokens', 'api_error', 'usage', 'resumable',
             'elapsed_seconds', 'context_compactions', 'budget_reserved_tokens') if key in snapshot}, secrets)
        # Validate before redaction; malformed legacy values are quarantined
        # explicitly. Give each fact separate identity/details/origin budgets.
        for key in ('evidence', 'executions'):
            safe[key] = snapshot.get(key, [])
        safe = recover_public_snapshot(safe, identifier, stop_running=False)
        self._report_contracts(identifier, safe.get('validation_warnings', []))
        safe['evidence'] = [sanitize_evidence(row, secrets) for row in safe['evidence']]
        safe['executions'] = [redact(row, secrets) for row in safe['executions']]
        encoded = json.dumps(safe, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
        if len(encoded) > CHECKPOINT_LIMIT:
            raise ValueError('Investigation journal limit exceeded')
        target = self.directory / (identifier + '.json')
        if portable_enabled():
            encoded = CredentialsStore._protect(encoded)
        return self._write(target, encoded)

    def load(self, identifier):
        self._identifier(identifier)
        path = self.directory / (identifier + '.json')
        if path.stat().st_size > CHECKPOINT_LIMIT:
            raise ValueError('Investigation journal limit exceeded')
        encoded = path.read_bytes()
        if portable_enabled():
            encoded = CredentialsStore._protect(encoded, decrypt=True)
        try:
            value = json.loads(encoded.decode('utf-8'))
        except RecursionError:
            raise InvestigationContractError('investigation', 'bounded JSON nesting', encoded) from None
        safe = recover_public_snapshot(value, identifier)
        self._report_contracts(identifier, safe.get('validation_warnings', []))
        return self._recover_checkpoint_evidence(identifier, value, safe)
