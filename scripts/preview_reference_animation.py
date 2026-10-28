"""Optional GIF QA preview of the actual shipped frames at 195px and 100px.

Requires Pillow only in the interpreter used to run this diagnostic script;
Pillow is not a GrangerPet runtime or build dependency. No artwork is changed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "grangerpet/assets"
OUTPUT = ROOT / "output/reference-qa"
STATES = ("idle", "hover", "happy", "thinking", "working", "walk", "error")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ASSETS / "animations.json").read_text(encoding="utf-8"))
    background = (37, 43, 53)
    font = ImageFont.truetype(str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts/segoeui.ttf"), 14)
    frames, durations = [], []
    for state in STATES:
        spec = manifest["states"][state]
        sheet = Image.open(ASSETS / spec["sheet"]).convert("RGBA")
        width, height, columns = spec["frame_width"], spec["frame_height"], spec["columns"]
        fps = spec.get("source_fps", 12)
        for index in range(spec["frames"]):
            left, top = index % columns * width, index // columns * height
            sprite = sheet.crop((left, top, left + width, top + height))
            canvas = Image.new("RGB", (448, 260), background)
            draw = ImageDraw.Draw(canvas)
            draw.line((224, 14, 224, 214), fill=(61, 72, 88))
            for column, size in enumerate((195, 100)):
                scaled = sprite.resize((size, size), Image.Resampling.LANCZOS)
                x, y = column * 224 + (224 - size) // 2, 218 - size
                canvas.paste(scaled, (x, y), scaled)
                label = f"{state} / {size}px"
                length = draw.textlength(label, font=font)
                draw.text((column * 224 + (224 - length) / 2, 232), label, font=font, fill=(235, 239, 245))
            frames.append(canvas)
            # GIF delays have 10ms precision. Distribute rounding rather than
            # making every 12fps source frame last80ms and speeding it up.
            durations.append(round((index + 1) * 100 / fps) * 10 - round(index * 100 / fps) * 10)
    samples = Image.new("RGB", (448 * len(STATES), 260), background)
    offset = 0
    for number, state in enumerate(STATES):
        count = manifest["states"][state]["frames"]
        samples.paste(frames[offset + count // 3], (number * 448, 0))
        offset += count
    palette = samples.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    path = OUTPUT / "animated-preview.gif"
    indexed[0].save(path, save_all=True, append_images=indexed[1:], loop=0, duration=durations, disposal=2, optimize=True)
    print(json.dumps({"path": str(path), "frames": len(frames), "duration_ms": sum(durations), "size_bytes": path.stat().st_size}))


if __name__ == "__main__":
    main()
