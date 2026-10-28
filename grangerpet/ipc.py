"""Per-user process locks and tiny newline-delimited local IPC."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Callable

from PySide6.QtCore import QObject, QLockFile, QProcess, QProcessEnvironment, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .config import data_directory


def server_name(role: str) -> str:
    identity = str(Path.home()).casefold().encode("utf-8")
    return "GrangerPet-" + hashlib.sha256(identity).hexdigest()[:12] + "-" + role


def send_command(role: str, command: str, payload: dict | None = None, timeout: int = 160) -> dict | None:
    socket = QLocalSocket()
    socket.connectToServer(server_name(role))
    if not socket.waitForConnected(timeout):
        socket.abort()
        return None
    socket.write((json.dumps({"command": command, "payload": payload or {}}, ensure_ascii=False) + "\n").encode("utf-8"))
    socket.flush()
    if not socket.bytesAvailable() and not socket.waitForReadyRead(timeout):
        socket.abort()
        return None
    response = bytes(socket.readAll())
    socket.disconnectFromServer()
    try:
        parsed = json.loads(response.split(b"\n", 1)[0])
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, UnicodeError):
        return None


class InstanceServer(QObject):
    def __init__(self, role: str, handler: Callable[[str, dict], dict], parent=None):
        super().__init__(parent)
        self.role = role
        self.handler = handler
        directory = data_directory()
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(directory / (server_name(role) + ".lock")))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        self.clients: dict[QLocalSocket, bytearray] = {}

    def acquire(self) -> bool:
        if not self.lock.tryLock(0):
            return False
        QLocalServer.removeServer(server_name(self.role))
        if not self.server.listen(server_name(self.role)):
            logging.getLogger(__name__).error("Cannot listen on local server: %s", self.server.errorString())
            self.lock.unlock()
            return False
        return True

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.clients[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._discard(s))
            QTimer.singleShot(3000, lambda s=socket: s.abort() if s in self.clients else None)
            if socket.bytesAvailable():
                self._read(socket)

    def _discard(self, socket):
        self.clients.pop(socket, None)
        socket.deleteLater()

    def _read(self, socket):
        if socket not in self.clients:
            return
        buffer = self.clients[socket]
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > 16384:
            socket.abort()
            return
        if b"\n" not in buffer:
            return
        try:
            message = json.loads(bytes(buffer).split(b"\n", 1)[0])
            command = message.get("command", "")
            payload = message.get("payload", {})
            if not isinstance(command, str) or not isinstance(payload, dict):
                raise ValueError("Invalid IPC message")
            response = self.handler(command, payload)
        except Exception:
            logging.getLogger(__name__).warning("Local command failed", exc_info=True)
            response = {"ok": False, "error": "command failed"}
        socket.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        socket.flush()
        socket.disconnectFromServer()

    def close(self):
        for socket in list(self.clients):
            socket.abort()
        self.server.close()
        self.lock.unlock()


def launch_process(pet: bool = False) -> bool:
    """Launch a detached process; packaged and source distributions use the same entry."""
    args = ["--pet"] if pet else []
    if getattr(sys, "frozen", False):
        executable = sys.executable
    else:
        python = Path(sys.executable)
        windowed = python.with_name("pythonw.exe")
        executable = str(windowed if windowed.exists() else python)
        args.insert(0, str(Path(__file__).resolve().parent.parent / "main.py"))
    process = QProcess()
    process.setProgram(executable)
    process.setArguments(args)
    process.setWorkingDirectory(str(Path(executable).parent))
    if getattr(sys, "frozen", False):
        # A detached onefile child outlives its launcher and needs its own
        # extraction directory. Otherwise the parent bootloader deletes shared
        # resources as soon as its Launcher window/process exits.
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYINSTALLER_RESET_ENVIRONMENT", "1")
        process.setProcessEnvironment(environment)
    success = process.startDetached()
    # PySide versions differ for the instance overload: recent bindings return
    # just bool, while older bindings expose (success, pid).
    return bool(success[0] if isinstance(success, tuple) else success)
