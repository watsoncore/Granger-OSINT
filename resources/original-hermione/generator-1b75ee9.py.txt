"""Bake GrangerPet's wand-reference rig without regenerating the character.

The approved source drawing is retained as raster layers. Face features, hair,
hands, wand, sleeves and legs are posed independently; no old character pixels
are used. Run with the existing desktop Python/PySide6 environment.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "resources" / "wand-reference"
ASSETS = ROOT / "grangerpet" / "assets"
QA = ROOT / "output" / "reference-qa"
SIZE = 512
FRAME_SIZE = 256
FPS = 12
STATES = ("idle", "hover", "happy", "thinking", "working", "walk", "error")
COUNTS = {state: 32 for state in STATES}
COUNTS.update(idle=48, hover=25, working=48)
EYES = ((155, 170, 45, 39), (234, 165, 49, 40))


def poly(points):
    result = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        result.lineTo(*point)
    result.closeSubpath()
    return result


def blank(width=SIZE, height=SIZE):
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    return image


def layer(image, shape):
    result = blank()
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(shape)
    painter.drawImage(0, 0, image)
    painter.end()
    return result


HEAD = poly([(137, 279), (119, 296), (90, 310), (65, 298), (69, 265),
    (68, 231), (83, 211), (76, 190), (95, 167), (108, 148), (112, 111),
    (131, 75), (159, 36), (191, 14), (252, 10), (303, 29), (333, 68),
    (344, 119), (363, 149), (392, 158), (413, 177), (422, 205),
    (444, 227), (443, 269), (420, 292), (390, 306), (352, 307),
    (316, 309), (292, 304), (273, 287), (276, 266), (282, 246),
    (278, 232), (261, 239), (239, 248), (213, 252), (192, 247),
    (171, 240), (154, 227), (147, 248), (137, 279)])
WAND_LINE = QPainterPath(QPointF(75, 195))
WAND_LINE.lineTo(133, 282)
_wand_stroker = QPainterPathStroker()
_wand_stroker.setWidth(7)
_wand_stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
WAND_MASK = _wand_stroker.createStroke(WAND_LINE)
HAND = poly([(118, 279), (123, 276), (129, 281), (134, 280), (143, 285),
    (144, 299), (135, 306), (124, 304), (116, 296), (114, 286)])
SLEEVE = poly([(138, 279), (165, 285), (188, 284), (189, 305),
    (179, 331), (168, 351), (153, 359), (141, 348), (135, 321), (133, 302)])
WAND_ARM = WAND_MASK.united(HAND).united(SLEEVE)
FREE_ARM = poly([(276, 294), (297, 303), (333, 320), (378, 346),
    (375, 352), (383, 358), (382, 365), (375, 371), (369, 378),
    (349, 378), (330, 369), (316, 350), (293, 338), (276, 294)])
LEFT_LEG = poly([(194, 409), (234, 410), (237, 437), (237, 467),
    (226, 487), (208, 498), (187, 497), (187, 478), (201, 460),
    (203, 439), (194, 409)])
RIGHT_LEG = poly([(250, 408), (288, 414), (300, 460), (318, 476),
    (318, 498), (282, 503), (270, 492), (271, 477), (266, 456),
    (250, 408)])


def stroke(painter, path, color="#30200f", width=2.2, fill=None):
    painter.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(QColor(fill) if fill else Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def eye_shape(index):
    if index == 0:
        return poly([(160, 179), (170, 175), (186, 176), (195, 182),
                     (195, 199), (186, 205), (172, 204), (162, 195)])
    return poly([(238, 178), (249, 169), (268, 169), (278, 177),
                 (275, 195), (264, 202), (250, 201), (241, 191)])


def paint_eyes(painter, base, gaze=0, look_up=0, closure=0):
    if abs(gaze) > 0.01 or abs(look_up) > 0.01:
        for index in range(2):
            painter.save()
            painter.setClipPath(eye_shape(index))
            painter.fillPath(eye_shape(index), QColor("#fffdf9"))
            painter.drawImage(QPointF(gaze * 2.8, -look_up * 2), base)
            painter.restore()
    if closure <= 0:
        return
    # Full skin patches cover the iris AND both old eye contour strokes. The
    # single new lid is painted only after all original eye pixels are hidden.
    left = QPainterPath(QPointF(152, 175))
    left.cubicTo(164, 163, 190, 163, 203, 178)
    left.cubicTo(203, 192, 196, 210, 181, 210)
    left.cubicTo(167, 210, 158, 200, 155, 178)
    right = QPainterPath(QPointF(231, 174))
    right.cubicTo(243, 157, 276, 155, 288, 174)
    right.cubicTo(285, 190, 276, 206, 261, 207)
    right.cubicTo(247, 207, 239, 196, 234, 177)
    patches = [left, right]
    for index, shape in enumerate(patches):
        painter.save()
        painter.setOpacity(closure)
        painter.fillPath(shape, QColor("#ffe5c9"))
        x = 155 if index == 0 else 237
        y = 190 if index == 0 else 186
        lid = QPainterPath(QPointF(x + 3, y))
        lid.cubicTo(x + 12, y + 8, x + 27, y + 8, x + 39, y - 1)
        stroke(painter, lid, width=2.8)
        lash = QPainterPath(QPointF(x + 3, y))
        lash.lineTo(x - 1, y - 3)
        stroke(painter, lash, width=2)
        painter.restore()


def paint_mouth(painter, state, amount):
    if state not in ("happy", "thinking", "working", "error"):
        return
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ffe5c9"))
    painter.drawEllipse(QRectF(211, 215, 28, 30))
    if state == "happy":
        smile = QPainterPath(QPointF(212, 226))
        smile.quadTo(222, 231, 234, 225)
        smile.quadTo(226, 245, 216, 238)
        smile.quadTo(213, 235, 212, 226)
        stroke(painter, smile, width=2.3, fill="#ef987f")
    elif state == "error":
        mouth = QPainterPath(QPointF(215, 235))
        mouth.quadTo(225, 227 - amount, 234, 234)
        stroke(painter, mouth, width=2.2)
    elif state == "thinking":
        mouth = QPainterPath(QPointF(219, 231))
        mouth.quadTo(226, 229, 233, 231)
        stroke(painter, mouth, width=1.8)
    else:
        mouth = QPainterPath(QPointF(215, 231))
        mouth.quadTo(224, 238, 233, 230)
        stroke(painter, mouth, width=1.8)


def paint_brows(painter, state, amount):
    if state not in ("thinking", "error"):
        return
    # Most of the eyebrows sit behind the reference bangs. Only the exposed
    # short tips move, preserving the hairstyle and the original face design.
    for x, y, sign in ((163, 162, 1), (240, 156, -1)):
        path = QPainterPath(QPointF(x, y - (2 if state == "thinking" else 0)))
        path.quadTo(x + 10, y - 5, x + 22, y + sign * (3 if state == "error" else -2))
        stroke(painter, path, width=2.4)


class Rig:
    def __init__(self, base):
        self.base = base
        clean_head = base.copy()
        painter = QPainter(clean_head)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipPath(HEAD)
        # Reconstruct the tiny hair area normally hidden by the wand/hand.
        # The COMPLETE original wand is then articulated as one foreground layer,
        # so its tip cannot remain attached to the head while its handle rotates.
        painter.setPen(QPen(QColor("#87704d"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(WAND_LINE)
        painter.fillPath(HAND, QColor("#705b3e"))
        painter.end()
        self.head = layer(clean_head, HEAD)
        self.wand_arm = layer(base, WAND_ARM)
        self.free_arm = layer(base, FREE_ARM.subtracted(HEAD))
        self.left_leg = layer(base, LEFT_LEG)
        self.right_leg = layer(base, RIGHT_LEG)
        removed = HEAD.united(WAND_ARM).united(FREE_ARM).united(LEFT_LEG).united(RIGHT_LEG)
        self.body = base.copy()
        painter = QPainter(self.body)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        painter.fillPath(removed, Qt.GlobalColor.white)
        painter.end()

    def posed(self, state, index):
        count = COUNTS[state]
        t = index / (count - 1)
        phase = math.tau * t
        breath = math.sin(phase * (2 if state in ("idle", "working") else 1))
        envelope = math.sin(math.pi * t) ** 0.8
        gaze = 2 * t - 1 if state == "hover" else 0
        closure = 0
        if state == "idle":
            closure = {30: 0.45, 31: 1, 32: 1, 33: 0.40}.get(index, 0)
        elif state in ("thinking", "working"):
            closure = 1 if index in (count - 9, count - 8) else 0
        head_angle = {"idle": 0.12 * breath, "hover": gaze * 1.8,
            "happy": 0.8 * math.sin(phase), "thinking": -1.5 + 0.25 * breath,
            "working": 0.55 * math.sin(phase), "walk": -0.8 * math.sin(phase),
            "error": 2.1 * math.sin(phase * 2) * envelope}[state]
        head_y = -0.8 * breath
        if state == "happy":
            head_y -= 1.3 * envelope
        if state == "walk":
            head_y -= 1.5 * abs(math.sin(phase))
        wand_angle = {"idle": 0.25 * breath, "hover": gaze * 0.7,
            "happy": 3 * math.sin(phase) * envelope, "thinking": -5 * envelope,
            "working": 8 * math.sin(phase * 2), "walk": -2.2 * math.sin(phase),
            "error": -3 * envelope}[state]
        arm_angle = {"happy": -38 * envelope + 6 * math.sin(phase * 3) * envelope,
            "error": -15 * envelope, "walk": 5 * math.sin(phase)}.get(state, 0.5 * breath)
        image = blank()
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Independently articulated feet/legs remain behind the robe hem.
        for leg, pivot, sign in ((self.left_leg, (216, 412), 1), (self.right_leg, (271, 416), -1)):
            painter.save()
            painter.translate(*pivot)
            if state == "walk":
                painter.rotate(sign * 7 * math.sin(phase))
                painter.translate(0, -max(0, sign * math.sin(phase)) * 2)
            painter.translate(-pivot[0], -pivot[1])
            painter.drawImage(0, 0, leg)
            painter.restore()
        # Robe and collar bridge fill the parts hidden by the detached sleeves
        # and head. They use the exact reference's flat material colors.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#25272a"))
        painter.drawPath(poly([(156, 289), (201, 269), (252, 263), (297, 307),
            (328, 345), (303, 368), (278, 379), (171, 376), (149, 335)]))
        painter.drawImage(0, breath * 0.45, self.body)
        # Fill under-arm areas to avoid opening a transparent seam when posed.
        painter.drawPath(poly([(146, 287), (177, 286), (182, 318), (158, 342), (142, 321)]))
        painter.drawPath(poly([(276, 299), (300, 312), (330, 344), (309, 359), (280, 339)]))
        for sprite, pivot, angle in ((self.free_arm, (282, 306), arm_angle),):
            painter.save()
            painter.translate(*pivot)
            painter.rotate(angle)
            painter.translate(-pivot[0], -pivot[1])
            painter.drawImage(0, -breath * 0.4, sprite)
            painter.restore()
        painter.save()
        painter.translate(229, 252 + head_y)
        painter.rotate(head_angle)
        painter.translate(-229, -252)
        painter.drawImage(0, 0, self.head)
        painter.save()
        painter.setClipPath(HEAD)
        paint_eyes(painter, self.base, gaze=gaze, look_up=0.75 if state == "thinking" else 0,
                   closure=closure)
        paint_mouth(painter, state, envelope)
        paint_brows(painter, state, envelope)
        painter.restore()
        painter.restore()
        # Wand, fingers and the bent sleeve are one uninterrupted foreground rig.
        painter.save()
        painter.translate(171, 298)
        painter.rotate(wand_angle)
        painter.translate(-171, -298)
        painter.drawImage(0, -breath * 0.4, self.wand_arm)
        painter.restore()
        painter.end()
        return image


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    QA.mkdir(parents=True, exist_ok=True)
    base_path = SOURCE / "base-512.png"
    base = QImage(str(base_path))
    if base.isNull() or base.size().width() != SIZE:
        raise SystemExit("Expected resources/wand-reference/base-512.png at512px")
    shutil.copyfile(base_path, ASSETS / "character.png")
    base.save(str(ASSETS / "GrangerPet.ico"), "ICO")
    rig = Rig(base)
    contact = blank(256 * len(STATES), 256 * 3)
    contact.fill(QColor("#252932"))
    contact_painter = QPainter(contact)
    for column, state in enumerate(STATES):
        count = COUNTS[state]
        columns = 8 if count in (32, 48) else 5
        rows = math.ceil(count / columns)
        sheet = blank(FRAME_SIZE * columns, FRAME_SIZE * rows)
        painter = QPainter(sheet)
        for index in range(count):
            frame = rig.posed(state, index)
            baked = frame.scaled(FRAME_SIZE, FRAME_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter.drawImage(index % columns * FRAME_SIZE, index // columns * FRAME_SIZE, baked)
            if index in (count // 4, count // 2, count * 3 // 4):
                row = (count // 4, count // 2, count * 3 // 4).index(index)
                contact_painter.drawImage(column * 256, row * 256,
                    frame.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        painter.end()
        sheet.save(str(ASSETS / f"{state}.png"))
    contact_painter.end()
    contact.save(str(QA / "animation-contact-sheet.png"))
    geometry = {"face_center": [0.432, 0.397], "collar_rect": [0.39, 0.48, 0.14, 0.09],
        "collar_split": 0.50, "leg_split": 0.805,
        "eye_rects": [[x / SIZE, y / SIZE, w / SIZE, h / SIZE] for x, y, w, h in EYES],
        "eyebrow_lines": [[[0.320, 0.315], [0.366, 0.324]], [[0.469, 0.306], [0.512, 0.310]]],
        "wand_tip": [0.145, 0.38], "wand_hand": [0.254, 0.57]}
    manifest = {"version": 3, "character": "Hermione / supplied wand-reference",
        "geometry": geometry, "features": {"blink": True, "breathing": True, "wand": True,
            "blink_frames": {"idle": [31, 32], "thinking": [23, 24], "working": [39, 40]}},
        "states": {state: {"sheet": f"{state}.png", "frame_width": FRAME_SIZE, "frame_height": FRAME_SIZE,
            "columns": 8 if COUNTS[state] in (32, 48) else 5, "frames": COUNTS[state],
            "source_fps": FPS, "loop": state not in ("happy", "error"),
            "source": "Qt articulated raster rig from supplied wand-reference full-body edit"} for state in STATES}}
    (ASSETS / "animations.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance = {"version": 3, "character": {"source": "User-supplied chibi Hermione drawing",
        "reference": {"path": "resources/wand-reference/reference.png", "sha256": sha(SOURCE / "reference.png")},
        "master": {"path": "resources/wand-reference/base-512.png", "sha256": sha(base_path)},
        "adaptation": "ImageGen edit removed screenshot UI/white background and completed only the cropped lower robe, legs and shoes; supplied face, bangs, hair, wand and outfit design retained",
        "full_body_source": "resources/wand-reference/full-body-source.png",
        "imagegen_prompt": "resources/wand-reference/imagegen-edit-prompt.txt",
        "rights": "Reference supplied by user; original artwork creator/license not established. No claim of original authorship."},
        "animation": {"script": "scripts/create_wand_animations.py", "renderer": "PySide6 QPainter",
            "articulated_layers": ["head/hair", "original eye textures and eyelids", "mouth/brows", "wand/sleeve/hand", "free arm", "left leg", "right leg", "robe/chest"],
            "states": {state: COUNTS[state] for state in STATES}, "embedded_behaviors": ["Blink", "Breathing"],
            "total_frames": sum(COUNTS.values()), "frame_size": FRAME_SIZE, "rig_canvas_size": SIZE},
        "imagegen_assets_included": True, "autosprite_assets_used_in_this_revision": False,
        "previous_assets_preserved": "resources/pre-wand-assets"}
    (ASSETS / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SOURCE / "rig-metadata.json").write_text(json.dumps({"geometry": geometry, "features": manifest["features"]}, indent=2) + "\n", encoding="utf-8")
    print(f"Baked {sum(COUNTS.values())} reference-preserving frames across {len(STATES)} states")


if __name__ == "__main__":
    main()
