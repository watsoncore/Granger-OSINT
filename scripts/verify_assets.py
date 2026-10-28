"""Validate bundled transparent, genuinely animated character resources."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "grangerpet" / "assets"
REQUIRED = ("idle", "hover", "happy", "thinking", "working", "walk", "error")


def verify() -> dict[str, int]:
    manifest_path = ASSETS / "animations.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    states = manifest.get("states", manifest.get("animations", manifest))
    if not isinstance(states, dict):
        raise ValueError("Animation manifest must contain a state dictionary")
    counts: dict[str, int] = {}
    for state in REQUIRED:
        spec = states.get(state)
        if not isinstance(spec, dict):
            raise ValueError(f"Missing animation state: {state}")
        relative = spec.get("sheet", spec.get("file", spec.get("path", f"{state}.png")))
        path = ASSETS / relative
        if not path.is_file():
            raise ValueError(f"Missing spritesheet for {state}: {path}")
        image = QImage(str(path))
        if image.isNull() or not image.hasAlphaChannel():
            raise ValueError(f"Invalid or opaque spritesheet: {path}")
        size = spec.get("frame_size", spec.get("frameSize", manifest.get("frame_size", 256)))
        width = int(spec.get("frame_width", spec.get("frameWidth", size)))
        height = int(spec.get("frame_height", spec.get("frameHeight", size)))
        columns = int(spec.get("columns", image.width() // width))
        raw_count = spec.get("frames", spec.get("frame_count", spec.get("frameCount", 0)))
        count = len(raw_count) if isinstance(raw_count, list) else int(raw_count)
        if count < 2 or columns < 1 or width < 1 or height < 1:
            raise ValueError(f"Invalid frame geometry for {state}")
        if columns * width > image.width() or ((count + columns - 1) // columns) * height > image.height():
            raise ValueError(f"Frames exceed sheet bounds for {state}")
        hashes: set[str] = set()
        transparent = False
        opaque = False
        for index in range(count):
            frame = image.copy((index % columns) * width, (index // columns) * height, width, height)
            rgba = frame.convertToFormat(QImage.Format.Format_RGBA8888)
            data = bytes(rgba.constBits())
            hashes.add(hashlib.sha256(data).hexdigest())
            alpha = data[3::4]
            transparent = transparent or any(value == 0 for value in alpha)
            opaque = opaque or any(value > 128 for value in alpha)
        if len(hashes) < 2:
            raise ValueError(f"Animation has no changing frames: {state}")
        if not transparent or not opaque:
            raise ValueError(f"Animation lacks a visible transparent cutout: {state}")
        counts[state] = count
    return counts


if __name__ == "__main__":
    try:
        for state, count in verify().items():
            print(f"{state}: {count} valid transparent frames")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Asset validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
