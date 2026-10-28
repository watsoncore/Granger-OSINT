"""Native notification lifecycle, hit testing, real turn routing and docking."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.config import Settings, SettingsStore
from grangerpet.pet import PetWindow
from grangerpet.pet_notifications import (
    ACCENTS, PetNotification, notification_pose, notification_position,
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def letter(app):
    now = [100.0]
    widget = PetNotification(clock=lambda: now[0])
    widget.apply_settings(SimpleNamespace())
    yield widget, now
    widget.dismiss()
    widget.deleteLater()
    app.processEvents()


def test_animation_is_finite_with_quiet_dwell_and_bounded_motion():
    start = notification_pose(0)
    middle = notification_pose(.12)
    dwell = notification_pose(3)
    end = notification_pose(10.4)
    assert start.phase == "appear" and start.opacity == 0
    assert 0 < middle.opacity < 1 and 0 <= middle.offset <= 8
    assert dwell == notification_pose(8)
    assert dwell.lid == 7 and dwell.spark == 0
    assert end.phase == "disappear" and 0 < end.opacity < 1
    assert notification_pose(10.5).phase == "finished"


def test_reduced_motion_is_static_and_still_expires():
    assert notification_pose(0, False) == notification_pose(8, False)
    assert notification_pose(10.5, False).phase == "finished"


def test_reduced_motion_dwell_does_not_poll_every_millisecond(letter):
    widget, now = letter
    widget.apply_settings(SimpleNamespace(notifications_animate=False))
    widget.notify("reply", "one")
    now[0] += 10.3
    widget.tick()
    assert 190 <= widget._timer.interval() <= 210


@pytest.mark.parametrize("setting,kind", [
    ("notifications_enabled", "reply"), ("notifications_reply", "reply"),
    ("notifications_investigation", "investigation"), ("notifications_errors", "error"),
])
def test_each_notification_preference_is_honored(letter, setting, kind):
    widget, _ = letter
    widget.apply_settings(SimpleNamespace(**{setting: False}))
    assert not widget.notify(kind, "message-1")
    assert widget.payload is None and not widget.isVisible()


def test_changing_preferences_dismisses_existing_notification(letter):
    widget, _ = letter
    widget.notify("reply", "one")
    widget.apply_settings(SimpleNamespace(notifications_enabled=False))
    assert widget.payload is None and not widget._timer.isActive()


def test_windows_reduced_motion_overrides_animation_preference(letter, monkeypatch):
    widget, _ = letter
    monkeypatch.setattr("grangerpet.pet_notifications.reduced_motion", lambda: True)
    widget.apply_settings(SimpleNamespace(notifications_animate=True))
    widget.notify("reply", "one")
    assert widget._pose.opacity == 1 and widget._pose.offset == 0


def test_only_one_overlay_reused_and_message_duplicates_are_bounded(letter):
    widget, now = letter
    assert widget.notify("reply", "one")
    started = widget._started
    now[0] += 1
    assert not widget.notify("reply", "one")
    assert widget._started == started
    assert widget.notify("investigation", "two")
    assert widget.payload.kind == "investigation"
    for index in range(150):
        widget.notify("reply", f"message-{index}")
    assert len(widget._seen) == 128
    assert widget.payload.message_id == "message-149"


def test_anonymous_events_coalesce_but_new_events_are_not_lost(letter):
    widget, now = letter
    assert widget.notify("error")
    assert not widget.notify("error")
    now[0] += 2.1
    assert widget.notify("error")


def test_expiry_hides_overlay_and_stops_timer(letter):
    widget, now = letter
    widget.notify("reply", "one")
    now[0] += 10.6
    widget.tick()
    assert not widget.isVisible()
    assert widget.payload is None
    assert not widget._timer.isActive()


def test_click_activates_exact_payload_and_dismisses_without_pet_drag(letter, app):
    widget, _ = letter
    activations = []
    widget.activated.connect(lambda kind, payload: activations.append((kind, payload)))
    widget.notify("investigation", "completed-42", index=42, conversation_id="conversation-42")
    app.processEvents()
    assert not widget.mask().contains(QPoint(0, 0))
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(100, 45))
    assert len(activations) == 1
    kind, payload = activations[0]
    assert (kind, payload.message_id, payload.index) == ("investigation", "completed-42", 42)
    assert payload.conversation_id == "conversation-42"
    assert widget.payload is None and not widget.isVisible()


def test_dragging_letter_does_not_accidentally_activate_it(letter):
    widget, _ = letter
    activations = []
    widget.activated.connect(lambda *args: activations.append(args))
    widget.notify("reply", "one")
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(100, 45))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(120, 45))
    assert not activations and widget.payload is not None


@pytest.mark.parametrize("kind", ("reply", "investigation", "error"))
def test_original_painter_has_transparency_distinct_state_and_sharp_pixels(app, kind):
    image = QImage(224, 96, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    PetNotification.paint_letter(painter, kind, notification_pose(3))
    painter.end()
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(12, 3).name() == ACCENTS[kind]
    assert image.pixelColor(18, 45).alpha() == 255


@pytest.mark.parametrize("character", [QRect(10, 10, 184, 184), QRect(710, 510, 184, 184), QRect(400, 300, 184, 184)])
def test_anchor_is_on_screen_and_never_covers_character(character):
    screen = QRect(0, 0, 1000, 800)
    size = QSize(224, 96)
    rect = QRect(notification_position(character, screen, size), size)
    assert screen.contains(rect)
    assert not rect.intersects(character)


def test_dock_fits_original_character_size_and_external_gaps_avoid_main():
    available = QRect(0, 0, 1280, 900)
    main = QRect(0, 0, 1280, 900)
    size = QSize(219, 219)
    dock = QRect(1040, 70, 240, 800)
    point = PetWindow._safe_overlay_position(QPoint(100, 600), size, main, available, dock)
    assert dock.contains(QRect(point, size))
    exact = QRect(1040, 100, 219, 219)
    point = PetWindow._safe_overlay_position(QPoint(), size, main, available, exact)
    assert exact.contains(QRect(point, size))
    narrow = QRect(200, 100, 700, 700)
    point = PetWindow._safe_overlay_position(QPoint(900, 600), size, narrow, available)
    assert not QRect(point, size).intersects(narrow)
    assert PetWindow._safe_overlay_position(QPoint(), size, main, available) is None


def test_finished_event_routes_when_main_minimized_and_click_opens_exact_message(app, tmp_path, monkeypatch):
    pet = PetWindow(Settings(), SettingsStore(tmp_path/"settings.json"))
    pet.frame_timer.stop()
    pet.cursor_timer.stop()
    pet.show()
    try:
        opened = []
        monkeypatch.setattr(pet.panel, "open_message", lambda message_id, index=None, conversation_id=None: opened.append((message_id, index, conversation_id)), raising=False)
        pet.panel.showMinimized()
        pet.panel.search_state.emit('thinking')
        pet.panel.search_state.emit('working')
        pet.panel.search_state.emit('happy')
        assert pet.notification.payload is None
        pet.panel.chat_widget.turn_completed.emit({"kind": "paused", "message_id": "not-finished"})
        assert pet.notification.payload is None
        pet.panel.chat_widget.turn_completed.emit({"kind": "investigation", "message_id": "actual-final", "index": 7, "conversation_id": "actual-conversation"})
        assert pet.notification.isVisible()
        assert pet.notification.payload.message_id == "actual-final"
        QTest.mouseClick(pet.notification, Qt.MouseButton.LeftButton, pos=QPoint(100, 45))
        assert opened == [("actual-final", 7, "actual-conversation")]
        pet.panel.chat_widget.turn_completed.emit({"kind": "error", "message_id": "actual-error"})
        assert pet.notification.payload.kind == "error"
        pet.panel.chat_widget.turn_completed.emit({"kind": "cancelled"})
        assert pet.notification.payload is None
    finally:
        pet.shutdown()
        pet.panel.deleteLater()
        pet.deleteLater()
        app.processEvents()


def test_docking_restores_and_saves_original_desktop_home(app, tmp_path, monkeypatch):
    pet = PetWindow(Settings(), SettingsStore(tmp_path/"settings.json"))
    pet.frame_timer.stop()
    pet.cursor_timer.stop()
    pet.move(220, 300)
    original = pet.pos()
    state = {"active": True, "geometry": QRect(0, 0, 800, 800), "dock": QRect(560, 0, 240, 800)}
    monkeypatch.setattr(pet.panel, "desktop_window_state", lambda: state, raising=False)
    try:
        pet._sync_overlay_placement()
        assert pet.pos() != original and pet._dock_home == original
        pet._save_position()
        saved = pet.store.load()
        assert (saved.x, saved.y) == (original.x(), original.y())
        state["active"] = False
        pet._sync_overlay_placement()
        assert pet.pos() == original and pet._dock_home is None
    finally:
        pet.shutdown()
        pet.panel.deleteLater()
        pet.deleteLater()
        app.processEvents()


def test_click_restores_real_encrypted_conversation_in_existing_panel(app, tmp_path):
    """Exercise the real receiver too, rather than substituting open_message."""
    pet = PetWindow(Settings(ai_provider='none'), SettingsStore(tmp_path/'settings.json'))
    pet.frame_timer.stop()
    pet.cursor_timer.stop()
    try:
        chat = pet.panel.chat_widget
        chat._append('user', 'Первый тестовый диалог')
        chat._append('model', 'Настоящий сохранённый тестовый ответ')
        original_id = chat.conversation_id
        message_id = chat.messages[-1]['id']
        chat._save_archive()
        chat.new_conversation()
        assert chat.conversation_id != original_id
        pet.panel.showMinimized()
        pet.panel.chat_widget.turn_completed.emit({'kind':'reply', 'message_id':message_id,
            'index':1, 'conversation_id':original_id})
        app.processEvents()
        assert pet.notification.isVisible()
        QTest.mouseClick(pet.notification, Qt.MouseButton.LeftButton, pos=QPoint(100,45))
        app.processEvents()
        assert chat.conversation_id == original_id
        assert chat.messages[-1]['id'] == message_id
        assert chat.messages[-1]['text'] == 'Настоящий сохранённый тестовый ответ'
        assert pet.panel.isVisible() and not pet.panel.isMinimized()
        assert not pet.notification.isVisible()
    finally:
        pet.shutdown()
        pet.panel.deleteLater()
        pet.deleteLater()
        app.processEvents()

