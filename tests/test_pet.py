"""Offscreen Qt interaction tests; no browser or user settings are changed."""
from dataclasses import replace
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QCursor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.animation import STATES
import grangerpet.animation as animation_module
from grangerpet.config import Settings, SettingsStore
import grangerpet.pet as pet_module


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def pet(app, monkeypatch, tmp_path):
    current = [100.0]
    monkeypatch.setattr(animation_module, "time", SimpleNamespace(monotonic=lambda: current[0]))
    class TestLibrary:
        def __init__(self):
            self.frames = {}
            self.specs = {name: {"source_fps": 10, "frames": 4} for name in STATES}
            for state in STATES:
                self.frames[state] = []
                for index in range(4):
                    image = QImage(96, 96, QImage.Format.Format_ARGB32_Premultiplied)
                    image.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(image)
                    painter.fillRect(30 + index, 18, 35, 72, QColor("#885533"))
                    painter.end()
                    self.frames[state].append(image)
    monkeypatch.setattr(pet_module, "SpriteLibrary", TestLibrary)
    window = pet_module.PetWindow(Settings(size=160, fps=24, cursor_reaction=True), SettingsStore(tmp_path / "settings.json"))
    window.move(240, 260)
    window.show()
    window.frame_timer.stop()
    window.cursor_timer.stop()
    app.processEvents()
    window._test_clock = current
    yield window
    window.shutdown()
    window.panel.deleteLater()
    window.deleteLater()
    app.processEvents()


