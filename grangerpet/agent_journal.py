"""Atomic public evidence journals and DPAPI-protected resumable checkpoints.

Legacy .json evidence reports retain their format. Conversation/protocol state
is written only to .checkpoint.dpapi, bound to the current Windows account.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import threading

from .agent_evidence import redact
from .config import data_directory
from .credentials import CredentialsStore, CredentialError


CHECKPOINT_LIMIT = 32_000_000


class InvestigationJournal:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else data_directory() / 'investigations'
        self._lock = threading.RLock()
        self._revisions = {}

    @staticmethod
    def _identifier(identifier):
        if not re.fullmatch(r'[a-f0-9]{32}', str(identifier)):
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
                   'registry_state', 'usage_requests', 'budget_reserved_tokens', 'protocol_archive', 'sent_content')
        value = {key: checkpoint[key] for key in allowed if key in checkpoint}
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        for secret in secrets:
            if isinstance(secret, str) and secret:
                raw = raw.replace(secret, '[скрытый ключ]')
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
        value = json.loads(decoded.decode('utf-8'))
        if (not isinstance(value, dict) or value.get('version') != 1 or value.get('id') != identifier
                or not isinstance(value.get('record'), dict) or value['record'].get('id') != identifier):
            raise ValueError('Invalid investigation checkpoint')
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
        if not isinstance(snapshot, dict) or not snapshot.get('evidence') and not snapshot.get('executions'):
            return None
        identifier = str(snapshot.get('id', ''))
        self._identifier(identifier)
        # No raw conversation, options, model reasoning, headers or runtime paths.
        safe = redact({key: snapshot[key] for key in
            ('id', 'started_at', 'finished_at', 'status', 'stop_reason', 'steps', 'tool_calls',
             'accounted_tokens', 'api_error', 'evidence', 'executions', 'usage', 'resumable',
             'elapsed_seconds', 'context_compactions', 'budget_reserved_tokens') if key in snapshot}, secrets)
        # Redact records individually so a general-purpose nested-list budget
        # cannot silently drop the tail of the bounded evidence ledger.
        safe['evidence'] = [redact(record, secrets) for record in snapshot.get('evidence', [])
                            if isinstance(record, dict)]
        safe['executions'] = [redact(record, secrets) for record in snapshot.get('executions', []) if isinstance(record, dict)]
        encoded = json.dumps(safe, ensure_ascii=False, indent=2).encode('utf-8')
        if len(encoded) > CHECKPOINT_LIMIT:
            raise ValueError('Investigation journal limit exceeded')
        target = self.directory / (identifier + '.json')
        return self._write(target, encoded)

    def load(self, identifier):
        self._identifier(identifier)
        path = self.directory / (identifier + '.json')
        if path.stat().st_size > CHECKPOINT_LIMIT:
            raise ValueError('Investigation journal limit exceeded')
        return json.loads(path.read_text(encoding='utf-8'))
