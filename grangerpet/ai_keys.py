"""DeepSeek gateway credentials from the active protected vault.

Old Gemini credentials, environment and local example/development files are not
used for this different third-party service.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .credentials import CredentialError, get_secret, portable_enabled

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_BASE_URL = "https://api.aikeysforyou.com/v1"


@dataclass(frozen=True)
class DeepSeekCredential:
    key: str = field(default="", repr=False)
    source: str = "missing"

    @property
    def available(self):
        return bool(self.key)


def deepseek_credentials(*, override=None, secret_getter=None):
    """An explicit unsaved input is used only for the requested connection test."""
    if isinstance(override, str) and override.strip():
        return DeepSeekCredential(override.strip(), "input")
    try:
        saved = (secret_getter or get_secret)("deepseek_api_key")
    except CredentialError:
        saved = ""
    if isinstance(saved, str) and saved.strip():
        return DeepSeekCredential(saved.strip(), "portable" if portable_enabled() else "windows")
    return DeepSeekCredential()


def resolve_deepseek_key(override=None, **kwargs):
    return deepseek_credentials(override=override, **kwargs).key


def deepseek_key_source(**kwargs):
    return deepseek_credentials(**kwargs).source


def resolve_deepseek_model(saved_model=""):
    return saved_model.strip() if isinstance(saved_model, str) and saved_model.strip() else DEFAULT_DEEPSEEK_MODEL
