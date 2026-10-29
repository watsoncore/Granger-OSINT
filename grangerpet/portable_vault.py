"""Versioned, password-unlocked portable storage using cryptography primitives.

Only ciphertext reaches disk. The password-derived key wraps a random data key;
changing a password therefore does not rewrite every historical artifact.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


class VaultError(RuntimeError):
    """Safe local error; never includes a password, key, or decrypted value."""


VAULT_MAGIC = b"GRANGERVAULT1\n"
ARTIFACT_MAGIC = b"GRANGERDATA1\n"
KDF = {"name": "argon2id", "memory_kib": 65536, "iterations": 3, "lanes": 4}
MAX_CONTAINER = 8 * 1024 * 1024
MAX_ARTIFACT = 96 * 1024 * 1024
_ARTIFACT_AAD = b"Granger-OSINT portable artifact v1"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64(value):
    return base64.b64encode(value).decode("ascii")


def _unb64(value, *, length=None):
    if not isinstance(value, str):
        raise ValueError("Invalid encoded field")
    result = base64.b64decode(value, validate=True)
    if length is not None and len(result) != length:
        raise ValueError("Invalid field length")
    return result


def atomic_write(path, data):
    """Replace only after a flushed complete ciphertext is available."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".granger-cipher-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _file_lock(path):
    """Filesystem lock shared by Granger launcher/pet, without a Windows service."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        locked = False
        for _ in range(50):
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except (OSError, BlockingIOError):
                time.sleep(.02)
        if not locked:
            raise VaultError("Хранилище занято другим окном Granger-OSINT. Повторите действие.")
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _password(value):
    if not isinstance(value, str) or len(value) < 12 or len(value.encode("utf-8")) > 4096:
        raise VaultError("Используйте парольную фразу от 12 символов (не более 4096 байт UTF-8).")
    return value.encode("utf-8")


class PortableVault:
    def __init__(self, path):
        self.path = Path(path)
        self._key = None
        self._data_key = None
        self._header = None
        self._payload = None
        self._fingerprint = None
        self._lock = threading.RLock()

    @property
    def exists(self):
        return self.path.is_file()

    @property
    def unlocked(self):
        return self._key is not None

    def status(self):
        result = {"enabled": self.exists, "unlocked": self.unlocked,
                  "migration_complete": False, "legacy_backup_retained": True}
        if self.unlocked:
            migration = self._payload.get("migration", {})
            result.update(migration_complete=bool(migration.get("complete")),
                          migrated_secrets=int(migration.get("secret_count", 0)),
                          migrated_artifacts=int(migration.get("artifact_count", 0)))
        return result

    @staticmethod
    def _derive(password, header):
        if header.get("version") != 1 or header.get("cipher") != "aes-256-gcm" or header.get("kdf") != KDF:
            raise VaultError("Неподдерживаемый формат или параметры защищённого хранилища.")
        return Argon2id(salt=_unb64(header["salt"], length=16), length=32,
                        iterations=KDF["iterations"], lanes=KDF["lanes"],
                        memory_cost=KDF["memory_kib"]).derive(_password(password))

    @staticmethod
    def _decode(encoded, key=None, password=None):
        try:
            if len(encoded) > MAX_CONTAINER or not encoded.startswith(VAULT_MAGIC):
                raise ValueError("Invalid vault")
            envelope = json.loads(encoded[len(VAULT_MAGIC):].decode("utf-8"))
            header = envelope["header"]
            if key is None:
                key = PortableVault._derive(password, header)
            payload = json.loads(AESGCM(key).decrypt(_unb64(envelope["nonce"], length=12),
                               _unb64(envelope["ciphertext"]), _json(header)).decode("utf-8"))
            if (not isinstance(payload, dict) or payload.get("version") != 1
                    or not isinstance(payload.get("secrets"), dict)):
                raise ValueError("Invalid payload")
            data_key = _unb64(payload["data_key"], length=32)
            if any(not isinstance(k, str) or not isinstance(v, str) for k, v in payload["secrets"].items()):
                raise ValueError("Invalid secrets")
            return header, payload, key, data_key
        except VaultError:
            raise
        except (InvalidTag, ValueError, TypeError, KeyError, UnicodeError):
            raise VaultError("Неверная парольная фраза или повреждённое хранилище. Исходные данные сохранены.") from None

    @staticmethod
    def _encode(header, payload, key):
        nonce = os.urandom(12)
        encoded = VAULT_MAGIC + _json({"header": header, "nonce": _b64(nonce),
                   "ciphertext": _b64(AESGCM(key).encrypt(nonce, _json(payload), _json(header)))})
        if len(encoded) > MAX_CONTAINER:
            raise VaultError("Превышен размер защищённого хранилища; прежняя версия сохранена.")
        return encoded

    def _read(self):
        try:
            if self.path.stat().st_size > MAX_CONTAINER:
                raise VaultError("Защищённое хранилище превышает допустимый размер.")
            return self.path.read_bytes()
        except OSError:
            raise VaultError("Не удалось прочитать защищённое хранилище.") from None

    def create(self, password, *, secrets=None, migration=None, data_key=None):
        with self._lock, _file_lock(self.path.with_suffix(".lock")):
            if self.exists:
                raise VaultError("Хранилище уже существует. Разблокируйте его; перезапись запрещена.")
            header = {"version": 1, "cipher": "aes-256-gcm", "kdf": dict(KDF), "salt": _b64(os.urandom(16))}
            key = self._derive(password, header)
            payload = {"version": 1, "data_key": _b64(data_key or os.urandom(32)),
                       "secrets": dict(secrets or {}), "migration": dict(migration or {})}
            encoded = self._encode(header, payload, key)
            self._decode(encoded, password=password)  # Verify before publishing.
            atomic_write(self.path, encoded)
            self._header, self._payload, self._key = header, payload, key
            self._data_key = _unb64(payload["data_key"], length=32)
            self._fingerprint = hashlib.sha256(encoded).digest()
        return self.status()

    def unlock(self, password):
        with self._lock:
            encoded = self._read()
            header, payload, key, data_key = self._decode(encoded, password=password)
            self._header, self._payload, self._key, self._data_key = header, payload, key, data_key
            self._fingerprint = hashlib.sha256(encoded).digest()
        return self.status()

    def lock(self):
        # Python/Qt cannot promise zeroization of copies already displayed in UI.
        with self._lock:
            self._key = self._data_key = self._header = self._payload = self._fingerprint = None
        return self.status()

    def _require(self):
        if not self.unlocked:
            raise VaultError("Защищённое хранилище заблокировано. Введите парольную фразу в настройках.")

    def _refresh(self):
        self._require()
        encoded = self._read()
        fingerprint = hashlib.sha256(encoded).digest()
        if fingerprint != self._fingerprint:
            header, payload, key, data_key = self._decode(encoded, key=self._key)
            self._header, self._payload, self._key, self._data_key = header, payload, key, data_key
            self._fingerprint = fingerprint

    def get(self, name):
        with self._lock:
            self._refresh()
            return self._payload["secrets"].get(name, "")

    def set(self, name, value):
        with self._lock, _file_lock(self.path.with_suffix(".lock")):
            self._refresh()
            payload = dict(self._payload)
            payload["secrets"] = dict(payload["secrets"])
            if value:
                payload["secrets"][name] = value
            else:
                payload["secrets"].pop(name, None)
            encoded = self._encode(self._header, payload, self._key)
            self._decode(encoded, key=self._key)
            atomic_write(self.path, encoded)
            self._payload = payload
            self._fingerprint = hashlib.sha256(encoded).digest()

    def change_password(self, old, new):
        with self._lock, _file_lock(self.path.with_suffix(".lock")):
            encoded = self._read()
            _, payload, _, data_key = self._decode(encoded, password=old)
            header = {"version": 1, "cipher": "aes-256-gcm", "kdf": dict(KDF), "salt": _b64(os.urandom(16))}
            key = self._derive(new, header)
            replacement = self._encode(header, payload, key)
            self._decode(replacement, password=new)
            atomic_write(self.path, replacement)
            self._header, self._payload, self._key, self._data_key = header, payload, key, data_key
            self._fingerprint = hashlib.sha256(replacement).digest()
        return self.status()

    @staticmethod
    def seal_with_key(data, key):
        if not isinstance(data, bytes) or len(data) > MAX_ARTIFACT:
            raise VaultError("Недопустимый размер защищаемого файла.")
        nonce = os.urandom(12)
        return ARTIFACT_MAGIC + nonce + AESGCM(key).encrypt(nonce, data, _ARTIFACT_AAD)

    @staticmethod
    def open_with_key(data, key):
        if (not isinstance(data, bytes) or len(data) > MAX_ARTIFACT + 64
                or not data.startswith(ARTIFACT_MAGIC) or len(data) < len(ARTIFACT_MAGIC) + 28):
            raise VaultError("Неподдерживаемый защищённый файл.")
        offset = len(ARTIFACT_MAGIC)
        try:
            return AESGCM(key).decrypt(data[offset:offset+12], data[offset+12:], _ARTIFACT_AAD)
        except InvalidTag:
            raise VaultError("Защищённый файл повреждён или принадлежит другому хранилищу.") from None

    def seal(self, data):
        with self._lock:
            self._require()
            return self.seal_with_key(data, self._data_key)

    def open(self, data):
        with self._lock:
            self._require()
            return self.open_with_key(data, self._data_key)
