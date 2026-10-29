"""Actual local-pixel GEOINT smoke with generated, non-personal fixtures.

Does not contact external services. An ephemeral test key encrypts attachments;
no real profile, user photographs or credentials are read or modified.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, ImageDraw, ImageFont

from grangerpet.geoint import AttachmentStore, GeointError


def execute(output):
    output.mkdir(parents=True, exist_ok=True)
    key = AESGCM.generate_key(bit_length=256)
    cipher = AESGCM(key)
    def seal(raw):
        nonce = os.urandom(12)
        return nonce + cipher.encrypt(nonce, raw, b"qa-geoint-fixture")
    def unseal(raw):
        return cipher.decrypt(raw[:12], raw[12:], b"qa-geoint-fixture")
    store = AttachmentStore(output / ("encrypted-fixtures-" + uuid.uuid4().hex), seal=seal, open_sealed=unseal)
    font = ImageFont.truetype(str(ROOT / "frontend/public/fonts/Manrope-Variable.ttf"), 70)
    results, checks = [], []
    for label, text, language, expected in [("english", "LONDON BRIDGE", "eng", "LONDON"), ("russian", "МОСКВА УЛИЦА МИРА", "rus", "МОСКВА")]:
        image = Image.new("RGB", (1800, 250), "white")
        ImageDraw.Draw(image).text((40, 65), text, font=font, fill="black")
        raw = io.BytesIO()
        image.save(raw, "PNG")
        started = time.monotonic()
        record = store.import_bytes(raw.getvalue(), label + ".png")
        import_ms = (time.monotonic() - started) * 1000
        result = store.ocr(record["id"], (language,))
        results.append({"fixture": label, "input_sha256": record["sha256"], "import_ms": round(import_ms, 2), "result": result})
        checks.append({"check": label + "_actual_pixel_ocr", "passed": result["status"] == "completed" and expected in result["text"].upper()})
    image = Image.new("RGB", (320, 240), "white")
    exif = Image.Exif()
    exif[271] = "Granger QA synthetic fixture"
    exif[34853] = {1: "N", 2: (51.0, 30.0, 0.0), 3: "W", 4: (0.0, 7.0, 30.0)}
    raw = io.BytesIO()
    image.save(raw, "JPEG", exif=exif)
    imported = store.import_bytes(raw.getvalue(), "known-gps.jpg")
    result = store.analyze(imported["id"])
    results.append({"fixture": "known-gps", "result": result})
    gps = result["metadata"]["gps"]
    checks.append({"check": "actual_exif_gps", "passed": gps["latitude"] == 51.5 and gps["longitude"] == -.125})
    raw = io.BytesIO()
    image.save(raw, "JPEG")
    result = store.analyze(store.import_bytes(raw.getvalue(), "no-gps.jpg")["id"])
    results.append({"fixture": "no-gps", "result": result})
    checks.append({"check": "no_gps_never_fabricates_coordinates", "passed": result["metadata"]["status"] == "no_gps_metadata" and result["metadata"]["gps"] is None})
    duplicate = store.import_bytes(raw.getvalue(), "same-again.jpg")
    checks.append({"check": "exact_duplicate", "passed": duplicate["duplicate"] is True})
    event = threading.Event()
    event.set()
    try:
        store.analyze(duplicate["id"], event)
        checks.append({"check": "cancelled_analysis", "passed": False})
    except GeointError as error:
        checks.append({"check": "cancelled_analysis", "passed": error.code == "cancelled"})
    for label, data in [("unsupported", b"<svg/>"), ("corrupt", b"\x89PNG\r\n\x1a\nBROKEN")]:
        try:
            store.import_bytes(data, label + ".jpg")
            checks.append({"check": label, "passed": False})
        except GeointError as error:
            checks.append({"check": label, "passed": error.code in ("unsupported_format", "invalid_image")})
    report = {"mode": "actual_local_pixels", "external_requests": 0, "real_user_data": False,
              "passed": all(check["passed"] for check in checks), "checks": checks, "executions": results,
              "limits": {"max_bytes": 20 * 1024 * 1024, "max_pixels": 24_000_000},
              "note": "Encrypted fixture key existed in process memory only; restarting this QA does not reuse user data."}
    (output / "local-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "ocr": [result["result"].get("text") for result in results[:2]]}, ensure_ascii=False))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/geoint-engine")
    args = parser.parse_args()
    raise SystemExit(0 if execute(args.output.resolve()) else 1)
