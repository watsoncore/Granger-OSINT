"""Atomic local evidence journals; never save transport messages or credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile

from .agent_evidence import redact
from .config import data_directory


class InvestigationJournal:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else data_directory() / 'investigations'

    def save(self, snapshot, *, secrets=()):
        if not isinstance(snapshot, dict) or not snapshot.get('evidence') and not snapshot.get('executions'):
            return None
        identifier = str(snapshot.get('id', ''))
        if not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise ValueError('Invalid investigation identifier')
        # No raw conversation, options, model reasoning, headers or runtime paths.
        safe = redact({key: snapshot[key] for key in
            ('id', 'started_at', 'finished_at', 'status', 'stop_reason', 'steps', 'tool_calls',
             'accounted_tokens', 'api_error', 'evidence', 'executions') if key in snapshot}, secrets)
        # Redact records individually so a general-purpose nested-list budget
        # cannot silently drop the tail of the bounded evidence ledger.
        safe['evidence'] = [redact(record, secrets) for record in snapshot.get('evidence', [])[:500]
                            if isinstance(record, dict)]
        encoded = json.dumps(safe, ensure_ascii=False, indent=2).encode('utf-8')
        if len(encoded) > 4_000_000:
            raise ValueError('Investigation journal limit exceeded')
        self.directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='journal-', dir=self.directory)
        target = self.directory / (identifier + '.json')
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return target

    def load(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{32}', str(identifier)):
            raise ValueError('Invalid investigation identifier')
        path = self.directory / (identifier + '.json')
        if path.stat().st_size > 4_000_000:
            raise ValueError('Investigation journal limit exceeded')
        return json.loads(path.read_text(encoding='utf-8'))
