"""Per-user Windows secret storage. No plaintext or reversible app-local cipher."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import sys
import tempfile

NAMES = frozenset({"google_api_key", "gemini_api_key", "deepseek_api_key", "vk_token", "telegram_api_hash",
                   "telegram_session", "instagram_session"})


class CredentialError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


class _Credential(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


class CredentialsStore:
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
                return self._protect(path.read_bytes(), decrypt=True).decode("utf-8")
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
            protected = self._protect(data)
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


_STORE = CredentialsStore()


def get_secret(name):
    return _STORE.get(name)


def set_secret(name, value):
    _STORE.set(name, value)


def delete_secret(name):
    _STORE.delete(name)
