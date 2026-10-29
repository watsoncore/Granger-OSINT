from __future__ import annotations

import base64
import io
import os
from pathlib import Path
import struct
import threading
import time
import zlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, ImageDraw, ImageFont
import pytest

from grangerpet.geoint.images import AttachmentStore, GeointError, MAX_IMAGE_BYTES, parse_tsv

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(tmp_path):
    key = AESGCM.generate_key(bit_length=256)
    cipher = AESGCM(key)

    def seal(data):
        nonce = os.urandom(12)
        return nonce + cipher.encrypt(nonce, data, b"geoint-test")

    def unseal(data):
        return cipher.decrypt(data[:12], data[12:], b"geoint-test")

    return AttachmentStore(tmp_path / "attachments", seal=seal, open_sealed=unseal)


def image_bytes(fmt="PNG", exif=None, color="white"):
    image = Image.new("RGB", (320, 240), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 30, 100, 200), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, fmt, **({"exif": exif} if exif else {}))
    return buffer.getvalue()


@pytest.mark.parametrize("fmt,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_validated_formats_preview_and_encrypted_restart(store, fmt, mime):
    raw = image_bytes(fmt)
    imported = store.import_bytes(raw, "../../Русский пример.jpg")
    assert imported["mime"] == mime
    assert imported["name"] == "Русский пример.jpg"
    assert imported["width"] == 320 and imported["height"] == 240
    preview = base64.b64decode(imported["preview"].split(",", 1)[1])
    assert Image.open(io.BytesIO(preview)).size == (320, 240)
    sealed = next(store.root.iterdir()).read_bytes()
    assert raw not in sealed and "Русский".encode("utf-8") not in sealed
    restarted = AttachmentStore(store.root, seal=store._seal, open_sealed=store._open)
    assert restarted.get(imported["id"])["sha256"] == imported["sha256"]
    assert restarted.analyze(imported["id"])["metadata"]["status"] == "no_gps_metadata"


def test_real_gps_exif_and_editability_warning(store):
    exif = Image.Exif()
    exif[271] = "Test Camera"
    exif[272] = "Fixture"
    exif[34853] = {1: "N", 2: (51.0, 30.0, 0.0), 3: "W", 4: (0.0, 7.0, 30.0), 5: 0, 6: 25.0}
    result = store.analyze(store.import_bytes(image_bytes("JPEG", exif), "gps.jpg")["id"])
    assert result["metadata"]["status"] == "gps_metadata_present"
    assert result["metadata"]["gps"]["latitude"] == pytest.approx(51.5)
    assert result["metadata"]["gps"]["longitude"] == pytest.approx(-.125)
    assert result["metadata"]["gps"]["altitude_m"] == 25
    assert result["metadata"]["gps"]["authenticity_verified"] is False
    assert result["metadata"]["exif"]["Make"] == "Test Camera"
    assert result["visual_features"]["semantic_geolocation"] == "unsupported_capability"


def test_invalid_gps_is_never_zero_coordinate(store):
    exif = Image.Exif()
    exif[34853] = {1: "N", 2: (91.0, 0.0, 0.0), 3: "E", 4: (10.0, 0.0, 0.0)}
    result = store.analyze(store.import_bytes(image_bytes("JPEG", exif), "invalid.jpg")["id"])
    assert result["metadata"]["status"] == "invalid_gps_metadata"
    assert result["metadata"]["gps"] is None


@pytest.mark.parametrize("data", [b"<svg xmlns='x'/>", b"fake.jpg", b"\x89PNG\r\n\x1a\nBROKEN", b"\xff\xd8\xffgarbage"])
def test_corrupt_and_unsupported_files_never_create_attachments(store, data):
    with pytest.raises(GeointError):
        store.import_bytes(data, "trusted.png")
    assert not store.root.exists()


def test_pixel_limit_before_decode(store):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    oversized = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 6000, 5000, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")
    with pytest.raises(GeointError, match="24 млн") as error:
        store.import_bytes(oversized, "large.png")
    assert error.value.code == "pixel_limit"


def test_file_limit_and_identifier_path_traversal(store):
    with pytest.raises(GeointError) as error:
        store.import_bytes(b"x" * (MAX_IMAGE_BYTES + 1), "large.jpg")
    assert error.value.code == "file_size_limit"
    with pytest.raises(GeointError) as error:
        store.get("../../secret.env")
    assert error.value.code == "invalid_attachment_id"


def test_repeated_import_is_exact_deduplication_and_detects_corruption(store):
    raw = image_bytes()
    one = store.import_bytes(raw, "one.png")
    two = store.import_bytes(raw, "two.png")
    assert one["id"] == two["id"] and two["duplicate"] is True
    assert len(list(store.root.iterdir())) == 1
    path = next(store.root.iterdir())
    path.write_bytes(path.read_bytes()[:-1] + bytes([path.read_bytes()[-1] ^ 1]))
    with pytest.raises(GeointError) as error:
        store.import_bytes(raw, "again.png")
    assert error.value.code == "attachment_integrity"


def test_compare_uses_actual_local_perceptual_hash(store):
    one = store.import_bytes(image_bytes("PNG"), "one.png")
    two = store.import_bytes(image_bytes("JPEG"), "compressed.jpg")
    result = store.compare(one["id"])
    assert result["scanned"] == 1
    assert result["matches"][0]["attachment_id"] == two["id"]
    assert result["matches"][0]["hamming_distance"] <= 10
    assert result["matches"][0]["exact_bytes"] is False


def test_cancelled_import_and_analysis(store):
    event = threading.Event()
    event.set()
    with pytest.raises(GeointError) as error:
        store.import_bytes(image_bytes(), "cancelled.png", event)
    assert error.value.code == "cancelled" and not store.root.exists()
    event.clear()
    identifier = store.import_bytes(image_bytes(), "image.png")["id"]
    event.set()
    with pytest.raises(GeointError) as error:
        store.analyze(identifier, event)
    assert error.value.code == "cancelled"


def test_vault_lock_does_not_serve_cached_preview(store):
    identifier = store.import_bytes(image_bytes(), "image.png")["id"]
    def locked(_):
        raise ValueError("locked")
    store._open = locked
    with pytest.raises(GeointError):
        store.get(identifier)


def test_repeated_analysis_does_not_decode_again_and_cache_requires_integrity(store, monkeypatch):
    import grangerpet.geoint.images as module
    identifier = store.import_bytes(image_bytes(), "image.png")["id"]
    assert store.analyze(identifier)["cached"] is False
    def unexpected_decode(*args, **kwargs):
        raise AssertionError("Immutable image was decoded twice")
    monkeypatch.setattr(module, "_decode", unexpected_decode)
    assert store.analyze(identifier)["cached"] is True
    next(store.root.iterdir()).write_bytes(b"corrupt")
    with pytest.raises(GeointError):
        store.analyze(identifier)


def test_interrupted_write_does_not_publish_plaintext_or_partial_record(store, monkeypatch):
    import grangerpet.geoint.images as module
    def fail(*args):
        raise OSError("test write interruption with private path")
    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(GeointError) as error:
        store.import_bytes(image_bytes(), "not-published.png")
    assert error.value.code == "storage_write_failed" and "private" not in str(error.value)
    assert list(store.root.iterdir()) == []


def test_missing_ocr_is_explicit_and_never_claimed_completed(store):
    identifier = store.import_bytes(image_bytes(), "image.png")["id"]
    store.tesseract = str(store.root / "nonexistent.exe")
    result = store.ocr(identifier)
    assert result["status"] == "not_installed" and result["segments"] == []
    assert result["error_code"] == "ocr_backend_missing"


def test_parse_actual_tsv_schema_bounds_and_utf8():
    tsv = "level\tleft\ttop\twidth\theight\tconf\ttext\n5\t10\t20\t30\t40\t92.5\tМосква\n5\t-1\t0\t10\t10\t90\tinvalid\n5\t0\t0\t1\t1\tnan\tbad\n1\t0\t0\t100\t100\t-1\t\n"
    assert parse_tsv(tsv, 2, 3) == [{"text": "Москва", "bbox": [20, 60, 80, 180], "confidence": .925}]


def text_fixture(text):
    image = Image.new("RGB", (1800, 250), "white")
    font = ImageFont.truetype(str(ROOT / "frontend/public/fonts/Manrope-Variable.ttf"), 70)
    ImageDraw.Draw(image).text((40, 65), text, font=font, fill="black")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


@pytest.mark.parametrize("text,languages,expected", [("LONDON BRIDGE", ("eng",), "LONDON"), ("МОСКВА УЛИЦА МИРА", ("rus",), "МОСКВА")])
def test_real_local_tesseract_english_and_russian_pixels(store, text, languages, expected):
    if not store._ocr_paths()[0]:
        pytest.skip("Real Tesseract runtime not installed; no simulated OCR success")
    identifier = store.import_bytes(text_fixture(text), "fixture.png")["id"]
    result = store.ocr(identifier, languages)
    assert result["status"] == "completed", result
    assert expected in result["text"].upper(), result
    assert all(len(item["bbox"]) == 4 and 0 <= item["confidence"] <= 1 for item in result["segments"])
    assert result["coordinate_space"] == "exif_oriented_original_pixels"


def test_damaged_exif_does_not_invent_gps(store):
    result = store.analyze(store.import_bytes(image_bytes("JPEG", b"Exif\x00\x00BROKEN"), "bad-exif.jpg")["id"])
    assert result["metadata"]["gps"] is None
    assert result["metadata"]["status"] in ("metadata_error", "no_gps_metadata")


def dense_text_fixture():
    image = Image.new("RGB", (3000, 3000), "white")
    font = ImageFont.truetype(str(ROOT / "frontend/public/fonts/Manrope-Variable.ttf"), 35)
    draw = ImageDraw.Draw(image)
    for top in range(10, 2960, 45):
        draw.text((15, top), "LONDON BRIDGE PUBLIC TEST TEXT " * 3, font=font, fill="black")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


@pytest.mark.parametrize("mode", ["cancel", "timeout"])
def test_real_ocr_cancel_timeout_terminate_owned_process(store, monkeypatch, mode):
    if not store._ocr_paths()[0]:
        pytest.skip("Real Tesseract runtime unavailable; no simulated execution")
    import grangerpet.geoint.images as module
    original = module.subprocess.Popen
    processes = []
    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(module.subprocess, "Popen", capture)
    identifier = store.import_bytes(dense_text_fixture(), "dense.png")["id"]
    event = threading.Event()
    timer = threading.Timer(.1, event.set) if mode == "cancel" else None
    if timer:
        timer.start()
    try:
        with pytest.raises(GeointError) as error:
            store.ocr(identifier, ("eng",), event, timeout=1)
        assert error.value.code == ("cancelled" if mode == "cancel" else "timeout")
        assert all(process.poll() is not None for process in processes)
        if mode == "timeout":
            assert len(processes) == 1
    finally:
        if timer:
            timer.cancel()
