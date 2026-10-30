"""Portable vault facade with an explicit read-only legacy migration path.

Existing Windows profiles continue working until their owner chooses a password.
Once the portable container exists, ordinary access never falls back to Windows.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import json
import shutil
import uuid
import re

from .portable_vault import (ARTIFACT_MAGIC, PortableVault, VaultError,
                             atomic_write)

NAMES = frozenset({"google_api_key", "gemini_api_key", "deepseek_api_key", "vk_token", "telegram_api_hash",
                   "telegram_session", "instagram_session", "virustotal_api_key",
                   'google_vision_api_key','yandex_search_api_key','yandex_folder_id','mapillary_token'})


CredentialError = VaultError


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


class _Credential(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


class WindowsLegacyStore:
    def __init__(self, *, prefix="GrangerPet/v2", directory=None):
        self.prefix = prefix
        self.directory = Path(directory) if directory else Path(os.environ.get("APPDATA", Path.home())) / "GrangerPet" / "vault"

    def _target(self, name):
        if name not in NAMES:
            raise CredentialError("Неизвестный тип учётных данных.")
        return f"{self.prefix}/{name}"

    def _file(self, name):
        return self.directory / (hashlib.sha256(self._target(name).encode()).hexdigest() + ".dpapi")

    @staticmethod
    def _windows():
        if sys.platform != "win32":
            raise CredentialError("Защищённое хранилище требует Windows.")
        advapi = ctypes.WinDLL("Advapi32", use_last_error=True)
        advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_Credential))]
        advapi.CredReadW.restype = wintypes.BOOL
        advapi.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
        advapi.CredWriteW.restype = wintypes.BOOL
        advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        advapi.CredDeleteW.restype = wintypes.BOOL
        advapi.CredFree.argtypes = [ctypes.c_void_p]
        advapi.CredFree.restype = None
        return advapi

    @staticmethod
    def _protect(data, decrypt=False):
        if sys.platform != "win32":
            raise CredentialError("Защищённое хранилище требует Windows.")
        crypt = ctypes.WinDLL("Crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("Kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        source, result = _Blob(len(data), buffer), _Blob()
        # UI_FORBIDDEN; DPAPI binds encrypted data to the signed-in Windows user.
        if decrypt:
            method = crypt.CryptUnprotectData
            method.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
            ok = method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
        else:
            method = crypt.CryptProtectData
            method.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
            ok = method(ctypes.byref(source), "GrangerPet session", None, None, None, 1, ctypes.byref(result))
        if not ok:
            raise CredentialError("Windows не смогла защитить или прочитать сессию.")
        try:
            return ctypes.string_at(result.data, result.size)
        finally:
            kernel.LocalFree(result.data)

    def get(self, name):
        target = self._target(name)
        path = self._file(name)
        if path.is_file():
            try:
                return WindowsLegacyStore._protect(path.read_bytes(), decrypt=True).decode("utf-8")
            except (OSError, UnicodeError):
                raise CredentialError("Не удалось прочитать защищённую сессию.") from None
        api = self._windows()
        pointer = ctypes.POINTER(_Credential)()
        if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return ""
            raise CredentialError("Windows Credential Manager недоступен.")
        try:
            return ctypes.string_at(pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize).decode("utf-8")
        finally:
            api.CredFree(pointer)

    def set(self, name, value):
        target = self._target(name)
        if not isinstance(value, str):
            raise CredentialError("Учётные данные должны быть строкой.")
        if not value:
            self.delete(name)
            return
        data = value.encode("utf-8")
        if len(data) > 512_000:
            raise CredentialError("Сессия превышает допустимый размер.")
        api = self._windows()
        if len(data) > 2400:
            protected = WindowsLegacyStore._protect(data)
            self.directory.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix="vault-", dir=self.directory)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(protected)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self._file(name))
            finally:
                Path(temporary).unlink(missing_ok=True)
            api.CredDeleteW(target, 1, 0)
            return
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        credential = _Credential()
        credential.Type, credential.TargetName = 1, target
        credential.CredentialBlobSize, credential.CredentialBlob = len(data), buffer
        credential.Persist, credential.UserName = 2, "GrangerPet"
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise CredentialError("Windows не смогла сохранить учётные данные.")
        self._file(name).unlink(missing_ok=True)

    def delete(self, name):
        target = self._target(name)
        api = self._windows()
        if not api.CredDeleteW(target, 1, 0) and ctypes.get_last_error() != 1168:
            raise CredentialError("Не удалось удалить учётные данные из Windows.")
        self._file(name).unlink(missing_ok=True)


class CredentialsStore(WindowsLegacyStore):
    def __init__(self, *, prefix="GrangerPet/v2", directory=None, data_root=None):
        super().__init__(prefix=prefix, directory=directory)
        self.data_root = Path(data_root) if data_root is not None else self.directory.parent
        digest = hashlib.sha256(self.prefix.encode("utf-8")).hexdigest()[:24]
        self.portable = PortableVault(self.directory / (digest + ".gpx"))

    @staticmethod
    def _protect(data, decrypt=False):
        # Existing archive/checkpoint callers retain their tested interface.
        return open_bytes(data) if decrypt else seal_bytes(data)

    def get(self, name):
        self._target(name)
        return self.portable.get(name) if self.portable.exists else super().get(name)

    def set(self, name, value):
        self._target(name)
        if not isinstance(value, str) or len(value.encode("utf-8")) > 512_000:
            raise CredentialError("Недопустимый формат или размер учётных данных.")
        if self.portable.exists:
            return self.portable.set(name, value)
        return super().set(name, value)

    def delete(self, name):
        self._target(name)
        if self.portable.exists:
            return self.portable.set(name, "")
        return super().delete(name)

    def migrate(self, passphrase, *, data_root=None, migrate=True):
        """Prepare encrypted copies, verify all, then atomically activate.

        Nothing is deleted from WCM or the original profile. A partial staging
        directory contains only ciphertext and cannot activate portable mode.
        """
        root = Path(data_root) if data_root is not None else self.data_root
        if root.resolve() != self.data_root.resolve():
            raise CredentialError("Каталог миграции не совпадает с каталогом профиля.")
        if self.portable.exists:
            raise CredentialError("Переносимое хранилище уже существует. Разблокируйте его.")
        # Validate password and KDF availability before reading any old values.
        from .portable_vault import _password
        _password(passphrase)
        secrets = {}
        legacy = WindowsLegacyStore(prefix=self.prefix, directory=self.directory)
        if migrate and sys.platform == "win32":
            for name in sorted(NAMES):
                value = legacy.get(name)
                if value:
                    secrets[name] = value
        source_paths = []
        if migrate:
            for name in ("chat-history.dpapi", "unread-messages.dpapi"):
                path = root / name
                if path.is_file():
                    source_paths.append((path, True))
            for subdir, pattern, protected in (
                ("conversations", "*.dpapi", True),
                ("conversations", "current.json", False),
                ("investigations", "*.checkpoint.dpapi", True),
                ("investigations", "*.json", False),
                ("canvas", "*.md", False), ("canvas", "*.json", False),
                ("attachments", "*.gpi", True),
            ):
                source_paths.extend((path, protected) for path in (root / subdir).glob(pattern) if path.is_file())
        data_key = os.urandom(32)
        stage = root / (".portable-stage-" + uuid.uuid4().hex)
        destination = root / "portable-data"
        if destination.exists():
            # A crash before activation can leave only encrypted staged copies.
            # Preserve them under an opaque recovery name and re-read originals.
            if destination.is_symlink() or destination.resolve().parent != root.resolve():
                raise CredentialError("Недопустимый каталог незавершённого переноса.")
            os.replace(destination, root / (".portable-recovery-" + uuid.uuid4().hex))
        manifest = []
        try:
            stage.mkdir(parents=True, exist_ok=False)
            for source, encrypted in source_paths:
                # Restrict migration to known profile subtrees, no symlinks.
                relative = source.relative_to(root)
                if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
                    raise CredentialError("Миграция остановлена: недопустимая ссылка в каталоге данных.")
                if source.stat().st_size > 96 * 1024 * 1024:
                    raise CredentialError("Миграция остановлена: файл превышает допустимый размер.")
                original = source.read_bytes()
                plain = WindowsLegacyStore._protect(original, decrypt=True) if encrypted else original
                # Parse structured legacy data so corruption is not called success.
                if source.suffix in (".json", ".dpapi"):
                    parsed = json.loads(plain.decode("utf-8"))
                    if relative.as_posix() == "conversations/current.json":
                        identifier = parsed.get("id") if isinstance(parsed, dict) else None
                        if not isinstance(identifier, str) or re.fullmatch(r'[a-f0-9]{32}', identifier) is None:
                            raise CredentialError("Некорректный индекс прежних диалогов. Миграция остановлена.")
                        plain = json.dumps({"id": identifier}).encode('ascii')
                sealed = PortableVault.seal_with_key(plain, data_key)
                if PortableVault.open_with_key(sealed, data_key) != plain:
                    raise CredentialError("Проверка переноса не пройдена; исходные данные сохранены.")
                # current.json holds only an opaque ID and remains a plaintext index.
                stored = plain if relative.as_posix() == "conversations/current.json" else sealed
                target = stage / relative
                atomic_write(target, stored)
                if target.read_bytes() != stored:
                    raise CredentialError("Проверка записи переноса не пройдена.")
                manifest.append({"path": relative.as_posix(), "original_sha256": hashlib.sha256(original).hexdigest()})
            # Commit artifacts first. The portable container is the activation
            # record and is published only after every artifact is verified.
            os.replace(stage, destination)
            migration = {"complete": True, "secret_count": len(secrets),
                         "artifact_count": len(source_paths), "legacy_preserved": True,
                         "artifacts": manifest}
            try:
                result = self.portable.create(passphrase, secrets=secrets, migration=migration, data_key=data_key)
            except Exception:
                # Safe rollback: only our newly created ciphertext is moved back.
                os.replace(destination, stage)
                raise
            return result
        except CredentialError:
            raise
        except (OSError, ValueError, UnicodeError):
            raise CredentialError("Миграция не завершена: не удалось прочитать или проверить прежние данные. Исходные данные сохранены.") from None
        finally:
            # Stage files contain ciphertext only, no original user file is removed.
            if stage.exists():
                if (stage.is_symlink() or stage.resolve().parent != root.resolve()
                        or not stage.name.startswith('.portable-stage-')):
                    raise CredentialError("Не удалось безопасно завершить очистку временного зашифрованного каталога.")
                shutil.rmtree(stage)


_STORE = CredentialsStore()


def get_secret(name):
    return _STORE.get(name)


def set_secret(name, value):
    _STORE.set(name, value)


def delete_secret(name):
    _STORE.delete(name)


def portable_enabled():
    return _STORE.portable.exists


def portable_unlocked():
    return _STORE.portable.unlocked


def vault_status():
    return _STORE.portable.status()


def create_portable_vault(passphrase, data_root=None, *, migrate=True):
    return _STORE.migrate(passphrase, data_root=data_root, migrate=migrate)


def unlock_portable_vault(passphrase):
    return _STORE.portable.unlock(passphrase)


def lock_portable_vault():
    return _STORE.portable.lock()


def change_vault_passphrase(old, new):
    return _STORE.portable.change_password(old, new)


def seal_bytes(data):
    if portable_enabled():
        return _STORE.portable.seal(data)
    return WindowsLegacyStore._protect(data)


def open_bytes(data):
    if portable_enabled():
        # No silent Windows/plaintext fallback after activation.
        return _STORE.portable.open(data)
    return WindowsLegacyStore._protect(data, decrypt=True)


def protected_path(path):
    """Map app-owned sensitive files into verified portable copies dynamically."""
    path = Path(path)
    if not portable_enabled():
        return path
    root = _STORE.data_root.resolve()
    resolved = path.resolve()
    portable = root / "portable-data"
    if resolved.is_relative_to(portable):
        return path
    if resolved.is_relative_to(root):
        return portable / resolved.relative_to(root)
    # Explicit custom paths remain custom, but their content is still encrypted.
    return path
