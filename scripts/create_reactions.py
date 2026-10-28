"""Render articulated reaction sequences from the actual AutoSprite character.

This is a reproducible Qt animation rig: original head, hair and costume pixels
stay intact; the free arm, eyes, mouth and book pages are posed independently.
It does not call a remote image service or use an enlarged still as animation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "grangerpet" / "assets"
SCALE = 4
COUNT = 25


def path(points):
    result = QPainterPath(QPointF(*points[0]))
    for command in points[1:]:
        if len(command) == 2:
            result.lineTo(*command)
        elif len(command) == 4:
            result.quadTo(*command)
        else:
            result.cubicTo(*command)
    result.closeSubpath()
    return result


def stroke(painter, shape, color, width=0.8, fill=None):
    painter.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(QColor(fill) if isinstance(fill, str) else fill or Qt.BrushStyle.NoBrush)
    painter.drawPath(shape)


def draw_eyes(painter, direction=0.0, thoughtful=False, blink=False):
    # Version 2 retains the edited portrait's almond eyes across EVERY state.
    for x, y, width, height in ((129.0, 66.0, 16.4, 11.5), (149.0, 66.0, 11.8, 10.5)):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffd3ba"))
        painter.drawEllipse(QRectF(x - width / 2 - 1.1, y - height / 2 - 1.2, width + 2.2, height + 3.0))
        eye = QPainterPath(QPointF(x - width / 2, y + 0.5))
        eye.cubicTo(x - width * 0.20, y - height * 0.64, x + width * 0.30, y - height * 0.60, x + width / 2, y - 0.8)
        eye.cubicTo(x + width * 0.25, y + height * 0.57, x - width * 0.28, y + height * 0.55, x - width / 2, y + 0.5)
        painter.save()
        painter.setClipPath(eye)
        painter.fillPath(eye, QColor("#fff8f1"))
        iris_x = x + direction * (1.7 if width > 10 else 1.2)
        iris_y = y - (1.6 if thoughtful else 0.1)
        gradient = QRadialGradient(iris_x, iris_y + 2.4, 7.5)
        gradient.setColorAt(0, QColor("#ad752e"))
        gradient.setColorAt(0.65, QColor("#684019"))
        gradient.setColorAt(1, QColor("#2d1b16"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QPointF(iris_x, iris_y), width * 0.27, height * 0.55)
        painter.setBrush(QColor("#261b1a"))
        painter.drawEllipse(QPointF(iris_x, iris_y - 0.6), width * 0.14, height * 0.33)
        painter.setBrush(QColor("#fffaf6"))
        painter.drawEllipse(QPointF(iris_x - 1.7, iris_y - 3.1), 1.2, 1.7)
        painter.drawEllipse(QPointF(iris_x + 1.4, iris_y + 2.6), 0.55, 0.6)
        if blink:
            painter.fillPath(eye, QColor("#f7cbb0"))
        painter.restore()
        top = QPainterPath(QPointF(x - width / 2 - 0.7, y - 0.4))
        top.cubicTo(x - width * 0.20, y - height * 0.65, x + width * 0.30, y - height * 0.62, x + width / 2, y - 1.1)
        if not blink:
            stroke(painter, top, "#422b28", 1.0)
        if blink:
            lid = QPainterPath(QPointF(x - width / 2, y + 1))
            lid.quadTo(x, y + 4, x + width / 2, y)
            stroke(painter, lid, "#50302a", 0.9)


def draw_mouth(painter, state, strength):
    if state not in ("happy", "thinking", "error"):
        return
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ffd1b7"))
    painter.drawEllipse(QRectF(130.6, 78.8, 17.4, 8.0))
    mouth = QPainterPath(QPointF(133, 81.9))
    if state == "happy":
        mouth.quadTo(139, 84.1 - strength, 145, 81.8)
        mouth.quadTo(140, 86.8 + strength, 133, 81.9)
        stroke(painter, mouth, "#9b6252", 0.65, "#783f37")
        teeth = QPainterPath(QPointF(134.3, 82.6))
        teeth.quadTo(139.8, 84.0, 144.9, 81.9)
        stroke(painter, teeth, "#fff0dc", 1.1)
    elif state == "thinking":
        mouth = QPainterPath(QPointF(136, 83))
        mouth.quadTo(139, 82.2, 142.4, 82.5)
        stroke(painter, mouth, "#a26c58", 0.7)
    else:
        mouth = QPainterPath(QPointF(135, 84.1))
        mouth.quadTo(140, 81.7 - strength * 0.6, 144, 83.8)
        stroke(painter, mouth, "#a26c58", 0.75)


def draw_arm(painter, elbow, wrist, pose="hand", phase=0.0):
    shoulder = QPointF(151, 116)
    elbow, wrist = QPointF(*elbow), QPointF(*wrist)
    first, second = elbow - shoulder, wrist - elbow
    length1 = max(1, math.hypot(first.x(), first.y()))
    length2 = max(1, math.hypot(second.x(), second.y()))
    n1 = QPointF(-first.y() / length1, first.x() / length1)
    n2 = QPointF(-second.y() / length2, second.x() / length2)
    a, b = shoulder + n1 * 5, shoulder - n1 * 5
    c, d = wrist + n2 * 5.5, wrist - n2 * 5.5
    sleeve = QPainterPath(a)
    sleeve.cubicTo(shoulder + first * 0.6 + n1 * 6, elbow + n2 * 8, c)
    sleeve.lineTo(d)
    sleeve.cubicTo(elbow - n2 * 6, shoulder + first * 0.5 - n1 * 6, b)
    sleeve.quadTo(shoulder - first * 0.2, a)
    gradient = QLinearGradient(shoulder, wrist)
    gradient.setColorAt(0, QColor("#343942"))
    gradient.setColorAt(0.6, QColor("#30343d"))
    gradient.setColorAt(1, QColor("#252a31"))
    stroke(painter, sleeve, "#20232b", 0.8, gradient)
    seam = QPainterPath(elbow - n2 * 4)
    seam.quadTo(elbow + first * 0.14, elbow + n2 * 4)
    stroke(painter, seam, "#22252c", 0.6)
    cuff = QPainterPath(c)
    cuff.lineTo(d)
    stroke(painter, cuff, "#171c22", 0.8)
    painter.save()
    painter.translate(wrist)
    angle = math.degrees(math.atan2(second.y(), second.x())) - 90
    painter.rotate(angle)
    if pose == "thinking":
        hand = path([(-3.1, 0), (-4.5, 4, -2.8, 7.2), (-1.5, 8.6, 1.8, 7.2),
                     (3.0, 4.5, 3.4, 1.0), (2.4, -3, 1.8, -7), (1.4, -8.4, 0.1, -7.8),
                     (-0.1, -3.5, -0.4, -0.5), (-2, -1.0), (-3.1, 0)])
    else:
        hand = path([(-3.4, 0), (-4.3, 4.3, -2.8, 8), (-1.9, 10.0, -0.6, 9.2),
                     (0.0, 7.4), (0.3, 10.3, 1.8, 9.3), (2.3, 7.0),
                     (2.6, 9.1, 3.7, 7.8), (4.7, 5.1, 4.1, 2.1),
                     (5.5, 3.7, 6.0, 2.2), (5.4, 0.2, 3.2, -1.7), (-3.4, 0)])
    skin = QLinearGradient(-4, 0, 5, 8)
    skin.setColorAt(0, QColor("#fbd3b1"))
    skin.setColorAt(1, QColor("#e6ad87"))
    stroke(painter, hand, "#94624b", 0.65, skin)
    if pose != "thinking":
        for dx in (-0.5, 1.7):
            finger = QPainterPath(QPointF(dx, 5.1))
            finger.lineTo(dx + 0.2, 8)
            stroke(painter, finger, "#bd8565", 0.45)
    painter.restore()


def draw_book(painter, phase):
    left = path([(111.5, 148), (120, 145.4, 129, 150), (129, 165), (120, 160, 110, 162), (111.5, 148)])
    right = path([(129, 150), (140, 143, 151, 148), (152.4, 161), (139, 157.5, 129, 165), (129, 150)])
    stroke(painter, left, "#694626", 1.5, "#e9d9b5")
    stroke(painter, right, "#694626", 1.5, "#f4e8cc")
    for dy in (0, 3, 6):
        a = QPainterPath(QPointF(114, 151 + dy))
        a.quadTo(120, 149 + dy, 126, 152.6 + dy)
        stroke(painter, a, "#b5a47f", 0.55)
        b = QPainterPath(QPointF(132, 152 + dy))
        b.quadTo(140, 148.6 + dy, 148, 150.2 + dy)
        stroke(painter, b, "#b5a47f", 0.55)
    # The moving page has a real curved fold; it crosses the centre of the book.
    turn = (math.sin(phase) + 1) / 2
    edge = 131 + 18 * (1 - turn)
    page = path([(129, 150), (133, 145 - 5 * turn, edge, 147 - 8 * turn),
                 (edge + 1, 159 - 7 * turn), (136, 156, 129, 165), (129, 150)])
    stroke(painter, page, "#b9a783", 0.6, "#fff1d4")
    crease = QPainterPath(QPointF(129, 150))
    crease.quadTo(128, 157, 129, 165)
    stroke(painter, crease, "#8a6b43", 0.8)


def render(base, state, index):
    t = index / (COUNT - 1)
    phase = t * math.tau
    envelope = math.sin(math.pi * t) ** 0.8
    direction = 2 * t - 1 if state == "hover" else 0
    head_angle = {"hover": direction * 3.0, "happy": 2.0 * math.sin(phase),
                  "thinking": -2.8 + math.sin(phase) * 0.6,
                  "working": 1.2 + math.sin(phase) * 1.1,
                  "error": math.sin(phase * 2) * 3.6 * envelope}[state]
    head_y = -0.4 * math.sin(phase) - (envelope if state == "happy" else 0)
    image = QImage(256 * SCALE, 256 * SCALE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.scale(SCALE, SCALE)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(0, 0, base)
    # Separate the head and free arm into real independently moving layers.
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    # Keep a ten-pixel overlap at the neck so rotating hair never opens a seam.
    painter.fillRect(QRectF(0, 0, 256, 98), Qt.GlobalColor.white)
    if state != "hover":
        painter.fillPath(path([(150, 116), (157, 120), (172, 153), (169, 176),
                              (155, 179), (151, 155), (149, 137), (150, 116)]), Qt.GlobalColor.white)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    if state != "hover":
        patch = path([(149, 114), (154, 132), (153, 159), (150, 188), (147.5, 192), (148, 146), (149, 114)])
        stroke(painter, patch, "#272c33", 0.45, "#2e333b")
    if state == "happy":
        # Raise the textured original sleeve and hand, keeping the artist's lines.
        painter.save()
        painter.translate(151, 116)
        painter.rotate(-133 * envelope + 8 * math.sin(phase * 3) * envelope)
        painter.translate(-151, -116)
        painter.setClipPath(path([(148, 113), (156, 117), (171, 154), (167, 177),
                                  (154, 177), (150, 153), (148, 113)]))
        painter.drawImage(0, 0, base)
        painter.restore()
    elif state == "working":
        draw_arm(painter, (158, 140), (137 + math.sin(phase) * 3.0, 146 + math.cos(phase) * 1.2))
        draw_book(painter, phase)
    elif state == "error":
        draw_arm(painter, (166 + envelope * 2, 140 - envelope * 6), (179 + envelope * 5, 137 - envelope * 10))
    painter.save()
    painter.translate(136, 103 + head_y)
    painter.rotate(head_angle)
    painter.translate(-136, -103)
    painter.setClipRect(QRectF(0, 0, 256, 109))
    painter.drawImage(0, 0, base)
    draw_eyes(painter, direction=direction, thoughtful=state == "thinking", blink=state != "hover" and index in (18, 19))
    draw_mouth(painter, state, envelope)
    painter.restore()
    if state == "thinking":
        # The chin-touching fingers must sit in front of the head layer.
        draw_arm(painter, (164, 132 + math.sin(phase) * 0.6), (145.5, 103 + math.sin(phase) * 0.4), "thinking")
    painter.end()
    return image.scaled(256, 256, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def main():
    base = QImage(str(ASSETS / "character.png"))
    if base.isNull():
        raise SystemExit("Missing original AutoSprite character.png")
    preview = QImage(256 * 5, 256 * 3, QImage.Format.Format_ARGB32_Premultiplied)
    preview.fill(QColor("#24272d"))
    preview_painter = QPainter(preview)
    for row, state in enumerate(("hover", "happy", "thinking", "working", "error")):
        sheet = QImage(256 * 5, 256 * 5, QImage.Format.Format_ARGB32_Premultiplied)
        sheet.fill(Qt.GlobalColor.transparent)
        painter = QPainter(sheet)
        for index in range(COUNT):
            frame = render(base, state, index)
            painter.drawImage(index % 5 * 256, index // 5 * 256, frame)
        painter.end()
        if not sheet.save(str(ASSETS / f"{state}.png")):
            raise SystemExit(f"Cannot save {state}")
        preview_painter.drawImage(row * 256, 0, render(base, state, 6))
        preview_painter.drawImage(row * 256, 256, render(base, state, 12))
        preview_painter.drawImage(row * 256, 512, render(base, state, 18))
    preview_painter.end()
    preview.save(str(ROOT / "test-output" / "reaction-contact-sheet.png"))
    manifest = {"version": 1, "character": "Hermione Granger / GrangerPet", "states": {}}
    for state in ("idle", "hover", "happy", "thinking", "working", "walk", "error"):
        manifest["states"][state] = {
            "sheet": f"{state}.png", "frame_width": 256, "frame_height": 256,
            "columns": 5, "frames": 25, "source_fps": 10.7 if state in ("idle", "walk") else 12.5,
            "loop": state not in ("happy", "error"),
            "source": "AutoSprite" if state in ("idle", "walk") else "Qt articulated rig from original AutoSprite character",
        }
    (ASSETS / "animations.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Rendered hover, happy, thinking, working, error: 25 distinct articulated 256px frames each")


if __name__ == "__main__":
    (ROOT / "test-output").mkdir(exist_ok=True)
    main()
