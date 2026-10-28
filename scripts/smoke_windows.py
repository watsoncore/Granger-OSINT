"""Native Windows application QA using only the project's own Qt widgets.

No user settings are touched. Browser/HTTP/process boundaries are mocked here;
the packaged EXE and actual desktop interaction require their own manual check.
Run after assets are ready: python scripts/smoke_windows.py
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.animation import STATES
from grangerpet.config import Settings, SettingsStore
from grangerpet.launcher import Launcher
from grangerpet.pet import PetWindow
from grangerpet.search import SearchResult
from grangerpet.theme import STYLE


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("This harness requires native Windows.")
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        raise SystemExit("Remove QT_QPA_PLATFORM=offscreen for native hit testing.")
    if not (ROOT / "grangerpet/assets/animations.json").is_file():
        raise SystemExit("Animation assets are not ready; generate animations.json first.")
    output = ROOT / "output/qa"
    output.mkdir(parents=True, exist_ok=True)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "platform": sys.platform,
              "checks": [], "unverified": ["Live Google API with account credentials",
              "Packaged EXE (this script tests source widgets)",
              "Other Windows versions, other DPI scales and multi-monitor arrangements",
              "Real browser opening (QDesktopServices boundary mocked)",
              "Physical mouse hover (cursor coordinates supplied to the polling method)"]}
    started = time.monotonic()
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    launcher = pet = restored = None

    def check(name, predicate, details=""):
        report["checks"].append({"name": name, "passed": bool(predicate), "details": details})
        if not predicate:
            raise AssertionError(name + (": " + details if details else ""))

    def wait_search(panel):
        for _ in range(70):
            QTest.qWait(20)
            if not panel._busy:
                return
        raise AssertionError("Search did not complete in the mocked network boundary")

    def visible_point(widget):
        image = widget._rendered
        center = QPoint(image.width() // 2, int(image.height() * 0.58))
        for radius in range(0, image.width(), 2):
            for x in (center.x() - radius, center.x() + radius):
                for y in range(max(0, center.y() - 15), min(image.height(), center.y() + 15)):
                    if 0 <= x < image.width() and image.pixelColor(x, y).alpha() > 240:
                        point = QPoint(x, y)
                        if widget._region.contains(point):
                            return point
        raise AssertionError("Sprite has no opaque torso point")

    try:
        with tempfile.TemporaryDirectory(prefix="grangerpet-qa-") as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            settings = Settings(size=220, fps=24, x=70, y=100)
            store.save(settings)
            # This harness never starts/stops another GrangerPet process.
            with patch("grangerpet.launcher.send_command", return_value=None), \
                 patch("grangerpet.launcher.launch_process", return_value=True) as spawn:
                launcher = Launcher(store)
                launcher.move(360, 100)
                launcher.show()
                QTest.qWait(120)
                launcher.grab().save(str(output / "launcher.png"))
                QTest.mouseClick(launcher.start_button, Qt.MouseButton.LeftButton)
                check("launcher_start_button", spawn.called,
                      "Launcher creates a detached-process request; process boundary mocked")
                launcher.start_deadline = 0
                with patch("grangerpet.launcher.send_command", return_value={"ok": True, "running": True}):
                    launcher.refresh_status()
                    check("launcher_real_status_consumption", launcher.running and not launcher.start_button.isEnabled())
                launcher.poll_timer.stop()
                launcher.hide()

            pet = PetWindow(store.load(), store)
            pet.move(70, 100)
            pet.show()
            pet.raise_()
            pet.frame_timer.stop()
            pet.cursor_timer.stop()
            pet.animation.set_state("idle", restart=True)
            pet._draw_frame()
            QTest.qWait(150)
            check("transparent_frameless_qt_flags",
                  pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                  and bool(pet.windowFlags() & Qt.WindowType.FramelessWindowHint)
                  and bool(pet.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
            opaque, transparent = visible_point(pet), QPoint(2, 2)
            check("alpha_native_mask", pet._region.contains(opaque) and not pet._region.contains(transparent))

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            get_long = user32.GetWindowLongPtrW
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_ssize_t
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user32.GetWindowRect.restype = wintypes.BOOL
            user32.WindowFromPoint.argtypes = [wintypes.POINT]
            user32.WindowFromPoint.restype = wintypes.HWND
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            hwnd = int(pet.winId())
            style, extended = get_long(hwnd, -16), get_long(hwnd, -20)
            check("native_topmost_layered_frameless", bool(extended & 0x8) and bool(extended & 0x80000)
                  and not bool(style & 0xC00000), f"style={style:#x}, exstyle={extended:#x}")
            rect = wintypes.RECT()
            check("native_rect", user32.GetWindowRect(hwnd, ctypes.byref(rect)))
            scale = pet.devicePixelRatioF()
            def hit(local):
                physical = wintypes.POINT(rect.left + round(local.x() * scale),
                                         rect.top + round(local.y() * scale))
                found = user32.WindowFromPoint(physical)
                return int(user32.GetAncestor(found, 2) or 0)
            visible_hit, transparent_hit = hit(opaque), hit(transparent)
            check("native_visible_hit", visible_hit == hwnd, f"expected={hwnd}, actual={visible_hit}")
            check("native_transparent_clickthrough", transparent_hit != hwnd,
                  f"transparent point reached underlying HWND={transparent_hit}")
            report["dpi"] = {"device_pixel_ratio": scale, "logical_pet_size": pet.width()}

            QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=opaque)
            check("click_opens_panel", pet.panel.isVisible())
            QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=opaque)
            check("second_click_closes_panel", not pet.panel.isVisible())

            start = pet.pos()
            QTest.mousePress(pet, Qt.MouseButton.LeftButton, pos=opaque)
            QTest.mouseMove(pet, opaque + QPoint(42, 24), delay=25)
            check("drag_uses_walk", pet._dragging and pet.animation.state == "walk")
            QTest.mouseRelease(pet, Qt.MouseButton.LeftButton, pos=opaque + QPoint(42, 24))
            saved = store.load()
            check("drag_saves_position", pet.pos() != start and (saved.x, saved.y) == (pet.x(), pet.y()))

            pet.animation.set_state("idle", restart=True)
            pet._last_attention = 0
            pet._draw_frame()
            with patch("grangerpet.pet.QCursor.pos", return_value=pet.mapToGlobal(opaque)):
                pet._poll_cursor()
            check("hover_detects_visible_figure", pet._near and pet._over and pet.animation.state == "hover")
            pet._last_attention = 0
            with patch("grangerpet.pet.QCursor.pos", return_value=pet.mapToGlobal(QPoint(-1000, -1000))):
                pet._poll_cursor()
            check("cursor_leave_returns_idle", not pet._near and not pet._over and pet.animation.state == "idle")

            canvas = QImage(7 * 244, 290, QImage.Format.Format_ARGB32)
            canvas.fill(QColor("#262932"))
            painter = QPainter(canvas)
            painter.setFont(QFont("Segoe UI", 10))
            painter.setPen(QColor("#e9e9ed"))
            diversity = {}
            for index, state in enumerate(STATES):
                pet.animation.set_state(state, restart=True)
                frames = pet.library.frames[state]
                hashes = set()
                for frame in frames:
                    bits = frame.constBits()
                    hashes.add(hashlib.sha256(bytes(bits)).hexdigest())
                diversity[state] = {"frames": len(frames), "unique_frames": len(hashes)}
                pet.animation.frame = min(len(frames) - 1, len(frames) // 3)
                pet._draw_frame()
                painter.drawImage(index * 244, 16, pet._rendered)
                painter.drawText(QRect(index * 244, 262, 244, 24), Qt.AlignmentFlag.AlignCenter, state)
            painter.end()
            canvas.save(str(output / "pet_states.png"))
            check("seven_real_frame_sequences", all(item["frames"] > 1 and item["unique_frames"] > 1 for item in diversity.values()),
                  json.dumps(diversity))

            pet.panel.domain.setText("example.org")
            pet.panel.text.setText("публичный отчёт")
            pet.panel.exact.setChecked(True)
            states = []
            pet.panel.search_state.connect(states.append)
            with patch("grangerpet.panel.QDesktopServices.openUrl", return_value=True) as opened:
                pet.panel.start_search()
                wait_search(pet.panel)
                address = opened.call_args.args[0].toString()
            check("browser_fallback_query", parse_qs(urlsplit(address).query)["q"] == ['site:example.org "публичный отчёт"'])
            check("search_animation_sequence", states == ["thinking", "working", "happy"], str(states))
            check("no_fake_results", pet.panel.results_layout.count() == 0 and "недоступна" in pet.panel.status.text())
            pet.settings.api_key, pet.settings.api_cx = "test-key", "test-engine"
            states.clear()
            fixture = SearchResult("Fixture resource", "https://example.org/report.pdf", "Fixture description", "site:example.org")
            with patch("grangerpet.panel.search_google", return_value=[fixture]):
                pet.panel.start_search()
                wait_search(pet.panel)
            check("async_fixture_results", pet.panel.results_layout.count() == 2 and states == ["thinking", "working", "happy"],
                  "Fixture only; no claim of live Google API validation")

            pet.settings.api_key = pet.settings.api_cx = ""
            pet.shutdown()
            check("pet_shutdown", not pet.isVisible() and not pet.frame_timer.isActive() and not pet.cursor_timer.isActive())
            restored = PetWindow(store.load(), store)
            restored.frame_timer.stop()
            restored.cursor_timer.stop()
            check("position_restored", (restored.x(), restored.y()) == (saved.x, saved.y))
            restored.shutdown()
        report["passed"] = True
    except Exception as exc:
        report["passed"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for widget in (restored, pet):
            if widget is not None:
                widget.shutdown()
                widget.deleteLater()
        if launcher is not None:
            launcher.poll_timer.stop()
            launcher.hide()
            launcher.deleteLater()
        app.processEvents()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (output / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
