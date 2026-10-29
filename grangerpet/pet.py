"""A frameless, alpha-shaped desktop character, independent of the Launcher."""
from __future__ import annotations

import logging
import math
import json
import os
from pathlib import Path
import time

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBitmap, QCursor, QGuiApplication, QImage, QPainter, QPixmap, QRegion, QTransform
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from .animation import AnimationController, SpriteLibrary
from .config import Settings, SettingsStore
from .ipc import launch_process
from .panel import OsintPanel
from .physics import CollarPhysics
from .reactions import facial_reaction
from .pet_life import PetLifeController, windows_idle_seconds
from .pet_actions import action_frame
from .pet_notifications import PetNotification, notification_position


class PetWindow(QWidget):
    stopped = Signal()

    def __init__(self, settings: Settings, store: SettingsStore, *, interaction_qa=False):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | (Qt.WindowType.Window if interaction_qa else Qt.WindowType.Tool) |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Granger-OSINT · Гермиона")
        self.setObjectName("DesktopPet")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAutoFillBackground(False)
        self.setStyleSheet("QWidget#DesktopPet { background: transparent; border: none; }")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.store, self.settings = store, settings
        self.library = SpriteLibrary()
        self.geometry = getattr(self.library, "geometry", {})
        self.animation = AnimationController(self.library, self)
        self.panel = OsintPanel(settings, store)
        self.panel.search_state.connect(self._search_state)
        self.panel.closed.connect(self._panel_closed)
        # Settings are saved by the panel, but the independent pet also owns
        # position persistence. Keep its reference current so a later drag or
        # shutdown cannot restore an older provider/model over the saved one.
        self.panel.settings_dialog.settings_saved.connect(self._panel_settings_saved)
        self._pressed_at = None
        self._dragging = False
        self._press_position = QPoint()
        self._window_start = QPoint()
        self._press_time = 0.0
        self._base_state = "idle"
        self._terminal_until = 0.0
        self._trace_count = 0
        self._trace_path = os.environ.get("GRANGERPET_INTERACTION_TRACE", "")
        self._last_sample_point = None
        self._collar_grab = False
        self._grab_pivot = QPointF()
        self.physics = CollarPhysics(trace=self._trace if self._trace_path else None)
        self._physics_time = time.monotonic()
        self._search_mode = "idle"
        self._busy = False
        self._ending = False
        self._near = False
        self._over = False
        self._last_attention = 0.0
        self._aim = QPointF()
        self._aim_target = QPointF()
        self._cache = {}
        self._rendered = QImage()
        self._previous = QImage()
        self._transition_started = 0.0
        self._render_signature = None
        self.life = PetLifeController()
        self._life_home = None
        self._life_exit_x = None
        self._system_idle = None
        self._next_idle_poll = 0.0
        self._next_dock_poll = 0.0
        self._dock_home = None
        self._dock_bounds = None
        self._dock_suppressed = False
        self._main_active = False
        self.notification = PetNotification(self, ledger_path=Path(store.path).parent / 'unread-messages.dpapi')
        self.notification.activated.connect(self._open_notification)
        self.panel.messages_seen.connect(self.notification.mark_seen)
        self.panel.messages_removed.connect(self.notification.mark_seen)
        self.animation.state_changed.connect(self._begin_transition)
        self._region = QRegion()
        self._padding = 12
        self.resize(settings.size + 24, settings.size + 24)
        self.frame_timer = QTimer(self)
        self.frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.frame_timer.timeout.connect(self._tick)
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(85)
        self.cursor_timer.timeout.connect(self._poll_cursor)
        self.drag_timer = QTimer(self)
        self.drag_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.drag_timer.setInterval(12)
        self.drag_timer.timeout.connect(self._poll_drag)
        self.apply_settings(settings)
        self._restore_position()
        if interaction_qa:
            area = QGuiApplication.primaryScreen().availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self._draw_frame()
        app = QApplication.instance()
        app.screenAdded.connect(self._screen_changed)
        app.screenRemoved.connect(self._screen_changed)
        chat = getattr(self.panel, 'chat_widget', None)
        if chat is not None:
            chat.input.textChanged.connect(self.notify_user_activity)
            if hasattr(chat, 'turn_completed'):
                chat.turn_completed.connect(self._turn_completed)
        if hasattr(self.panel, 'user_activity'):
            self.panel.user_activity.connect(self.notify_user_activity)

    def _trace(self, value):
        if not self._trace_path or self._trace_count >= 20000:
            return
        try:
            path = Path(self._trace_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"pid": os.getpid(), **value}, ensure_ascii=False) + "\n")
            self._trace_count += 1
        except OSError:
            pass

    def _capture_reaction(self, label):
        if self._trace_path and not self._ending:
            destination = Path(self._trace_path).parent / f"reaction-{label}-{self._trace_count}.png"
            self._rendered.save(str(destination))

    def _sync_activity(self):
        now = time.monotonic()
        if self._dragging:
            desired = "idle" if self._collar_grab else "walk"
        elif self._busy:
            desired = self._search_mode
        elif now < self._terminal_until:
            desired = self._base_state
        elif self.life.active:
            desired = 'walk' if self.life.action in ('leave', 'return') else 'working' if self.life.action in ('cast', 'avada') else 'thinking' if self.life.action == 'reading' else 'idle'
        else:
            desired = "hover" if self._near and self.settings.cursor_reaction and not self.physics.active else "idle"
        self.animation.set_state(desired)

    def _restore_position(self):
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        if self.settings.x is None or self.settings.y is None:
            self.move(area.right() - self.width() - 48, area.bottom() - self.height() - 16)
        else:
            self.move(self.settings.x, self.settings.y)
        self._clamp_position()

    def _clamp_position(self):
        if self._life_home is not None:
            return
        center = self.frameGeometry().center()
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))

    def _screen_changed(self, *_):
        QTimer.singleShot(100, self._clamp_position)

    def apply_settings(self, settings):
        settings.size = max(100, min(195, settings.size))
        foot = self.y() + self.height()
        self.settings = settings
        self.notification.apply_settings(settings)
        if self.width() != settings.size + 24:
            self.setFixedSize(settings.size + 24, settings.size + 24)
            self.move(self.x(), foot - self.height())
            self._cache.clear()
            self._clamp_position()
        self.frame_timer.start(round(1000 / settings.fps))
        self._sync_cursor_polling()
        self.panel.set_settings(settings)
        self._draw_frame()
        if self.panel.isVisible():
            self._position_panel()

    def _sync_cursor_polling(self):
        if self.settings.cursor_reaction and not self._ending:
            if not self.cursor_timer.isActive():
                self.cursor_timer.start()
        else:
            self.cursor_timer.stop()
            self._near = self._over = False
            self._aim_target = QPointF()
            if not self._busy and not self._dragging:
                self._sync_activity()

    def _panel_settings_saved(self, settings):
        self.settings = settings
        self.notification.apply_settings(settings)
        self._sync_cursor_polling()

    def notify(self, kind, message_id=None, *, index=None, conversation_id=None):
        """Notify only an actual completed reply, investigation or error."""
        if self._ending:
            return False
        if kind == 'cancelled':
            return False
        self._update_notification_context()
        self._update_notification_anchor()
        return self.notification.notify(kind, message_id, index=index, conversation_id=conversation_id)

    def dismiss_notification(self):
        self.notification.dismiss()

    def _turn_completed(self, metadata):
        if not isinstance(metadata, dict):
            return
        kind = metadata.get('kind')
        if kind not in ('reply', 'investigation', 'error', 'cancelled'):
            return
        self.notify(kind, metadata.get('message_id'), index=metadata.get('index'), conversation_id=metadata.get('conversation_id'))

    def _open_notification(self, kind, payload):
        self.notify_user_activity()
        opener = getattr(self.panel, 'open_message', None)
        if callable(opener):
            if payload.conversation_id is not None:
                opener(payload.message_id, index=payload.index, conversation_id=payload.conversation_id)
            else:
                opener(payload.message_id, index=payload.index)
        else:
            # Compatibility with the existing Qt panel, including minimized
            # windows. The WebEngine host supplies its own message navigation.
            self.panel.mode_tabs.setCurrentWidget(self.panel.chat_widget)
            if self.panel.isMinimized():
                self.panel.showNormal()
            else:
                self.panel.show()
            self.panel.raise_()
            self.panel.activateWindow()
            self.panel.chat_widget.input.setFocus()
        self._sync_overlay_placement()

    def _update_notification_context(self):
        context = self.panel.notification_context()
        self.notification.set_context(context.get('conversation_id') if context.get('active') else None,
                                      suppressed=self._dock_suppressed or not self.isVisible())

    def _update_notification_anchor(self):
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        bounds = self._dock_bounds or screen.availableGeometry().adjusted(6, 6, -6, -6)
        self.notification.move(notification_position(self.frameGeometry(), bounds, self.notification.size()))

    @staticmethod
    def _safe_overlay_position(current, size, main, available, dock=None):
        """Fit the native character in its reserved dock or outside the UI."""
        if dock is not None:
            dock = dock.intersected(available)
        if dock is not None and dock.width() >= size.width() and dock.height() >= size.height():
            bottom_margin = min(8, dock.height()-size.height())
            return QPoint(dock.center().x()-size.width()//2, dock.bottom()-size.height()+1-bottom_margin)
        gaps = (
            QRect(available.left(), available.top(), max(0, main.left()-available.left()-8), available.height()),
            QRect(main.right()+9, available.top(), max(0, available.right()-main.right()-8), available.height()),
            QRect(available.left(), available.top(), available.width(), max(0, main.top()-available.top()-8)),
            QRect(available.left(), main.bottom()+9, available.width(), max(0, available.bottom()-main.bottom()-8)),
        )
        candidates = []
        for gap in gaps:
            if gap.width() >= size.width() and gap.height() >= size.height():
                point = QPoint(max(gap.left(), min(current.x(), gap.right()-size.width()+1)),
                               max(gap.top(), min(current.y(), gap.bottom()-size.height()+1)))
                candidates.append(point)
        return min(candidates, key=lambda point: (point-current).manhattanLength()) if candidates else None

    def _sync_overlay_placement(self):
        """The host reports only its own window; no other app is inspected."""
        if self._ending or self._pressed_at is not None or self._dragging:
            return
        state_getter = getattr(self.panel, 'desktop_window_state', None)
        state = {}
        if callable(state_getter):
            state = state_getter()
            active = bool(state.get('active'))
            main, dock = state.get('geometry'), state.get('dock')
        else:
            active = self.panel.isVisible() and not self.panel.isMinimized() and self.panel.isActiveWindow()
            main = self.panel.frameGeometry()
            dock_getter = getattr(self.panel, 'hermione_dock_geometry', None)
            dock = dock_getter() if callable(dock_getter) else None
        self._main_active = active
        if active and isinstance(main, QRect) and not main.isEmpty():
            self.life.notify_activity(immediate=True)
            self._restore_life_position()
            if self._dock_home is None:
                self._dock_home = self.pos()
            screen = QGuiApplication.screenAt(main.center()) or QGuiApplication.primaryScreen()
            dock = dock if isinstance(dock, QRect) and not dock.isEmpty() else None
            position = self._safe_overlay_position(self._dock_home, self.size(), main, screen.availableGeometry(), dock)
            if position is not None and any(isinstance(box,QRect) and QRect(position,self.size()).intersects(box)
                    for box in state.get('obstructions',[])):
                position=None
            self._dock_bounds = dock.intersected(screen.availableGeometry()) if dock is not None else None
            if position is None:
                # An unusually narrow/full-screen host without a reserved dock
                # cannot safely display a second native window over its text.
                self._dock_suppressed = True
                self.hide()
                self.notification.hide()
            else:
                self.move(position)
                if self._dock_suppressed:
                    self.show()
                self._dock_suppressed = False
        else:
            self._dock_bounds = None
            if self._dock_home is not None:
                self.move(self._dock_home)
                self._dock_home = None
                if self._dock_suppressed:
                    self.show()
                self._dock_suppressed = False
        self._update_notification_anchor()
        self._update_notification_context()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'notification'):
            self._update_notification_anchor()

    def notify_user_activity(self, *_):
        """Typing, a new reply or a user gesture interrupts local idle actions."""
        previous_action = self.life.action
        self.life.notify_activity()
        # A stationary nearby cursor is activity too, but does not change a
        # pose. Preserve the render guard unless an idle action was interrupted.
        if self.life.action != previous_action:
            self._render_signature = None

    def _restore_life_position(self):
        if self._life_home is not None:
            self.move(self._life_home)
            self._life_home = self._life_exit_x = None

    def _apply_life_travel(self, pose):
        if pose.action in ('leave', 'away', 'return'):
            if self._life_home is None:
                self._life_home = self.pos()
                screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
                area = screen.availableGeometry()
                self._life_exit_x = area.left() - self.width() - 2 if self.frameGeometry().center().x() < area.center().x() else area.right() + 2
            self.move(round(self._life_home.x() + (self._life_exit_x-self._life_home.x())*pose.travel), self._life_home.y())
        else:
            self._restore_life_position()

    def _poll_cursor(self):
        if self._ending or not self.settings.cursor_reaction or self._dragging:
            return
        local = self.mapFromGlobal(QCursor.pos())
        face = self.geometry.get("face_center", [0.5, 0.40])
        center = QPointF(self._padding + self.settings.size * face[0],
                         self._padding + self.settings.size * face[1])
        dx, dy = local.x() - center.x(), local.y() - center.y()
        distance = math.hypot(dx, dy)
        near = distance < self.settings.size * (1.15 if self._near else 0.95)
        over = self._region.contains(local)
        self._near, self._over = near, over
        if near:
            self.notify_user_activity()
        self._aim_target = QPointF(max(-1.0, min(1.0, dx / 120)),
                                  max(-1.0, min(1.0, dy / 120))) if near else QPointF()
        now = time.monotonic()
        if self._busy or self.physics.active or time.monotonic() < self._terminal_until:
            return
        desired = "hover" if near else "idle"
        if self.animation.state != desired and now - self._last_attention > 0.65:
            self.animation.set_state(desired)
            self._last_attention = now

    def _tick(self):
        if self._ending:
            return
        now = time.monotonic()
        if now >= self._next_idle_poll:
            self._system_idle = windows_idle_seconds()
            self._next_idle_poll = now + .5
        if now >= self._next_dock_poll:
            self._sync_overlay_placement()
            self._next_dock_poll = now + .25
        available = not (self._busy or self._dragging or self._pressed_at is not None or self.physics.active
                         or self.panel.isVisible() or self._main_active or self._near or now < self._terminal_until)
        life_pose = self.life.update(now, available=available, system_idle=self._system_idle)
        self._apply_life_travel(life_pose)
        self.physics.advance(now - self._physics_time, now)
        self._physics_time = now
        self._aim += (self._aim_target - self._aim) * 0.16
        if self.animation.state == "hover":
            # Hover is an ordered left-to-right gaze sequence. Selecting its frame
            # from the eased cursor vector makes the eyes follow the actual mouse.
            count = len(self.library.frames["hover"])
            self.animation.frame = round((self._aim.x() + 1) * (count - 1) / 2)
        else:
            self.animation.advance()
        if self.animation.completed:
            self._terminal_until = 0.0
        self._sync_activity()
        self._draw_frame()

    def _begin_transition(self, state):
        self._previous = self._rendered
        self._transition_started = time.monotonic()
        self._render_signature = None

    def _draw_frame(self, *, force=False):
        # Keep the animation/life clocks running while an owned modal suppresses
        # this overlay, but do not build invisible images or native hit regions.
        # Initial construction still prepares its first alpha mask before show.
        if not force and not self.isVisible() and not self._rendered.isNull():
            self._render_signature = None
            return
        key = (self.animation.state, self.animation.frame, self.settings.size)
        life_pose = self.life.pose()
        use_life = life_pose.action and not self.physics.active and not self._dragging and (not self._busy or life_pose.action == 'return')
        angle = round(self._aim.x() * (1.3 if self._over else 0.65), 2) if self.animation.state == "hover" else 0
        blend = min(1.0, max(0.0, (time.monotonic() - self._transition_started) / 0.16))
        pose = self.physics.pose
        signature = ((life_pose.action, life_pose.frame, round(life_pose.strength, 2), self.settings.size) if use_life else key,
                     angle, round(pose.angle, 2), round(pose.sag, 2), round(pose.tuck, 2), round(pose.squash, 2), round(pose.upset, 2), round(pose.embarrassed, 2), round(pose.leg_swing, 2))
        if signature == self._render_signature and blend >= 1:
            return
        self._render_signature = signature if blend >= 1 else None
        if key not in self._cache:
            self._cache[key] = QPixmap.fromImage(self.animation.image).scaled(
                self.settings.size, self.settings.size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        if use_life:
            pixmap = QPixmap.fromImage(action_frame(self.library, life_pose)).scaled(
                self.settings.size, self.settings.size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        else:
            pixmap = facial_reaction(self._cache[key], pose, self.geometry)
        image = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self._previous.isNull() and blend < 1:
            painter.setOpacity(1 - blend)
            painter.drawImage(0, 0, self._previous)
            painter.setOpacity(blend)
        else:
            self._previous = QImage()
        # Small, eased inclination supplements the directional head/eye frames.
        if self.physics.active:
            # Pivot at the anatomical collar. Body parts react independently;
            # head and chest retain their dimensions during a leg tuck/squat.
            px, py = self._grab_pivot.x(), self._grab_pivot.y()
            painter.translate(px, py)
            painter.rotate(pose.angle)
            painter.translate(-px, -py)
            x, y = self._padding, self._padding
            cut = round(pixmap.height() * self.geometry.get("leg_split", 0.69))
            collar = round(pixmap.height() * self.geometry.get("collar_split", 0.43))
            head = pixmap.copy(0, 0, pixmap.width(), collar)
            torso = pixmap.copy(0, collar, pixmap.width(), cut - collar)
            lower = pixmap.copy(0, cut, pixmap.width(), pixmap.height() - cut)
            # Anchor the collar exactly; upper and lower parts have different
            # transforms so up-tuck and down-squat are visible distinct poses.
            painter.drawPixmap(x, y + pose.squash * self.settings.size * .030, head)
            torso_height = torso.height() * (1 + .09 * pose.stretch - .13 * pose.squash) + pose.sag
            leg_scale = 1 - .56 * pose.tuck - .28 * pose.squash
            leg_height = lower.height() * leg_scale
            leg_y = y + collar + torso_height
            middle = lower.width() // 2
            for start, length, sign in ((0, middle, -1), (middle, lower.width() - middle, 1)):
                leg = lower.copy(start, 0, length, lower.height())
                offset = sign * pose.tuck * self.settings.size * .028 + sign * pose.squash * self.settings.size * .014
                swing = sign * pose.leg_swing * self.settings.size * .012
                painter.drawPixmap(QRectF(x + start + offset + swing, leg_y, length, leg_height), leg, QRectF(leg.rect()))
            # Tucked knees go BEHIND the robe. Painting legs over its hem left
            # a duplicated horizontal strip when the upward pose overlapped it.
            painter.drawPixmap(QRectF(x, y + collar, torso.width(), torso_height), torso, QRectF(torso.rect()))
        else:
            painter.translate(self.width() / 2, self.height() - self._padding)
            painter.rotate(angle)
            painter.drawPixmap(QPointF(-pixmap.width() / 2, -pixmap.height()), pixmap)
        painter.end()
        self._rendered = image
        # A real native window region makes every transparent pixel click-through,
        # even over windows belonging to other processes. Recomputed with animation.
        region = QRegion(QBitmap.fromImage(image.createAlphaMask()))
        if region != self._region:
            self._region = region
            self.setMask(region)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        # A hidden overlay may have advanced to another frame/state. Render the
        # current pose before presenting it again, without replaying old frames.
        if hasattr(self, '_rendered'):
            self._render_signature = None
            self._draw_frame(force=True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(0, 0, self._rendered)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.life.notify_activity(immediate=True)
            self._restore_life_position()
            self._pressed_at = event.globalPosition().toPoint()
            self._press_position = event.position().toPoint()
            self._window_start = self.pos()
            self._press_time = time.monotonic()
            self._last_sample_point = self._pressed_at
            self._dragging = False
            self._collar_grab = self._is_collar(self._press_position)
            if self._collar_grab:
                self._grab_pivot = QPointF(self._press_position)
                self.physics.grab(self._pressed_at.x(), self._pressed_at.y(), time.monotonic())
            self.grabMouse()
            self.drag_timer.start()
            self._trace({"event": "mouse_press", "time_s": self._press_time,
                         "x_px": self._pressed_at.x(), "y_px": self._pressed_at.y(),
                         "local_x": self._press_position.x(), "local_y": self._press_position.y(),
                         "collar": self._collar_grab, "dpr": self.devicePixelRatioF()})
            event.accept()

    def _is_collar(self, point):
        x = (point.x() - self._padding) / self.settings.size
        y = (point.y() - self._padding) / self.settings.size
        left, top, width, height = self.geometry.get("collar_rect", [0.43, 0.36, 0.21, 0.11])
        return left <= x <= left + width and top <= y <= top + height

    def mouseMoveEvent(self, event):
        if self._pressed_at is None:
            return
        self._drag_to(event.globalPosition().toPoint(), "mouse_event")
        event.accept()

    def _poll_drag(self):
        if self._pressed_at is None:
            self.drag_timer.stop()
            return
        if not QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self._finish_drag("button_not_held")
            return
        self._drag_to(QCursor.pos(), "cursor_poll")

    def _drag_to(self, position, source):
        if self._pressed_at is None:
            return
        now = time.monotonic()
        delta = position - self._pressed_at
        reaction = None
        if self._collar_grab:
            reaction = self.physics.sample(position.x(), position.y(), now, source=source)
        if not self._dragging and delta.manhattanLength() >= QApplication.startDragDistance():
            self._dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._sync_activity()
        if self._dragging:
            if reaction:
                QTimer.singleShot(160, lambda state=reaction: self._capture_reaction(state))
            self.move(self._window_start + delta)
            if self.panel.isVisible():
                self._position_panel()
        self._last_sample_point = position

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._pressed_at is None:
            return
        self._finish_drag("mouse_release")
        event.accept()

    def _finish_drag(self, reason):
        if self._pressed_at is None:
            return
        now = time.monotonic()
        dragged = self._dragging
        if self._collar_grab:
            self.physics.release(now, reason=reason)
        self.drag_timer.stop()
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        self._pressed_at = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if dragged:
            self._clamp_position()
            self._save_position()
            self._sync_activity()
        else:
            self.toggle_panel()
            if now - self._press_time <= .5 and self.physics.embarrass(now):
                QTimer.singleShot(180, lambda: self._capture_reaction("embarrassed"))
        self._trace({"event": "mouse_release", "time_s": now, "reason": reason,
                     "dragged": dragged, "reaction": self.physics.pose.reaction})

    def _position_panel(self):
        if getattr(self.panel, 'independent_main_window', False):
            return
        if self.panel.isMaximized() or self.panel.isFullScreen():
            return
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        width, height = min(self.panel.width(), area.width() - 24), min(self.panel.height(), area.height() - 24)
        self.panel.resize(width, height)
        x = self.x() - width - 10
        if x < area.left() + 8:
            x = self.x() + self.width() + 10
        x = max(area.left() + 8, min(x, area.right() - width - 8))
        y = max(area.top() + 12, min(self.y() + self.height() - height,
                                     area.bottom() - height - 12))
        self.panel.move(x, y)

    def toggle_panel(self):
        self.life.notify_activity(immediate=True)
        self._restore_life_position()
        if self.panel.isVisible():
            self.panel.hide()
            self._panel_closed()
        else:
            self._position_panel()
            self.panel.show()
            self.panel.raise_()
            self.panel.activateWindow()
            if not self._busy:
                self.animation.set_state("hover" if self._near else "idle")
            self.panel.text.setFocus()

    def _panel_closed(self):
        self._sync_activity()

    def _search_state(self, state):
        self.life.notify_activity(immediate=True)
        # An incoming task brings an away character back through a short real
        # walk rather than teleporting it or hiding/showing the widget.
        if self.life.action != 'return':
            self._restore_life_position()
        self._busy = state in ("thinking", "working")
        self._search_mode = state if self._busy else "idle"
        self._base_state = state
        if state in ("happy", "error"):
            spec = self.library.specs[state]
            self._terminal_until = time.monotonic() + len(self.library.frames[state]) / spec.get("source_fps", 12)
        elif state == "idle":
            self._terminal_until = 0.0
        self._sync_activity()

    def contextMenuEvent(self, event):
        self.life.notify_activity(immediate=True)
        self._restore_life_position()
        menu = QMenu()
        panel_action = menu.addAction("Закрыть поиск" if self.panel.isVisible() else "Открыть поиск")
        react = menu.addAction("Реагировать на курсор")
        react.setCheckable(True)
        react.setChecked(self.settings.cursor_reaction)
        menu.addSeparator()
        launcher = menu.addAction("Открыть лаунчер Granger-OSINT")
        back = menu.addAction("Остановить и вернуться в лаунчер")
        quit_action = menu.addAction("Закрыть Гермиону")
        chosen = menu.exec(event.globalPos())
        if chosen == panel_action:
            self.toggle_panel()
        elif chosen == react:
            self.settings.cursor_reaction = react.isChecked()
            self._save_position(cursor_reaction=react.isChecked())
            self.apply_settings(self.settings)
        elif chosen == launcher:
            launch_process(pet=False)
        elif chosen == back:
            launch_process(pet=False)
            self.shutdown()
        elif chosen == quit_action:
            self.shutdown()

    def _save_position(self, **appearance_changes):
        try:
            # Other windows/processes may have saved connections since this
            # pet was opened. Position changes own x/y only, never AI options.
            current = self.store.load() if self.store.path.exists() else self.settings
            position = self._dock_home if self._dock_home is not None else self._life_home if self._life_home is not None else self.pos()
            current.x, current.y = position.x(), position.y()
            if 'cursor_reaction' in appearance_changes:
                current.cursor_reaction = bool(appearance_changes['cursor_reaction'])
            self.store.save(current)
            self.settings = current
        except OSError:
            logging.getLogger(__name__).exception("Could not save pet position")

    def shutdown(self):
        if self._ending:
            return
        self._ending = True
        self.dismiss_notification()
        self._restore_life_position()
        if self._dock_home is not None:
            self.move(self._dock_home)
            self._dock_home = None
        self._save_position()
        self.frame_timer.stop()
        self.cursor_timer.stop()
        self.drag_timer.stop()
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        self.panel.shutdown()
        self.hide()
        self.stopped.emit()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()
