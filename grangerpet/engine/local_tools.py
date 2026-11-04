"""Actual calls into supplied vendor code, kept outside the GUI's interpreter.

No vendor files are patched. Explicit Maigret modes use the original database;
adapters do not activate CAPTCHA solvers, TLS impersonation, login or recovery.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit

FOLDERS = {"maigret": "maigret-main", "blackbird": "blackbird-main", "snoop": "snoop-master",
           "holehe": "holehe-master", "phoneinfoga": "phoneinfoga-master", "social_analyzer": "social-analyzer-main"}


def _outcome(source, results, *, checked=0, message="", failures=0):
    return {"source": source, "status": "partial" if results and failures else "complete" if results else "error" if failures and failures >= checked else "partial" if failures else "empty",
            "results": results, "checked": checked, "message": message}


def _result(source, name, username, url, *, description="", details=None, type="profile", status="detected"):
    return {"id": f"{name}:{username}", "title": f"{name} · {username}", "type": type, "platform": name,
            "url": url, "description": description or "Источник обнаружил публичный профиль с этим идентификатором. Совпадение никнейма не доказывает принадлежность одному человеку.",
            "details": details or {}, "status": status, "sources": [source]}


def _emit(options, result):
    if callable(options.get("_emit")):
        options["_emit"]({"event": "result", "result": result})


def _limit(query):
    return max(1, min(50, int(query.get("limit", 20))))


def _timeout(query):
    return max(1, min(7, float(query.get("timeout", 25)) / 3))


def _selected(options, name, url=""):
    selected = options.get("profile_sites", [])
    return not selected or any(str(value).casefold() in (name + " " + url).casefold() for value in selected)


def maigret_adapter(root, query, options):
    try:
        from .maigret_bridge import run_adapter
    except ImportError:
        from maigret_bridge import run_adapter
    return run_adapter(root, query, options)


def blackbird_adapter(root, query, options):
    sys.path.insert(0, str(root / "src"))
    from modules.core.username import checkSite
    from rich.console import Console
    import aiohttp
    cache = Path(options["tools_root"]) / ".toolenvs/blackbird/wmn-data.json"
    database = root / "data/wmn-data.json"
    if not database.is_file():
        database = cache
    if not database.is_file():
        return {"source": "blackbird", "status": "unavailable", "results": [],
                "message": "Нет локальной базы площадок. Установщик подключений загрузит официальную базу WhatsMyName один раз."}
    data = json.loads(database.read_text(encoding="utf-8"))
    sites = [site for site in data.get("sites", []) if not site.get("valid", True) is False
             and site.get("cat") != "xx NSFW xx" and site.get("uri_check", "").startswith("https://")
             and _selected(options, site.get("name", ""), site.get("uri_check", ""))][:_limit(query)]
    config = SimpleNamespace(timeout=_timeout(query), proxy=None, verbose=False,
        console=Console(file=io.StringIO(), force_terminal=False), metadata_params={"sites": {}},
        ai=False, aiModel=None, instagram_session_id=None, dump=False, currentUser=query["text"],
        userAgent="GrangerPet/2.0 (public-profile-check)")
    bad_http = [0]
    # Vendor code requests ssl=False. Retain its real detection logic but enforce
    # normal CA validation in the supplied session, without editing vendor files.
    class VerifiedSession:
        def __init__(self, session):
            self.session = session
        async def request(self, method, url, **kwargs):
            kwargs["ssl"] = True
            kwargs["max_redirects"] = 4
            response = await self.session.request(method, url, **kwargs)
            if response.status in (401, 403, 429) or response.status >= 500:
                bad_http[0] += 1
            return response
    results = []
    async def run():
        sem = asyncio.Semaphore(3)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=_timeout(query))) as session:
            tasks = [checkSite(site, "GET", site["uri_check"].replace("{account}", query["text"]), VerifiedSession(session), sem, config) for site in sites]
            rows = []
            for task in asyncio.as_completed(tasks):
                item = await task
                rows.append(item)
                if item.get("status") == "FOUND":
                    result = _result("blackbird", item["name"], query["text"], item["url"],
                                     details={"category": item.get("category"), "verification": "WhatsMyName response rule via Blackbird"})
                    results.append(result)
                    _emit(options, result)
            return rows
    raw = asyncio.run(run())
    failures = min(len(sites), bad_http[0] + sum(row.get("status") in ("ERROR", "NONE") for row in raw))
    return _outcome("blackbird", results, checked=len(sites), failures=failures,
                    message=f"Проверено: {len(sites)}. Ограничений или ошибок: {failures}.")


def snoop_adapter(root, query, options):
    if query["text"].casefold() in ("snoop", "snoop project", "snoop_project", "snoop-project", "snooppr"):
        return {"source": "snoop", "status": "unavailable", "results": [],
                "message": "Этот никнейм зарезервирован локальным источником. Остальные источники продолжат поиск."}
    # Snoop's import reads domainlist.txt relative to cwd and creates results/.
    # Supply only that required read-only asset inside a disposable working copy.
    original = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="grangerpet-snoop-") as temporary:
        shutil.copyfile(root / "domainlist.txt", Path(temporary) / "domainlist.txt")
        try:
            os.chdir(temporary)
            return _snoop_run(root, query, options)
        finally:
            os.chdir(original)


def _snoop_run(root, query, options):
    sys.path.insert(0, str(root))
    import snoop
    import snoopbanner
    snoop.license()  # Respect the installed demo's expiry; no bypass.
    database = snoopbanner.DB(str(root / "BDdemo"))
    selected = dict([(name, item) for name, item in database.items()
                     if _selected(options, name, item.get("urlMain", ""))][:_limit(query)])
    if not selected:
        return _outcome("snoop", [], checked=0, message="Подходящих площадок в локальной Demo-базе нет.")
    raw, executor, _ = snoop.snoop(query["text"], selected, norm=True, reports=False, user=False, lst_username=[query["text"]],
                                  speed=3, print_found_only=True, timeout=_timeout(query), color=False, cert=True)
    if executor:
        executor.shutdown(wait=True)
    if not isinstance(raw, dict):
        return _outcome("snoop", [], checked=0)
    results = []
    for name, item in raw.items():
        # Vendor strings are localized; only its explicit affirmative is a hit.
        if str(item.get("exists", "")).casefold() in ("найден!", "найден", "found", "yes"):
            result = _result("snoop", name, query["text"], item.get("url_user", ""), details={"http_status": item.get("http_status")})
            results.append(result)
            _emit(options, result)
    failures = sum(str(item.get("exists", "")).casefold() == "блок" for item in raw.values())
    return _outcome("snoop", results, checked=len(selected), failures=failures,
                    message=f"Локальная Demo: только личное использование, в EXE не включается. Ограничений: {failures}.")


def social_adapter(root, query, options):
    specification = importlib.util.spec_from_file_location("grangerpet_social_analyzer", root / "app.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    import requests
    request_count, counter_lock = [0], threading.Lock()
    class VerifiedSession(requests.Session):
        def request(self, method, url, **kwargs):
            with counter_lock:
                if request_count[0] >= _limit(query):
                    raise requests.exceptions.RequestException("Source request budget exhausted")
                request_count[0] += 1
            kwargs["verify"] = True
            kwargs["timeout"] = min(float(kwargs.get("timeout", 5)), _timeout(query))
            return super().request(method, url, **kwargs)
    module.Session = VerifiedSession
    analyzer = module.SocialAnalyzer(silent=True)
    analyzer.workers = 3
    # top= uses the tool's own rank-limited site selection and actual detection.
    websites = " ".join(options.get("profile_sites", [])) or "all"
    raw = analyzer.run_as_object(username=query["text"], websites=websites, top=str(_limit(query)),
        timeout=0, silent=True, output="json", profiles="detected", method="find",
        filter="good", logs=False, screenshots=False, metadata=False, extract=False, ret=True)
    results = []
    for item in raw.get("detected", []):
        url = item.get("link", "")
        if not url.startswith(("https://", "http://")):
            continue
        name = urlsplit(url).hostname or "Web"
        result = _result("social_analyzer", name, query["text"], url,
            description=str(item.get("title", "Публичная страница, обнаруженная правилом источника.")),
            details={"rate": item.get("rate"), "source_status": item.get("status"), "verification": "Heuristic public-page detection; not identity confirmation"}, status="heuristic")
        results.append(result)
        _emit(options, result)
    return _outcome("social_analyzer", results, checked=request_count[0])


def holehe_adapter(root, query, options):
    sys.path.insert(0, str(root))
    import httpx
    import trio
    # Read actual module declarations and use only non-recovery GET probes.
    # This excludes modules which send password-reset or confirmation messages.
    candidates = []
    for path in sorted((root / "holehe/modules").glob("*/*.py")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        if 'method="other"' not in text.replace(" ", "") and 'method="register"' not in text.replace(" ", ""):
            continue
        if any(token in text for token in ("client.post(", "client.put(", "client.patch(", "password_reset", "send_email", "sendemail", "/recover", "/forgot")):
            continue
        candidates.append(path)
    # Public Gravatar lookup first; then bounded, read-only registration checks.
    candidates.sort(key=lambda path: (path.stem != "gravatar", path.stem))
    candidates = candidates[:min(_limit(query), 8)]
    rows = []
    bad_http = [0]
    class TrackedClient(httpx.AsyncClient):
        async def get(self, *args, **kwargs):
            response = await super().get(*args, **kwargs)
            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                bad_http[0] += 1
            return response
    async def run():
        limiter = trio.CapacityLimiter(3)
        async with TrackedClient(timeout=_timeout(query), follow_redirects=True) as client:
            async def check(path):
                module_name = "holehe.modules." + path.parent.name + "." + path.stem
                module = importlib.import_module(module_name)
                func = getattr(module, path.stem)
                async with limiter:
                    try:
                        with trio.move_on_after(_timeout(query)) as scope:
                            await func(query["text"], client, rows)
                        if scope.cancelled_caught:
                            rows.append({"name": path.stem, "error": True, "timeout": True})
                    except Exception:
                        rows.append({"name": path.stem, "error": True})
            async with trio.open_nursery() as nursery:
                for path in candidates:
                    nursery.start_soon(check, path)
    trio.run(run)
    results = []
    for item in rows:
        if item.get("exists") is not True or item.get("rateLimit") or item.get("error"):
            continue
        domain = item.get("domain", "")
        result = _result("holehe", item.get("name", domain), query["text"], "https://" + domain if domain else "",
            type="email_check", description="Сервис сообщил наличие email. Это проверка регистрации, а не доказательство личности владельца.",
            details={"method": item.get("method"), "email": query["text"], "confirmed_data": item.get("others")}, status="registration_detected")
        # Registration checks do not provide a personal-profile URL. Keep the
        # email-qualified ID and no URL so different registrations never merge.
        result["url"] = ""
        result["details"]["service_url"] = "https://" + domain if domain else ""
        results.append(result)
        _emit(options, result)
    failures = min(len(candidates), bad_http[0] + sum(bool(item.get("error") or item.get("rateLimit")) for item in rows))
    return _outcome("holehe", results, checked=len(candidates), failures=failures,
                    message=f"Проверено: {len(candidates)}; ограничений/ошибок: {failures}. Восстановление паролей отключено.")


def run_adapter(source, query, options):
    root = Path(options["tools_root"]) / FOLDERS[source]
    if source == "phoneinfoga":
        return {"source": source, "status": "unavailable", "results": [],
                "message": "Требуется сборка локального PhoneInfoga bridge через scripts/setup_sources.py с Go."}
    functions = {"maigret": maigret_adapter, "blackbird": blackbird_adapter, "snoop": snoop_adapter,
                 "social_analyzer": social_adapter, "holehe": holehe_adapter}
    return functions[source](root, query, options)
