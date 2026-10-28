"""Fixed, typed OSINT registry over GrangerPet's actual adapters.

The LLM selects data arguments only. It cannot supply an interpreter, command,
source path, credentials, arbitrary adapter name, or a Python callback.
"""
from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import ipaddress
import json
import re
import threading
import time

from .agent_evidence import normalize_evidence, redact, utc_now
from .investigation import InvestigationEvidence
from .credentials import CredentialError, get_secret
from .engine.adapters import SourceAdapter, SOURCE_META
from .engine.controller import Context
from .engine.models import SearchQuery
from .engine.readiness import runtime_readiness


@dataclass(frozen=True)
class ToolSpec:
    name: str
    source: str
    kind: str
    argument: str
    description: str
    requires_approval: bool = False
    max_length: int = 300


_SPECS = (
    ToolSpec("username_maigret", "maigret", "username", "username", "Maigret: ограниченная проверка существования публичных профилей по точному никнейму. Совпадение никнейма не доказывает общего владельца.", max_length=64),
    ToolSpec("username_blackbird", "blackbird", "username", "username", "Blackbird: независимая проверка публичных профилей по точному никнейму, по локальной базе WhatsMyName.", max_length=64),
    ToolSpec("username_social_analyzer", "social_analyzer", "username", "username", "Social Analyzer: проверка публичных страниц профилей по никнейму; не устанавливает личность.", max_length=64),
    ToolSpec("username_snoop", "snoop", "username", "username", "Snoop: дополнительная локальная проверка публичных профилей, только если интеграция включена пользователем.", max_length=64),
    ToolSpec("email_holehe", "holehe", "email", "email", "Holehe: проверка сигналов регистрации email у ограниченного набора сервисов. Это взаимодействие с сервисами, требуется явное подтверждение пользователя; не доказывает личность.", True, 254),
    ToolSpec("phone_metadata", "phoneinfoga", "phone", "phone", "PhoneInfoga bridge: формат, код страны и доступные метаданные номера. Не поиск владельца и не сканирование телефона.", max_length=32),
    ToolSpec("blockchain_gansar", "blockchain", "blockchain", "address", "Gansar: публичные наблюдения блокчейна — баланс, транзакции и доступные метки адреса. TON и другие поддержанные локальным валидатором сети; метки не устанавливают личность.", max_length=128),
    ToolSpec("web_archive", "wayback", "web", "url", "Wayback: публичные архивные снимки конкретной HTTP(S)-страницы. Только публичные сайты, без обхода доступа.", max_length=1000),
    ToolSpec("telegram_public", "telegram", "telegram", "username", "Telegram через существующую разрешённую сессию: доступные публичные сведения по точному имени. Требуется авторизация и явное подтверждение пользователя.", True, 64),
    ToolSpec("vk_public", "vk", "vk", "username", "VK через существующий разрешённый API-токен: публичный профиль по точному идентификатору. Требуется явное подтверждение пользователя.", True, 64),
    ToolSpec("instagram_public", "instagram", "instagram", "username", "Instagram: доступный публичный профиль по точному имени, без обхода авторизации. Доступ зависит от ограничений сервиса; требуется подтверждение.", True, 64),
    ToolSpec("web_search", "web_search", "dork", "query", "Поиск индексируемых публичных упоминаний: реальные URL, заголовки и фрагменты. Отдельный веб-поиск, не проверка регистрации и не выдуманная выдача.", max_length=300),
    ToolSpec("web_read", "web_read", "web", "url", "Непосредственно прочитать найденную публичную страницу: основной текст, фрагмент, заголовки, метаданные, таблицы, JSON-LD и связанные ссылки. Это прямое чтение, не сниппет поисковика. Только URL из реальных находок, ссылок прочитанных страниц или явно указанные пользователем; глубина и число страниц ограничены.", max_length=2000),
    ToolSpec("domain_lookup", "domain_lookup", "domain", "domain", "Пассивные DNS и доступные RDAP-сведения публичного домена. Не сканирование портов или уязвимостей.", max_length=253),
    ToolSpec("ip_lookup", "ip_lookup", "ip", "address", "Публичные сведения RIPEstat об ASN и сетевом префиксе IP. Только глобальный IP, без геолокации человека и активного сканирования.", max_length=64),
    ToolSpec("evidence_get", "evidence_get", "evidence", "evidence_id", "Вернуться к полной безопасной записи ранее полученной находки по точному evidence_id. Не выполняет новый поиск и не доказывает личность.", max_length=23),
)
_BY_NAME = {spec.name: spec for spec in _SPECS}
_AUTH = {"telegram": ("telegram_api_hash", "telegram_session"), "vk": ("vk_token",), "instagram": ("instagram_session",)}
_BASE_OPTIONS = ("source_root", "tools_root", "runtime_python", "telegram_api_id", "instagram_username", "google_cx", "api_cx", "enable_snoop", "profile_sites")


