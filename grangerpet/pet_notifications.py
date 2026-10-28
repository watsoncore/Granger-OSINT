"""One native, animated pixel letter beside the unchanged desktop character.

Only completed application events enter here. No model text, secrets or source
content is copied into this overlay, and no process or network request is made.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import time

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPolygon, QRegion
from PySide6.QtWidgets import QWidget

from .motion import reduced_motion


KINDS = frozenset(("reply", "investigation", "error"))
LABELS = {"reply": "Ответ готов", "investigation": "Исследование\nзавершено", "error": "Произошла ошибка"}
ACCENTS = {"reply": "#c8b88a", "investigation": "#92c7b4", "error": "#df9990"}


@dataclass(frozen=True)
class NotificationPayload:
    kind: str
    message_id: str | None = None
    index: int | None = None
    conversation_id: str | None = None


@dataclass(frozen=True)
class NotificationPose:
    phase: str
    opacity: float
    offset: int
    lid: int
    spark: int


def notification_pose(elapsed: float, animate: bool = True) -> NotificationPose:
    """A finite animation with a quiet dwell; elapsed is injectable for QA."""
    elapsed = max(0.0, elapsed)
    if elapsed >= 10.5:
        return NotificationPose("finished", 0, 0, 7, 0)
    if not animate:
        return NotificationPose("dwell", 1, 0, 7, 0)
    if elapsed < .28:
        progress = elapsed / .28
        eased = 1 - (1-progress)**3
        phase, opacity, offset = "appear", eased, round((1-eased)*8)
    elif elapsed >= 10.22:
        progress = min(1, (elapsed-10.22)/.28)
        phase, opacity, offset = "disappear", 1-progress, -round(progress*5)
    else:
        phase, opacity, offset = "dwell", 1.0, 0
    lid = round(min(1, max(0, (elapsed-.18)/.62))*7)
    spark = 2 if .36 <= elapsed < .7 else 1 if .7 <= elapsed < 1.05 else 0
    return NotificationPose(phase, opacity, offset, lid, spark)


def notification_position(character: QRect, bounds: QRect, size, obstacle: QRect | None = None) -> QPoint:
    """Choose a stable on-screen position outside the character's hit region."""
    width, height = size.width(), size.height()
    candidates = (
        QPoint(character.center().x()-width//2, character.top()-height-8),
        QPoint(character.left()-width-10, character.top()+12),
        QPoint(character.right()+11, character.top()+12),
        QPoint(character.center().x()-width//2, character.bottom()+9),
    )
    placed = []
    for position in candidates:
        point = QPoint(max(bounds.left(), min(position.x(), bounds.right()-width+1)),
                       max(bounds.top(), min(position.y(), bounds.bottom()-height+1)))
        rect = QRect(point, size)
        collision = rect.intersected(character)
        score = collision.width()*collision.height()
        if obstacle is not None and not obstacle.isEmpty():
            collision = rect.intersected(obstacle)
            score += collision.width()*collision.height()*2
        placed.append((score, point))
    return min(placed, key=lambda item: item[0])[1]


class PetNotification(QWidget):
    """A reusable top-level tool owned by the same Qt process as Hermione."""
    activated = Signal(str, object)

    def __init__(self, parent=None, *, clock=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowTitle("Granger-OSINT · Уведомление Гермионы")
        self.setObjectName("HermioneNotification")
        self.setStyleSheet("QWidget#HermioneNotification { background: transparent; border: none; }")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(224, 96)
        self._clock = clock or time.monotonic
        self._started = 0.0
        self._animate = True
        self._enabled = True
        self._allowed = dict.fromkeys(KINDS, True)
        self._seen = OrderedDict()
        self._last_anonymous = {}
        self._pose = notification_pose(10.5)
        self._pressed = None
        self.payload = None
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self.tick)
        self.setMask(QRegion(QRect(8, 2, 208, 90)).united(QRegion(QRect(2, 8, 220, 78))))
        self.setAccessibleName("Уведомление Гермионы")

    def apply_settings(self, settings):
        self._enabled = bool(getattr(settings, "notifications_enabled", True))
        self._animate = bool(getattr(settings, "notifications_animate", True)) and not reduced_motion()
        self._allowed = {
            "reply": bool(getattr(settings, "notifications_reply", True)),
            "investigation": bool(getattr(settings, "notifications_investigation", True)),
            "error": bool(getattr(settings, "notifications_errors", True)),
        }
        if not self._enabled or (self.payload and not self._allowed[self.payload.kind]):
            self.dismiss()
        elif self.payload:
            self.tick()

    def notify(self, kind: str, message_id=None, *, index=None, conversation_id=None) -> bool:
        if kind not in KINDS:
            raise ValueError("Unknown notification event")
        if not self._enabled or not self._allowed[kind]:
            return False
        message_id = str(message_id)[:160] if message_id is not None else None
        conversation_id = str(conversation_id)[:128] if conversation_id is not None else None
        now = self._clock()
        key = (kind, conversation_id, message_id)
        if message_id is not None:
            if key in self._seen:
                return False
            self._seen[key] = now
            while len(self._seen) > 128:
                self._seen.popitem(last=False)
        else:
            if now-self._last_anonymous.get(kind, -100) < 2:
                return False
            self._last_anonymous[kind] = now
        self.payload = NotificationPayload(kind, message_id, index if isinstance(index, int) and index >= 0 else None, conversation_id)
        self._started = now
        self._pressed = None
        self.setAccessibleName(LABELS[kind].replace("\n", " ")+". Открыть чат Granger-OSINT")
        self.setToolTip("Открыть завершённый ответ" if kind != "error" else "Открыть сообщение об ошибке")
        self.tick()
        self.update()
        self.show()
        self.raise_()
        return True

    def dismiss(self):
        self._timer.stop()
        self._pressed = None
        self.payload = None
        self.hide()

    def tick(self):
        if self.payload is None:
            return
        elapsed = self._clock()-self._started
        pose = notification_pose(elapsed, self._animate)
        if pose.phase == "finished":
            self.dismiss()
            return
        if pose != self._pose:
            self._pose = pose
            self.update()
        # The letter only moves at the start/end. Its long quiet dwell does not
        # continuously repaint, and no timer remains after it disappears.
        remaining = (10.22 if self._animate else 10.5)-elapsed
        interval = 24 if self._animate and (elapsed < 1.05 or remaining <= 0) else max(1, min(1000, round(remaining*1000)))
        self._timer.start(interval)

    def paintEvent(self, event):
        if self.payload is None:
            return
        painter = QPainter(self)
        self.paint_letter(painter, self.payload.kind, self._pose)

    @staticmethod
    def paint_letter(painter: QPainter, kind: str, pose: NotificationPose):
        """Integer-aligned Qt primitives retain crisp pixels at any native DPI."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setOpacity(pose.opacity)
        painter.translate(0, pose.offset)
        accent = QColor(ACCENTS[kind])
        outline = QPolygon([QPoint(8, 2), QPoint(216, 2), QPoint(216, 8), QPoint(222, 8),
                            QPoint(222, 86), QPoint(216, 86), QPoint(216, 92), QPoint(8, 92),
                            QPoint(8, 86), QPoint(2, 86), QPoint(2, 8), QPoint(8, 8)])
        painter.setPen(accent.darker(180))
        painter.setBrush(QColor("#1c222b"))
        painter.drawPolygon(outline)
        painter.fillRect(9, 3, 206, 2, accent)
        # The lifted flap, paper and envelope are all original QPainter pixels.
        left, top, width, height = 18, 40, 36, 24
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent.darker(140))
        painter.drawPolygon(QPolygon([QPoint(left, top), QPoint(left+18, top-pose.lid*2), QPoint(left+width, top)]))
        painter.fillRect(left+6, top+3-pose.lid, 24, 15, QColor("#e9e2cf"))
        painter.fillRect(left+10, top+7-pose.lid, 14, 2, accent.darker(140))
        painter.fillRect(left+10, top+11-pose.lid, 10, 2, accent.darker(140))
        painter.fillRect(left, top+3, width, height, accent)
        painter.setPen(accent.darker(170))
        painter.drawLine(left, top+3, left+18, top+16)
        painter.drawLine(left+width-1, top+3, left+18, top+16)
        painter.drawLine(left, top+height+2, left+13, top+15)
        painter.drawLine(left+width-1, top+height+2, left+23, top+15)
        if kind == "error":
            painter.fillRect(left+16, top+7, 4, 8, QColor("#694140"))
            painter.fillRect(left+16, top+18, 4, 3, QColor("#694140"))
        elif pose.spark:
            x, y = 52, 21-pose.spark*2
            painter.fillRect(x, y+4, 12, 4, accent)
            painter.fillRect(x+4, y, 4, 12, accent)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(QColor("#aab1bd"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRect(68, 11, 147, 18), Qt.AlignmentFlag.AlignLeft, "Гермиона")
        painter.setPen(QColor("#f2f0eb"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(QRect(68, 30, 148, 38), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, LABELS[kind])
        painter.setPen(accent)
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRect(68, 71, 145, 16), Qt.AlignmentFlag.AlignLeft, "Открыть чат")
        painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = event.position().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._pressed is None:
            return
        pressed, self._pressed = self._pressed, None
        if self.payload and (event.position().toPoint()-pressed).manhattanLength() <= 6 and self.mask().contains(event.position().toPoint()):
            payload = self.payload
            self.activated.emit(payload.kind, payload)
            self.dismiss()
        event.accept()

