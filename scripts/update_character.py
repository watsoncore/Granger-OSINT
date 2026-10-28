"""Transfer the ImageGen portrait edit to the original animated body frames.

Original v1 sheets remain in resources/original-v1. The body, book, feet and
walking/breathing motion are preserved; head placement and blinking follow the
original animation. No network generation is performed by this script.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "grangerpet" / "assets"
ORIGINAL = ROOT / "resources" / "original-v1"
spec = importlib.util.spec_from_file_location("reaction_renderer", ROOT / "scripts" / "create_reactions.py")
rig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rig)


def bounds(image):
    points = [(x, y) for y in range(8, 96) for x in range(60, 190) if image.pixelColor(x, y).alpha() > 100]
    return ((min(p[0] for p in points) + max(p[0] for p in points)) / 2, min(p[1] for p in points))


def whites(image, dx=0, dy=0):
    return sum(1 for y in range(60 + dy, 73 + dy) for x in range(120 + dx, 134 + dx)
               if (lambda c: c.red() > 215 and c.green() > 210 and c.blue() > 200)(image.pixelColor(x, y)))


def replace_head(body, portrait, dx=0, dy=0, blink=False):
    result = body.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    # Darken old orange hair strands in the tiny neck overlap only. They remain
    # part of the original silhouette and must match the edited chestnut hair.
    for y in range(97 + dy, 115 + dy):
        for x in range(65, 180):
            color = result.pixelColor(x, y)
            if color.alpha() and 60 < color.red() < 210 and color.red() > color.green() * 1.2 and color.green() > color.blue() * 1.15:
                color.setRgb(round(color.red() * 0.78), round(color.green() * 0.87), round(color.blue() * 0.95), color.alpha())
                result.setPixelColor(x, y, color)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    painter.fillRect(QRectF(0, 0, 256, 98 + dy), Qt.GlobalColor.white)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.save()
    painter.setClipRect(QRectF(0, 0, 256, 112 + dy))
    painter.drawImage(QPointF(-3 + dx, 7 + dy), portrait)
    painter.translate(dx, dy)
    rig.draw_eyes(painter, blink=blink)
    painter.restore()
    painter.end()
    return result


def main():
    portrait = QImage(str(ROOT / "resources" / "character-v2-edit.png"))
    if portrait.isNull():
        raise SystemExit("Missing successful ImageGen edit resources/character-v2-edit.png")
    portrait = portrait.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    original_base = QImage(str(ORIGINAL / "character.png"))
    updated = replace_head(original_base, portrait)
    updated.save(str(ASSETS / "character.png"))
    base_center, base_top = bounds(original_base)
    white_base = max(1, whites(original_base))
    frame_metadata = {}
    for state in ("idle", "walk"):
        source = QImage(str(ORIGINAL / f"{state}.png"))
        target = QImage(source.size(), QImage.Format.Format_ARGB32_Premultiplied)
        target.fill(Qt.GlobalColor.transparent)
        painter = QPainter(target)
        metadata = []
        for index in range(25):
            frame = source.copy(index % 5 * 256, index // 5 * 256, 256, 256)
            center, top = bounds(frame)
            dx, dy = max(-8, min(8, round(center - base_center))), max(-7, min(7, round(top - base_top)))
            blink = whites(frame, dx, dy) < white_base * 0.28
            painter.drawImage(index % 5 * 256, index // 5 * 256, replace_head(frame, portrait, dx, dy, blink))
            metadata.append({"dx": dx, "dy": dy, "blink": blink})
        painter.end()
        target.save(str(ASSETS / f"{state}.png"))
        frame_metadata[state] = metadata
    rig.main()
    manifest_path = ASSETS / "animations.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = 2
    manifest["face_revision"] = "imagegen-reference-edit-v2"
    for state in ("idle", "walk"):
        manifest["states"][state]["source"] = "Original AutoSprite body animation with consistent ImageGen/Qt v2 portrait"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance_path = ASSETS / "provenance.json"
    provenance = json.loads((ORIGINAL / "provenance.json").read_text(encoding="utf-8"))
    provenance["revision"] = 2
    provenance["imagegen_assets_included"] = True
    provenance["portrait_update"] = {
        "tool": "image_gen.imagegen", "target": "original AutoSprite character.png",
        "generated_asset": "resources/character-v2-edit.png", "reference_photos_reviewed": 6,
        "reference_photos_sent": ["19_43_39.jpg", "19_43_43.jpg", "19_43_49.jpg", "19_43_55.jpg"],
        "changes": "Almond eyes, natural brows/nose/lips, less round face, chestnut hair within original chibi style",
        "preserved": "Original body, robe, tie, book, legs and all original walking/breathing body frames",
        "transfer_script": "scripts/update_character.py", "frame_mapping": frame_metadata,
    }
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Updated all 175 frames; original sources preserved in resources/original-v1")


if __name__ == "__main__":
    (ROOT / "test-output").mkdir(exist_ok=True)
    main()