class _Cancellation:
    def __init__(self, parent=None, deadline=None):
        self.parent, self.deadline = parent, deadline
        self._local = threading.Event()

    def is_set(self):
        return self._local.is_set() or bool(self.parent and self.parent.is_set()) or bool(self.deadline is not None and time.monotonic() >= self.deadline)

    def set(self):
        self._local.set()

    def wait(self, timeout=None):
        end = time.monotonic() + timeout if timeout is not None else None
        while not self.is_set():
            if end is not None and time.monotonic() >= end:
                return False
            self._local.wait(min(.05, max(0, end - time.monotonic())) if end is not None else .05)
        return True


class ToolRegistry:
    def __init__(self, settings, *, options=None, readiness=None, adapters=None, secret_getter=None, web_provider=None, redactions=()):
        self.settings = settings
        self._options = {key: deepcopy(value) for key, value in dict(options or {}).items() if key in _BASE_OPTIONS or key in ("secrets", "google_api_key", "vk_token", "telegram_api_hash", "telegram_session", "instagram_session")}
        self._readiness = readiness or runtime_readiness
        self._secret_getter = secret_getter or get_secret
        self._adapters = {item.id: item for item in adapters} if adapters is not None and not isinstance(adapters, dict) else dict(adapters or {})
        self._web_provider = web_provider
        self._availability = {}
        self.evidence = InvestigationEvidence()
        self._lock = threading.RLock()
        self._redactions = {value for value in redactions if isinstance(value, str) and len(value) >= 4}
        from .agent_browser import PublicPageReader
        self.web_reader = PublicPageReader(max_pages=getattr(settings, 'agent_page_limit', 0),
                                           max_depth=getattr(settings, 'agent_page_depth', 2))

    def seed_urls_from_user(self, text):
        """Only the human's actual text seeds initial URLs, never model output."""
        self.web_reader.seed_urls_from_user(text)

    def begin_investigation(self):
        self.web_reader.begin_run()

    def checkpoint_state(self):
        return self.web_reader.checkpoint_state()

    def restore_investigation(self, records, state):
        self.evidence.restore(records, [])
        self.web_reader.restore_state(state, records)

    def _secret(self, name):
        value = self._options.get("secrets", {}).get(name) or self._options.get(name)
        if not value:
            try:
                value = self._secret_getter(name)
            except CredentialError:
                value = ""
        if isinstance(value, str) and value:
            with self._lock:
                self._redactions.add(value)
            return value
        return ""

    def _source_options(self, source):
        options = {name: deepcopy(self._options.get(name, getattr(self.settings, name, ""))) for name in _BASE_OPTIONS}
        options["tools_root"] = options.get("tools_root") or options.get("source_root")
        options["google_cx"] = options.get("google_cx") or getattr(self.settings, "api_cx", "")
        for name in _AUTH.get(source, ()):
            options[name] = self._secret(name)
        if source == "web_search":
            options["google_api_key"] = getattr(self.settings, "api_key", "") or self._secret("google_api_key")
            if options["google_api_key"]:
                with self._lock:
                    self._redactions.add(options["google_api_key"])
        return options

    def _web(self):
        if self._web_provider is None:
            from .agent_web import WebSearchProvider
            self._web_provider = WebSearchProvider(self.settings, self._source_options("web_search"))
        return self._web_provider

    def _state(self, spec, cancelled=None):
        with self._lock:
            cached = self._availability.get(spec.name)
        if cached is not None and time.monotonic() - cached[0] < 45:
            return deepcopy(cached[1])
        base = {"name": spec.name, "source": spec.source, "kind": spec.kind, "description": spec.description,
                "requires_approval": spec.requires_approval, "needs_confirmation": spec.requires_approval,
                "available": False, "state": "unavailable", "reason": "Инструмент недоступен."}
        if cancelled is not None and cancelled.is_set():
            base.update(state="cancelled", reason="Проверка отменена.")
            return base
        if spec.source == "web_read":
            base.update(available=True, state="unverified", reason="Прямое чтение обнаруженных публичных URL; DNS и каждый переход проверяются при запросе.")
        elif spec.source == "evidence_get":
            base.update(available=True, state="ready", reason="Только уже полученные безопасные находки текущего диалога.")
        elif spec.source == "web_search":
            try:
                row = self._web().availability()
                base.update(available=bool(row.get("available")), state=str(row.get("state", "unverified")),
                            reason="Веб-источник проверяется фактическим запросом; наличие настроек не доказывает доступ к выдаче.")
            except (ImportError, RuntimeError, ValueError):
                base.update(reason="Модуль веб-поиска недоступен.")
        elif spec.source in ("domain_lookup", "ip_lookup"):
            try:
                from . import agent_web
                available = callable(getattr(agent_web, "lookup_domain" if spec.source == "domain_lookup" else "lookup_ip", None))
            except ImportError:
                available = False
            base.update(available=available, state="unverified" if available else "unavailable",
                        reason="Пассивный публичный источник проверяется фактическим запросом." if available else "Модуль пассивных сведений недоступен.")
        elif spec.source == "snoop" and not getattr(self.settings, "enable_snoop", False):
            base.update(state="disabled", reason="Интеграция Snoop выключена пользователем; учитывайте ограничения лицензии.")
        else:
            options = self._source_options(spec.source)
            try:
                row = self._readiness(spec.source, options, cancelled=cancelled)
            except Exception:
                row = {"runtime_ready": False}
            if row.get("runtime_ready"):
                missing = any(not options.get(name) for name in _AUTH.get(spec.source, ()) if name != "instagram_session")
                if spec.source == "telegram" and not options.get("telegram_api_id"):
                    missing = True
                if missing:
                    base.update(state="auth_required", reason="Нужна авторизация источника в существующих настройках.")
                else:
                    base.update(available=True, state="configured_unverified" if spec.source in _AUTH else "ready",
                                reason="Окружение проверено; доступ внешнего источника подтверждается только результатом запроса.")
            else:
                base.update(reason="Не готов исполняемый мост, зависимости или локальная база. Проверьте Настройки → Источники.")
        if cancelled is None or not cancelled.is_set():
            with self._lock:
                self._availability[spec.name] = (time.monotonic(), deepcopy(base))
        return base

    def catalog(self, *, cancel_event=None, deadline=None):
        # A cold discovery cannot consume the entire investigation deadline.
        end = min(deadline, time.monotonic() + 12) if deadline is not None else time.monotonic() + 12
        cancelled = _Cancellation(cancel_event, end)
        instant = {spec.name: self._state(spec, cancelled) for spec in _SPECS
                   if spec.source in ("web_search", "web_read", "domain_lookup", "ip_lookup", "evidence_get")}
        # The existing worker transport has its own global two-process budget.
        # Cold import probes share that budget and never run on the GUI thread.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="GrangerPetToolReadiness") as pool:
            checked = list(pool.map(lambda spec: self._state(spec, cancelled),
                                    [spec for spec in _SPECS if spec.name not in instant]))
        rows = {row["name"]: row for row in checked}
        rows.update(instant)
        return [rows[spec.name] for spec in _SPECS]

    def schemas(self, *, cancel_event=None, deadline=None):
        rows = {row["name"]: row for row in self.catalog(cancel_event=cancel_event, deadline=deadline)}
        tools = []
        for spec in _SPECS:
            if not rows[spec.name]["available"]:
                continue
            tools.append({"type": "function", "function": {"name": spec.name, "description": spec.description,
                "parameters": {"type": "object", "properties": {
                    spec.argument: {"type": "string", "minLength": 1, "maxLength": spec.max_length},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10 if spec.name == "web_search" else 20}},
                    "required": [spec.argument], "additionalProperties": False}}})
        return tools

    descriptions = schemas

    def _validate(self, spec, args):
        if not isinstance(args, dict) or set(args) - {spec.argument, "limit"} or spec.argument not in args:
            raise ValueError("Аргументы не соответствуют зарегистрированной схеме.")
        value = args[spec.argument]
        if not isinstance(value, str) or not value.strip() or len(value) > spec.max_length or any(ord(char) < 32 for char in value):
            raise ValueError("Некорректное значение исследуемого объекта.")
        value = value.strip()
        maximum = 10 if spec.name == "web_search" else 20
        limit = args.get("limit", min(maximum, getattr(self.settings, "request_limit", 20)))
        if type(limit) is not int or not 1 <= limit <= maximum:
            raise ValueError("Лимит результата вне допустимого диапазона.")
        options = self._source_options(spec.source)
        if spec.source in ("web_search", "web_read", "domain_lookup", "ip_lookup", "evidence_get"):
            if spec.source == "web_read":
                from .agent_browser import PageReadError, public_url
                try:
                    value = public_url(value)
                except PageReadError:
                    raise ValueError('Unsafe page URL') from None
            elif spec.source == "evidence_get":
                if not re.fullmatch(r"ev_[a-f0-9]{20}", value):
                    raise ValueError("Укажите точный идентификатор находки.")
            elif spec.source == "ip_lookup":
                try:
                    address = ipaddress.ip_address(value)
                except ValueError:
                    raise ValueError("Укажите корректный публичный IP-адрес.") from None
                if not address.is_global:
                    raise ValueError("Локальные, зарезервированные и служебные IP не исследуются.")
                value = str(address)
            elif spec.source == "domain_lookup":
                if "://" in value or "/" in value or "@" in value:
                    raise ValueError("Укажите домен без URL, порта и учётных данных.")
                from .engine.router import _domain
                value = _domain(value)
                if value.endswith((".local", ".internal", ".localhost", ".test", ".invalid")):
                    raise ValueError("Укажите публичный домен.")
            return value, limit, options, None
        query = SearchQuery(value, spec.kind, limit, min(25, max(3, getattr(self.settings, "search_timeout", 25))), options).normalized()
        if query.kind != spec.kind:
            raise ValueError("Тип объекта не соответствует назначению инструмента.")
        return query.text, limit, options, query

    def execute(self, name, args, *, cancel_event=None, deadline=None, approved=False, on_event=None):
        when = utc_now()
        started = time.monotonic()
        envelope = {"tool": str(name)[:80], "status": "invalid_arguments", "query": "", "obtained_at": when,
                    "started_at": when, "results": [], "sources": [], "limitations": []}
        spec = _BY_NAME.get(name) if isinstance(name, str) else None
        if spec is None:
            envelope.update(status="unknown_tool", error="Инструмент не зарегистрирован.")
            return envelope
        if deadline is None:
            deadline = time.monotonic() + 25
        cancelled = _Cancellation(cancel_event, deadline)
        if cancelled.is_set():
            envelope["status"] = "cancelled" if cancel_event and cancel_event.is_set() else "timeout"
            return envelope
        try:
            value, limit, options, query = self._validate(spec, args)
        except (ValueError, TypeError, OverflowError):
            envelope["error"] = "Некорректные аргументы инструмента. Используйте его строго заданный тип и допустимый лимит."
            return envelope
        envelope["query"] = redact(value, self._redactions)
        state = self._state(spec, cancelled)
        if not state["available"]:
            envelope.update(status=state["state"], error=state["reason"])
            return envelope
        if spec.requires_approval and approved is not True:
            envelope.update(status="approval_required", error="Нужно явное подтверждение пользователя перед взаимодействием с этим источником.")
            return envelope
        if spec.source == "evidence_get":
            record = self.evidence.get(value)
            envelope.update(status="complete" if record else "empty", results=[record] if record else [],
                            result_count=1 if record else 0, sources=record.get("sources", []) if record else [],
                            limitations=["Получена сохранённая находка; новый сетевой запрос не выполнялся."] if record else ["Такой находки нет в текущем диалоге."])
            return envelope
        if cancelled.is_set():
            envelope["status"] = "cancelled" if cancel_event and cancel_event.is_set() else "timeout"
            return envelope
        records = {}
        def receive(raw):
            if cancelled.is_set():
                return
            try:
                record = normalize_evidence(raw, spec.name, value, utc_now(), tuple(self._redactions))
            except (TypeError, ValueError):
                return
            key = record["evidence_id"]
            if key in records or len(records) >= limit:
                return
            records[key] = record
            self.web_reader.add_evidence([record])
            self.evidence.add({"tool": spec.name, "query": value, "obtained_at": when,
                               "status": "partial", "results": [record]})
            if callable(on_event):
                try:
                    on_event({"type": "evidence", "tool": spec.name, "records": [deepcopy(record)]})
                except Exception:
                    pass
        def event(row):
            if isinstance(row, dict) and row.get("event") == "result":
                receive(row.get("result"))
        try:
            if spec.source == "web_read":
                # Search evidence is the URL authority. The model cannot invent
                # a new URL and gain network access through ordinary text.
                self.web_reader.add_evidence(self.evidence.records())
                outcome = self.web_reader.read(value, cancel_event=cancelled, deadline=deadline)
            elif spec.source == "web_search":
                outcome = self._web().search(value, limit=limit, cancel_event=cancelled, deadline=deadline)
            elif spec.source in ("domain_lookup", "ip_lookup"):
                from .agent_web import lookup_domain, lookup_ip
                outcome = (lookup_domain if spec.source == "domain_lookup" else lookup_ip)(value, cancel_event=cancelled, deadline=deadline)
            else:
                remaining = max(0, deadline - time.monotonic())
                query.timeout = min(query.timeout, remaining)
                adapter = self._adapters.get(spec.source) or SourceAdapter(spec.source, SOURCE_META[spec.source][0], SOURCE_META[spec.source][1])
                outcome = adapter.run(query, Context(cancelled, options, event))
            if not isinstance(outcome, dict):
                raise ValueError()
            for raw in outcome.get("results", [])[:limit] if isinstance(outcome.get("results"), list) else []:
                receive(raw)
            status = str(outcome.get("status", "error"))
            allowed = {"complete", "completed", "partial", "empty", "error", "timeout", "cancelled", "unavailable", "auth_required", "blocked", "limit_reached"}
            envelope["status"] = status if status in allowed else "error"
            if spec.source == 'web_read' and outcome.get('error'):
                envelope['error'] = str(outcome['error'])[:80]
            if spec.source == 'web_read' and isinstance(outcome.get('page_budget'), dict):
                envelope['page_budget'] = deepcopy(outcome['page_budget'])
            if type(outcome.get("checked")) is int:
                envelope["checked"] = max(0, min(100000, outcome["checked"]))
            if outcome.get("limitations"):
                limitations = outcome["limitations"]
                envelope["limitations"] = redact(limitations if isinstance(limitations, list) else [str(limitations)], tuple(self._redactions))
            if outcome.get("message"):
                envelope["limitations"].append(redact(str(outcome["message"]), tuple(self._redactions))[:1000])
        except InterruptedError:
            envelope["status"] = "cancelled"
        except Exception:
            envelope.update(status="error", error="Источник не выполнил запрос. Проверьте его доступность и настройки.")
        if cancelled.is_set():
            envelope["status"] = "cancelled" if cancel_event and cancel_event.is_set() else "timeout"
        envelope["results"] = list(records.values())
        envelope["obtained_at"] = utc_now()
        envelope["elapsed_seconds"] = round(time.monotonic() - started, 3)
        envelope["sources"] = list(dict.fromkeys(source for record in records.values() for source in record.get("sources", [])))
        envelope["result_count"] = len(records)
        envelope["limitations"].append("Проверен ограниченный набор источников. Нулевой результат не доказывает отсутствия объекта; совпадение идентификаторов не устанавливает личность.")
        self.evidence.add(envelope)
        return envelope
