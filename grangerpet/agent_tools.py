"""Fixed, typed OSINT registry over GrangerPet's actual adapters.

The LLM selects data arguments only. It cannot supply an interpreter, command,
source path, credentials, arbitrary adapter name, or a Python callback.
"""
from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import ipaddress
import hashlib
import json
import re
import threading
import time
import uuid

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
    input_schema: dict | None = None
    execution_mode: str = ''
    documentation_url: str = ''
    category: str = ''


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
    ToolSpec("github_repository", "github_repository", "repository", "repository", "GitHub REST API: публичные метаданные конкретного репозитория owner/name, без чтения приватного кода.", max_length=140),
    ToolSpec("threat_feodo", "threat_feodo", "ip", "address", "Feodo Tracker: сверить публичный IP с рекомендованным открытым C2-списком. Отсутствие совпадения не означает безопасность.", max_length=45),
    ToolSpec("hash_virustotal", "hash_virustotal", "hash", "sha256", "VirusTotal API: прочитать существующий отчёт SHA-256 с собственным ключом. Файлы не загружаются; требуется подтверждение платного/персонального источника.", True, 64),
    ToolSpec('image_metadata','image_metadata','image','attachment_id','Локально прочитать выбранное изображение: настоящий EXIF/GPS, SHA-256, размеры и dHash. Отсутствие GPS не означает координаты 0,0. Не определяет место по внешности.',max_length=68),
    ToolSpec('image_ocr','image_ocr','image','attachment_id','Локальный Tesseract: русский и английский текст из пикселей выбранного изображения, bounding boxes и confidence. Без загрузки в облако.',max_length=68),
    ToolSpec('image_compare','image_compare','image','attachment_id','Сопоставить dHash с ранее выбранными локальными изображениями; сходство не доказывает одинаковое место съёмки.',max_length=68),
    ToolSpec('map_geocode','map_geocode','coordinates','place','Найти географических кандидатов по публичному топониму через ограниченный публичный Nominatim: единичный запрос, кэш и атрибуция, без массового геокодирования.',False,300),
    ToolSpec('map_overpass','map_overpass','coordinates','coordinates','Именованные достопримечательности в радиусе500м от заданных latitude,longitude через ограниченный публичный Overpass, кэш и backoff; координаты передаются провайдеру.',False,64),
    ToolSpec('map_wikimedia','map_wikimedia','coordinates','coordinates','MediaWiki Commons API: геотеги до20медиа в радиусе1км от latitude,longitude. Совпадение пикселей не проверяется; координаты передаются Commons.',False,64),
    ToolSpec('github_profile','github_profile','username','username','GitHub: настоящая публичная запись точного username через официальный API без персонального ключа.',max_length=39),
    ToolSpec('github_users','github_users','dork','query','GitHub: поиск публичных профилей по запросу через официальный API без ключа; совпадение имени не устанавливает личность.',max_length=256),
    ToolSpec('github_repositories','github_repositories','dork','query','GitHub: публичные репозитории по запросу, описания, язык и даты; без приватного кода и без ключа.',max_length=256),
    ToolSpec('hn_search','hn_search','dork','query','Hacker News Algolia: реальные публичные публикации/комментарии, автор, дата и текст при наличии, без ключа.',max_length=300),
    ToolSpec('hn_profile','hn_profile','username','username','Hacker News: точный публичный username, about, karma и дата через официальный Firebase API без ключа.',max_length=32),
    ToolSpec('openlibrary_search','openlibrary_search','dork','query','Open Library: поиск опубликованных книг, авторов, дат и идентификаторов через публичный API без ключа.',max_length=300),
    ToolSpec('wikipedia_search','wikipedia_search','dork','query','Wikipedia: поиск статей и фактическое извлечение вступительного текста через MediaWiki API без ключа.',max_length=300),
)
_BY_NAME = {spec.name: spec for spec in _SPECS}
_PUBLIC_SOURCES=frozenset(('github_profile','github_users','github_repositories','hn_search','hn_profile','openlibrary_search','wikipedia_search'))
# Multi-input operations still belong to this registry and the same agent loop.
from .integrations19.local_tools import INPUT_SCHEMAS as _LOCAL19_INPUTS
from .integrations19.public_tools import INPUT_SCHEMAS as _PUBLIC19_INPUTS
from .visual_models.tools import INPUT_SCHEMAS as _VISUAL_INPUTS
from .visual_models.pipeline import INPUT_SCHEMA as _VISUAL_PIPELINE_INPUT
_GRAPH_INPUT={'type':'object','properties':{
    'evidence_ids':{'type':'array','maxItems':100,'items':{'type':'string','minLength':23,'maxLength':23}},
    'entity_types':{'type':'array','maxItems':16,'items':{'type':'string','maxLength':30}},
    'entity_id':{'type':'string','minLength':28,'maxLength':28},
    'offset':{'type':'integer','minimum':0,'maximum':10000},
    'limit':{'type':'integer','minimum':1,'maximum':100}},'required':[],'additionalProperties':False}
