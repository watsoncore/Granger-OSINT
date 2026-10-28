"""Local conversation continuity protected by the signed-in Windows user's DPAPI."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import tempfile

from .credentials import CredentialsStore, CredentialError


class ChatArchive:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            if self.path.stat().st_size > 2_000_000:
                return {}
            raw = CredentialsStore._protect(self.path.read_bytes(), decrypt=True)
            value = json.loads(raw.decode('utf-8'))
            if not isinstance(value, dict):
                return {}
            result = {}
            for key, maximum in (('messages', 300), ('context', 24)):
                result[key] = []
                for row in value.get(key, [])[-maximum:]:
                    if not isinstance(row, dict) or row.get('role') not in ('user', 'model', 'status') or not isinstance(row.get('text'), str):
                        continue
                    item = {'role': row['role'], 'text': row['text'][:120000]}
                    if key == 'messages' and isinstance(row.get('id'), str) and len(row['id']) <= 64:
                        item['id'] = row['id']
                    if key == 'messages':
                        if isinstance(row.get('investigation_id'), str) and re.fullmatch(r'[a-f0-9]{16,64}', row['investigation_id']):
                            item['investigation_id'] = row['investigation_id']
                        if isinstance(row.get('evidence_ids'), list):
                            item['evidence_ids'] = [value for value in row['evidence_ids'][:200] if isinstance(value,str) and re.fullmatch(r'ev_[a-f0-9]{20}',value)]
                    result[key].append(item)
            return result
        except (OSError, ValueError, UnicodeError, CredentialError, TypeError):
            return {}

    def save(self, messages, context, *, secrets=()):
        value = {'messages': messages[-300:], 'context': context[-24:]}
        raw = json.dumps(value, ensure_ascii=False)
        for secret in secrets:
            if isinstance(secret, str) and secret:
                raw = raw.replace(secret, '[скрытый ключ]')
        encoded = raw.encode('utf-8')
        if len(encoded) > 1_500_000:
            # Retain recent complete messages rather than writing a truncated JSON.
            value['messages'] = messages[-60:]
            encoded = json.dumps(value, ensure_ascii=False).encode('utf-8')
            for secret in secrets:
                if isinstance(secret, str) and secret:
                    encoded = encoded.replace(secret.encode('utf-8'), '[скрытый ключ]'.encode('utf-8'))
        if len(encoded) > 1_500_000:
            raise ValueError('Conversation archive limit exceeded')
        protected = CredentialsStore._protect(encoded)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='chat-', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(protected)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