def test_native_mask_excludes_transparent_area_but_contains_visible_character(pet):
    assert pet.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert pet.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert not pet.mask().isEmpty()
    assert not pet.mask().contains(QPoint(1, 1))
    assert pet.mask().contains(QPoint(pet.width() // 2, pet.height() // 2))


def test_click_toggles_compact_panel_and_close_returns_to_idle(pet, app):
    point = QPoint(pet.width() // 2, pet.height() // 2)
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert pet.panel.isVisible()
    assert pet.animation.state in ("idle", "hover")
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert not pet.panel.isVisible()
    assert pet.animation.state == "idle"
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=point)
    pet.panel.close()
    app.processEvents()
    assert not pet.panel.isVisible()
    assert pet.animation.state == "idle"


def test_drag_plays_walk_moves_and_persists_position(pet, app):
    start = pet.pos()
    center = QPoint(pet.width() // 2, pet.height() // 2)
    QTest.mousePress(pet, Qt.MouseButton.LeftButton, pos=center)
    QTest.mouseMove(pet, center + QPoint(45, -25))
    app.processEvents()
    assert pet.animation.state == "walk"
    assert pet.pos() != start
    QTest.mouseRelease(pet, Qt.MouseButton.LeftButton, pos=center)
    assert pet.animation.state == "idle"
    saved = pet.store.load()
    assert (saved.x, saved.y) == (pet.x(), pet.y())
    assert not pet.panel.isVisible()


def test_cursor_attention_enters_and_leaves_without_interrupting_search(pet):
    QCursor.setPos(pet.mapToGlobal(QPoint(pet.width() // 2, pet.height() // 2)))
    pet._last_attention = 0
    pet._poll_cursor()
    assert pet._over
    assert pet.animation.state == "hover"
    pet.panel.search_state.emit("thinking")
    pet._last_attention = 0
    pet._poll_cursor()
    assert pet.animation.state == "thinking"
    pet.panel.search_state.emit("working")
    assert pet.animation.state == "working"
    QCursor.setPos(pet.mapToGlobal(QPoint(-600, -600)))
    pet._poll_cursor()
    pet.panel.search_state.emit("happy")
    pet._test_clock[0] += 10.0
    pet._tick()
    assert pet.animation.state == "idle"
    pet._last_attention = 0
    pet._poll_cursor()
    assert not pet._near


def test_live_preferences_resize_and_disable_attention(pet):
    settings = replace(pet.settings, size=188, fps=12, cursor_reaction=False)
    pet.apply_settings(settings)
    assert pet.size().width() == pet.size().height() == 212
    assert pet.frame_timer.interval() == round(1000 / 12)
    QCursor.setPos(pet.mapToGlobal(QPoint(pet.width() // 2, pet.height() // 2)))
    pet._poll_cursor()
    assert pet.animation.state == "idle"


def test_shutdown_hides_both_windows_stops_timers_and_emits_once(pet):
    stopped = []
    pet.stopped.connect(lambda: stopped.append(True))
    pet.toggle_panel()
    pet.shutdown()
    pet.shutdown()
    assert not pet.isVisible()
    assert not pet.panel.isVisible()
    assert not pet.frame_timer.isActive()
    assert not pet.cursor_timer.isActive()
    assert stopped == [True]


def test_position_save_and_shutdown_do_not_overwrite_new_ai_profile(pet, monkeypatch):
    monkeypatch.setattr('grangerpet.credentials.get_secret', lambda name: '')
    saved = replace(pet.settings, ai_provider='deepseek', deepseek_model='deepseek-v4-flash', source_root='current-tools')
    pet.store.save(saved)
    assert pet.settings.ai_provider == 'none'  # Deliberately stale independent process.
    pet.move(330, 280)
    pet._save_position()
    actual = pet.store.load()
    assert (actual.ai_provider, actual.deepseek_model, actual.source_root) == ('deepseek', 'deepseek-v4-flash', 'current-tools')
    assert (actual.x, actual.y) == (pet.x(), pet.y())
    pet.shutdown()
    assert pet.store.load().ai_provider == 'deepseek'


def test_panel_save_updates_pet_reference_immediately(pet):
    saved = replace(pet.settings, ai_provider='deepseek', deepseek_model='deepseek-v4-flash')
    pet.panel.settings_dialog.settings_saved.emit(saved)
    assert pet.settings is saved


def test_disabled_cursor_reaction_stops_poll_timer_and_live_setting_restarts_it(pet):
    pet.apply_settings(replace(pet.settings, cursor_reaction=False))
    assert not pet.cursor_timer.isActive()
    assert not pet._near and not pet._over
    pet.panel.settings_dialog.settings_saved.emit(replace(pet.settings, cursor_reaction=True))
    assert pet.cursor_timer.isActive()
    pet.panel.settings_dialog.settings_saved.emit(replace(pet.settings, cursor_reaction=False))
    assert not pet.cursor_timer.isActive()


def test_activity_without_pose_change_does_not_rebuild_same_visible_frame(pet):
    pet._transition_started = 0
    pet._draw_frame()
    rendered = pet._rendered.cacheKey()
    pet.notify_user_activity()
    pet._draw_frame()
    assert pet._rendered.cacheKey() == rendered
    pet.life.start_action('reading')
    pet.notify_user_activity()
    assert pet.life.action == 'settle'
    pet._draw_frame()
    assert pet._rendered.cacheKey() != rendered


def test_hidden_overlay_skips_raster_work_and_shows_current_advanced_frame(pet, app):
    pet._transition_started = 0
    pet._draw_frame()
    rendered = pet._rendered.cacheKey()
    prior_frame = pet.animation.frame
    pet.hide()
    pet._test_clock[0] += .2
    pet.animation.advance()
    assert pet.animation.frame != prior_frame
    pet._draw_frame()
    assert pet._rendered.cacheKey() == rendered
    pet.show()
    app.processEvents()
    assert pet.isVisible() and pet._rendered.cacheKey() != rendered
    assert not pet.mask().isEmpty()


def test_changed_pixels_with_identical_alpha_do_not_reapply_native_mask(pet, monkeypatch):
    pet._transition_started = 0
    pet.animation.frame = 0
    pet._render_signature = None
    pet._draw_frame()
    previous_image = pet._rendered.cacheKey()
    same_shape = pet.library.frames['idle'][0].copy()
    painter = QPainter(same_shape)
    painter.fillRect(35, 25, 20, 35, QColor('#ffcc88'))
    painter.end()
    pet.library.frames['idle'][1] = same_shape
    calls = []
    apply_mask = pet.setMask
    monkeypatch.setattr(pet, 'setMask', lambda region: (calls.append(region), apply_mask(region)))
    pet.animation.frame = 1
    pet._draw_frame()
    assert pet._rendered.cacheKey() != previous_image
    assert not calls
    assert pet.mask().contains(QPoint(pet.width() // 2, pet.height() // 2))
