"""Render the original application SVG into a multi-resolution Windows ICO.

QtSvg is already an application dependency. PNG-in-ICO entries are supported by
all supported Windows 10/11 versions; no Pillow or downloaded artwork is needed.
The existing Hermione assets are neither read nor modified.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 64, 128, 256)


def icon_bytes(svg: bytes) -> bytes:
    renderer = QSvgRenderer(QByteArray(svg))
    if not renderer.isValid():
        raise ValueError("Invalid Granger-OSINT application SVG")
    entries = []
    for size in SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        encoded = QByteArray()
        buffer = QBuffer(encoded)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise ValueError("Qt could not encode application icon")
        buffer.close()
        entries.append((size, bytes(encoded)))
    offset = 6 + len(entries)*16
    directory, payload = bytearray(struct.pack("<HHH", 0, 1, len(entries))), bytearray()
    for size, encoded in entries:
        directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(encoded), offset))
        payload.extend(encoded)
        offset += len(encoded)
    return bytes(directory+payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the committed ICO is not reproducible")
    args = parser.parse_args()
    application = QGuiApplication.instance() or QGuiApplication([])
    resources = ROOT / "resources"
    encoded = icon_bytes((resources / "Granger-OSINT.svg").read_bytes())
    target = resources / "Granger-OSINT.ico"
    if args.check:
        if not target.is_file() or target.read_bytes() != encoded:
            raise SystemExit("Application ICO differs; run scripts/generate_app_icon.py")
    else:
        target.write_bytes(encoded)
    print(f"{target.name}: {len(SIZES)} resolutions, {len(encoded)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
