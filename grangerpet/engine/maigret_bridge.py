"""Run the original, installed Maigret engine, with explicit measured coverage.

This module is also loaded as a sibling by the isolated worker. Vendor files,
databases, settings and the user's profile are never written.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import logging
from pathlib import Path
import re
import ssl
import sys
import time
from urllib.parse import quote, urljoin, urlsplit

MAX_RESPONSE_BYTES = 4_000_000


class BoundedContent:
    """Proxy the original response stream; never hand detection truncated HTML."""
    def __init__(self, content, state, maximum=MAX_RESPONSE_BYTES):
        self.content, self.state, self.maximum, self.received = content, state, maximum, 0

    def __getattr__(self, name):
        return getattr(self.content, name)

    async def read(self, n=-1):
        async def chunk(size):
            value=await self.content.read(min(size,self.maximum-self.received+1))
            self.received+=len(value)
            if self.received>self.maximum:
                self.state['body_limit_exceeded']=True
                raise ValueError('Response body exceeds public page budget')
            return value
        if n is not None and n>=0:
            return await chunk(n)
        parts=[]
        while True:
            value=await chunk(min(65536,self.maximum-self.received+1))
            if not value:break
            parts.append(value)
        return b''.join(parts)

try:
    from .maigret_contracts import normalize_options
except ImportError:  # standalone worker
    from maigret_contracts import normalize_options


def public_https_url(value):
    """Validate literal hosts too: aiohttp need not call a resolver for them."""
    p = urlsplit(str(value))
    host = (p.hostname or "").rstrip(".").lower()
    if (p.scheme != "https" or not host or p.username or p.password or
            p.port not in (None, 443) or any(ord(c) < 33 for c in str(value))):
        raise ValueError("Non-public HTTPS URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.endswith((".local", ".localhost", ".internal", ".onion", ".i2p")):
            raise ValueError("Non-public host")
    else:
        if not address.is_global or address.is_multicast:
            raise ValueError("Non-public address")
    return str(value)


def formatted_url(site, username, template=None):
    value = (template if template is not None else site.url).format(
        urlMain=site.url_main, urlSubpath=site.url_subpath, username=quote(username))
    return re.sub("(?<!:)/+", "/", value)


def skip_reason(site, username):
    if getattr(site, "similar_search", False):
        return "similar_search"
    if getattr(site, "protection", None) or getattr(site, "tls_fingerprint", None):
        return "protected"
    if getattr(site, "activation", None):
        return "activation"
    if {str(key).lower() for key in (getattr(site, "headers", None) or {})} & {"authorization", "proxy-authorization", "cookie"}:
        return "credential_headers"
    protocol = getattr(site, "protocol", "")
    if protocol not in ("", "http", "https"):
        return "unsupported_protocol:" + str(protocol)
    if getattr(site, "request_method", "GET").upper() not in ("", "GET", "HEAD") or getattr(site, "request_payload", None):
        return "non_read_method"
    if set(getattr(site, "tags", ())) & {"porn", "nsfw", "tor", "i2p"}:
        return "excluded_category"
    try:
        public_https_url(formatted_url(site, username))
        probe = getattr(site, "url_probe", None)
        if probe:
            public_https_url(formatted_url(site, username, probe))
    except (ValueError, KeyError, AttributeError):
        return "non_public_https"
    return ""


def select_sites(database, username, config, defaults=None):
    defaults = defaults or {}
    mode = config["mode"]
    top = (config["site_count"] if mode in ("quick", "custom") else
           int(defaults.get("top_sites_count", 500)) if mode == "standard" else 0)
    kwargs = {"disabled": False}
    if top:
        kwargs["top"] = top
    if mode == "custom":
        kwargs.update(tags=config["tags"], names=config["sites"], excluded_tags=config["exclude_tags"])
    selected = database.ranked_sites_dict(**kwargs)
    if mode == "custom" and not config["include_mirrors"] and config["sites"]:
        names = {name.casefold() for name in config["sites"]}
        selected = {name: site for name, site in selected.items() if name.casefold() in names}
    eligible, skipped = {}, {}
    for name, site in selected.items():
        reason = skip_reason(site, username)
        if reason:
            skipped[name] = reason
        else:
            eligible[name] = site
    return selected, eligible, skipped


@contextmanager
def verified_transport(checking):
    """Use original HTTP/detection methods with verified, public-only transport.

    This checkout's original check() explicitly disables certificate validation.
    Substituting its transport constructor is necessary; its request and site
    detection implementation remain original. The substitution is worker-local.
    """
    import aiohttp
    from aiohttp.resolver import ThreadedResolver

    original = checking.SimpleAiohttpChecker

    class PublicResolver(ThreadedResolver):
        async def resolve(self, host, port=0, family=0):
            rows = await super().resolve(host, port, family)
            if not rows or any(not ipaddress.ip_address(row["host"]).is_global or
                               ipaddress.ip_address(row["host"]).is_multicast for row in rows):
                raise OSError("Non-public DNS destination")
            return rows

    class VerifiedChecker(original):
        async def check(self):
            try:
                public_https_url(self.url)
                body_state={}
                class BoundedResponse(aiohttp.ClientResponse):
                    async def start(self, connection):
                        result=await super().start(connection)
                        self.content=BoundedContent(self.content,body_state)
                        return result
                trace = aiohttp.TraceConfig()
                async def on_start(session, context, params):
                    public_https_url(str(params.url))
                    context.redirect_count = 0
                async def on_redirect(session, context, params):
                    context.redirect_count += 1
                    if context.redirect_count > 4:
                        raise ValueError("Redirect limit exceeded")
                    public_https_url(urljoin(str(params.url), params.response.headers.get("Location", "")))
                trace.on_request_start.append(on_start)
                trace.on_request_redirect.append(on_redirect)
                connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(), resolver=PublicResolver(), limit=1)
                async with aiohttp.ClientSession(connector=connector, trust_env=False,
                        cookie_jar=self.cookie_jar if self.cookie_jar else None, trace_configs=[trace],
                        response_class=BoundedResponse) as session:
                    content, status, error = await self._make_request(session, self.url, self.headers,
                        self.allow_redirects, self.timeout, self.method, self.logger, self.payload)
                if body_state.get('body_limit_exceeded'):
                    return '',0,checking.CheckError('Response size limit')
                return str(content) if content else "", status, error
            except (ValueError, OSError) as exc:
                # A policy refusal is unknown/unavailable, never "not found".
                return "", 0, checking.CheckError("Public transport policy", type(exc).__name__)

    checking.SimpleAiohttpChecker = VerifiedChecker
    try:
        yield VerifiedChecker
    finally:
        checking.SimpleAiohttpChecker = original


def classify(item):
    check = item.get("status")
    status = getattr(getattr(check, "status", None), "name", "UNKNOWN")
    error = getattr(check, "error", None)
    error_type = str(getattr(error, "type", ""))[:160]
    http = item.get("http_status")
    try:
        http = int(http)
    except (ValueError, TypeError):
        http = 0
    # Access restrictions take precedence even when a site rule misclassifies it.
    if http in (401, 403, 429) or any(x in error_type.lower() for x in ("captcha", "challenge", "cloudflare", "forbidden", "blocked")):
        return "blocked"
    if http >= 500:
        return "unavailable"
    if status == "CLAIMED":
        return "found"
    if status == "AVAILABLE":
        return "not_found"
    if status == "ILLEGAL":
        return "skipped"
    if any(x in error_type.lower() for x in ("timeout", "connect", "dns", "ssl", "request failed", "server", "transport", "proxy", "response size limit")):
        return "unavailable"
    if error_type and error_type not in ("Unknown", "Unknown error"):
        return "errors"
    return "unknown"


def _json_public(value):
    """Keep actual public extraction values, without retaining HTML/checker objects."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_public(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_public(v) for k, v in value.items()}
    return str(value)


