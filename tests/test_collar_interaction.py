import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import grangerpet.pet as pet_module
import grangerpet.animation as animation_module
from grangerpet.config import Settings, SettingsStore


@pytest.fixture
def collar_pet(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    clock = [100.0]
    fake = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(pet_module, "time", fake)
    monkeypatch.setattr(animation_module, "time", fake)
    pet = pet_module.PetWindow(Settings(size=195), SettingsStore(tmp_path / "settings.json"))
    pet.move(300, 260)
    pet.show()
    pet.frame_timer.stop()
    pet.cursor_timer.stop()
    app.processEvents()
    yield pet, clock, app
    pet.shutdown()
    pet.panel.deleteLater()
    pet.deleteLater()
    app.processEvents()


def test_collar_drag_holds_pressed_point_has_upset_release_and_recovers(collar_pet):
    pet, clock, app = collar_pet
    x, y, width, height = getattr(pet.library, "geometry", {}).get("collar_rect", [0.43, 0.36, 0.21, 0.11])
    point = QPoint(round(pet._padding + pet.settings.size * (x + width / 2)),
                   round(pet._padding + pet.settings.size * (y + height / 2)))
    assert pet._is_collar(point)
    assert pet.mask().contains(point)
    start = pet.pos()
    QTest.mousePress(pet, Qt.MouseButton.LeftButton, pos=point)
    assert pet.physics.pose.held
    assert pet._grab_pivot.toPoint() == point
    clock[0] += 0.15
    QTest.mouseMove(pet, point + QPoint(20, 0))
    pet._tick()
    assert pet._dragging and pet.animation.state == "idle"
    assert pet.pos() == start + QPoint(20, 0)
    # High-frequency messages stay below16px each: the exact old missed-drag
    # failure. Relative local motion follows the moving native window.
    for _ in range(9):
        clock[0] += .008
        QTest.mouseMove(pet, point + QPoint(0, -8))
    for _ in range(10):
        clock[0] += 1 / 60
        pet._tick()
    assert pet.physics.pose.reaction == "jerk_up"
    assert pet.physics.pose.tuck > 0.5
    assert pet.animation.state == "idle", "The emotion overlays rather than destroys the base activity"
    assert pet.mask().contains(point), "The collar under the cursor must stay hittable"
    QTest.mouseRelease(pet, Qt.MouseButton.LeftButton, pos=point)
    assert not pet.physics.pose.held
    assert not pet.panel.isVisible()
    assert (pet.store.load().x, pet.store.load().y) == (pet.x(), pet.y())
    # The replacement Error sequence is longer than the original one. Allow
    # the brief angry hold plus one complete reaction cycle, then require Idle.
    for _ in range(480):
        clock[0] += 1 / 60
        pet._tick()
    assert not pet.physics.active
    assert pet.animation.state == "idle"


def test_live_size_always_clamps_even_if_mutated_directly(collar_pet):
    pet, _, _ = collar_pet
    for value, expected in ((999, 195), (1, 100), (170, 170)):
        pet.settings.size = value
        pet.apply_settings(pet.settings)
        assert pet.settings.size == expected
        assert pet.width() == expected + 24
