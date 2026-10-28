"""Real Launcher button -> detached desktop pet lifecycle using temporary settings."""
import os
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.config import SettingsStore
from grangerpet.ipc import send_command
from grangerpet.launcher import Launcher


def test_launcher_button_starts_real_pet_and_close_leaves_it_running(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if send_command("pet", "status", timeout=100):
        pytest.skip("A desktop pet is already running; leave the user's process untouched")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    store = SettingsStore()
    launcher = Launcher(store)
    other = None

    def wait_until(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(40)
        return False

    try:
        launcher.show()
        app.processEvents()
        launcher.start_button.click()
        assert wait_until(lambda: send_command("pet", "status", timeout=100)), (
            (store.path.parent / "logs/pet.log").read_text(encoding="utf-8")
            if (store.path.parent / "logs/pet.log").exists() else "No pet process became ready"
        )
        status = send_command("pet", "status", timeout=500)
        assert status["ok"] and status["running"]
        actual_pid = status["pid"]
        launcher.refresh_status()
        assert launcher.running
        assert not launcher.start_button.isEnabled()
        assert launcher.stop_button.isEnabled()

        launcher.close()
        app.processEvents()
        assert send_command("pet", "status", timeout=500)["pid"] == actual_pid

        other = Launcher(store)
        other.start_button.click()
        assert send_command("pet", "status", timeout=500)["pid"] == actual_pid
        other.exit_all()
        assert wait_until(lambda: send_command("pet", "status", timeout=100) is None, timeout=8)
        assert store.path.exists()
    finally:
        # This test only reaches here after checking no pre-existing pet exists.
        send_command("pet", "stop", timeout=500)
        wait_until(lambda: send_command("pet", "status", timeout=100) is None, timeout=8)
        launcher.close()
        launcher.deleteLater()
        if other is not None:
            other.close()
            other.deleteLater()
        app.processEvents()
