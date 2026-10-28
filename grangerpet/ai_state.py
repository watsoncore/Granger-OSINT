"""Shared, secret-free AI configuration and connection state for open windows.

An API test proves a particular draft. Only a successful save commits that draft
for chat; ordinary configuration reloads never manufacture a connected proof.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib

from PySide6.QtCore import QObject, Signal

from .ai_keys import DEFAULT_DEEPSEEK_MODEL, resolve_deepseek_key, resolve_deepseek_model


def model_title(provider, model_id):
    if provider == "deepseek" and model_id == DEFAULT_DEEPSEEK_MODEL:
        return "DeepSeek V4 Flash"
    return model_id or ("Ollama" if provider == "ollama" else "ИИ")


ERROR_STATES = {
    "auth": "authentication_failed", "invalid_key": "authentication_failed",
    "authentication_failed": "authentication_failed", "forbidden": "permission_denied",
    "access_denied": "permission_denied", "permission_denied": "permission_denied",
    "quota": "quota_exceeded", "quota_exceeded": "quota_exceeded",
    "model_not_found": "model_unavailable", "model_unavailable": "model_unavailable",
    "invalid_model": "model_unavailable", "missing_key": "not_configured",
    "network": "network_error", "timeout": "network_error", "provider_error": "network_error",
    "payment": "payment_required", "payment_required": "payment_required",
    "insufficient_balance": "payment_required",
}


class AIState(QObject):
    changed = Signal(object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = deepcopy(settings)
        self._committed_identity = self._identity(settings.ai_provider, self._model(settings))
        self._verified = {}
        self._committed_status = self._configured_status(self._committed_identity)
        self._committed_error = ""
        self._draft = None
        self._generation = 0
        self._checking_identity = None
        self._request_identity = None

    @staticmethod
    def _model(settings):
        provider = getattr(settings, "ai_provider", "none")
        return resolve_deepseek_model(getattr(settings, "deepseek_model", "")) if provider == "deepseek" else getattr(settings, "ollama_model", "") if provider == "ollama" else ""

    def _identity(self, provider, model_id, key_override=None, endpoint=None):
        available = False
        fingerprint = b""
        if provider == "deepseek":
            try:
                key = key_override.strip() if isinstance(key_override, str) else resolve_deepseek_key()
            except Exception:
                key = ""
            available = bool(key)
            fingerprint = hashlib.sha256(key.encode("utf-8")).digest() if key else b""
        elif provider == "ollama":
            available = bool(model_id)
            address = getattr(self._settings, "ollama_url", "") if endpoint is None else endpoint
            fingerprint = hashlib.sha256(str(address).strip().rstrip("/").encode()).digest()
        return str(provider or "none"), str(model_id or ""), available, fingerprint

    @staticmethod
    def _configured_status(identity):
        return "configured_unverified" if identity[0] in ("deepseek", "ollama") and identity[2] and identity[1] else "not_configured"

    @property
    def can_send(self):
        identity = self._committed_identity
        return bool(identity[0] in ("deepseek", "ollama") and identity[1] and identity[2])

    @property
    def settings(self):
        return deepcopy(self._settings)

    def _safe(self, identity, saved, status, error="", verified_at=None):
        return {"provider": identity[0], "model_id": identity[1], "credential_available": identity[2],
                "configuration_saved": bool(saved), "connection_status": status, "last_error": str(error or ""),
                "last_verified_at": verified_at}

    def committed_snapshot(self):
        return self._safe(self._committed_identity, True, self._committed_status, self._committed_error,
                          self._verified.get(self._committed_identity))

    def snapshot(self):
        if self._draft:
            return self._safe(self._draft["identity"], False, self._draft["status"], self._draft.get("error", ""),
                              self._verified.get(self._draft["identity"]))
        return self.committed_snapshot()

    def is_verified(self, provider=None, model_id=None, key_override=None, endpoint=None):
        identity = self._identity(provider, model_id or "", key_override, endpoint) if provider is not None else self._committed_identity
        return identity in self._verified

    def _emit(self):
        self.changed.emit(self.snapshot())

    def set_settings(self, settings):
        self._settings = deepcopy(settings)
        identity = self._identity(settings.ai_provider, self._model(settings))
        if identity != self._committed_identity:
            self._committed_identity = identity
            self._committed_status = "connected" if identity in self._verified else self._configured_status(identity)
            self._committed_error = ""
        self._emit()

    def update_draft(self, provider, model_id, key_override=None, endpoint=None):
        identity = self._identity(provider, model_id, key_override, endpoint)
        if identity == self._committed_identity:
            if self._draft is not None:
                self._generation += 1
                self._draft = None
            self._emit()
            return
        if self._draft is None or self._draft["identity"] != identity:
            self._generation += 1
            self._draft = {"identity": identity, "status": "verified_unsaved" if identity in self._verified else self._configured_status(identity), "error": ""}
        self._emit()

    def begin_check(self, provider=None, model_id=None, key_override=None, endpoint=None):
        if provider is not None:
            self.update_draft(provider, model_id or "", key_override, endpoint)
        self._generation += 1
        identity = self._draft["identity"] if self._draft else self._committed_identity
        self._checking_identity = identity
        if self._draft:
            self._draft.update(status="checking", error="")
        else:
            self._committed_status, self._committed_error = "checking", ""
        self._emit()
        return self._generation

    def finish_check(self, token, success=True, error=None):
        current = self._draft["identity"] if self._draft else self._committed_identity
        if token != self._generation or current != self._checking_identity:
            return False
        if success and error is None:
            self._verified[current] = datetime.now(timezone.utc).isoformat()
            if self._draft:
                self._draft.update(status="verified_unsaved", error="")
            else:
                self._committed_status, self._committed_error = "connected", ""
        else:
            status, message = self._error(error)
            self._verified.pop(current, None)
            if self._draft:
                self._draft.update(status=status, error=message)
            else:
                self._committed_status, self._committed_error = status, message
        self._emit()
        return True

    def cancel_check(self):
        self._generation += 1
        if self._draft and self._draft["status"] == "checking":
            self._draft["status"] = "verified_unsaved" if self._draft["identity"] in self._verified else self._configured_status(self._draft["identity"])
        elif self._committed_status == "checking":
            self._committed_status = "connected" if self._committed_identity in self._verified else self._configured_status(self._committed_identity)
        self._emit()

    def commit(self, settings):
        self._settings = deepcopy(settings)
        self._committed_identity = self._identity(settings.ai_provider, self._model(settings))
        self._committed_status = "connected" if self._committed_identity in self._verified else self._configured_status(self._committed_identity)
        self._committed_error = ""
        self._draft = None
        self._generation += 1
        self._emit()

    def save_failed(self):
        if self._draft and self._draft["identity"] in self._verified:
            self._draft.update(status="verified_unsaved", error="Подключение проверено, но настройки не сохранены")
        self._emit()

    def discard_draft(self):
        self._draft = None
        self._generation += 1
        self._emit()

    def request_started(self, provider=None, model_id=None):
        if provider is not None and (provider, model_id) != self._committed_identity[:2]:
            return
        self._request_identity = self._committed_identity
        self._committed_status, self._committed_error = "checking", ""
        self._emit()

    def request_succeeded(self, provider=None, model_id=None):
        if self._request_identity != self._committed_identity or (provider is not None and (provider, model_id) != self._committed_identity[:2]):
            return
        self._verified[self._committed_identity] = datetime.now(timezone.utc).isoformat()
        self._committed_status, self._committed_error = "connected", ""
        self._emit()

    def request_failed(self, error_or_metadata, provider=None, model_id=None):
        if self._request_identity != self._committed_identity or (provider is not None and (provider, model_id) != self._committed_identity[:2]):
            return
        self._committed_status, self._committed_error = self._error(error_or_metadata)
        self._verified.pop(self._committed_identity, None)
        self._emit()

    def cancel_request(self):
        if self._request_identity == self._committed_identity:
            self._committed_status = "connected" if self._committed_identity in self._verified else self._configured_status(self._committed_identity)
            self._committed_error = ""
            self._emit()

    @staticmethod
    def _error(error):
        code = error.get("code", "") if isinstance(error, dict) else getattr(error, "code", "")
        status = error.get("http_status") if isinstance(error, dict) else getattr(error, "http_status", None)
        if status in (400, 401) and code in ("auth", "invalid_key", "authentication_failed") or status == 401:
            state = "authentication_failed"
        elif status == 403:
            state = "permission_denied"
        elif status == 402:
            state = "payment_required"
        elif status == 429:
            state = "quota_exceeded"
        elif status == 404:
            state = "model_unavailable"
        else:
            state = ERROR_STATES.get(code, "network_error")
        messages = {"authentication_failed": "Не удалось подтвердить API-ключ", "permission_denied": "Нет доступа к DeepSeek API",
                    "quota_exceeded": "Достигнут лимит запросов DeepSeek API", "model_unavailable": "Выбранная модель DeepSeek недоступна",
                    "network_error": "Нет соединения со шлюзом DeepSeek", "not_configured": "Добавьте API-ключ DeepSeek в настройках",
                    "payment_required": "Недостаточно средств или требуется оплата у поставщика API (HTTP 402)"}
        if code in ("empty_response", "invalid_response", "blocked", "tools_not_enabled", "invalid_request"):
            return "response_error", {
                "empty_response": "DeepSeek не вернул текст ответа",
                "invalid_response": "DeepSeek вернул некорректный ответ",
                "blocked": "DeepSeek отклонил запрос",
                "tools_not_enabled": "Автоматический запуск OSINT не подключён. Используйте ручной поиск и анализ выбранных находок.",
                "invalid_request": "Шлюз DeepSeek отклонил параметры запроса. Проверьте выбранную модель.",
            }[code]
        if code == "timeout":
            return state, "Время ожидания ответа DeepSeek истекло"
        if status in (500, 502, 503, 504):
            return state, "Сервис DeepSeek временно недоступен"
        # Only controlled application messages cross the shared-state boundary;
        # SDK bodies, exception text and credential-looking input never do.
        return state, messages[state]

    def status_text(self, snapshot=None):
        value = snapshot or self.snapshot()
        state = value["connection_status"]
        model = model_title(value["provider"], value["model_id"])
        if state == "not_configured":
            return value.get("last_error") or ("ИИ не настроен" if value["configuration_saved"] else "Подключение изменено · Сохраните настройки")
        if state == "checking":
            return "Проверяю подключение…"
        if state == "verified_unsaved":
            return value.get("last_error") or "Подключение проверено · Сохраните настройки"
        if state == "connected":
            return model + " · Подключено"
        if state == "configured_unverified":
            return (model + " · Настроено, не проверено") if value["configuration_saved"] else "Настройки изменены · Сохраните подключение"
        return value.get("last_error") or "Не удалось подключиться к ИИ"
