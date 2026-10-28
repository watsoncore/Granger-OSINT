"""Small native Qt window chrome: system movement/resize, no custom desktop hooks."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from .typography import ui_font
from .motion import reduced_motion


class HeaderControl(QToolButton):
    """Small painted control with a bounded hover transition, without effects."""
    def __init__(self, *, close=False, parent=None):
        super().__init__(parent)
        self._close = close
        self._hover = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(120)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._advance)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _advance(self, value):
        self._hover = float(value)
        self.update()

    def _animate(self, target):
        self._animation.stop()
        if reduced_motion():
            self._advance(target)
            return
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor('#344656')
        color.setAlphaF(.9 * self._hover)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 7, 7)
        if self.hasFocus():
            painter.setPen(QPen(QColor('#6C9ED2'), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 6, 6)
        if self._close:
            painter.setPen(QPen(QColor('#A6B2BF'), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            center = self.rect().center()
            painter.drawLine(QPointF(center.x()-4, center.y()-4), QPointF(center.x()+4, center.y()+4))
            painter.drawLine(QPointF(center.x()-4, center.y()+4), QPointF(center.x()+4, center.y()-4))
        else:
            self.icon().paint(painter, QRect((self.width()-20)//2, (self.height()-20)//2, 20, 20))


class WindowHeader(QWidget):
    def __init__(self, window, title, subtitle="", *, settings_action=None):
        super().__init__(window)
        self.setObjectName("WindowHeader")
        self.setFixedHeight(54)
        self._window, self._origin = window, None
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 8, 10, 8)
        row.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("WindowTitle")
        heading.setFont(ui_font(18, QFont.Weight.DemiBold))
        heading.setToolTip(subtitle)
        heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(heading, 1)
        self.settings_button = None
        if settings_action:
            self.settings_button = HeaderControl(parent=self)
            icon = QPixmap(40, 40)
            icon.setDevicePixelRatio(2)
            icon.fill(Qt.GlobalColor.transparent)
            painter = QPainter(icon)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor('#A6B2BF'), 1.4))
            painter.drawEllipse(QPointF(10, 10), 5.4, 5.4)
            painter.drawEllipse(QPointF(10, 10), 2.0, 2.0)
            for angle in range(0, 360, 45):
                painter.save()
                painter.translate(10, 10)
                painter.rotate(angle)
                painter.drawLine(QPointF(0, -6.5), QPointF(0, -8))
                painter.restore()
            painter.end()
            self.settings_button.setIcon(QIcon(icon))
            self.settings_button.setIconSize(QSize(20, 20))
            self.settings_button.setAccessibleName("Настройки")
            self.settings_button.setToolTip("Настройки источников и ИИ")
            self.settings_button.setObjectName("WindowControl")
            self.settings_button.clicked.connect(settings_action)
            row.addWidget(self.settings_button)
        self.close_button = HeaderControl(close=True, parent=self)
        self.close_button.setAccessibleName("Закрыть панель")
        self.close_button.setToolTip("Закрыть панель")
        self.close_button.setObjectName("WindowClose")
        self.close_button.clicked.connect(window.close)
        row.addWidget(self.close_button)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle and handle.startSystemMove():
                event.accept()
                return
            self._origin = (event.globalPosition().toPoint(), self._window.pos())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._origin and event.buttons() & Qt.MouseButton.LeftButton:
            point, position = self._origin
            self._window.move(position + event.globalPosition().toPoint() - point)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._origin = None
        event.accept()


class FramelessWindow(QWidget):
    """Top-level Window keeps Alt+Tab while native Qt handles edge resizing."""
    EDGE = 5

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self._resize_origin = None
        self.setMouseTracking(True)
        QApplication.instance().installEventFilter(self)

    def _edges(self, point):
        edges = Qt.Edge(0)
        if point.x() < self.EDGE:
            edges |= Qt.Edge.LeftEdge
        elif point.x() >= self.width() - self.EDGE:
            edges |= Qt.Edge.RightEdge
        if point.y() < self.EDGE:
            edges |= Qt.Edge.TopEdge
        elif point.y() >= self.height() - self.EDGE:
            edges |= Qt.Edge.BottomEdge
        return edges

    def eventFilter(self, watched, event):
        if isinstance(watched, QWidget) and watched.window() is self:
            kind = event.type()
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                point = event.globalPosition().toPoint()
                edges = self._edges(self.mapFromGlobal(point))
                if edges:
                    handle = self.windowHandle()
                    if handle and handle.startSystemResize(edges):
                        return True
                    self._resize_origin = (point, QRect(self.geometry()), edges)
                    return True
            elif kind == QEvent.Type.MouseMove and self._resize_origin:
                point, original, edges = self._resize_origin
                delta = event.globalPosition().toPoint() - point
                rect = QRect(original)
                if edges & Qt.Edge.LeftEdge:
                    rect.setLeft(min(original.left() + delta.x(), original.right() - self.minimumWidth() + 1))
                if edges & Qt.Edge.RightEdge:
                    rect.setRight(max(original.right() + delta.x(), original.left() + self.minimumWidth() - 1))
                if edges & Qt.Edge.TopEdge:
                    rect.setTop(min(original.top() + delta.y(), original.bottom() - self.minimumHeight() + 1))
                if edges & Qt.Edge.BottomEdge:
                    rect.setBottom(max(original.bottom() + delta.y(), original.top() + self.minimumHeight() - 1))
                self.setGeometry(rect)
                return True
            elif kind == QEvent.Type.MouseButtonRelease:
                self._resize_origin = None
        return super().eventFilter(watched, event)
