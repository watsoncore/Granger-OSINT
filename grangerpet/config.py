"""Validated, atomic per-user configuration without import-time side effects."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import logging
import os
from pathlib import Path
import sys
import tempfile


def data_directory() -> Path:
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home() / ".config") / "GrangerPet"


def resource_path(relative: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    requested = Path(relative)
    if requested.parts and requested.parts[0].casefold() == "assets":
        return root / "grangerpet" / requested
    return root / requested


@dataclass
class Settings:
    size: int = 195
    fps: int = 24
    cursor_reaction: bool = True
    x: int | None = None
    y: int | None = None
    api_key: str = ""
    api_cx: str = ""
    ai_provider: str = "none"
    deepseek_model: str = "deepseek-v4-flash"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = ""
    source_root: str = ""
    runtime_python: str = ""
    telegram_api_id: str = ""
    instagram_username: str = ""
    request_limit: int = 20
    search_timeout: int = 25
    enable_snoop: bool = False
    agent_steps: int = 10
    agent_calls: int = 14
    agent_timeout: int = 240
    agent_tokens: int = 48000
    agent_page_limit: int = 6
    agent_page_depth: int = 2

    def __post_init__(self):
        try:
            self.size = max(100, min(195, int(self.size))) if not isinstance(self.size, bool) else 195
        except (TypeError, ValueError, OverflowError):
            self.size = 195

    @classmethod
    def from_dict(cls, values: dict) -> "Settings":
        settings = cls()
        if not isinstance(values, dict):
            return settings
        for key, low, high in (("size", 100, 195), ("fps", 8, 30), ("request_limit", 5, 50), ("search_timeout", 5, 60),
                               ("agent_steps", 2, 20), ("agent_calls", 1, 30), ("agent_timeout", 30, 600),
                               ("agent_tokens", 4000, 100000), ("agent_page_limit", 1, 12), ("agent_page_depth", 0, 3)):
            value = values.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                try:
                    setattr(settings, key, max(low, min(high, int(value))))
                except (OverflowError, ValueError):
                    pass
        if isinstance(values.get("cursor_reaction"), bool):
            settings.cursor_reaction = values["cursor_reaction"]
        if isinstance(values.get("enable_snoop"), bool):
            settings.enable_snoop = values["enable_snoop"]
        for key in ("x", "y"):
            value = values.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and -100000 <= value <= 100000:
                setattr(settings, key, value)
        for key in ("api_key", "api_cx", "deepseek_model", "ollama_model", "source_root", "runtime_python", "telegram_api_id", "instagram_username"):
            value = values.get(key)
            if isinstance(value, str):
                setattr(settings, key, value.strip()[:4096])
        if values.get("ai_provider") in ("none", "deepseek", "ollama"):
            settings.ai_provider = values["ai_provider"]
        elif values.get("ai_provider") == "gemini":
            # Migrate the provider choice only. Gemini's model/key are never
            # sent to the unrelated gateway; the user must enter a new key.
            settings.ai_provider = "deepseek"
            settings.deepseek_model = "deepseek-v4-flash"
        if isinstance(values.get("ollama_url"), str):
            from urllib.parse import urlsplit
            value = values["ollama_url"].strip().rstrip("/")
            try:
                url = urlsplit(value)
                if url.scheme in ("http", "https") and url.hostname and not url.username and not url.password:
                    settings.ollama_url = value[:2048]
            except ValueError:
                pass
        return settings

    def to_dict(self) -> dict:
        value = asdict(self)
        value.pop("api_key", None)
        return value


def with_pet_preferences(current: Settings, values: dict) -> Settings:
    """A Launcher update owns appearance fields and cannot replace AI config."""
    merged = asdict(current)
    if isinstance(values, dict):
        for name in ('size', 'fps', 'cursor_reaction'):
            if name in values:
                merged[name] = values[name]
    return Settings.from_dict(merged)


class SettingsStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else data_directory() / "settings.json"

    def load(self) -> Settings:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            values = {}
        except (OSError, ValueError, TypeError):
            logging.getLogger(__name__).warning("Could not read configuration; using defaults", exc_info=True)
            values = {}
        settings = Settings.from_dict(values)
        from .credentials import get_secret, set_secret, CredentialError
        try:
            if isinstance(values, dict) and values.get("api_key"):
                set_secret("google_api_key", settings.api_key)
                self.save(settings)
            settings.api_key = get_secret("google_api_key")
        except CredentialError:
            logging.getLogger(__name__).warning("Secure credential storage is unavailable")
            settings.api_key = ""
        return settings

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = Settings.from_dict({field.name: getattr(settings, field.name) for field in fields(Settings)})
        if settings.api_key:
            from .credentials import set_secret, get_secret
            if get_secret("google_api_key") != settings.api_key:
                set_secret("google_api_key", settings.api_key)
        fd, temporary = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload.to_dict(), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
