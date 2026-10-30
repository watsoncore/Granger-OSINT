"""Small user-triggered geographic lookups with application-wide quotas.

Public defaults are a deliberate limited single-user desktop integration, not
bulk geocoding, autocomplete, grid crawling or a resold API. Operators may change
the endpoints without a software update. No image is uploaded by these tools.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from copy import deepcopy
import json
import math
import threading
import time
from urllib.parse import urlsplit

import httpx

from .images import GeointError, _cancelled

USER_AGENT = "Granger-OSINT/3.1 (+https://github.com/watsoncore/Granger-OSINT)"
OSM_ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0 — https://www.openstreetmap.org/copyright"
COMMONS_ATTRIBUTION = "Wikimedia Commons; individual media licences and authors are listed on the original file pages."
_NETWORK_LOCK = threading.RLock()
_NEXT_REQUEST = {}
_NETWORK_CACHE = OrderedDict()
_REQUEST_TIMES = {}
DEFAULT_NOMINATIM = "https://nominatim.openstreetmap.org"
DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM_POLICY = "https://operations.osmfoundation.org/policies/nominatim/"
OVERPASS_POLICY = "https://dev.overpass-api.de/overpass-doc/en/preface/commons.html"


def coordinates(value):
    if not isinstance(value, str) or len(value) > 80:
        raise GeointError("invalid_coordinates", "Введите координаты как широта,долгота.")
    try:
        lat, lon = map(float, value.split(","))
    except (ValueError, TypeError):
        raise GeointError("invalid_coordinates", "Введите координаты как широта,долгота.") from None
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise GeointError("invalid_coordinates", "Широта должна быть от −90 до 90, долгота от −180 до 180.")
    return lat, lon


def _endpoint(value):
    if not value:
        return ""
    parsed = urlsplit(str(value))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GeointError("invalid_endpoint", "Картографический endpoint должен быть HTTPS URL без пароля и параметров.")
    return str(value).rstrip("/")


class MappingClient:
    def __init__(self, *, nominatim_endpoint="", overpass_endpoint="",
                 commons_endpoint="https://commons.wikimedia.org/w/api.php", transport=None,
                 min_interval=1.1, cache_seconds=3600):
        self.nominatim_endpoint = _endpoint(nominatim_endpoint or DEFAULT_NOMINATIM)
        self.overpass_endpoint = _endpoint(overpass_endpoint or DEFAULT_OVERPASS)
        self.commons_endpoint = _endpoint(commons_endpoint)
        self._transport = transport
        self._interval = max(1.1, float(min_interval))
        self._cache_seconds = max(60, float(cache_seconds))
        # Real clients share one application-wide request gate, including across
        # conversations. Explicit test transports remain isolated from live state.
        self._lock = _NETWORK_LOCK if transport is None else threading.RLock()
        self._next_request = _NEXT_REQUEST if transport is None else {}
        self._cache = _NETWORK_CACHE if transport is None else OrderedDict()
        self._request_times = _REQUEST_TIMES if transport is None else {}

    def readiness(self, tool):
        endpoint = {"map_geocode": self.nominatim_endpoint, "map_overpass": self.overpass_endpoint,
                    "map_wikimedia": self.commons_endpoint}.get(tool)
        return {"available": bool(endpoint), "state": "ready_local" if endpoint else "configuration_required",
                "reason": "Публичный режим для отдельных запросов готов без ключа. Доступ подтверждается только выполнением; массовые запросы запрещены." if endpoint else
                          "Картографический сервис не настроен.",
                "execution_verified": False}

    def _request(self, endpoint, params, cancel_event=None):
        from ..download_budget import check as check_bytes, consume
        check_bytes()
        _cancelled(cancel_event)
        if not endpoint:
            raise GeointError("endpoint_required", "Для этого инструмента нужен настроенный разрешённый endpoint.")
        key = endpoint + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        host = urlsplit(endpoint).netloc
        with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < self._cache_seconds:
                self._cache.move_to_end(key)
                return deepcopy(cached[1]), True
            # Conservative desktop quotas, deliberately far below bulk access.
            # This is independent from a model's investigation budget. Cache
            # hits do not consume public infrastructure or this rolling quota.
            recent = self._request_times.setdefault(host, deque())
            now = time.monotonic()
            while recent and recent[0] <= now - 3600:
                recent.popleft()
            limit = 30 if host == urlsplit(DEFAULT_NOMINATIM).netloc else 60
            if len(recent) >= limit:
                raise GeointError("rate_limited", "Исчерпан часовой лимит отдельных картографических запросов. Массовый сбор не поддерживается.")
            delay = self._next_request.get(host, 0) - time.monotonic()
            if delay > 5:
                raise GeointError("rate_limited", "Сервис временно ограничил запросы. Повторите позднее.")
            end = time.monotonic() + max(0, delay)
            while time.monotonic() < end:
                _cancelled(cancel_event)
                if cancel_event is not None:
                    cancel_event.wait(min(.05, end - time.monotonic()))
                else:
                    time.sleep(min(.05, end - time.monotonic()))
            _cancelled(cancel_event)
            self._next_request[host] = time.monotonic() + self._interval
            recent.append(time.monotonic())
            try:
                # The public Overpass queue may wait15s before a small query is
                # executed. A12s read timeout guaranteed premature failures on
                # a queued response. Stay inside the25s outer tool budget.
                timeout=httpx.Timeout(12,connect=2,read=20) if endpoint==self.overpass_endpoint else httpx.Timeout(12,connect=5)
                request_deadline=time.monotonic()+22
                with httpx.Client(transport=self._transport, headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                                  timeout=timeout, follow_redirects=False, trust_env=False) as client:
                    with client.stream("GET", endpoint, params=params) as response:
                        if response.status_code == 429:
                            try:
                                cooldown = max(1, min(3600, int(response.headers.get("Retry-After", 60))))
                            except ValueError:
                                cooldown = 60
                            self._next_request[host] = time.monotonic() + cooldown
                            raise GeointError("rate_limited", "Сервис ограничил частоту запросов (HTTP 429); автоматические повторы отключены.")
                        if response.status_code in (401, 403):
                            raise GeointError("access_denied", "Картографический сервис отказал в доступе; обход ограничений не выполняется.")
                        if response.status_code >= 500:
                            self._next_request[host] = time.monotonic() + 30
                            raise GeointError("service_unavailable", "Картографический сервис временно недоступен.")
                        if response.status_code != 200:
                            raise GeointError("http_error", "Картографический сервис вернул ошибку HTTP.")
                        content = bytearray()
                        for chunk in response.iter_bytes(64 * 1024):
                            consume(len(chunk))
                            _cancelled(cancel_event)
                            if time.monotonic()>request_deadline:
                                raise GeointError("timeout", "Истекло общее время картографического запроса.")
                            content.extend(chunk)
                            if len(content) > 1024 * 1024:
                                raise GeointError("response_limit", "Ответ картографического сервиса превышает 1 МиБ.")
                value = json.loads(content)
                if not isinstance(value, (dict, list)):
                    raise ValueError("invalid JSON root")
                self._cache[key] = (time.monotonic(), value)
                while len(self._cache) > 128:
                    self._cache.popitem(last=False)
                return deepcopy(value), False
            except GeointError:
                raise
            except httpx.TimeoutException as exc:
                self._next_request[host] = time.monotonic() + 15
                raise GeointError("timeout", "Истекло время ожидания картографического сервиса.") from exc
            except httpx.HTTPError as exc:
                raise GeointError("network_error", "Не удалось связаться с картографическим сервисом.") from exc
            except (ValueError, UnicodeError) as exc:
                raise GeointError("invalid_response", "Картографический сервис вернул некорректные данные.") from exc

    def execute(self, tool, value, cancel_event=None):
        begin = time.monotonic()
        if tool == "map_geocode":
            if not isinstance(value, str) or not value.strip() or len(value) > 300 or any(ord(char) < 32 for char in value):
                raise GeointError("invalid_query", "Укажите публичный топоним длиной до 300 символов.")
            data, cached = self._request(self.nominatim_endpoint + "/search" if self.nominatim_endpoint else "",
                                          {"q": value.strip(), "format": "jsonv2", "limit": 5, "addressdetails": 1}, cancel_event)
            if not isinstance(data, list):
                raise GeointError("invalid_response", "Геокодер вернул некорректный список.")
            places = []
            for item in data[:5]:
                try:
                    lat, lon = coordinates(str(item["lat"]) + "," + str(item["lon"]))
                    kind, identifier = str(item.get("osm_type", "")), int(item["osm_id"])
                    if kind not in ("node", "way", "relation") or identifier <= 0:
                        continue
                    places.append({"name": str(item.get("display_name", ""))[:700], "latitude": lat, "longitude": lon,
                                   "osm_type": kind, "osm_id": identifier,
                                   "source_url": f"https://www.openstreetmap.org/{kind}/{identifier}"})
                except (KeyError, TypeError, ValueError, GeointError):
                    continue
            if data and not places:
                raise GeointError("invalid_response", "Геокодер вернул записи, не соответствующие ожидаемой схеме.")
            return {"tool": tool, "status": "completed", "query": value, "places": places, "cached": cached,
                    "attribution": OSM_ATTRIBUTION, "duration_ms": round((time.monotonic() - begin) * 1000, 2),
                    "usage_policy": NOMINATIM_POLICY,
                    "limitations": ["Совпадение топонима не доказывает место съёмки; результаты — географические кандидаты.",
                                    "Только отдельные пользовательские запросы; нет autocomplete, массового или систематического геокодирования. Публичный default: максимум30 новых запросов/час, пауза1.1с и кэш1час."]}
        lat, lon = coordinates(value)
        if tool == "map_overpass":
            # No arbitrary Overpass QL, bulk areas, grids, selectors or model-generated code.
            query = f'[out:json][timeout:10][maxsize:1048576];nwr(around:500,{lat:.7f},{lon:.7f})["name"]["tourism"="attraction"];out center 20;'
            data, cached = self._request(self.overpass_endpoint, {"data": query}, cancel_event)
            if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
                raise GeointError("invalid_response", "Overpass вернул некорректный список объектов.")
            rows = []
            for item in data["elements"][:20]:
                try:
                    kind, identifier = item["type"], int(item["id"])
                    if kind not in ("node", "way", "relation"):
                        continue
                    center = item.get("center") or item
                    item_lat, item_lon = coordinates(str(center["lat"]) + "," + str(center["lon"]))
                    tags = item.get("tags", {})
                    rows.append({"name": str(tags.get("name", ""))[:300], "type": kind, "id": identifier,
                                 "latitude": item_lat, "longitude": item_lon,
                                 "url": f"https://www.openstreetmap.org/{kind}/{identifier}"})
                except (KeyError, TypeError, ValueError, GeointError):
                    continue
            if data["elements"] and not rows:
                raise GeointError("invalid_response", "Overpass вернул записи, не соответствующие ожидаемой схеме.")
            return {"tool": tool, "status": "completed", "query": value, "radius_m": 500,
                    "objects": rows, "cached": cached, "attribution": OSM_ATTRIBUTION,
                    "duration_ms": round((time.monotonic() - begin) * 1000, 2), "usage_policy": OVERPASS_POLICY,
                    "limitations": ["Возвращаются до 20 именованных достопримечательностей; полнота OSM не гарантируется.",
                                    "Близость объекта к координатам не подтверждает, что он изображён на фотографии."]}
        if tool == "map_wikimedia":
            data, cached = self._request(self.commons_endpoint, {"action": "query", "format": "json", "list": "geosearch",
                                         "gscoord": f"{lat}|{lon}", "gsradius": 1000, "gslimit": 20, "gsnamespace": 6}, cancel_event)
            if not isinstance(data, dict) or "error" in data or not isinstance(data.get("query", {}).get("geosearch"), list):
                raise GeointError("invalid_response", "Wikimedia вернула ошибку или некорректный список.")
            rows = []
            for item in data["query"]["geosearch"][:20]:
                try:
                    item_lat, item_lon = coordinates(str(item["lat"]) + "," + str(item["lon"]))
                    rows.append({"title": str(item["title"])[:500], "page_id": int(item["pageid"]),
                                 "latitude": item_lat, "longitude": item_lon, "distance_m": float(item["dist"]),
                                 "url": f"https://commons.wikimedia.org/?curid={int(item['pageid'])}"})
                except (KeyError, TypeError, ValueError, GeointError):
                    continue
            if data["query"]["geosearch"] and not rows:
                raise GeointError("invalid_response", "Wikimedia вернула записи, не соответствующие ожидаемой схеме.")
            return {"tool": tool, "status": "completed", "query": value, "radius_m": 1000, "media": rows,
                    "cached": cached, "attribution": COMMONS_ATTRIBUTION,
                    "duration_ms": round((time.monotonic() - begin) * 1000, 2),
                    "limitations": ["Получены геотеги файлов Commons; визуальное совпадение с загруженным фото не проверялось.",
                                    "Медиа не скачиваются автоматически; авторство и лицензию проверяйте на исходной странице."]}
        raise GeointError("unsupported_capability", "Этот картографический инструмент не поддерживается.")


def reverse_search_providers():
    """A truthful handoff catalogue, never a successful image-search result."""
    return [
        {"id": "google_lens", "name": "Google Lens", "mode": "manual_handoff", "url": "https://lens.google/",
         "documentation_url": "https://support.google.com/websearch/answer/1325808", "automated": False,
         "reason": "Официальная справка описывает ручную загрузку. Публичный Lens API не подключён."},
        {"id": "yandex_images", "name": "Яндекс Картинки", "mode": "manual_handoff", "url": "https://yandex.com/images/",
         "documentation_url": "https://yandex.com/support/images/en/similar", "automated": False,
         "reason": "Ручной поиск в интерфейсе. Официальный Yandex SearchByImage подключается отдельно с вашим ключом и разрешением на передачу снимка."},
        {"id": "bing_visual_search", "name": "Bing Visual Search API", "mode": "unavailable", "automated": False,
         "documentation_url": "https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement",
         "reason": "Прежние Bing Search APIs выведены из эксплуатации 11.08.2025; замена reverse-image API не подключена."},
        {"id": "tineye", "name": "TinEye", "mode": "manual_handoff", "url": "https://tineye.com/",
         "documentation_url": "https://services.tineye.com/TinEyeAPI", "automated": False,
         "reason": "Коммерческий TinEye API требует отдельного доступа; credentials и выполнение здесь не проверены."},
    ]
