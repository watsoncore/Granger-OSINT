"""Validate the supplied wand reference's integration at real desktop sizes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from grangerpet.animation import SpriteLibrary, STATES
from grangerpet.config import Settings, SettingsStore, resource_path
import grangerpet.pet as pet_module


def image_hash(image):
    return hashlib.sha256(bytes(image.constBits())).hexdigest()


def test_wand_reference_base_is_full_body_cutout_and_not_previous_portrait():
    root = Path(__file__).resolve().parents[1]
    source = root / "resources/wand-reference/reference.png"
    master = root / "resources/wand-reference/base-512.png"
    assert source.is_file() and master.is_file()
    base = QImage(str(resource_path("assets/character.png")))
    expected = QImage(str(master))
    assert base.size() == expected.size()
    assert image_hash(base) == image_hash(expected)
    assert base.hasAlphaChannel()
    assert base.pixelColor(0, 0).alpha() == 0
    # The completed figure includes opaque shoe pixels below the original crop.
    assert any(base.pixelColor(x, y).alpha() > 200
               for y in range(round(base.height() * .91), round(base.height() * .97))
               for x in range(round(base.width() * .34), round(base.width() * .64)))
    provenance = json.loads(resource_path("assets/provenance.json").read_text(encoding="utf-8"))
    serialized = json.dumps(provenance, ensure_ascii=False)
    assert hashlib.sha256(source.read_bytes()).hexdigest() in serialized
    assert "reference" in serialized.lower()


def test_all_states_share_new_geometry_and_include_real_blink_and_breathing():
    library = SpriteLibrary()
    manifest = json.loads(resource_path("assets/animations.json").read_text(encoding="utf-8"))
    assert manifest["version"] >= 3
    assert manifest["features"]["wand"]
    assert manifest["features"]["blink"]
    assert manifest["features"]["breathing"]
    geometry = manifest["geometry"]
    x, y, width, height = geometry["collar_rect"]
    assert 0 < x < x + width < 1
    assert .46 < y < y + height < .72
    assert geometry["collar_split"] < geometry["leg_split"]
    assert geometry["leg_split"] > .73
    for state in STATES:
        frames = library.frames[state]
        assert len(frames) >= 20
        assert len({image_hash(frame) for frame in frames}) > 8, state
        assert all(frame.hasAlphaChannel() for frame in frames)
        assert all(frame.pixelColor(0, 0).alpha() == 0 for frame in frames)


def test_idle_contains_closed_eyes_and_independent_body_breathing():
    library = SpriteLibrary()
    frames = library.frames["idle"]
    geometry = library.geometry
    eyes = geometry["eye_rects"]
    assert len(eyes) == 2
    whites = []
    for frame in frames:
        count = 0
        for x, y, width, height in eyes:
            left, top = round(x * frame.width()), round(y * frame.height())
            right, bottom = round((x + width) * frame.width()), round((y + height) * frame.height())
            for py in range(top, bottom):
                for px in range(left, right):
                    color = frame.pixelColor(px, py)
                    if color.alpha() > 200 and color.red() > 225 and color.green() > 225 and color.blue() > 210:
                        count += 1
        whites.append(count)
    assert max(whites) > 30, "Open eyes should contain the reference's white highlights/sclera"
    assert min(whites) < max(whites) * .35, "Blinking must close the actual illustrated eyes"
    # A facial blink alone is insufficient: the torso below the collar must
    # also change during the idle breathing cycle, independent of head pixels.
    hashes = set()
    for frame in frames:
        y = round((geometry["collar_split"] + .02) * frame.height())
        bottom = round((geometry["leg_split"] - .02) * frame.height())
        torso = frame.copy(round(.27 * frame.width()), y, round(.47 * frame.width()), bottom - y)
        hashes.add(image_hash(torso))
    assert len(hashes) >= 5, "Idle must preserve a real body breathing cycle"


@pytest.mark.parametrize("size", [100, 195])
def test_new_sprite_keeps_hittable_collar_and_clickthrough_at_display_limits(size, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    now = [100.0]
    monkeypatch.setattr(pet_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    pet = pet_module.PetWindow(Settings(size=size), SettingsStore(tmp_path / "settings.json"))
    try:
        pet.show()
        pet.frame_timer.stop()
        pet.cursor_timer.stop()
        now[0] += 1
        pet._draw_frame()
        app.processEvents()
        assert pet.width() == size + 24
        assert not pet.mask().contains(QPoint(1, 1))
        geometry = pet.library.geometry
        x, y, width, height = geometry["collar_rect"]
        collar = QPoint(round(pet._padding + size * (x + width / 2)),
                        round(pet._padding + size * (y + height / 2)))
        assert pet._is_collar(collar)
        assert pet.mask().contains(collar)
        # Clicks still open the existing panel; no replacement window/application.
        QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=collar)
        app.processEvents()
        assert pet.panel.isVisible()
        pet.panel.close()
        assert not pet.panel.isVisible()
        assert pet.settings.size == size
    finally:
        pet.shutdown()
        pet.panel.deleteLater()
        pet.deleteLater()
        app.processEvents()
