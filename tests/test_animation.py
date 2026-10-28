"""Frame decoding and animation completion without a running desktop."""
import json
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QColor, QImage

from grangerpet.animation import AnimationController, SpriteLibrary, STATES
import grangerpet.animation as animation_module
from grangerpet.config import resource_path


@pytest.fixture
def sprite_library(tmp_path):
    sheet = QImage(64, 64, QImage.Format.Format_ARGB32)
    sheet.fill(0)
    colors = (QColor("#804b32"), QColor("#a06b42"), QColor("#c08b52"))
    for index, color in enumerate(colors):
        for y in range(5, 27):
            for x in range(10, 22):
                sheet.setPixelColor((index % 2) * 32 + x, (index // 2) * 32 + y, color)
    assert sheet.save(str(tmp_path / "sheet.png"))
    spec = {"sheet": "sheet.png", "frame_width": 32, "frame_height": 32, "columns": 2, "frames": 3, "source_fps": 10}
    (tmp_path / "animations.json").write_text(json.dumps({"states": {name: spec for name in STATES}}), encoding="utf-8")
    return SpriteLibrary(tmp_path)


@pytest.fixture
def clock(monkeypatch):
    current = [0.0]
    monkeypatch.setattr(animation_module, "time", SimpleNamespace(monotonic=lambda: current[0]))
    return current


def test_sheet_rows_decode_in_order_and_keep_cutout_alpha(sprite_library):
    frames = sprite_library.frames["idle"]
    assert [frame.pixelColor(15, 15).name() for frame in frames] == ["#804b32", "#a06b42", "#c08b52"]
    assert all(frame.pixelColor(0, 0).alpha() == 0 for frame in frames)
    assert all(frame.width() == frame.height() == 32 for frame in frames)


def test_looping_work_then_success_finishes_once_and_returns_to_idle(sprite_library, clock):
    animation = AnimationController(sprite_library)
    changes = []
    animation.state_changed.connect(changes.append)
    animation.set_state("thinking")
    animation.set_state("working")
    for _ in range(10):
        clock[0] += 0.25
        animation.advance()
        assert not animation.completed
        assert not animation.image.isNull()
    animation.set_state("happy")
    clock[0] += 10.0
    animation.advance()
    assert animation.completed
    assert animation.frame == 2
    animation.set_state("idle")
    assert not animation.completed
    assert changes == ["thinking", "working", "happy", "idle"]


def test_error_can_be_replayed_without_staying_on_completed_frame(sprite_library, clock):
    animation = AnimationController(sprite_library)
    animation.set_state("error")
    clock[0] += 10.0
    animation.advance()
    assert animation.completed
    animation.set_state("error", restart=True)
    assert animation.frame == 0
    assert not animation.completed


def test_shipped_character_has_seven_nonempty_distinct_transparent_sequences():
    directory = resource_path("assets")
    if not (directory / "animations.json").exists():
        pytest.skip("Final generated character assets are not yet present")
    library = SpriteLibrary(directory)
    for name in STATES:
        frames = library.frames[name]
        assert len(frames) >= 2, name
        assert all(not image.isNull() and image.hasAlphaChannel() for image in frames), name
        assert len({bytes(image.constBits()) for image in frames}) >= 2, name
