"""Render and exercise the actual reference-based pet; no user's profile is used.

Run --native for native Windows HWND hit testing, otherwise use Qt offscreen.
This tests source widgets; scripts/smoke_exe.py independently tests the binary.
"""
from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if "--native" in sys.argv:
    os.environ.pop("QT_QPA_PLATFORM", None)
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.animation import STATES
from grangerpet.config import Settings, SettingsStore
from grangerpet.launcher import Launcher
from grangerpet.pet import PetWindow
from grangerpet.theme import STYLE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    output = ROOT / "output/reference-qa"
    output.mkdir(parents=True, exist_ok=True)
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(), "checks": [],
              "unverified": ["Physical mouse input (QTest injects into the project's own widgets)",
                             "Packaged EXE (separate smoke/lifecycle test required)",
                             "Live search and AI services (not part of this graphics-only check)"]}
    assets = ROOT / "grangerpet/assets"
    audited_names = ["character.png", "animations.json", "provenance.json"] + [state + ".png" for state in STATES]
    report["asset_sha256"] = {name: hashlib.sha256((assets / name).read_bytes()).hexdigest() for name in audited_names}
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    if app.platformName() == "offscreen":
        for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / font))
    app.setFont(QFont("Segoe UI", 10))
    report["qt_platform"] = app.platformName()
    windows = []
    painter = None

    def check(name, condition, details=""):
        report["checks"].append({"name": name, "passed": bool(condition), "details": details})
        if not condition:
            raise AssertionError(name + ": " + details)

    def render_state(pet, state, frame=None):
        pet.animation.set_state(state, restart=True)
        pet.animation.frame = frame if frame is not None else len(pet.library.frames[state]) // 3
        pet._previous = QImage()
        pet._transition_started = time.monotonic() - 1
        pet._render_signature = None
        pet._draw_frame()
        return pet._rendered.copy()

    def torso_point(pet):
        for fy in (.70, .75, .80, .83, .60):
            for fx in (.45, .50, .40, .55):
                point = QPoint(round(pet._padding + pet.settings.size * fx), round(pet._padding + pet.settings.size * fy))
                if pet.mask().contains(point) and not pet._is_collar(point):
                    return point
        raise AssertionError("No hittable torso point outside the collar")

    try:
        with tempfile.TemporaryDirectory(prefix="GrangerPet-reference-QA-") as temporary:
            store = SettingsStore(Path(temporary) / "settings.json")
            source = ROOT / "resources/wand-reference/reference.png"
            report["reference_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            canvas = QImage(7 * 224, 2 * 260, QImage.Format.Format_ARGB32_Premultiplied)
            canvas.fill(QColor("#252b35"))
            painter = QPainter(canvas)
            painter.setFont(QFont("Segoe UI", 10))
            painter.setPen(QColor("#edf0f4"))
            for row, size in enumerate((195, 100)):
                pet = PetWindow(Settings(size=size, cursor_reaction=True), store)
                windows.append(pet)
                pet.move(80, 80)
                pet.show()
                pet.raise_()
                pet.frame_timer.stop()
                pet.cursor_timer.stop()
                QTest.qWait(120)
                render_state(pet, "idle", 0)
                check(f"size_{size}_window", pet.width() == size + 24)
                check(f"size_{size}_transparency", pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                      and not pet.mask().contains(QPoint(1, 1)))
                geometry = pet.library.geometry
                x, y, width, height = geometry["collar_rect"]
                collar = QPoint(round(pet._padding + size * (x + width / 2)),
                                round(pet._padding + size * (y + height / 2)))
                check(f"size_{size}_collar", pet._is_collar(collar) and pet.mask().contains(collar))
                torso = torso_point(pet)
                if args.native:
                    check("native_platform", sys.platform == "win32" and app.platformName() == "windows")
                    user32 = ctypes.WinDLL("user32", use_last_error=True)
                    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
                    user32.WindowFromPoint.argtypes = [wintypes.POINT]
                    user32.WindowFromPoint.restype = wintypes.HWND
                    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
                    user32.GetAncestor.restype = wintypes.HWND
                    rect = wintypes.RECT()
                    hwnd = int(pet.winId())
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    ratio = pet.devicePixelRatioF()
                    def hit(point):
                        physical = wintypes.POINT(rect.left + round(point.x() * ratio), rect.top + round(point.y() * ratio))
                        found = user32.WindowFromPoint(physical)
                        return int(user32.GetAncestor(found, 2) or 0)
                    check(f"size_{size}_native_visible_hit", hit(torso) == hwnd)
                    check(f"size_{size}_native_clickthrough", hit(QPoint(1, 1)) != hwnd)
                    report["device_pixel_ratio"] = ratio
                QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=torso)
                check(f"size_{size}_panel_open", pet.panel.isVisible())
                QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=torso)
                check(f"size_{size}_panel_close", not pet.panel.isVisible())
                start = pet.pos()
                QTest.mousePress(pet, Qt.MouseButton.LeftButton, pos=torso)
                QTest.mouseMove(pet, torso + QPoint(28, 16), delay=40)
                check(f"size_{size}_walk_during_drag", pet._dragging and pet.animation.state == "walk")
                QTest.mouseRelease(pet, Qt.MouseButton.LeftButton, pos=torso)
                saved = store.load()
                check(f"size_{size}_drag_saved", pet.pos() != start and (saved.x, saved.y) == (pet.x(), pet.y()))
                pet._last_attention = 0
                with patch("grangerpet.pet.QCursor.pos", return_value=pet.mapToGlobal(torso)):
                    pet._poll_cursor()
                check(f"size_{size}_hover", pet.animation.state == "hover" and pet._over)
                pet._last_attention = 0
                with patch("grangerpet.pet.QCursor.pos", return_value=pet.mapToGlobal(QPoint(-500, -500))):
                    pet._poll_cursor()
                check(f"size_{size}_cursor_leave", pet.animation.state == "idle" and not pet._near)
                diversity = {}
                for column, state in enumerate(STATES):
                    frame = render_state(pet, state)
                    painter.drawImage(column * 224 + (224 - frame.width()) // 2, row * 260 + 8, frame)
                    painter.drawText(QRect(column * 224, row * 260 + 230, 224, 24), Qt.AlignmentFlag.AlignCenter, f"{state} · {size}px")
                    hashes = {hashlib.sha256(bytes(image.constBits())).hexdigest() for image in pet.library.frames[state]}
                    diversity[state] = len(hashes)
                check(f"size_{size}_all_states_animated", all(count > 8 for count in diversity.values()), str(diversity))
                render_state(pet, "idle", 0).save(str(output / f"pet-{size}px.png"))
                pet.shutdown()
            painter.end()
            canvas.save(str(output / "states-195-and-100.png"))
            with patch("grangerpet.launcher.send_command", return_value=None):
                launcher = Launcher(store)
                windows.append(launcher)
                launcher.show()
                app.processEvents()
                launcher.grab().save(str(output / "launcher.png"))
                check("launcher_new_preview", not launcher.preview.pixmap().isNull())
                launcher.close()
            report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if painter is not None and painter.isActive():
            painter.end()
        for window in windows:
            if isinstance(window, PetWindow):
                window.shutdown()
                window.panel.deleteLater()
            window.hide()
            window.deleteLater()
        app.processEvents()
        report["assets_unchanged_during_check"] = all(
            hashlib.sha256((assets / name).read_bytes()).hexdigest() == value
            for name, value in report["asset_sha256"].items())
        if not report["assets_unchanged_during_check"]:
            report["passed"] = False
            report["error"] = "Assets changed while QA was running; rerun after the animation render finishes."
        (output / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
