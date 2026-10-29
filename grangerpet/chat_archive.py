"""Encrypted conversation continuity with portable-vault and legacy readers."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import tempfile
import shutil

from .credentials import CredentialsStore, CredentialError, protected_path

# Storage safety is a byte policy, not an invisible message-retention policy.
# Exceeding it raises on save and leaves the previous ciphertext intact.
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


class ChatArchive:
    def __init__(self, path):
        self._path = Path(path)
        self.last_error = None
        self._format_version = None

    @property
    def path(self):
        return protected_path(self._path)

    def load(self):
        try:
            if self.path.stat().st_size > MAX_ARCHIVE_BYTES + 65536:
                raise ValueError('Conversation archive exceeds the 64 MiB storage policy; no history was deleted.')
            raw = CredentialsStore._protect(self.path.read_bytes(), decrypt=True)
            value = json.loads(raw.decode('utf-8'))
            if not isinstance(value, dict):
                return {}
            self._format_version = value.get('version',1)
            result = {}
            for key in ('messages', 'context'):
                result[key] = []
                rows = value.get(key, [])
                if not isinstance(rows, list):
                    raise ValueError('Invalid conversation archive')
                for row in rows:
                    if not isinstance(row, dict) or row.get('role') not in ('user', 'model', 'status') or not isinstance(row.get('text'), str):
                        continue
                    item = {'role': row['role'], 'text': row['text']}
                    if key == 'messages' and isinstance(row.get('id'), str) and len(row['id']) <= 64:
                        item['id'] = row['id']
                    if key == 'messages':
                        if isinstance(row.get('attachments'),list):
                            item['attachments']=[{k:v for k,v in image.items() if k in ('id','name','mime','format','bytes','width','height','sha256')}
                                for image in row['attachments'][:4] if isinstance(image,dict) and re.fullmatch(r'img_[a-f0-9]{64}',str(image.get('id','')))]
                        if isinstance(row.get('investigation_id'), str) and re.fullmatch(r'[a-f0-9]{16,64}', row['investigation_id']):
                            item['investigation_id'] = row['investigation_id']
                        if isinstance(row.get('evidence_ids'), list):
                            item['evidence_ids'] = [value for value in row['evidence_ids'] if isinstance(value,str) and re.fullmatch(r'ev_[a-f0-9]{20}',value)]
                    result[key].append(item)
            self.last_error = None
            return result
        except (OSError, ValueError, UnicodeError, CredentialError, TypeError):
            self.last_error = 'archive_unavailable' if self.path.exists() else None
            return {}

    def save(self, messages, context, *, secrets=()):
        value = {'version': 2, 'messages': list(messages), 'context': list(context),
                 'storage_policy': {'max_bytes': MAX_ARCHIVE_BYTES, 'message_count_limit': None}}
        raw = json.dumps(value, ensure_ascii=False)
        for secret in secrets:
            if isinstance(secret, str) and secret:
                raw = raw.replace(secret, '[скрытый ключ]')
        encoded = raw.encode('utf-8')
        if len(encoded) > MAX_ARCHIVE_BYTES:
            raise ValueError('Достигнут размер архива 64 МиБ. Прежняя история сохранена; сообщения не удалялись.')
        protected = CredentialsStore._protect(encoded)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file() and self._format_version != 2:
            try:
                previous = json.loads(CredentialsStore._protect(self.path.read_bytes(), decrypt=True).decode('utf-8'))
                legacy = not isinstance(previous, dict) or previous.get('version') != 2
            except (ValueError, UnicodeError, CredentialError):
                raise CredentialError('Не удалось прочитать прежний архив. Он сохранён без изменений; автоматическая перезапись запрещена.') from None
            backup = self.path.with_name(self.path.name + '.v1-backup')
            if legacy and not backup.exists():
                # Preserve original ciphertext before any format migration.
                with self.path.open('rb') as source, backup.open('xb') as target:
                    shutil.copyfileobj(source, target)
                    target.flush(); os.fsync(target.fileno())
        descriptor, temporary = tempfile.mkstemp(prefix='chat-', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(protected)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self._format_version = 2
        finally:
            Path(temporary).unlink(missing_ok=True)
