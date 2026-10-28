"""Crop the EXISTING Hermione artwork into a multi-resolution Windows ICO.

QtSvg is already an application dependency. PNG-in-ICO entries are supported by
all supported Windows 10/11 versions; no Pillow or downloaded artwork is needed.
The original face/artwork is not regenerated or modified. The new icon retains
the source fan-art rights; this script supplies no new distribution permission.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import struct
import base64
import hashlib
import json

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 64, 128, 256)
CROP = (64, 8, 384, 320)


def png_bytes(image):
    encoded=QByteArray();buffer=QBuffer(encoded);buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer,'PNG'):raise ValueError('Qt could not encode application icon')
    buffer.close();return bytes(encoded)

def icon_image(source):
    if source.isNull() or source.size().width()!=512 or source.size().height()!=512:
        raise ValueError('Expected the existing512px Hermione asset')
    portrait=source.copy(QRect(*CROP))
    image=QImage(384,384,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
    painter=QPainter(image);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.drawImage(0,32,portrait);painter.end()
    return image

def icon_bytes(source):
    portrait=icon_image(source)
    entries = []
    for size in SIZES:
        image=portrait.scaled(size,size,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        entries.append((size,png_bytes(image)))
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
    source_path=ROOT/'grangerpet/assets/character.png'
    source=QImage(str(source_path));encoded=icon_bytes(source)
    portrait=png_bytes(icon_image(source))
    svg=('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 384 384">'
        '<title>Granger-OSINT — Hermione</title><desc>Crop of existing user-supplied fan artwork; source rights unchanged.</desc>'
        '<image width="384" height="384" href="data:image/png;base64,'+base64.b64encode(portrait).decode('ascii')+'"/></svg>\n').encode('utf-8')
    provenance=json.dumps({'source':'grangerpet/assets/character.png','source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
        'operation':'Crop existing head/hair, transparent square canvas, rescale only; no AI generation or face redraw',
        'crop_xywh':list(CROP),'canvas':384,'resolutions':list(SIZES),
        'rights':'User-supplied fan artwork. Original creator/license not established; not an official Harry Potter asset. Public/commercial redistribution permission has NOT been established. See grangerpet/assets/provenance.json and THIRD_PARTY_NOTICES.md.'},ensure_ascii=False,indent=2).encode('utf-8')+b'\n'
    target = resources / "Granger-OSINT.ico"
    outputs={target:encoded,resources/'Granger-OSINT.svg':svg,resources/'Granger-OSINT.png':portrait,
             resources/'Granger-OSINT-icon.provenance.json':provenance}
    if args.check:
        if any(not path.is_file() or path.read_bytes()!=data for path,data in outputs.items()):
            raise SystemExit("Application ICO differs; run scripts/generate_app_icon.py")
    else:
        for path,data in outputs.items():path.write_bytes(data)
    print(f"{target.name}: {len(SIZES)} resolutions, {len(encoded)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
