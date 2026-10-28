"""Deterministic images from the real Qt notification widget, without an API.

This is renderer QA, not a claim that a packaged EXE or paid request was tested.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from grangerpet.animation import SpriteLibrary
from grangerpet.pet_notifications import PetNotification


def main():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    font = Path(os.environ.get("WINDIR", r"C:\Windows"))/"Fonts"/"segoeui.ttf"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    output = Path(__file__).resolve().parents[1]/"output"/"master-qa"/"pixel-notifications"
    output.mkdir(parents=True, exist_ok=True)
    library = SpriteLibrary()
    character = QPixmap.fromImage(library.frames["idle"][0]).scaled(184, 184, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    sheet = QImage(1120, 1044, QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(QColor("#121820"))
    painter = QPainter(sheet)
    painter.setFont(QFont("Segoe UI", 10))
    report = {"source": "real PetNotification QWidget.grab; unchanged SpriteLibrary idle frame", "packaged_exe_test": False, "network_requests": 0, "frames": []}
    phases = (("appear", .1), ("letter opens", .52), ("quiet dwell", 3), ("disappear", 10.4))
    now = [100.0]
    widget = PetNotification(clock=lambda: now[0])
    for row, kind in enumerate(("reply", "investigation", "error")):
        for column, (label, elapsed) in enumerate(phases):
            now[0] = 100
            widget.notify(kind, f"qa-{row}-{column}")
            now[0] += elapsed
            widget.tick()
            app.processEvents()
            image = widget.grab().toImage()
            image.save(str(output/f"{kind}-{column}.png"))
            x, y = column*280, row*348
            painter.setPen(QColor("#d7dde7"))
            painter.drawText(x+14, y+24, f"{kind} / {label}")
            painter.drawImage(x+28, y+42, image)
            painter.drawPixmap(x+48, y+146, character)
            report["frames"].append({"kind": kind, "elapsed": elapsed, "pose": asdict(widget._pose)})
    painter.end()
    sheet.save(str(output/"contact-sheet.png"))
    widget.dismiss()
    widget.deleteLater()
    app.processEvents()
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output/"contact-sheet.png")


if __name__ == "__main__":
    main()

