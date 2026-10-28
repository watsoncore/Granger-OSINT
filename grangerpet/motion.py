"""Short Qt transitions which honor Windows client-area animation preference."""
import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect


def reduced_motion():
    if sys.platform == 'win32':
        try:
            import ctypes
            enabled = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
                return not bool(enabled.value)
        except (OSError, AttributeError):
            pass
    return False


def fade_in(widget, duration=150):
    if reduced_motion() or not widget.isVisible():
        return None
    previous = getattr(widget, '_appearance_animation', None)
    if previous is not None:
        previous.stop()
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b'opacity', widget)
    animation.setDuration(int(duration))
    animation.setStartValue(0.18)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._appearance_animation = animation
    def finish():
        # Keeping opacity effects on every old message would turn a simple
        # scroll view into a permanent stack of composited surfaces.
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)
        widget._appearance_animation = None
        animation.deleteLater()
    animation.finished.connect(finish)
    animation.start()
    return animation
