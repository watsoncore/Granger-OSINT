"""Validated, encrypted local attachments, EXIF and actual Tesseract TSV OCR.

Pillow handles JPEG/PNG/WebP decoding. Storage encryption is injected by the
application's unlocked vault; there is deliberately no plaintext fallback.
The original bytes remain encrypted and are never sent to an external service.
"""
from __future__ import annotations

import base64
from collections import OrderedDict
from copy import deepcopy
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import warnings

from PIL import ExifTags, Image, ImageOps, ImageStat, UnidentifiedImageError

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_IMAGE_EDGE = 16_384
_ID = re.compile(r"img_[0-9a-f]{64}\Z")
_MIMES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_SELECTED_EXIF = {"Make", "Model", "Software", "DateTime", "DateTimeOriginal", "DateTimeDigitized", "Orientation", "ExposureTime", "FNumber", "ISOSpeedRatings", "LensModel", "Copyright", "Artist", "ImageDescription"}


class GeointError(ValueError):
    """A stable error code with a safe, user-facing message (no local path)."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _cancelled(event):
    if event is not None and event.is_set():
        raise GeointError("cancelled", "Анализ изображения отменён.")


def _signature(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    raise GeointError("unsupported_format", "Поддерживаются настоящие JPEG, PNG и WebP; расширение файла не определяет его формат.")


def _decode(data, cancel_event=None):
    _cancelled(cancel_event)
    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise GeointError("file_size_limit", "Изображение пустое или превышает ограничение 20 МиБ.")
    fmt = _signature(data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[fmt]) as probe:
                width, height = probe.size
                if width < 1 or height < 1 or width > MAX_IMAGE_EDGE or height > MAX_IMAGE_EDGE or width * height > MAX_IMAGE_PIXELS:
                    raise GeointError("pixel_limit", "Изображение превышает предел 24 млн пикселей или 16384 пикселя по стороне.")
                if getattr(probe, "n_frames", 1) != 1:
                    raise GeointError("animated_image", "Для анализа выберите отдельный статичный кадр изображения.")
                probe.verify()
            _cancelled(cancel_event)
            image = Image.open(io.BytesIO(data), formats=[fmt])
            image.load()
            return image
    except GeointError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise GeointError("invalid_image", "Файл повреждён или не может быть безопасно декодирован.") from exc


def _filename(value):
    # Names are labels only. Both platform separators and control chars are removed.
    name = str(value or "image").replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[\x00-\x1f\x7f]", "", name)[:180] or "image"


def _safe_text(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, (str, int, float)):
        return str(value).replace("\x00", "").strip()[:1000]
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def _coordinate(values, reference, latitude):
    if isinstance(reference, bytes):
        reference = reference.decode("ascii", "ignore")
    refs = ("N", "S") if latitude else ("E", "W")
    if reference not in refs or not isinstance(values, (tuple, list)) or len(values) != 3:
        raise ValueError("invalid GPS representation")
    d, m, s = map(float, values)
    if not all(math.isfinite(v) for v in (d, m, s)) or not 0 <= d <= (90 if latitude else 180) or not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError("invalid GPS range")
    value = d + m / 60 + s / 3600
    if value > (90 if latitude else 180):
        raise ValueError("invalid GPS range")
    return -value if reference in ("S", "W") else value


def _metadata(image):
    result = {"status": "no_gps_metadata", "exif": {}, "gps": None,
              "limitations": ["Метаданные могут быть изменены; GPS EXIF не доказывает место съёмки."]}
    try:
        with warnings.catch_warnings(record=True) as observed:
            exif = image.getexif()
            values = dict(exif)
            try:
                values.update(exif.get_ifd(ExifTags.IFD.Exif))
            except (KeyError, ValueError, TypeError, OSError, SyntaxError):
                result["limitations"].append("Часть EXIF-полей повреждена или не поддерживается.")
            for key, value in values.items():
                name = ExifTags.TAGS.get(key, str(key))
                if name in _SELECTED_EXIF:
                    safe = _safe_text(value)
                    if safe is not None:
                        result["exif"][name] = safe
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
            if observed:
                result["limitations"].append("Декодер сообщил о некорректных метаданных.")
        if gps:
            try:
                lat = _coordinate(gps.get(2), gps.get(1), True)
                lon = _coordinate(gps.get(4), gps.get(3), False)
                position = {"latitude": lat, "longitude": lon, "basis": "EXIF GPS", "authenticity_verified": False}
                if 6 in gps:
                    altitude = float(gps[6])
                    if math.isfinite(altitude):
                        position["altitude_m"] = -altitude if gps.get(5) in (1, b"\x01") else altitude
                result.update(status="gps_metadata_present", gps=position)
            except (TypeError, ValueError, ZeroDivisionError, OverflowError):
                result.update(status="invalid_gps_metadata")
                result["limitations"].append("GPS-поля присутствуют, но их значения некорректны.")
        result["icc_profile_present"] = bool(image.info.get("icc_profile"))
        # Deliberately bound text chunks. No binary maker notes or embedded thumbnails.
        result["text_metadata"] = {str(k)[:80]: str(v)[:1000] for k, v in list(image.info.items())[:30]
                                   if isinstance(v, str) and k not in ("exif", "icc_profile")}
    except (ValueError, TypeError, OSError, SyntaxError, KeyError, ZeroDivisionError):
        result.update(status="metadata_error")
        result["limitations"].append("Метаданные повреждены; координаты не установлены.")
    return result


def _dhash(image):
    sample = ImageOps.exif_transpose(image).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    values = list(sample.get_flattened_data())
    number = 0
    for y in range(8):
        for x in range(8):
            number = (number << 1) | (values[y * 9 + x] > values[y * 9 + x + 1])
    return f"{number:016x}"


def _preview(image, max_size=400, quality=75):
    preview = ImageOps.exif_transpose(image).convert("RGB")
    preview.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    preview.save(buffer, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".attachment-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class AttachmentStore:
    def __init__(self, root, *, seal, open_sealed, tesseract=None, tessdata=None):
        if not callable(seal) or not callable(open_sealed):
            raise ValueError("An unlocked encrypted storage provider is required")
        self.root = Path(root)
        self._seal, self._open = seal, open_sealed
        self.tesseract = str(tesseract) if tesseract else None
        self.tessdata = str(tessdata) if tessdata else None
        self._analysis = OrderedDict()
        self._lock = threading.RLock()

    def clear_sensitive_cache(self):
        """Drop decrypted metadata when the owner locks the vault."""
        with self._lock:
            self._analysis.clear()

    def _path(self, identifier):
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise GeointError("invalid_attachment_id", "Некорректный идентификатор вложения.")
        path = self.root / (identifier + ".gpi")
        if path.is_symlink():
            raise GeointError("unsafe_attachment", "Символические ссылки не используются как вложения.")
        return path

    def import_bytes(self, data, filename="image", cancel_event=None):
        image = _decode(data, cancel_event)
        try:
            digest = hashlib.sha256(data).hexdigest()
            identifier = "img_" + digest
            path = self._path(identifier)
            duplicate = path.exists()
            record = {"id": identifier, "name": _filename(filename), "mime": _MIMES[image.format],
                      "format": image.format, "bytes": len(data), "width": image.width,
                      "height": image.height, "sha256": digest, "preview": _preview(image), "dhash": _dhash(image)}
            _cancelled(cancel_event)
            if not duplicate:
                metadata = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                sealed = self._seal(struct.pack(">I", len(metadata)) + metadata + data)
                _cancelled(cancel_event)
                try:
                    _atomic_write(path, sealed)
                except OSError as exc:
                    raise GeointError("storage_write_failed", "Не удалось атомарно сохранить защищённое вложение.") from exc
            else:
                # Re-validate existing ciphertext rather than hiding a corrupt record.
                record, _ = self._read(identifier)
            return {**record, "duplicate": duplicate}
        finally:
            image.close()

    def _read(self, identifier):
        path = self._path(identifier)
        try:
            if path.stat().st_size > MAX_IMAGE_BYTES * 2:
                raise GeointError("invalid_attachment", "Сохранённое вложение имеет некорректный размер.")
            packed = self._open(path.read_bytes())
            if len(packed) < 4:
                raise ValueError("short record")
            size = struct.unpack(">I", packed[:4])[0]
            if not 2 <= size <= 300_000 or 4 + size >= len(packed):
                raise ValueError("bad header")
            metadata = json.loads(packed[4:4 + size].decode("utf-8"))
            data = packed[4 + size:]
            if metadata.get("id") != identifier or "img_" + hashlib.sha256(data).hexdigest() != identifier:
                raise ValueError("digest mismatch")
            return metadata, data
        except GeointError:
            raise
        except FileNotFoundError as exc:
            raise GeointError("attachment_missing", "Локальное вложение не найдено в этом профиле.") from exc
        except Exception as exc:
            # Vault-lock exceptions should retain their type for the application's unlock UI.
            if type(exc).__name__ in ("VaultLocked", "VaultLockedError", "CredentialError"):
                raise
            raise GeointError("attachment_integrity", "Не удалось проверить целостность защищённого вложения.") from exc

    def get(self, identifier):
        self._path(identifier)
        # Always consult encryption provider after a vault lock; never serve plaintext
        # cached data without checking that the current user can decrypt the record.
        record, _ = self._read(identifier)
        return deepcopy(record)

    def read_bytes(self, identifier, cancel_event=None):
        """Decrypt one validated attachment for a caller-authorized local worker."""
        _cancelled(cancel_event)
        _, data = self._read(identifier)
        _cancelled(cancel_event)
        return data

    def small_preview(self, identifier, cancel_event=None):
        data=self.read_bytes(identifier,cancel_event)
        image=_decode(data,cancel_event)
        try:return _preview(image,max_size=128,quality=50)
        finally:image.close()

    def analyze(self, identifier, cancel_event=None):
        started = time.monotonic()
        _cancelled(cancel_event)
        record, data = self._read(identifier)
        _cancelled(cancel_event)
        with self._lock:
            if identifier in self._analysis:
                cached = deepcopy(self._analysis[identifier])
                self._analysis.move_to_end(identifier)
                cached.update(cached=True, duration_ms=round((time.monotonic() - started) * 1000, 2))
                return cached
        image = _decode(data, cancel_event)
        try:
            metadata = _metadata(image)
            sample = image.convert("RGB").resize((64, 64))
            stats = ImageStat.Stat(sample)
            _cancelled(cancel_event)
            result = {"tool": "image_metadata", "status": "completed", "attachment_id": identifier,
                    "image": {k: record[k] for k in ("id", "name", "format", "mime", "bytes", "width", "height", "sha256")},
                    "metadata": metadata,
                    "visual_features": {"dhash": record["dhash"], "dhash_bits": 64,
                                        "mean_rgb": [round(v, 2) for v in stats.mean],
                                        "semantic_geolocation": "unsupported_capability"},
                    "facts": ["Размеры и формат получены локальным декодированием исходного файла.",
                              "SHA-256 вычислен по исходным байтам изображения."],
                    "limitations": metadata["limitations"] + ["Цвет и perceptual hash не определяют город, страну или здание."],
                    "duration_ms": round((time.monotonic() - started) * 1000, 2), "cached": False}
            with self._lock:
                self._analysis[identifier] = deepcopy(result)
                while len(self._analysis) > 16:
                    self._analysis.popitem(last=False)
            return result
        finally:
            image.close()

    def compare(self, identifier, cancel_event=None, max_candidates=200):
        record, _ = self._read(identifier)
        _cancelled(cancel_event)
        candidates, scanned = [], 0
        for path in self.root.glob("img_*.gpi"):
            _cancelled(cancel_event)
            if scanned >= max(1, min(1000, int(max_candidates))):
                break
            if path.stem == identifier or not _ID.fullmatch(path.stem):
                continue
            scanned += 1
            try:
                other, _ = self._read(path.stem)
                distance = (int(record["dhash"], 16) ^ int(other["dhash"], 16)).bit_count()
                if distance <= 10:
                    candidates.append({"attachment_id": other["id"], "name": other["name"],
                                       "hamming_distance": distance, "exact_bytes": other["sha256"] == record["sha256"]})
            except (GeointError, ValueError, KeyError):
                continue
        return {"tool": "image_compare", "status": "completed", "attachment_id": identifier,
                "matches": sorted(candidates, key=lambda item: item["hamming_distance"])[:30], "scanned": scanned,
                "candidate_limit": max(1, min(1000, int(max_candidates))),
                "limitations": ["Сравниваются только ранее загруженные локальные изображения.",
                                "Близкий dHash означает сходство структуры, а не доказанное совпадение объекта."]}

    def ocr(self, identifier, languages=("rus", "eng"), cancel_event=None, timeout=30):
        record, data = self._read(identifier)
        _cancelled(cancel_event)
        executable, tessdata = self._ocr_paths()
        if executable is None:
            return {"tool": "image_ocr", "status": "not_installed", "error_code": "ocr_backend_missing",
                    "attachment_id": identifier, "segments": [], "text": "",
                    "limitations": ["Для OCR нужен локальный Tesseract и модели rus/eng. Распознавание не выполнялось."]}
        if not isinstance(languages, (list, tuple)) or not languages or any(v not in ("rus", "eng") for v in languages):
            raise GeointError("invalid_language", "OCR поддерживает только выбранные модели rus и eng.")
        requested_languages = tuple(dict.fromkeys(languages))
        languages = tuple(lang for lang in requested_languages if tessdata is None or (Path(tessdata) / (lang + ".traineddata")).is_file())
        if not languages:
            return {"tool": "image_ocr", "status": "configuration_required", "error_code": "ocr_language_missing",
                    "attachment_id": identifier, "segments": [], "text": "", "languages": [],
                    "limitations": ["Нет ни одной выбранной языковой модели Tesseract; OCR не запускался."]}
        image = _decode(data, cancel_event)
        try:
            oriented = ImageOps.exif_transpose(image).convert("RGB")
            source_width, source_height = oriented.size
            oriented.thumbnail((3000, 3000), Image.Resampling.LANCZOS)
            oriented = ImageOps.autocontrast(ImageOps.grayscale(oriented))
            buffer = io.BytesIO()
            # Strip metadata before OCR. Input and TSV travel via anonymous pipes;
            # there are no decrypted temporary pictures or result files.
            oriented.save(buffer, "PNG")
            command = [str(executable), "stdin", "stdout", "--oem", "1", "--psm", "6", "-l", "+".join(languages)]
            if tessdata:
                command += ["--tessdata-dir", str(tessdata)]
            command += ["tsv"]
            environment = {**os.environ, "OMP_THREAD_LIMIT": "1"}
            if sys.platform == "win32":
                # The portable engine resolves only its own DLLs and Windows DLLs.
                environment["PATH"] = os.pathsep.join([str(Path(executable).parent),
                                                       str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")])
            kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                      "cwd": str(Path(executable).parent), "env": environment}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            _cancelled(cancel_event)
            begin = time.monotonic()
            process = subprocess.Popen(command, **kwargs)
            pending = buffer.getvalue()
            try:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        process.kill()
                        process.communicate()
                        raise GeointError("cancelled", "Распознавание текста отменено.")
                    if time.monotonic() - begin > max(1, min(90, float(timeout))):
                        process.kill()
                        process.communicate()
                        raise GeointError("timeout", "Превышено время локального распознавания текста.")
                    try:
                        output, _stderr = process.communicate(input=pending, timeout=.1)
                        break
                    except subprocess.TimeoutExpired:
                        pending = None
                if process.returncode != 0:
                    return {"tool": "image_ocr", "status": "failed", "error_code": "ocr_process_failed",
                            "attachment_id": identifier, "segments": [], "text": "",
                            "limitations": ["Tesseract не завершил распознавание; проверьте локальную установку и модели."]}
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            if len(output) > 4 * 1024 * 1024:
                raise GeointError("ocr_output_limit", "Результат OCR превышает безопасный размер.")
            scale_x, scale_y = source_width / oriented.width, source_height / oriented.height
            segments = parse_tsv(output.decode("utf-8", "replace"), scale_x, scale_y)
            confidence = sum(segment["confidence"] * len(segment["text"]) for segment in segments) / max(1, sum(len(segment["text"]) for segment in segments))
            low_confidence = not segments or confidence < .6
            limitations = ["OCR может ошибаться; confidence — оценка распознавателя, а не подтверждение содержания."]
            if requested_languages != languages:
                limitations.append("Недоступные языковые пакеты исключены; использованы только установленные модели: " + ", ".join(languages) + ".")
            if low_confidence:
                limitations.append("Низкая уверенность OCR. Исходные строки сохранены как неподтверждённые; попробуйте более чёткое изображение или другой язык распознавания.")
            return {"tool": "image_ocr", "status": "low_confidence" if low_confidence else "completed", "attachment_id": identifier,
                    "languages": list(languages), "segments": segments,
                    "requested_languages": list(requested_languages), "confidence": round(confidence, 4),
                    "orientation": {"method": "EXIF transpose", "automatic_rotation_without_exif": False},
                    "preprocessing": ["EXIF orientation", "bounded resize3000px", "grayscale", "autocontrast"],
                    "text": " ".join(segment["text"] for segment in segments)[:20000],
                    "coordinate_space": "exif_oriented_original_pixels", "width": source_width, "height": source_height,
                    "duration_ms": round((time.monotonic() - begin) * 1000, 2),
                    "limitations": limitations}
        except OSError as exc:
            raise GeointError("ocr_launch_failed", "Не удалось запустить локальный Tesseract.") from exc
        finally:
            image.close()

    def _ocr_paths(self):
        executable = Path(self.tesseract) if self.tesseract else None
        data = Path(self.tessdata) if self.tessdata else None
        if executable is None:
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
            bundled = base / "resources" / "ocr" / "tesseract.exe"
            if bundled.is_file():
                executable, data = bundled, bundled.parent / "tessdata"
            elif shutil.which("tesseract"):
                executable = Path(shutil.which("tesseract"))
        if executable is None or not executable.is_file():
            return None, None
        return executable, data


def parse_tsv(text, scale_x=1, scale_y=1):
    """Normalize actual word rows; malformed rows are omitted, never guessed."""
    segments = []
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        try:
            word = (row.get("text") or "").strip()[:300]
            confidence = float(row["conf"])
            x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
            if row.get("level") != "5" or not word or not math.isfinite(confidence) or not 0 <= confidence <= 100 or min(x, y, w, h) < 0 or w == 0 or h == 0:
                continue
            segments.append({"text": word, "bbox": [round(x * scale_x), round(y * scale_y),
                                                     round((x + w) * scale_x), round((y + h) * scale_y)],
                             "confidence": round(confidence / 100, 4)})
            if len(segments) >= 3000:
                break
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return segments