def finding(name, username, item):
    check = item.get("status")
    url = item.get("url_user") or getattr(check, "site_url_user", "")
    public_https_url(url)
    metadata = _json_public(getattr(check, "ids_data", None) or {})
    details = {"username": username, "http_status": item.get("http_status"),
        "verification": "Original Maigret site-specific rule", "engine_status": "CLAIMED",
        "identity_match": "unconfirmed", "extracted_metadata": metadata,
        "extracted_usernames": _json_public(item.get("ids_usernames") or {}),
        "links": _json_public(item.get("ids_links") or []), "tags": _json_public(getattr(check, "tags", []) or [])}
    # Only actual extracted fields. Never infer missing names/avatars/biography.
    for target, keys in {"full_name": ("fullname", "full_name", "name"), "bio": ("bio", "biography", "description"),
                         "avatar_url": ("avatar", "avatar_url", "photo", "image"), "location": ("location",),
                         "website": ("website",), "followers": ("followers",), "following": ("following",)}.items():
        for key in keys:
            if isinstance(metadata, dict) and metadata.get(key) not in (None, "", [], {}):
                details[target] = metadata[key]
                break
    return {"id": f"{name}:{username}", "title": f"{name} · {username}", "type": "profile", "platform": name,
        "url": url, "description": "Maigret обнаружил публичный профиль по правилу площадки. Совпадение никнейма не доказывает принадлежность одному человеку.",
        "details": details, "status": "detected", "sources": ["maigret"]}


