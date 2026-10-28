"""Offline readiness probes of the actual source interpreters and entry modules.

Run from a background UI job. Probes import vendor code only in its isolated
worker process, with output suppressed and a disposable working directory.
No external account is labelled connected merely because a token exists.
"""
from __future__ import annotations

import copy
import queue
from pathlib import Path
import threading
import time

from .runtime import VENDOR_DIRS, run_worker, tool_root, runtime_diagnostic
from ..agent_evidence import utc_now

LABELS = {"maigret": "Публичные профили", "blackbird": "Дополнительная проверка профилей",
          "social_analyzer": "Анализ публичных страниц", "snoop": "Локальная проверка профилей",
          "holehe": "Проверка email", "phoneinfoga": "Сведения о номере", "telegram": "Telegram",
          "vk": "ВКонтакте", "instagram": "Instagram", "wayback": "Веб-архив", "blockchain": "Блокчейн · Gansar", "google": "Google"}
_CACHE, _LOCK = {}, threading.Lock()


def clear_readiness_cache():
    with _LOCK:
        _CACHE.clear()


def _credentials(options, name):
    return str(options.get("secrets", {}).get(name, options.get(name, "")) or "")


def _probe(source, options, cancelled=None):
    cancelled = cancelled if cancelled is not None else threading.Event()
    if cancelled.is_set():
        return {"id": source, "label": LABELS[source], "state": "cancelled", "message": "Проверка отменена.", "runtime_ready": False}
    started = time.monotonic()
    root = tool_root(options)
    diagnostic = runtime_diagnostic(source, options)
    key = (str(root), str(options.get("runtime_python", "")), source)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < 45:
            return copy.deepcopy(cached[1])
    if diagnostic['code'] != 'probe_required':
        messages = {'missing_sources':'Исходники не найдены в выбранной папке.',
                    'missing_runtime':'Изолированный Python этого инструмента не найден.',
                    'invalid_interpreter':'Выбранный исполняемый файл Python не найден.',
                    'missing_worker':'В комплекте приложения отсутствует worker.py.',
                    'missing_bridge':'Исполняемый PhoneInfoga bridge не найден.'}
        outcome = {"status": "unavailable", "error_code": diagnostic['code'], "message": messages.get(diagnostic['code'], 'Неизвестный источник.')}
    else:
        try:
            outcome = run_worker(source, {"text": "", "kind": "probe", "limit": 1, "timeout": 7},
                                 {"source_root": str(root), "runtime_python": options.get("runtime_python", ""),
                                  "operation": "probe"}, cancelled)
        except (OSError, RuntimeError, ValueError):
            outcome = {"status": "unavailable", "message": "Не удалось запустить интерпретатор источника. Проверьте путь и зависимости."}
    if source == "phoneinfoga" and outcome.get("status") == "complete" and outcome.get("results"):
        outcome = {"status": "ready", "message": "Исполняемый мост запущен; настоящий парсер PhoneInfoga проверен на зарезервированном примере."}
    code = 'runtime_ready' if outcome.get('status') == 'ready' else outcome.get('error_code',
        'probe_timeout' if outcome.get('status') == 'timeout' else 'probe_failed')
    states = {'missing_sources':'configuration_error', 'invalid_interpreter':'configuration_error',
              'missing_runtime':'missing_dependency', 'missing_dependency':'missing_dependency',
              'missing_bridge':'missing_dependency', 'missing_worker':'unsupported_environment',
              'missing_database':'missing_dependency', 'probe_timeout':'unverified', 'probe_failed':'configuration_error'}
    diagnostic.update(code=code, checked_at=utc_now(), execution_verified=False,
                      missing_module=outcome.get('missing_module'), exit_code=outcome.get('exit_code'))
    if code == 'missing_dependency':
        diagnostic['remedy'] = 'Установите зависимости в изолированное окружение этого инструмента: scripts/setup_sources.py --groups ' + ('platforms' if source in ('telegram','vk','instagram','wayback') else source)
    elif code == 'missing_database':
        diagnostic['remedy'] = 'Восстановите локальную базу инструмента через проверенную настройку источников.'
    elif code == 'runtime_ready':
        diagnostic['remedy'] = 'Локальная проверка пройдена; внешний сервис проверяется только при явном запросе.'
    row = {"id": source, "label": LABELS[source], "state": "ready" if outcome.get("status") == "ready" else states.get(code, 'unavailable'),
           "message": outcome.get("message", "Зависимости источника не готовы."),
           "runtime_ready": outcome.get("status") == "ready", "probe_seconds": round(time.monotonic() - started, 3),
           "diagnostic": diagnostic}
    if outcome.get("status") == "cancelled":
        row.update(state="cancelled", message="Проверка отменена.")
    else:
        with _LOCK:
            _CACHE[key] = (time.monotonic(), copy.deepcopy(row))
    return row