_SPECS += (
    ToolSpec('visual_geoint','visual_model','visual_geoint','attachment_id','Единый Visual GEOINT: реальные EXIF/OCR, выбранные GeoCLIP/Waypoint, сравнение географических кандидатов и при известных параметрах ShadowFinder. Без GPS исследование продолжается. Результаты моделей — гипотезы, не установленное место. Локальный CPU, без передачи снимка в API.',input_schema=_VISUAL_PIPELINE_INPUT,execution_mode='LOCAL_MODEL',documentation_url='https://github.com/watsoncore/Granger-OSINT',category='geoint'),
    ToolSpec('geoclip_predict','visual_model','visual_geoint','attachment_id','GeoCLIP: локальные географические гипотезы по пикселям выбранного изображения даже без EXIF. Raw scores не вероятности. Нужен отдельно установленный CPU-runtime.',input_schema=_VISUAL_INPUTS['geoclip_predict'],execution_mode='LOCAL_MODEL',documentation_url='https://github.com/VicenteVivan/geo-clip',category='geoint'),
    ToolSpec('waypoint_predict','visual_model','visual_geoint','attachment_id','Waypoint: локальные DINOv2 + PLONK YFCC, географические гипотезы по пикселям без EXIF. Доли сэмплов не вероятность. Не угадывай место по слабым кандидатам.',input_schema=_VISUAL_INPUTS['waypoint_predict'],execution_mode='LOCAL_MODEL',documentation_url='https://github.com/KillaMeep/waypoint-osint',category='geoint'),
    ToolSpec('waypoint_match','visual_model','visual_geoint','attachment_id','Waypoint: локальное DISK/LightGlue-сопоставление двух выбранных пользователем изображений. Совпадения признаков не доказывают одно место.',input_schema=_VISUAL_INPUTS['waypoint_match'],execution_mode='LOCAL_MODEL',documentation_url='https://github.com/KillaMeep/waypoint-osint',category='geoint'),
    ToolSpec('tiktok_timestamp','local19','chronology','value','Локально извлечь UTC-время из поддержанного TikTok video ID или полного URL. Это кодируемое время, не независимая проверка публикации.',input_schema=_LOCAL19_INPUTS['tiktok_timestamp'],execution_mode='LOCAL_PYTHON',documentation_url='https://github.com/bellingcat/tiktok-timestamp',category='chronology'),
    ToolSpec('shadow_regions','local19','geoint_geometry','datetime_utc','ShadowFinder: вычислить неоднозначные географические полосы по известным UTC-дате/времени и высоте объекта/длине тени либо высоте Солнца. Не определяет место по одному фото; параметры не угадывать.',input_schema=_LOCAL19_INPUTS['shadow_regions'],execution_mode='LOCAL_PYTHON',documentation_url='https://github.com/bellingcat/ShadowFinder',category='geoint'),
    ToolSpec('role_classify','local19','social_analytics','titles','Локально классифицировать уже полученные англоязычные должности по ключевым словам LinkedIn Toolkit. Без LinkedIn login и Groq; эвристика не подтверждает трудоустройство.',input_schema=_LOCAL19_INPUTS['role_classify'],execution_mode='LOCAL_PYTHON',documentation_url='https://github.com/michaelelizarov/linkedin-osint-toolkit',category='social_graph'),
    ToolSpec('evidence_graph','graph','graph','entity_id','Получить локальные сущности, направления связей и основания из сохранённого evidence. Пагинация, фильтр по типам, соседи entity_id; не объединяет владельцев по никнейму.',input_schema=_GRAPH_INPUT,execution_mode='LOCAL_PYTHON',documentation_url='https://github.com/watsoncore/Granger-OSINT',category='social_graph'),
    ToolSpec('mail_dns','public19','email','email','MailAccess · независимое бесплатное ядро: проверить синтаксис email и публичные MX/SPF/DMARC домена. Не подтверждает ящик; письма, recovery и регистрацию не запускает.',input_schema=_PUBLIC19_INPUTS['mail_dns'],execution_mode='PUBLIC_API_NO_KEY',documentation_url='https://github.com/KatrielMoses/MailAccess',category='socmint'),
    ToolSpec('historical_contacts','public19','domain','domain','kronikier · ограниченный поиск исторически опубликованных email/телефонов в3илименее снимках Wayback. Исторические контакты не доказывают нынешнего владельца.',input_schema=_PUBLIC19_INPUTS['historical_contacts'],execution_mode='PUBLIC_API_NO_KEY',documentation_url='https://github.com/soxoj/kronikier',category='archives'),
    ToolSpec('x_post','public19','x_post','url','X Tweet Fetcher · один публичный пост по точному URL через документированный FxTwitter API без ключа. Не поиск, не лента и не доступ к закрытым/удалённым данным.',input_schema=_PUBLIC19_INPUTS['x_post'],execution_mode='PUBLIC_API_NO_KEY',documentation_url='https://github.com/ythx-101/x-tweet-fetcher',category='socmint'),
    ToolSpec('x_profile','public19','x_post','username','X Tweet Fetcher · один публичный профиль по точному username через FxTwitter API без ключа. Только опубликованные поля, не timeline, не владелец и не обход закрытого доступа.',input_schema=_PUBLIC19_INPUTS['x_profile'],execution_mode='PUBLIC_API_NO_KEY',documentation_url='https://github.com/ythx-101/x-tweet-fetcher',category='socmint'),
    ToolSpec('arctic_posts','public19','reddit','query','Arctic Shift: исторические Reddit-публикации с ограничением по author/subreddit, времени и лимиту20. Архив неполон; совпадение username не устанавливает личность.',input_schema=_PUBLIC19_INPUTS['arctic_posts'],execution_mode='PUBLIC_API_NO_KEY',documentation_url='https://github.com/ArthurHeitmann/arctic_shift',category='archives'),
    ToolSpec('arctic_comments','public19','reddit','query','Arctic Shift: исторические комментарии Reddit по author/subreddit, времени и лимиту20; без массового скачивания дампов и без персональных ключей.',input_schema=_PUBLIC19_INPUTS['arctic_comments'],execution_mode='PUBLIC_API_NO_KEY',documentation_url='https://github.com/ArthurHeitmann/arctic_shift',category='archives'),
    ToolSpec('nuclei_check','public19','active_security','target','Nuclei: только один HEAD-запрос к явно подтверждённому своему origin. Наблюдает статус и наличие HTTP-заголовков, не устанавливает уязвимость. Выключен по умолчанию; каждую цель подтверждает пользователь.',True,input_schema=_PUBLIC19_INPUTS['nuclei_check'],execution_mode='LOCAL_CLI',documentation_url='https://github.com/projectdiscovery/nuclei',category='security'),
)
_BY_NAME={spec.name:spec for spec in _SPECS}
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
    def __init__(self, settings, *, options=None, readiness=None, adapters=None, secret_getter=None, web_provider=None, redactions=(), attachment_ids=(), image_store=None):
        self.settings = settings
        self._options = {key: deepcopy(value) for key, value in dict(options or {}).items() if key in _BASE_OPTIONS or key in ("secrets", "google_api_key", "vk_token", "telegram_api_hash", "telegram_session", "instagram_session")}
        self._readiness = readiness or runtime_readiness
        self._secret_getter = secret_getter or get_secret
        self._adapters = {item.id: item for item in adapters} if adapters is not None and not isinstance(adapters, dict) else dict(adapters or {})
        self._web_provider = web_provider
        self._availability = {}
        self._last_executions = {}
        self._attachment_ids=set(attachment_ids)
        self._image_store=image_store
        self._mapping_client=None
        self.evidence = InvestigationEvidence()
        self._lock = threading.RLock()
        self._redactions = {value for value in redactions if isinstance(value, str) and len(value) >= 4}
        from .agent_browser import PublicPageReader
        self.web_reader = PublicPageReader(max_pages=getattr(settings, 'agent_page_limit', 0),
                                           max_depth=getattr(settings, 'agent_page_depth', 2),agent_model=getattr(settings,'deepseek_model',''))

    def seed_urls_from_user(self, text):
        """Only the human's actual text seeds initial URLs, never model output."""
        self.web_reader.seed_urls_from_user(text)

    def begin_investigation(self):
        self.web_reader.begin_run()

    def checkpoint_state(self):
        return {**self.web_reader.checkpoint_state(),'attachment_ids':sorted(self._attachment_ids)}

    def restore_investigation(self, records, state):
        self.evidence.restore(records, [])
        self.web_reader.restore_state(state, records)
        self.allow_attachments(state.get('attachment_ids',[]))

    def allow_attachments(self, identifiers):
        for value in identifiers:
            if isinstance(value,str) and re.fullmatch(r'img_[a-f0-9]{64}',value): self._attachment_ids.add(value)

    @staticmethod
    def timeout_for(name, requested):
        spec=_BY_NAME.get(name)
        # CPU model cold starts are materially slower than HTTP requests.
        # An overall investigation deadline still takes precedence.
        return max(requested,240 if name=='visual_geoint' else 180) if spec and spec.execution_mode=='LOCAL_MODEL' else requested

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
            value=deepcopy(cached[1])
            if spec.name in self._last_executions:
                value['last_execution']=deepcopy(self._last_executions[spec.name])
                value.setdefault('diagnostic',{})['execution_verified']=self._last_executions[spec.name]['status'] in ('complete','completed','empty')
            return value
        base = {"name": spec.name, "source": spec.source, "kind": spec.kind, "description": spec.description,
                "requires_approval": spec.requires_approval, "needs_confirmation": spec.requires_approval,
                "available": False, "state": "unavailable", "reason": "Инструмент недоступен."}
        if cancelled is not None and cancelled.is_set():
            base.update(state="cancelled", reason="Проверка отменена.")
            return base
        if spec.source == "web_read":
            base.update(available=True, state="unverified", reason="Прямое чтение обнаруженных публичных URL; DNS и каждый переход проверяются при запросе.")
        elif spec.source=='local19':
            from .integrations19.local_tools import readiness
            base.update(readiness(spec.name,self.settings))
        elif spec.source=='visual_model':
            from .visual_models.tools import readiness
            base.update(readiness())
        elif spec.source=='public19':
            from .integrations19.public_tools import readiness
            base.update(readiness(spec.name,self.settings))
        elif spec.source=='graph':
            base.update(available=True,state='ready',reason='Локальные связи только из уже сохранённых evidence; сеть и внешние ключи не используются.')
        elif spec.source == "evidence_get":
            base.update(available=True, state="ready", reason="Только уже полученные безопасные находки текущего диалога.")
        elif spec.source == "web_search":
            try:
                row = self._web().availability()
                base.update(available=bool(row.get("available")), state=str(row.get("state", "unverified")),
                            reason="Веб-источник проверяется фактическим запросом; наличие настроек не доказывает доступ к выдаче.")
            except (ImportError, RuntimeError, ValueError):
                base.update(reason="Модуль веб-поиска недоступен.")
        elif spec.source in _PUBLIC_SOURCES:
            base.update(available=True,state='ready',reason='Встроенный публичный адаптер без персонального ключа; сеть подтверждается только выполнением.')
        elif spec.source in ('github_repository','threat_feodo','hash_virustotal'):
            configured=spec.source!='hash_virustotal' or bool(self._secret('virustotal_api_key'))
            base.update(available=configured,state='ready' if configured else 'auth_required',
                reason='Локальный адаптер готов; внешний API ещё не проверен.' if configured else 'Нужен собственный API-ключ VirusTotal.')
        elif spec.kind in ('image','coordinates'):
            from .geoint_tools import readiness
            base.update(readiness(spec.source,self.settings,self._image_store))
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
                row = {"runtime_ready": False, 'state': 'configuration_error',
                       'message': 'Не удалось выполнить безопасную проверку окружения.',
                       'diagnostic': {'code':'probe_failed','remedy':'Проверьте папку источников и путь к Python.'}}
            base['diagnostic'] = deepcopy(row.get('diagnostic', {}))
            base['diagnostic'].update(runtime_ready=bool(row.get('runtime_ready')), probe_seconds=row.get('probe_seconds'), execution_verified=False)
            if row.get("runtime_ready"):
                missing = any(not options.get(name) for name in _AUTH.get(spec.source, ()) if name != "instagram_session")
                if spec.source == "telegram" and not options.get("telegram_api_id"):
                    missing = True
                if missing:
                    base.update(state="auth_required", reason="Окружение готово. Нужны собственные учётные данные источника; вход и права ещё не проверялись.")
                    base['diagnostic'].update(code='authorization_required',remedy='Сохраните собственный токен или сессию в защищённых настройках источника.')
                else:
                    base.update(available=True, state="configured_unverified" if spec.source in _AUTH else "ready",
                                reason=str(row.get('message') or "Окружение проверено.") + ' Внешний доступ подтверждается только результатом запроса.')
            else:
                base.update(state=row.get('state','unavailable'), reason=str(row.get('message') or 'Не готово исполняемое окружение источника.'))
        base.setdefault('diagnostic', {'code': 'local_ready' if base['available'] else base['state'],
            'runtime_ready':base['available'], 'execution_verified':False, 'checked_at':utc_now(),
            'remedy':'Доступ внешнего сервиса проверяется только явным запросом.' if base['available'] else
                     'Включите интеграцию в настройках.' if base['state']=='disabled' else 'Проверьте настройки инструмента.'})
        base['runtime_state']=base['state']
        with self._lock:
            if spec.name in self._last_executions:
                base['last_execution']=deepcopy(self._last_executions[spec.name])
                base['diagnostic']['execution_verified']=base['last_execution']['status'] in ('complete','completed','empty')
        if cancelled is None or not cancelled.is_set():
            with self._lock:
                self._availability[spec.name] = (time.monotonic(), deepcopy(base))
        return base

    def catalog(self, *, cancel_event=None, deadline=None, force_refresh=False, on_update=None):
        if force_refresh:
            with self._lock:
                self._availability.clear()
            from .engine.readiness import clear_readiness_cache
            clear_readiness_cache()
        # A cold discovery cannot consume the entire investigation deadline.
        end = min(deadline, time.monotonic() + 12) if deadline is not None else time.monotonic() + 12
        cancelled = _Cancellation(cancel_event, end)
        instant = {spec.name: self._state(spec, cancelled) for spec in _SPECS
                   if spec.source in ("web_search", "web_read", "domain_lookup", "ip_lookup", "evidence_get")}
        if callable(on_update):
            for row in instant.values():
                try:on_update(deepcopy(row))
                except Exception:pass
        # The existing worker transport has its own global two-process budget.
        # Cold import probes share that budget and never run on the GUI thread.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="GrangerPetToolReadiness") as pool:
            futures = [pool.submit(self._state,spec,cancelled) for spec in _SPECS if spec.name not in instant]
            checked = []
            for future in as_completed(futures):
                row = future.result();checked.append(row)
                if callable(on_update):
                    try:on_update(deepcopy(row))
                    except Exception:pass
        rows = {row["name"]: row for row in checked}
        rows.update(instant)
        from .tool_manifest import manifest, technical_state
        result=[rows[spec.name] for spec in _SPECS]
        for spec,row in zip(_SPECS,result):
            row.update(manifest=manifest(spec).to_dict(),readiness_status=technical_state(row),implemented=True)
        return result

    def schemas(self, *, cancel_event=None, deadline=None, task=None):
        from .tool_manifest import relevant_names
        selected=relevant_names(_SPECS,task)
        rows = {row["name"]: row for row in self.catalog(cancel_event=cancel_event, deadline=deadline)}
        tools = []
        for spec in _SPECS:
            if spec.name not in selected or not rows.get(spec.name,{}).get("available"):
                continue
            if spec.input_schema is not None:
                tools.append({'type':'function','function':{'name':spec.name,'description':spec.description,
                    'parameters':deepcopy(spec.input_schema)}})
                continue
            tools.append({"type": "function", "function": {"name": spec.name, "description": spec.description,
                "parameters": {"type": "object", "properties": {
                    spec.argument: {"type": "string", "minLength": 1, "maxLength": spec.max_length},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10 if spec.name == "web_search" else 20}},
                    "required": [spec.argument], "additionalProperties": False}}})
            if spec.source == 'evidence_get':
                tools[-1]['function']['parameters']['properties'].update(
                    focus={'type':'string','maxLength':300,'description':'Тема для выбора релевантного фрагмента сохранённой записи.'},
                    offset={'type':'integer','minimum':0,'maximum':16000,'description':'Начальный символ для точного чтения длинного текста.'},
                    length={'type':'integer','minimum':100,'maximum':6000,'description':'Длина фрагмента, оригинал остаётся в хранилище.'})
        return tools

    descriptions = schemas

    def _validate(self, spec, args):
        if spec.input_schema is not None:
            from .tool_inputs import validate_object
            arguments=validate_object(args,spec.input_schema)
            if spec.source=='visual_model':
                for field in ('attachment_id','reference_id'):
                    if field in arguments and (not re.fullmatch(r'img_[a-f0-9]{64}',arguments[field]) or arguments[field] not in self._attachment_ids):
                        raise ValueError('Изображение не выбрано пользователем для этой задачи.')
            summary=arguments.get(spec.argument)
            if not isinstance(summary,str):summary=json.dumps(arguments,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            return summary[:2000],arguments.get('limit',20),{'structured_arguments':arguments},None
        permitted = {spec.argument, 'limit'} | ({'focus','offset','length'} if spec.source=='evidence_get' else set())
        if not isinstance(args, dict) or set(args) - permitted or spec.argument not in args:
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
        if spec.kind in ('image','coordinates'):
            if spec.kind=='image':
                if not re.fullmatch(r'img_[a-f0-9]{64}',value) or value not in self._attachment_ids:
                    raise ValueError('Изображение не выбрано пользователем для этой задачи.')
            elif spec.source!='map_geocode':
                from .geoint.mapping import coordinates
                from .geoint import GeointError
                try: coordinates(value)
                except GeointError: raise ValueError('Некорректные координаты.') from None
            return value,limit,options,None
        if spec.source in _PUBLIC_SOURCES:
            from .public_sources import validate
            return validate(spec.source,value),limit,options,None
        if spec.source in ('github_repository','threat_feodo','hash_virustotal'):
            from .public_integrations import validate
            value=validate(spec.source,value)
            return value,limit,options,None
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
                if 'focus' in args and (not isinstance(args['focus'],str) or len(args['focus'])>300 or any(ord(c)<32 for c in args['focus'])):
                    raise ValueError('Некорректная тема фрагмента.')
                for field,low,high in (('offset',0,16000),('length',100,6000)):
                    if field in args and (type(args[field]) is not int or not low<=args[field]<=high):
                        raise ValueError('Некорректный диапазон фрагмента.')
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
        started=utc_now()
        result=self._execute(name,args,cancel_event=cancel_event,deadline=deadline,approved=approved,on_event=on_event)
        # Keep compatibility with the existing agent/evidence path while exposing
        # one versioned invocation contract for every success and failure.
        result.update(invocation_id=uuid.uuid4().hex,tool_id=result.get('tool',str(name)[:80]),
            started_at=result.get('started_at',started),finished_at=utc_now(),
            input_summary={'query':result.get('query','')},data={'results':deepcopy(result.get('results',[]))},
            evidence_ids=[r['evidence_id'] for r in result.get('results',[]) if r.get('evidence_id')],
            warnings=list(result.get('limitations',[])),errors=[result['error']] if result.get('error') else
            [] if result.get('status') in ('complete','completed','empty') else [result.get('status','error')])
        return result

    def _execute(self, name, args, *, cancel_event=None, deadline=None, approved=False, on_event=None):
        when = utc_now()
        started = time.monotonic()
        envelope = {"tool": str(name)[:80], "status": "invalid_arguments", "query": "", "obtained_at": when,
                    "started_at": when, "results": [], "sources": [], "limitations": []}
        spec = _BY_NAME.get(name) if isinstance(name, str) else None
        if spec is None:
            envelope.update(status="unknown_tool", error="Инструмент не зарегистрирован.")
            return envelope
        if deadline is None:
            deadline = time.monotonic() + self.timeout_for(name,25)
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
            envelope['context_selection'] = {key:args[key] for key in ('focus','offset','length') if key in args}
            with self._lock:
                self._last_executions[spec.name]={'status':envelope['status'],'obtained_at':when,
                    'result_count':len(envelope['results']),'error_code':'','kind':'local_record'}
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
        outcome=None
        try:
            if spec.input_schema is not None:
                outcome=self._structured_operation(spec,options['structured_arguments'],cancelled,deadline,approved,on_result=receive)
            elif spec.source == "web_read":
                # Search evidence is the URL authority. The model cannot invent
                # a new URL and gain network access through ordinary text.
                self.web_reader.add_evidence(self.evidence.records())
                outcome = self.web_reader.read(value, cancel_event=cancelled, deadline=deadline)
            elif spec.source == "web_search":
                outcome = self._web().search(value, limit=limit, cancel_event=cancelled, deadline=deadline)
            elif spec.source in ("domain_lookup", "ip_lookup"):
                from .agent_web import lookup_domain, lookup_ip
                outcome = (lookup_domain if spec.source == "domain_lookup" else lookup_ip)(value, cancel_event=cancelled, deadline=deadline)
            elif spec.source in _PUBLIC_SOURCES:
                from .public_sources import execute
                outcome=execute(spec.source,value,limit=limit,cancel_event=cancelled,deadline=deadline,agent_model=getattr(self.settings,'deepseek_model',''))
            elif spec.source in ('github_repository','threat_feodo','hash_virustotal'):
                from .public_integrations import execute
                outcome=execute(spec.source,value,secret=self._secret('virustotal_api_key') if spec.source=='hash_virustotal' else '',
                    cancel_event=cancelled,deadline=deadline)
            elif spec.kind in ('image','coordinates'):
                from .geoint_tools import execute,mapping_client
                if self._mapping_client is None: self._mapping_client=mapping_client(self.settings)
                outcome=execute(spec.source,value,settings=self.settings,store=self._image_store,maps=self._mapping_client,
                    cancel_event=cancelled,deadline=deadline)
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
            allowed = {"complete", "completed", "partial", "empty", "error", "timeout", "cancelled", "unavailable", "auth_required", "blocked", "limit_reached", "rate_limited", "invalid_arguments"}
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
            code=outcome.get('error_code')
            if isinstance(code,str) and re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}',code):envelope['error_code']=code
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
        error_code = redact(str(outcome.get('error_code') or (outcome.get('error') if spec.source=='web_read' else '') or ''), self._redactions) if isinstance(outcome,dict) else ''
        if not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,80}',error_code):error_code=''
        with self._lock:
            self._last_executions[spec.name]={'status':envelope['status'],'obtained_at':envelope['obtained_at'],
                'result_count':len(envelope['results']),'error_code':error_code, 'kind':'source_request'}
        return envelope

    def _structured_operation(self,spec,args,cancelled,deadline,approved,on_result=None):
        """Repository-owned dispatch, without model-defined handlers or paths."""
        if spec.source=='local19':
            from .integrations19.local_tools import execute
            from .integrations19.solar import LocalToolError
            try:data=execute(spec.name,args,cancel_event=cancelled,deadline=deadline,settings=self.settings)
            except LocalToolError as error:
                return {'status':error.code if error.code in ('cancelled','timeout','invalid_arguments') else 'error','error_code':error.code,'results':[],'limitations':[str(error)]}
            if spec.name=='shadow_regions':
                from .integrations19.local_tools import bound_shadow_evidence
                data=bound_shadow_evidence(data)
            url=data.get('source_url','');title={'tiktok_timestamp':'Время из TikTok ID','shadow_regions':'ShadowFinder · солнечная геометрия','role_classify':'Локальная классификация должностей'}[spec.name]
            description=(data.get('date_utc') or 'Получены результаты локального вычисления по явно переданным параметрам.')
        elif spec.source=='graph':
            from .evidence_graph import build
            records=self.evidence.records();ids=args.get('evidence_ids')
            if ids:
                if any(not re.fullmatch(r'ev_[a-f0-9]{20}',i) for i in ids):raise ValueError('Invalid evidence ID')
                selected={r['evidence_id']:r for r in records}
                if any(i not in selected for i in ids):raise ValueError('Evidence not in this conversation')
                records=[selected[i] for i in ids]
            data=build(records,limit=args.get('limit',50),offset=args.get('offset',0),entity_types=args.get('entity_types',()),center=args.get('entity_id',''),cancel_event=cancelled)
            data['request_arguments']=args
            title='Сущности и связи сохранённых свидетельств';url=''
            description=f"Сущностей: {data['total_entities']}; связей: {data['total_relations']}. Это отношения источников, не установленная общая личность."
        elif spec.source=='public19':
            from .integrations19.public_tools import execute
            return execute(spec.name,args,cancel_event=cancelled,deadline=deadline,settings=self.settings,approved=approved)
        elif spec.source=='visual_model':
            from .geoint_tools import attachment_store
            if spec.name=='visual_geoint':
                from .visual_models.pipeline import execute
                return execute(args,settings=self.settings,store=self._image_store or attachment_store(),cancel_event=cancelled,deadline=deadline,on_result=on_result)
            from .visual_models.tools import execute
            return execute(spec.name,args,store=self._image_store or attachment_store(),cancel_event=cancelled,deadline=deadline)
        else:raise ValueError('Unsupported structured operation')
        data={**data,'execution_mode':spec.execution_mode,'capability':spec.name,'source_record':True}
        identifier=hashlib.sha256(json.dumps(args,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()[:24]
        return {'status':'complete','results':[{'id':spec.name+':'+identifier,'title':title,'type':'evidence_graph' if spec.source=='graph' else 'local_computation',
            'platform':spec.name,'url':url,'description':description,'status':'computed','details':data,'sources':[spec.name]}],
            'limitations':data.get('warnings',[])}
