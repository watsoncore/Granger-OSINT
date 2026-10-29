"""Bounded actual DeepSeek tool calling over generated local image pixels.

Uses only the existing saved credential, never environment/example credentials.
The source image is synthetic and is not uploaded: the model sees an opaque
attachment id and actual local tool observations. Tool scope is metadata/OCR.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image, ImageDraw, ImageFont

from grangerpet.agent import AgentLimits, AgentRunner
from grangerpet.agent_tools import ToolRegistry
from grangerpet.ai import AIError, DeepSeekClient
from grangerpet.ai_keys import DEFAULT_DEEPSEEK_MODEL, resolve_deepseek_key
from grangerpet.config import Settings
from grangerpet.geoint import AttachmentStore


class LocalImageScope(ToolRegistry):
    """Deny every operation outside this explicitly permitted QA task scope."""
    allowed = frozenset(("image_metadata", "image_ocr"))
    def catalog(self, **kwargs):
        return [row for row in super().catalog(**kwargs) if row["name"] in self.allowed]

    def schemas(self, **kwargs):
        return [row for row in super().schemas(**kwargs) if row["function"]["name"] in self.allowed]

    def execute(self, name, *args, **kwargs):
        if name not in self.allowed:
            raise ValueError("Operation outside explicit local image QA scope")
        return super().execute(name, *args, **kwargs)


def run(path):
    if path.exists():
        raise SystemExit("Prior live evidence exists; do not repeat paid calls automatically")
    path.parent.mkdir(parents=True, exist_ok=True)
    key = resolve_deepseek_key()
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(), "mode": "actual_gateway_production_agent_and_local_pixel_tools",
              "mock": False, "image_uploaded": False, "user_photographs_or_history_read": False,
              "gateway": "https://api.aikeysforyou.com/v1", "model": DEFAULT_DEEPSEEK_MODEL,
              "key_available": bool(key), "limits": {"max_steps": 4, "max_tool_calls": 4, "timeout_seconds": 120, "max_tokens": 12000},
              "events": [], "passed": False}
    if not key:
        report.update(status="not_executed_no_saved_key")
    else:
        with tempfile.TemporaryDirectory(prefix="geoint-live-synthetic-", dir=path.parent) as temporary:
            cipher = AESGCM(AESGCM.generate_key(bit_length=256))
            def seal(raw):
                nonce = os.urandom(12)
                return nonce + cipher.encrypt(nonce, raw, b"synthetic-geoint-live")
            def open_sealed(raw):
                return cipher.decrypt(raw[:12], raw[12:], b"synthetic-geoint-live")
            store = AttachmentStore(Path(temporary), seal=seal, open_sealed=open_sealed)
            image = Image.new("RGB", (1800, 250), "white")
            font = ImageFont.truetype(str(ROOT / "frontend/public/fonts/Manrope-Variable.ttf"), 70)
            ImageDraw.Draw(image).text((40, 65), "МОСКВА УЛИЦА МИРА", font=font, fill="black")
            raw = io.BytesIO()
            image.save(raw, "PNG")
            record = store.import_bytes(raw.getvalue(), "synthetic-local-text.png")
            registry = LocalImageScope(Settings(), image_store=store, attachment_ids=[record["id"]], redactions=(key,))
            runner = AgentRunner(DeepSeekClient(key), registry, limits=AgentLimits(max_steps=4, max_tool_calls=4, timeout=120,
                                                                               max_tokens=12000, max_parallel=2))
            goal = ("Проверь выбранное локальное тестовое изображение " + record["id"] +
                    ". Сначала выполни image_metadata и image_ocr, оба по этому attachment_id. "
                    "Пиксели в сообщении не переданы: надпись заранее неизвестна. "
                    "После инструментов кратко процитируй фактически распознанный текст, укажи наличие GPS и ограничения. "
                    "Не определяй место по самой надписи и не утверждай, что прочитала пиксели без инструмента. "
                    "Никаких внешних источников: разрешены только эти две локальные операции.")
            started = time.monotonic()
            try:
                result = runner.run(DEFAULT_DEEPSEEK_MODEL, [{"role": "user", "text": goal}], cancel_event=threading.Event(),
                                    on_event=lambda event: report["events"].append({name: event[name] for name in
                                        ("type", "tool", "status", "step", "count", "code") if name in event}))
                evidence = result.get("evidence", [])
                successful = {row.get("provenance", {}).get("tool") for row in evidence}
                ocr = next((row for row in evidence if row.get("provenance", {}).get("tool") == "image_ocr"), {})
                metadata = next((row for row in evidence if row.get("provenance", {}).get("tool") == "image_metadata"), {})
                final_text = result.get("text", "")
                report.update(status="executed", result=result, elapsed_seconds=round(time.monotonic() - started, 3),
                              passed={"image_metadata", "image_ocr"} <= successful and "МОСКВА" in ocr.get("details", {}).get("text", "")
                              and metadata.get("details", {}).get("metadata", {}).get("status") == "no_gps_metadata"
                              and "МОСКВА" in final_text.upper() and result.get("investigation", {}).get("status") == "completed")
            except AIError as error:
                report.update(status="api_error", code=error.code, http_status=error.http_status,
                              elapsed_seconds=round(time.monotonic() - started, 3), partial=runner.snapshot())
            except Exception:
                report.update(status="execution_error", code="local_protocol_or_tool_error",
                              elapsed_seconds=round(time.monotonic() - started, 3), partial=runner.snapshot())
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if key and key in encoded:
        raise RuntimeError("Secret safety check rejected report publication")
    path.write_text(encoded + "\n", encoding="utf-8")
    investigation = report.get("result", {}).get("investigation", {})
    print(json.dumps({"passed": report["passed"], "status": report["status"], "elapsed_seconds": report.get("elapsed_seconds"),
                      "steps": investigation.get("steps"), "tool_calls": investigation.get("tool_calls"), "usage": investigation.get("usage"),
                      "api_code": report.get("code")}, ensure_ascii=True))
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/geoint-engine/live-agent.json")
    raise SystemExit(0 if run(parser.parse_args().output.resolve()) else 1)