def _authorization_state(row, options):
    row = copy.deepcopy(row)
    source = row["id"]
    if row["runtime_ready"]:
        required = {"telegram": ("telegram_api_id", "telegram_api_hash", "telegram_session"),
                    "vk": ("vk_token",)}.get(source, ())
        if required and not all(_credentials(options, name) for name in required):
            row.update(state="auth_required", message="Нужна авторизация в настройках. Доступность аккаунта ещё не проверялась.")
        elif required:
            row["message"] = "Окружение готово; сессия сохранена, права проверяются при запросе."
        elif source == "instagram":
            row["message"] = "Окружение готово; анонимный доступ зависит от ограничений Instagram."
        elif source == "snoop" and not options.get("enable_snoop"):
            row.update(state="disabled", message="Локальная интеграция выключена. Лицензия источника — только личное использование.")
    return row


def source_readiness(options=None, refresh=False, cancelled=None, on_update=None, on_result=None):
    options = dict(options or {})
    cancelled = cancelled if cancelled is not None else threading.Event()
    if refresh:
        with _LOCK:
            _CACHE.clear()
    pending, completed = queue.Queue(), queue.Queue()
    for source in VENDOR_DIRS:
        pending.put(source)
    def worker():
        while not cancelled.is_set():
            try:
                source = pending.get_nowait()
            except queue.Empty:
                return
            row = _authorization_state(_probe(source, options, cancelled), options)
            completed.put(row)
            callback = on_result or on_update
            if callable(callback) and not cancelled.is_set():
                try:
                    callback(copy.deepcopy(row))
                except RuntimeError:
                    pass  # The receiver's Qt object may have closed meanwhile.
    workers = [threading.Thread(target=worker, name="GrangerPetReadiness", daemon=True) for _ in range(2)]
    for thread in workers:
        thread.start()
    outcomes = {}
    while len(outcomes) < len(VENDOR_DIRS) and not cancelled.is_set():
        try:
            row = completed.get(timeout=.05)
            outcomes[row["id"]] = row
        except queue.Empty:
            if not any(thread.is_alive() for thread in workers):
                break
    rows = []
    for source in VENDOR_DIRS:
        row = outcomes.get(source, {"id": source, "label": LABELS[source], "state": "cancelled", "message": "Проверка отменена.", "runtime_ready": False})
        rows.append(row)
    api = bool(_credentials(options, "google_api_key") and (options.get("google_cx") or options.get("api_cx")))
    google = {"id": "google", "label": LABELS["google"], "state": "ready" if api else "auth_required", "runtime_ready": True,
              "message": "Ключ сохранён; доступ API проверяется запросом." if api else "Без API-ключа доступен поиск через браузер."}
    rows.append(google)
    callback = on_result or on_update
    if callable(callback) and not cancelled.is_set():
        try:
            callback(copy.deepcopy(google))
        except RuntimeError:
            pass
    return rows


def runtime_readiness(source, options=None, cancelled=None):
    return _probe(source, dict(options or {}), cancelled)
