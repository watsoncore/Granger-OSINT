"""Transient facial overlays on the existing sprite, without replacing its art."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap


def facial_reaction(pixmap, pose, geometry):
    if pose.upset < .02 and pose.embarrassed < .02:
        return pixmap
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    width, height = image.width(), image.height()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(width, height)
    eyes = geometry.get("eye_rects", [[.3027, .332, .0879, .0762], [.457, .3223, .0957, .0781]])
    mouth = geometry.get("mouth_center", [.4355, .4492])
    skin = QColor("#ffe5c9")
    if pose.upset > .02:
        painter.setOpacity(min(1, pose.upset))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(skin)
        painter.drawEllipse(QRectF(mouth[0] - .027, mouth[1] - .033, .054, .066))
        painter.setPen(QPen(QColor("#382511"), .008, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for index, (x, y, w, h) in enumerate(eyes):
            # Visible slopes sit just above the eyes, below the unchanged bangs.
            start_y, end_y = (y + .002, y + .020) if index == 0 else (y + .022, y + .003)
            painter.drawLine(QPointF(x + .008, start_y), QPointF(x + w - .004, end_y))
        path = QPainterPath(QPointF(mouth[0] - .018, mouth[1] + .010))
        path.quadTo(mouth[0], mouth[1] - .017, mouth[0] + .022, mouth[1] + .009)
        painter.setPen(QPen(QColor("#442818"), .006, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    if pose.embarrassed > .02:
        painter.setOpacity(min(1, pose.embarrassed))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(223, 104, 94, 115))
        for x, y, w, h in eyes:
            painter.drawEllipse(QRectF(x + .002, y + h + .005, w * .8, .030))
        painter.setBrush(skin)
        painter.drawEllipse(QRectF(mouth[0] - .027, mouth[1] - .033, .054, .066))
        painter.setPen(QPen(QColor("#67422d"), .004, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        path = QPainterPath(QPointF(mouth[0] - .010, mouth[1] + .006))
        path.quadTo(mouth[0] + .003, mouth[1] + .015, mouth[0] + .019, mouth[1] + .004)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        # A short lowered upper lid changes the gaze without swapping the face.
        painter.setPen(QPen(QColor("#5c412b"), .004, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for x, y, w, h in eyes:
            path = QPainterPath(QPointF(x + .012, y + .020))
            path.quadTo(x + w * .5, y + .032, x + w - .010, y + .019)
            painter.drawPath(path)
    painter.end()
    return QPixmap.fromImage(image)
