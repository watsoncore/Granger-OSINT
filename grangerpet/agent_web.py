"""Bounded public web/DNS/network observations for the local agent registry.

No browser automation, challenge solving, arbitrary page fetch or paid service
registration. Search uses the existing Google configuration when present;
otherwise one ordinary public DuckDuckGo HTML request is attempted.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import logging
import re
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import httpx

from .search import SearchError, parse_results


_DDG = "https://html.duckduckgo.com/html/"
_GOOGLE = "https://www.googleapis.com/customsearch/v1"
_MAX_BYTES = 2_000_000


class _PrivateSearchURLFilter(logging.Filter):
    def filter(self, record):
        # CSE requires a key in its URL. HTTPX's ordinary INFO line must not
        # turn that existing source credential into a log entry.
        if "www.googleapis.com/customsearch/v1" in record.getMessage():
            record.msg, record.args = "HTTP request: Google search (private URL omitted)", ()
        return True


_logger = logging.getLogger("httpx")
if not any(isinstance(item, _PrivateSearchURLFilter) for item in _logger.filters):
    _logger.addFilter(_PrivateSearchURLFilter())


class _FetchError(RuntimeError):
    def __init__(self, code, *, status="unavailable", http_status=None):
        self.code, self.status, self.http_status = code, status, http_status
        super().__init__(code)


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _clean(value, maximum=1200):
    return " ".join(str(value or "").split())[:maximum]


def _check_cancel(cancelled, deadline):
    if cancelled is not None and cancelled.is_set():
        raise _FetchError("cancelled", status="cancelled")
    if deadline is not None and time.monotonic() >= deadline:
        raise _FetchError("timeout", status="timeout")


def _run(factory, *, cancel_event=None, deadline=None, timeout=15):
    deadline = min(deadline, time.monotonic() + timeout) if deadline is not None else time.monotonic() + timeout
    async def run():
        _check_cancel(cancel_event, deadline)
        task = asyncio.create_task(factory())
        try:
            while not task.done():
                _check_cancel(cancel_event, deadline)
                await asyncio.wait({task}, timeout=.03)
            _check_cancel(cancel_event, deadline)
            return await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    try:
        return asyncio.run(run())
    except _FetchError:
        raise
    except (httpx.TimeoutException, TimeoutError):
        raise _FetchError("timeout", status="timeout") from None
    except (httpx.TransportError, OSError):
        raise _FetchError("network") from None
    except (ValueError, TypeError, UnicodeError):
        raise _FetchError("invalid_response") from None


def _client(factory=None):
    return (factory or httpx.AsyncClient)(timeout=httpx.Timeout(10), follow_redirects=False,
        headers={"User-Agent": "GrangerPet/2 public-source-research", "Accept": "application/json,text/html"})


async def _fetch(client, url, *, params=None):
    async with client.stream("GET", url, params=params) as response:
        if response.status_code != 200:
            raise _FetchError("http_" + str(response.status_code), http_status=response.status_code)
        raw = bytearray()
        async for part in response.aiter_bytes():
            raw.extend(part)
            if len(raw) > _MAX_BYTES:
                raise _FetchError("response_too_large")
    return bytes(raw)


async def _json(client, url, *, params=None):
    try:
        value = json.loads((await _fetch(client, url, params=params)).decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        raise _FetchError("invalid_response") from None
    if not isinstance(value, dict):
        raise _FetchError("invalid_response")
    return value


def _public_host(host):
    host = str(host or "").strip().rstrip(".").lower()
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".invalid", ".test", ".example", ".onion", ".home.arpa")):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." in host
    return address.is_global and not address.is_multicast and not address.is_reserved and not address.is_unspecified


def _public_url(value):
    try:
        parsed = urlsplit(str(value))
        if parsed.scheme not in ("https", "http") or parsed.username or parsed.password or not _public_host(parsed.hostname):
            return ""
        if len(value) > 4096:
            return ""
        return str(value)
    except (ValueError, UnicodeError):
        return ""


def _search_url(value):
    value = urljoin(_DDG, value)
    parsed = urlsplit(value)
    if parsed.hostname in ("duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com"):
        value = parse_qs(parsed.query).get("uddg", [""])[0]
    return _public_url(value)


class _SearchHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.stack = [], []
        self.title, self.snippet = None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            return
        self.stack.append(tag)
        if tag == "a" and "result__a" in classes:
            self.title = {"depth": len(self.stack), "url": _search_url(attrs.get("href", "")), "text": []}
        if "result__snippet" in classes and self.rows:
            self.snippet = {"depth": len(self.stack), "text": []}

    def handle_endtag(self, tag):
        depth = len(self.stack)
        if self.title is not None and tag == "a" and depth == self.title["depth"]:
            if self.title["url"]:
                self.rows.append({"url": self.title["url"], "title": _clean("".join(self.title["text"]), 500), "snippet": ""})
            self.title = None
        if self.snippet is not None and depth == self.snippet["depth"]:
            self.rows[-1]["snippet"] = _clean("".join(self.snippet["text"]))
            self.snippet = None
        # Tolerate ordinary void elements / imperfect upstream HTML.
        if tag in self.stack:
            last = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[last:]

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_data(self, value):
        if self.title is not None:
            self.title["text"].append(value)
        if self.snippet is not None:
            self.snippet["text"].append(value)


def _record(source, query, title, url, description, *, kind="web", details=None):
    now = _utc()
    return {"id": hashlib.sha256((source + "|" + query + "|" + url + "|" + title).encode("utf-8")).hexdigest()[:24],
            "title": _clean(title, 500), "type": kind, "platform": source, "url": url,
            "description": _clean(description, 1800), "date": now, "status": "indexed" if kind == "web" else "metadata",
            "sources": [source], "details": {"query": query, "obtained_at": now,
                "verification": "Сведения получены от указанного публичного источника; принадлежность человеку не установлена.", **(details or {})}}


def _envelope(tool, query, *, status="complete", results=None, limitations=None, error_code=None):
    result = {"tool": tool, "status": status, "query": query, "obtained_at": _utc(),
              "results": results or [], "limitations": limitations or []}
    if error_code:
        result["error_code"] = error_code
    return result


class WebSearchProvider:
    def __init__(self, settings=None, options=None, *, client_factory=None):
        options = options or {}
        secrets = options.get("secrets") if isinstance(options.get("secrets"), dict) else {}
        self._key = str(options.get("google_api_key") or secrets.get("google_api_key") or getattr(settings, "api_key", "") or "")
        self._cx = str(options.get("google_cx") or options.get("api_cx") or getattr(settings, "api_cx", "") or "")
        self._factory, self._blocked = client_factory, None
        self.provider = "google_cse" if self._key and self._cx else "duckduckgo_html"

    def availability(self):
        return {"available": self._blocked is None, "state": "unavailable" if self._blocked else "configured" if self.provider == "google_cse" else "unverified",
                "provider": self.provider, "reason": self._blocked or ("Используется существующая настройка Google CSE." if self.provider == "google_cse" else "Публичный HTML-поиск без ключа; доступность проверяется самим запросом, возможны ограничения источника.")}

    def search(self, query, *, limit=5, cancel_event=None, deadline=None):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300 or any(ord(c) < 32 for c in query) or type(limit) is not int or not 1 <= limit <= 10:
            return _envelope("web_search", "", status="invalid_arguments", error_code="invalid_query")
        query = query.strip()
        if self._blocked:
            return _envelope("web_search", query, status="unavailable", limitations=[self._blocked], error_code="source_blocked")
        async def operation():
            async with _client(self._factory) as client:
                if self.provider == "google_cse":
                    payload = await _json(client, _GOOGLE, params={"key": self._key, "cx": self._cx, "q": query, "num": limit, "hl": "ru"})
                    try:
                        rows = parse_results(payload, query)
                    except SearchError:
                        raise _FetchError("provider_rejected") from None
                    records = [_record("google_cse", query, row.title, row.url, row.snippet) for row in rows[:limit] if _public_url(row.url)]
                    return _envelope("web_search", query, status="complete" if records else "empty", results=records,
                        limitations=["Выдача индекса не гарантирует полноту упоминаний; фрагменты не проверяют содержимое страницы."])
                html = (await _fetch(client, _DDG, params={"q": query})).decode("utf-8", errors="replace")
                lowered = html.lower()
                if any(marker in lowered for marker in ("anomaly.js", "anomaly-modal", "challenge-form", "bots use duckduckgo")):
                    raise _FetchError("source_challenge")
                parser = _SearchHTML()
                parser.feed(html)
                records, seen = [], set()
                for row in parser.rows:
                    if row["url"] in seen or not row["title"]:
                        continue
                    seen.add(row["url"])
                    records.append(_record("duckduckgo_html", query, row["title"], row["url"], row["snippet"] or "Описание не предоставлено источником."))
                    if len(records) >= limit:
                        break
                if not records and not any(marker in lowered for marker in ("no-results", "no results found", "no more results")):
                    raise _FetchError("unrecognized_search_response")
                return _envelope("web_search", query, status="complete" if records else "empty", results=records,
                    limitations=["Публичная HTML-выдача ограничена источником и может блокироваться. Найденный URL не доказывает принадлежность аккаунта."])
        try:
            return _run(operation, cancel_event=cancel_event, deadline=deadline, timeout=15)
        except _FetchError as error:
            reason = ("Источник ограничил автоматический доступ. CAPTCHA, авторизация и ограничения не обходились."
                      if error.code in ("source_challenge", "http_202", "http_401", "http_403", "http_429") else
                      "Веб-поиск сейчас не выполнил запрос; сгенерированная выдача не подставляется.")
            if error.code in ("source_challenge", "http_202", "http_401", "http_403", "http_429"):
                self._blocked = reason
            return _envelope("web_search", query, status=error.status, limitations=[reason], error_code=error.code)


def _domain(value):
    if not isinstance(value, str) or len(value) > 253 or any(c in value for c in "/:@%\\"):
        raise ValueError()
    domain = value.strip().rstrip(".").lower().encode("idna").decode("ascii")
    labels = domain.split(".")
    if len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels) or not _public_host(domain):
        raise ValueError()
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        return domain
    raise ValueError()


def lookup_domain(domain, *, cancel_event=None, deadline=None, client_factory=None):
    try:
        domain = _domain(domain)
    except (ValueError, UnicodeError):
        return _envelope("domain_lookup", "", status="invalid_arguments", error_code="public_domain_required")
    records, limitations = [], []
    async def operation():
        async with _client(client_factory) as client:
            for kind in ("A", "MX", "NS"):
                _check_cancel(cancel_event, deadline)
                try:
                    data = await _json(client, "https://dns.google/resolve", params={"name": domain, "type": kind})
                    if data.get("Status") not in (0, 3):
                        limitations.append("DNS-источник не завершил проверку " + kind + ".")
                        continue
                    answers = data.get("Answer", []) if isinstance(data.get("Answer", []), list) else []
                    if not answers:
                        url = "https://dns.google/resolve?" + urlencode({"name": domain, "type": kind})
                        records.append(_record("google_dns", domain, "DNS · " + kind + " · " + ("NXDOMAIN" if data["Status"] == 3 else "нет записей"), url,
                            "Ответ публичного резолвера; отсутствие DNS-записи не устанавливает статус регистрации домена.", kind="domain",
                            details={"record_type": kind, "response_code": data["Status"], "answer_count": 0}))
                    for row in answers[:20]:
                        if not isinstance(row, dict) or not isinstance(row.get("data"), str):
                            continue
                        value = _clean(row["data"], 800)
                        url = "https://dns.google/resolve?" + urlencode({"name": domain, "type": kind})
                        actual_type = {1: "A", 2: "NS", 5: "CNAME", 15: "MX", 16: "TXT", 28: "AAAA"}.get(row.get("type"), "OTHER")
                        records.append(_record("google_dns", domain, actual_type + " · " + value, url, "Публичная DNS-запись.", kind="domain",
                            details={"record_type": actual_type, "query_type": kind, "value": value, "ttl": row.get("TTL") if type(row.get("TTL")) is int else None}))
                except _FetchError:
                    limitations.append("Публичный DNS-источник недоступен для " + kind + ".")
            endpoints = {"com": "https://rdap.verisign.com/com/v1/domain/", "net": "https://rdap.verisign.com/net/v1/domain/",
                         "org": "https://rdap.publicinterestregistry.org/rdap/domain/"}
            endpoint = endpoints.get(domain.rsplit(".", 1)[-1])
            if endpoint:
                _check_cancel(cancel_event, deadline)
                try:
                    url = endpoint + domain
                    data = await _json(client, url)
                    if not isinstance(data.get("objectClassName"), str) or data.get("objectClassName") != "domain":
                        raise _FetchError("invalid_response")
                    details = {"domain": _clean(data.get("ldhName") or domain, 253), "handle": _clean(data.get("handle"), 200),
                               "status": [_clean(s, 100) for s in data.get("status", [])[:10]] if isinstance(data.get("status"), list) else []}
                    records.append(_record("rdap_registry", domain, "RDAP · " + domain, url,
                        "Публичная регистрационная запись. Скрытые контакты не восстанавливаются.", kind="domain", details=details))
                except _FetchError:
                    limitations.append("RDAP-реестр не предоставил запись; это не доказывает отсутствие регистрации.")
            else:
                limitations.append("RDAP реализован для .com/.net/.org; для этой зоны выполнен только DNS.")
        return _envelope("domain_lookup", domain, status="partial" if records and limitations else "complete" if records else "unavailable" if limitations else "empty", results=records, limitations=limitations)
    try:
        return _run(operation, cancel_event=cancel_event, deadline=deadline, timeout=25)
    except _FetchError as error:
        return _envelope("domain_lookup", domain, status=error.status, results=records, error_code=error.code, limitations=limitations + ["Доменная проверка прервана или источник недоступен; полученные записи сохранены."])


def lookup_ip(address, *, cancel_event=None, deadline=None, client_factory=None):
    try:
        if not isinstance(address, str) or "%" in address or len(address) > 45:
            raise ValueError()
        value = ipaddress.ip_address(address.strip())
        if not value.is_global or value.is_multicast or value.is_reserved or value.is_unspecified:
            raise ValueError()
        address = str(value)
    except ValueError:
        return _envelope("ip_lookup", "", status="invalid_arguments", error_code="public_ip_required")
    async def operation():
        async with _client(client_factory) as client:
            endpoint = "https://stat.ripe.net/data/network-info/data.json"
            payload = await _json(client, endpoint, params={"resource": address})
            data = payload.get("data")
            if payload.get("status") != "ok" or not isinstance(data, dict) or not isinstance(data.get("asns"), list):
                raise _FetchError("invalid_response")
            asns = [str(n) for n in data["asns"][:10] if (type(n) is int and n > 0) or isinstance(n, str) and re.fullmatch(r"[0-9]{1,10}", n)]
            prefix = _clean(data.get("prefix"), 100)
            if not asns and not prefix:
                return _envelope("ip_lookup", address, status="empty", limitations=["RIPEstat не сообщил ASN или сеть; это не геолокация и не идентификация владельца."])
            record = _record("ripestat", address, "Сеть IP · " + address, endpoint + "?" + urlencode({"resource": address}),
                "Публичные сведения маршрутизации RIPEstat.", kind="ip", details={"address": address, "prefix": prefix, "asns": asns})
            return _envelope("ip_lookup", address, results=[record], limitations=["ASN и префикс — сведения о сети, не точный адрес или личность пользователя. Порты не сканировались."])
    try:
        return _run(operation, cancel_event=cancel_event, deadline=deadline, timeout=12)
    except _FetchError as error:
        return _envelope("ip_lookup", address, status=error.status, error_code=error.code, limitations=["Публичный источник сетевых сведений сейчас недоступен."])
