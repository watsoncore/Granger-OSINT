"""Named encrypted conversations, retaining the legacy current-archive location.

The index contains only an opaque identifier. Titles are derived in memory from
Encrypted content; they are never written into an unencrypted index.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from .chat_archive import ChatArchive


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='conversation-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class ConversationLibrary:
    def __init__(self, current_archive):
        self.archive = current_archive
        self._metadata_cache = {}
        try:
            value = json.loads(self.pointer.read_text(encoding='utf-8'))['id']
        except (OSError, ValueError, KeyError, TypeError):
            value = ''
        self.current_id = value if self.valid_id(value) else uuid.uuid4().hex
        self._write_pointer()

    @property
    def directory(self):
        return self.archive.path.parent / 'conversations'

    @property
    def pointer(self):
        return self.directory / 'current.json'

    @staticmethod
    def valid_id(value):
        return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value) is not None

    def _write_pointer(self):
        _atomic(self.pointer, json.dumps({'id': self.current_id}).encode('ascii'))

    def seal(self):
        # Copy ciphertext as-is: no new encryption key, entropy or vault name.
        if self.archive.path.is_file():
            _atomic(self.directory / (self.current_id + '.dpapi'), self.archive.path.read_bytes())

    def new(self):
        self.seal()
        self.current_id = uuid.uuid4().hex
        self._write_pointer()
        return self.current_id

    def load(self, identifier):
        if not self.valid_id(identifier):
            raise ValueError('Некорректный идентификатор диалога.')
        if identifier == self.current_id:
            return self.archive.load()
        source = self.directory / (identifier + '.dpapi')
        if not source.is_file():
            raise ValueError('Сохранённый диалог не найден.')
        source_archive = ChatArchive(source)
        value = source_archive.load()
        if not value:
            raise ValueError('Не удалось расшифровать этот диалог. Проверьте состояние защищённого хранилища.')
        if source_archive._format_version != 2:
            backup=source.with_name(source.name+'.v1-backup')
            if not backup.exists():_atomic(backup,source.read_bytes())
        self.seal()
        _atomic(self.archive.path, source.read_bytes())
        self.archive._format_version = source_archive._format_version
        self.current_id = identifier
        self._write_pointer()
        return value

    def list(self, limit=60):
        paths = list(self.directory.glob('*.dpapi'))
        if self.archive.path.is_file():
            paths = [p for p in paths if p.stem != self.current_id] + [self.archive.path]
        result = []
        for path in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[:max(1, min(200, limit))]:
            stat = path.stat()
            fingerprint = (stat.st_mtime_ns,stat.st_size)
            cached = self._metadata_cache.get(path)
            if cached and cached[0]==fingerprint:
                title,count=cached[1:]
            else:
                value = ChatArchive(path).load()
                rows = value.get('messages', [])
                if not rows:
                    continue
                title = next((row['text'].strip().replace('\n', ' ')[:85] for row in rows if row['role']=='user'), 'Разговор с Гермионой')
                count=len(rows)
                # Titles remain in process memory, never in the plaintext index.
                self._metadata_cache[path]=(fingerprint,title,count)
            identifier = self.current_id if path == self.archive.path else path.stem
            result.append({'id': identifier, 'title': title,
                'updated_at': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                'message_count': count, 'current': identifier == self.current_id})
        return result
