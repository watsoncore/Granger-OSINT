"""Cached sprite sequences and a small deterministic animation state machine."""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from .config import resource_path

STATES = ("idle", "hover", "happy", "thinking", "working", "walk", "error")


class SpriteLibrary:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or resource_path("assets")
        manifest = json.loads((self.directory / "animations.json").read_text(encoding="utf-8"))
        self.revision = manifest.get("version", 1)
        self.geometry = manifest.get("geometry", {})
        self.features = manifest.get("features", {})
        self.specs = manifest["states"]
        self.frames: dict[str, list[QImage]] = {}
        for state in STATES:
            spec = self.specs[state]
            sheet = QImage(str(self.directory / spec["sheet"]))
            if sheet.isNull():
                raise ValueError(f"Не удалось прочитать анимацию {state}")
            width = spec.get("frame_width", 256)
            height = spec.get("frame_height", 256)
            columns = spec["columns"]
            count = spec["frames"]
            self.frames[state] = [sheet.copy(i % columns * width, i // columns * height, width, height)
                                  for i in range(count)]
        self.scenes=None
        if (self.directory/'scenes/provenance.json').is_file():
            from .scene_art import SceneArtLibrary
            self.scenes=SceneArtLibrary(self.directory/'scenes')


class AnimationController(QObject):
    state_changed = Signal(str)

    def __init__(self, library: SpriteLibrary, parent=None):
        super().__init__(parent)
        self.library = library
        self.state = "idle"
        self.frame = 0
        self.started = time.monotonic()
        self.one_shot = False
        self.completed = False

    def set_state(self, state: str, *, restart=False):
        if state not in STATES or (state == self.state and not restart):
            return
        self.state, self.frame = state, 0
        self.started = time.monotonic()
        self.one_shot = state in ("happy", "error")
        self.completed = False
        self.state_changed.emit(state)

    def advance(self):
        count = len(self.library.frames[self.state])
        source_fps = self.library.specs[self.state].get("source_fps", 12)
        position = int(max(0, time.monotonic() - self.started) * source_fps)
        self.completed = self.one_shot and position >= count
        self.frame = min(position, count - 1) if self.one_shot else position % count

    @property
    def image(self):
        return self.library.frames[self.state][self.frame]
