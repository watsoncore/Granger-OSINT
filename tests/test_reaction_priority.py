import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.config import Settings, SettingsStore
import grangerpet.pet as pet_module
import grangerpet.animation as animation_module


def test_search_survives_click_and_both_jerk_overlays_with_distinct_rendering(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    clock = [100.0]
    fake = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(pet_module, "time", fake)
    monkeypatch.setattr(animation_module, "time", fake)
    pet = pet_module.PetWindow(Settings(size=195), SettingsStore(tmp_path / "settings.json"))
    try:
        pet.show()
        pet.frame_timer.stop()
        pet.cursor_timer.stop()
        pet.panel.search_state.emit("working")
        point = QPoint(100, 140)
        QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=point)
        for _ in range(14):
            clock[0] += .02
            pet._tick()
        assert pet.physics.pose.reaction == "embarrassed"
        assert pet.physics.pose.embarrassed > .8
        assert pet.animation.state == "working" and pet._busy
        pictures = []
        for sign, expected in ((-1, "jerk_up"), (1, "jerk_down")):
            clock[0] += 3
            pet.physics.grab(400, 400, clock[0])
            for index in range(1, 13):
                clock[0] += .008
                pet.physics.sample(400, 400 + sign * index * 8, clock[0])
                pet._tick()
            for _ in range(12):
                clock[0] += .02
                pet._tick()
            assert pet.physics.pose.reaction == expected
            assert pet.animation.state == "working"
            pictures.append(bytes(pet._rendered.constBits()))
            pet.physics.release(clock[0])
        assert pictures[0] != pictures[1]
        for _ in range(220):
            clock[0] += .02
            pet._tick()
        assert pet.physics.pose.reaction == "calm"
        assert pet.animation.state == "working" and pet._busy
        pet.panel.search_state.emit("idle")
        pet._tick()
        assert pet.animation.state == "idle"
    finally:
        pet.shutdown()
        pet.panel.deleteLater()
        pet.deleteLater()
        app.processEvents()
