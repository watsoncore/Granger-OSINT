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
    ui_theme: str = "dark"
    geoint_nominatim_url: str = ""
    geoint_overpass_url: str = ""
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
    nuclei_enabled: bool = False
    # Zero disables a USER budget; request timeouts and loop guards remain on.
    agent_steps: int = 0
    agent_calls: int = 0
    agent_timeout: int = 0
    agent_tokens: int = 0
    agent_page_limit: int = 0
    agent_page_depth: int = 2
    agent_parallel: int = 2
    agent_tool_timeout: int = 25
    agent_request_timeout: int = 90
    agent_no_progress_rounds: int = 3
    agent_auto_continue: bool = True
    agent_budget_behavior: str = "pause"
    research_settings_version: int = 2
    notifications_enabled: bool = True
    notifications_animate: bool = True
    notifications_reply: bool = True
    notifications_investigation: bool = True
    notifications_errors: bool = True
    reduced_motion: bool = False

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
        values = dict(values)
        if values.get("ui_theme") in ("dark", "black", "light", "mono"):
            settings.ui_theme = values["ui_theme"]
        from urllib.parse import urlsplit
        for field in ('geoint_nominatim_url','geoint_overpass_url'):
            raw=values.get(field,'')
            if isinstance(raw,str) and len(raw)<=2048:
                try:
                    parsed=urlsplit(raw)
                    if not raw or parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment:
                        setattr(settings,field,raw.rstrip('/'))
                except ValueError: pass
        previous_defaults = {"agent_steps": 10, "agent_calls": 14, "agent_timeout": 240,
                             "agent_tokens": 48000, "agent_page_limit": 6, "agent_page_depth": 2}
        revision = values.get("research_settings_version", 1)
        if (type(revision) is not int or revision < 2) and all(
                values.get(key, value) == value for key, value in previous_defaults.items()):
            # The exact old preset was imposed by the app, not chosen as a
            # spending budget. Preserve any explicitly changed legacy preset.
            for key in ("agent_steps", "agent_calls", "agent_timeout", "agent_tokens", "agent_page_limit"):
                values[key] = 0
        for key, low, high in (("size", 100, 195), ("fps", 8, 30), ("request_limit", 5, 50), ("search_timeout", 5, 60),
                               ("agent_steps", 0, 2_000_000_000), ("agent_calls", 0, 2_000_000_000),
                               ("agent_timeout", 0, 31_536_000), ("agent_tokens", 0, 2_000_000_000),
                               ("agent_page_limit", 0, 2_000_000_000), ("agent_page_depth", 0, 8),
                               ("agent_parallel", 1, 4), ("agent_tool_timeout", 1, 300),
                               ("agent_request_timeout", 1, 300)):
            value = values.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                try:
                    setattr(settings, key, max(low, min(high, int(value))))
                except (OverflowError, ValueError):
                    pass
        if type(values.get('agent_no_progress_rounds')) is int:
            settings.agent_no_progress_rounds = max(2, min(10, values['agent_no_progress_rounds']))
        for key in ("cursor_reaction", "enable_snoop", "nuclei_enabled", "agent_auto_continue", "notifications_enabled",
                    "notifications_animate", "notifications_reply", "notifications_investigation", "notifications_errors", "reduced_motion"):
            if isinstance(values.get(key), bool):
                setattr(settings, key, values[key])
        if values.get("agent_budget_behavior") in ("pause", "stop"):
            settings.agent_budget_behavior = values["agent_budget_behavior"]
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
