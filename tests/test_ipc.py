"""Exercise actual independent Qt processes; clients never block their own server loop."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from PySide6.QtWidgets import QApplication

from grangerpet.ipc import send_command


WORKER_SOURCE = '''
import json
import os
from pathlib import Path
import sys
from PySide6.QtCore import QCoreApplication, QTimer
from grangerpet.ipc import InstanceServer

role, ready_file = sys.argv[1:]
app = QCoreApplication([])
state = {"size": 220, "cursor_reaction": True}
def announce(status):
    temporary = Path(ready_file + ".tmp")
    temporary.write_text(json.dumps({"status": status, "pid": os.getpid()}), encoding="utf-8")
    temporary.replace(ready_file)
def handle(command, payload):
    if command == "status":
        return {"ok": True, "running": True, "pid": os.getpid(), "settings": state}
    if command == "settings":
        state.update(payload)
        return {"ok": True, "settings": state}
    if command == "stop":
        QTimer.singleShot(40, app.quit)
        return {"ok": True}
    return {"ok": False, "error": "unknown command"}
server = InstanceServer(role, handle)
if not server.acquire():
    announce("locked")
    raise SystemExit(0)
app.aboutToQuit.connect(server.close)
announce("ready")
QTimer.singleShot(20000, app.quit)
raise SystemExit(app.exec())
'''


class ProcessIpcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The suite also creates widgets later; keep its shared client app GUI-capable.
        # The server itself remains a minimal QCoreApplication in another process.
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.worker = self.directory / "ipc_worker.py"
        self.worker.write_text(WORKER_SOURCE, encoding="utf-8")
        self.role = "test-" + str(os.getpid()) + "-" + uuid.uuid4().hex[:10]
        self.environment = os.environ.copy()
        self.environment["APPDATA"] = str(self.directory / "appdata")
        self.environment["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
        self.environment_patch = patch.dict(os.environ, {"APPDATA": self.environment["APPDATA"]})
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        self.processes = []
        self.addCleanup(self._cleanup_processes)

    def _cleanup_processes(self):
        for process in self.processes:
            if process.poll() is None:
                self._kill_worker(process)
            process.communicate(timeout=5)

    def _kill_worker(self, process):
        # Windows venv python.exe can be a launcher whose PID differs from the
        # interpreter owning the QLockFile. Terminate that actual known worker.
        actual_pid = getattr(process, "server_pid", process.pid)
        try:
            os.kill(actual_pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        if actual_pid != process.pid:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def _start_worker(self):
        ready = self.directory / (uuid.uuid4().hex + ".ready")
        process = subprocess.Popen(
            [sys.executable, str(self.worker), self.role, str(ready)],
            env=self.environment, cwd=self.directory, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.processes.append(process)
        deadline = time.monotonic() + 8
        while not ready.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail(f"Worker exited before readiness: {stdout!r} {stderr!r}")
            if time.monotonic() > deadline:
                self.fail("Worker did not become ready")
            time.sleep(0.02)
        announcement = json.loads(ready.read_text(encoding="utf-8"))
        process.server_pid = announcement["pid"]
        return process, announcement["status"]

    def test_status_settings_single_instance_and_stop_across_processes(self):
        worker, result = self._start_worker()
        self.assertEqual(result, "ready")
        status = send_command(self.role, "status", timeout=1000)
        self.assertTrue(status["running"])
        self.assertEqual(status["pid"], worker.server_pid)
        self.assertEqual(status["settings"]["size"], 220)

        reply = send_command(self.role, "settings", {"size": 310, "cursor_reaction": False}, timeout=1000)
        self.assertTrue(reply["ok"])
        status = send_command(self.role, "status", timeout=1000)
        self.assertEqual(status["settings"], {"size": 310, "cursor_reaction": False})

        duplicate, result = self._start_worker()
        self.assertEqual(result, "locked")
        self.assertEqual(duplicate.wait(timeout=5), 0)
        self.assertEqual(send_command(self.role, "status", timeout=1000)["pid"], worker.server_pid)
        self.assertTrue(send_command(self.role, "stop", timeout=1000)["ok"])
        self.assertEqual(worker.wait(timeout=5), 0)
        self.assertIsNone(send_command(self.role, "status", timeout=100))

    def test_dead_process_lock_is_recovered_even_with_zero_stale_time(self):
        worker, result = self._start_worker()
        self.assertEqual(result, "ready")
        self._kill_worker(worker)
        worker.wait(timeout=5)
        replacement, result = self._start_worker()
        self.assertEqual(result, "ready")
        self.assertEqual(send_command(self.role, "status", timeout=1000)["pid"], replacement.server_pid)
        self.assertTrue(send_command(self.role, "stop", timeout=1000)["ok"])
        self.assertEqual(replacement.wait(timeout=5), 0)


if __name__ == "__main__":
    unittest.main()