def load_engine(root):
    root = Path(root)
    sys.path.insert(0, str(root))
    import maigret.checking as checking
    from maigret.sites import MaigretDatabase
    from maigret.__version__ import __version__
    path = root / "maigret/resources/data.json"
    database = MaigretDatabase().load_from_file(str(path))
    defaults = json.loads((root / "maigret/resources/settings.json").read_text(encoding="utf-8"))
    identity = {"engine_version": __version__, "database_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "database_bytes": path.stat().st_size, "database_total": len(database.sites),
        "enabled_username": len(database.ranked_sites_dict(disabled=False)),
        "database_version": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}
    return checking, database, defaults, identity


def capability(root):
    _, database, defaults, identity = load_engine(root)
    modes = {}
    for mode in ("quick", "standard", "full"):
        config = normalize_options({"mode": mode})
        selected, eligible, skipped = select_sites(database, "solvnox", config, defaults)
        modes[mode] = {"selected": len(selected), "eligible": len(eligible), "skipped": len(skipped),
                       "skipped_reasons": dict(Counter(skipped.values()))}
    return {**identity, "modes": modes, "native_durable_resume": False,
        "notes": "Counts depend on the identifier and database; no network requests performed."}


def run_adapter(root, query, options):
    arguments = options.get("maigret") or query.get("options", {}).get("maigret") or {}
    if not arguments and options.get("profile_sites"):
        arguments = {"mode": "custom", "sites": list(options["profile_sites"]), "site_count": 0}
    config = normalize_options(arguments, legacy_limit=query.get("limit", 10), legacy_timeout=query.get("timeout", 25))
    checking, database, defaults, identity = load_engine(root)
    selected, sites, skipped = select_sites(database, query["text"], config, defaults)
    observations = [{"site": n, "status": "skipped", "reason": r} for n, r in skipped.items()]
    counts = Counter({key: 0 for key in ("found", "not_found", "unknown", "blocked", "unavailable", "errors")})
    started, last_emit = time.monotonic(), [0.0]
    completed, results, raw = set(), [], {}
    callback = options.get("_emit")
    coverage = {**identity, "mode": config["mode"], "selected": len(selected), "scheduled": len(sites),
        "checked": 0, "skipped": len(skipped), "skipped_reasons": dict(Counter(skipped.values())),
        "pending": len(sites), "complete": False, "cancelled": False, "phase": "running"}

    def emit_progress(force=False):
        now = time.monotonic()
        coverage.update(counts, checked=sum(counts.values()), processed=len(completed), pending=max(0, len(sites) - len(completed)),
                        elapsed_seconds=round(now - started, 3))
        if callable(callback) and (force or now - last_emit[0] >= .35):
            callback({"event": "maigret_progress", "source": "maigret", "progress": dict(coverage)})
            last_emit[0] = now

    def flush():
        batch = []
        for name, item in tuple(raw.items()):
            if name in completed:
                continue
            completed.add(name)
            state = classify(item)
            check = item.get("status")
            reason = str(getattr(getattr(check, "error", None), "type", ""))[:160]
            observations.append({"site": name, "status": state, "http_status": item.get("http_status"),
                                 "reason": reason})
            batch.append(observations[-1])
            if state == "skipped":
                coverage["skipped"] += 1
                reasons = coverage["skipped_reasons"]
                reasons["engine:" + (reason or "illegal")] = reasons.get("engine:" + (reason or "illegal"), 0) + 1
            else:
                counts[state] += 1
            if state == "found":
                try:
                    row = finding(name, query["text"], item)
                except ValueError:
                    counts["found"] -= 1
                    counts["errors"] += 1
                    observations[-1].update(status="errors", reason="non_public_result_url")
                    continue
                results.append(row)
                if callable(callback):
                    callback({"event": "result", "result": row})
        if batch and callable(callback):
            callback({"event": "maigret_checks", "source": "maigret", "checks": batch})
        emit_progress()

    async def execute():
        if callable(callback):
            callback({"event": "maigret_plan", "source": "maigret", "configuration": config,
                      "scheduled_sites": list(sites)})
        emit_progress(True)
        if observations and callable(callback):
            callback({"event": "maigret_checks", "source": "maigret", "checks": observations[:len(skipped)]})
        if not sites:
            return "empty"
        with verified_transport(checking):
            task = asyncio.create_task(checking.maigret(query["text"], sites, logging.getLogger("grangerpet.vendor"),
                timeout=config["per_site_timeout"], max_connections=config["concurrency"], no_progressbar=True,
                retries=0, is_parsing_enabled=config["parse_metadata"], is_enrich_enabled=False, check_domains=False,
                cloudflare_bypass=None, dns_resolver="threaded", output_container=raw))
            # Leave time for final serialization before the outer process deadline.
            budget = max(.1, min(float(config["time_budget"]), float(query.get("timeout", config["time_budget"]))) - .5)
            deadline = time.monotonic() + budget
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=min(.1, max(.01, deadline - time.monotonic())))
                    flush()
                    if time.monotonic() >= deadline and not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                        flush()
                        return "timeout"
                value = await task
                raw.update(value or {})
                flush()
                return "complete"
            except asyncio.CancelledError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                flush()
                return "cancelled"
            except Exception:
                flush()
                return "error"
    status = asyncio.run(execute())
    flush()
    coverage.update(complete=status in ("complete", "empty") and not coverage["pending"], cancelled=status == "cancelled")
    if status == "complete":
        uncertain = counts["unknown"] + counts["blocked"] + counts["unavailable"] + counts["errors"]
        status = "partial" if uncertain else "complete" if results else "empty"
    if status == "error" and results:
        status = "partial"
    coverage["phase"] = status
    emit_progress(True)
    diagnostics = {"coverage": dict(coverage), "site_checks": observations, "configuration": config,
        "original_defaults": {k: defaults.get(k) for k in ("top_sites_count", "max_connections", "timeout", "info_extracting", "recursive_search")},
        "resumption": {"native_durable_resume": False,
            "remaining_sites": [n for n in sites if n not in completed],
            "method": "Explicit Custom sites filter; reruns remaining checks, not a native durable Maigret session."},
        "policy": {"tls_verified": True, "public_https_only": True, "bypass": False, "recursive_search": False,
                   "enrichment_requests": False, "auto_update": False}}
    return {"source": "maigret", "status": status, "results": results, "checked": coverage["checked"],
        "source_diagnostics": diagnostics,
        "message": f"Maigret {identity['engine_version']} · {config['mode']}: проверено {len(completed)}/{len(sites)}, найдено {len(results)}, пропущено {coverage['skipped']}, осталось {coverage['pending']}."}
