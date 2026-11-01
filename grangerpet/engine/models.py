"""Small source-independent search objects; identifiers never imply a person match."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import copy
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

KINDS = ("auto", "username", "email", "phone", "telegram", "vk", "instagram", "web", "blockchain", "dork", "ip", "network", "domain")


@dataclass
class SearchQuery:
    text: str
    kind: str = "auto"
    limit: int = 20
    timeout: float = 25
    options: dict = field(default_factory=dict)

    def normalized(self):
        from .router import detect_query
        resolution = detect_query(self.text, self.kind, self.options)
        if not resolution.valid:
            raise ValueError(resolution.error)
        if resolution.requires_clarification:
            raise ValueError("Уточните, что искать: публичные профили или упоминания.")
        options = dict(self.options)
        if resolution.chain:
            options["chain"] = resolution.chain
        return SearchQuery(resolution.text, resolution.kind, max(1, min(50, int(self.limit))),
                           max(3, min(90, float(self.timeout))), options)

    def to_dict(self):
        return asdict(self)


def classify(text: str) -> str:
    from .router import detect_query
    resolution = detect_query(text)
    return resolution.kind if resolution.valid and not resolution.requires_clarification else "auto"


def canonical_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return ""
        host = parsed.hostname.lower().encode("idna").decode("ascii")
        aliases = {"www.github.com": "github.com", "www.gitlab.com": "gitlab.com",
                   "m.vk.com": "vk.com", "www.vk.com": "vk.com", "vk.ru": "vk.com", "m.vk.ru": "vk.com",
                   "www.instagram.com": "instagram.com", "www.telegram.me": "t.me", "telegram.me": "t.me",
                   "www.twitter.com": "x.com", "twitter.com": "x.com", "mobile.twitter.com": "x.com", "www.x.com": "x.com",
                   "www.youtube.com": "youtube.com", "m.youtube.com": "youtube.com", "www.tiktok.com": "tiktok.com"}
        host = aliases.get(host, host)
        path = parsed.path.rstrip("/") or "/"
        # Account identifiers on these platforms are case-insensitive. Other
        # URL paths (archive files, arbitrary websites) keep their actual case.
        if host in {"github.com", "gitlab.com", "vk.com", "instagram.com", "t.me", "x.com", "tiktok.com"}:
            parts = path.split("/")
            if len(parts) > 1:
                parts[1] = parts[1].lower()
            path = "/".join(parts)
        if host == "youtube.com" and path.startswith("/@"):
            parts = path.split("/")
            parts[1] = parts[1].lower()
            if len(parts) == 3 and parts[2] in {"about", "featured", "videos", "shorts", "streams", "playlists", "community"}:
                parts.pop()
            path = "/".join(parts)
        port = parsed.port
        if port and (parsed.scheme.lower(), port) not in (("http", 80), ("https", 443)):
            host += f":{port}"
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
        scheme = "https" if host in {"github.com", "gitlab.com", "vk.com", "instagram.com", "t.me", "x.com", "youtube.com", "tiktok.com"} else parsed.scheme.lower()
        fragment = parsed.fragment if parsed.fragment.startswith("/address/") and host == "tronscan.org" else ""
        return urlunsplit((scheme, host, path, urlencode(sorted(query)), fragment))
    except (ValueError, UnicodeError):
        return ""


@dataclass
class Result:
    id: str
    title: str
    type: str
    platform: str
    url: str = ""
    description: str = ""
    date: str = ""
    details: dict = field(default_factory=dict)
    status: str = "verified"
    sources: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value, source=""):
        if not isinstance(value, dict):
            raise ValueError("Invalid result object")
        # Execution messages are a different entity. Do not fabricate title/id/
        # platform defaults, which used to turn a status-shaped dict into a hit.
        kind, title, platform = (value.get(name) for name in ("type", "title", "platform"))
        if (not isinstance(kind, str) or not kind.strip() or kind in {"status", "execution", "source_execution", "progress"}
                or not isinstance(title, str) or not title.strip()
                or not isinstance(platform, str) or not platform.strip()):
            raise ValueError("A search result needs explicit type, title and platform")
        url = canonical_url(str(value.get("url", "")))
        if value.get("url") and not url:
            raise ValueError("Invalid result source URL")
        if kind in {"profile", "community", "post", "archive", "snapshot", "web_snapshot", "web", "resource"} and not url:
            raise ValueError("A web/profile finding needs its real source URL")
        if value.get("status") in {"queued", "running", "complete", "completed", "empty", "error", "timeout", "cancelled", "auth_required", "unavailable"}:
            raise ValueError("Source execution status is not finding verification")
        if kind not in {"profile", "community", "post", "archive", "snapshot", "web_snapshot", "web", "resource"} and not value.get("id"):
            raise ValueError("A structured observation needs its actual identifier")
        platform = platform.strip()[:160]
        identifier = str(value.get("id", ""))[:500]
        if not identifier:
            identifier = hashlib.sha256((platform + "|" + url + "|" + str(value.get("title", ""))).encode()).hexdigest()[:20]
        sources = [str(x)[:80] for x in value.get("sources", []) if isinstance(x, str)]
        if source and source not in sources:
            sources.append(source)
        return cls(identifier, title.strip()[:500], kind.strip()[:80],
                   platform, url, str(value.get("description") or "")[:5000], str(value.get("date") or "")[:100],
                   copy.deepcopy(value.get("details", {})) if isinstance(value.get("details", {}), dict) else {},
                   str(value.get("status", "unknown"))[:80], sources)

    def to_dict(self):
        return asdict(self)

    @property
    def confirmed(self):
        return is_confirmed(self)


CONFIRMED_STATUSES = frozenset({"verified", "confirmed", "found", "indexed", "detected", "registration_detected", "metadata"})


def is_confirmed(result):
    status = result.status if isinstance(result, Result) else result.get("status", "unknown")
    return str(status).lower() in CONFIRMED_STATUSES


class ResultIndex:
    """Deduplicate the same resource; a nickname alone is never a merge key."""
    def __init__(self):
        self.items = {}

    def key(self, result):
        return result_key(result)

    def contains(self, result):
        return self.key(result) in self.items

    def add(self, result: Result):
        key = self.key(result)
        existing = self.items.get(key)
        if existing:
            changed = False
            same_source = bool(set(existing.sources).intersection(result.sources))
            for source in result.sources:
                if source not in existing.sources:
                    existing.sources.append(source)
                    changed = True
            for name, value in result.details.items():
                if name != "source_confirmations" and existing.details.get(name) != value:
                    existing.details[name] = copy.deepcopy(value)
                    changed = True
            for name in ("title", "description", "date", "status"):
                value = getattr(result, name)
                if value and value != getattr(existing, name) and (same_source or not getattr(existing, name)):
                    setattr(existing, name, value)
                    changed = True
            if is_confirmed(result) and not is_confirmed(existing):
                existing.status = result.status
                changed = True
            # Gansar's transaction `confirmations` is an integer or None. Keep
            # network confirmations intact; source evidence has its own key.
            if not isinstance(existing.details.get("source_confirmations"), dict):
                existing.details["source_confirmations"] = {}
            for source in result.sources:
                if existing.details["source_confirmations"].get(source) != result.status:
                    existing.details["source_confirmations"][source] = result.status
                    changed = True
            return existing, False, changed
        self.items[key] = result
        return result, True, False


def result_key(result):
    """The same URL may evidence several different facts; keep those distinct."""
    value = result.to_dict() if isinstance(result, Result) else result
    kind = str(value.get("type", "resource")).casefold()
    url = canonical_url(str(value.get("url", "")))
    if url and kind in ("profile", "resource", "web", "snapshot", "post", "archive", "web_snapshot"):
        return ("url", kind, url)
    return ("id", kind, str(value.get("platform", "")).casefold(), str(value.get("id", "")))


@dataclass
class SourceExecution:
    source: str
    state: str
    message: str = ""
    checked: int = 0
    found: int = 0
    label: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str = ""

    def to_dict(self):
        return asdict(self)

    @property
    def source_id(self):
        return self.source

    @property
    def results_count(self):
        return self.found


# Compatibility names retain one canonical result type and one execution type.
SearchResult = Result
SourceStatus = SourceExecution


@dataclass
class SearchSummary:
    query: SearchQuery
    result_count: int
    cancelled: bool
    statuses: list[SourceStatus]
    elapsed: float
    phase: str = ""
    confirmed_count: int = 0
    uncertain_count: int = 0
    checked_sources: int = 0

    def to_dict(self):
        value = asdict(self)
        # Runtime options carry credentials through stdin to trusted local
        # adapters. Reports/diagnostics need routing options, never those keys.
        secret_names = {"api_key", "google_api_key", "gemini_api_key", "vk_token", "telegram_api_hash",
                        "telegram_session", "instagram_session", "secrets"}
        def public_options(item):
            if isinstance(item, dict):
                return {name: public_options(nested) for name, nested in item.items()
                        if str(name).casefold() not in secret_names}
            if isinstance(item, (list, tuple)):
                return [public_options(nested) for nested in item]
            return item
        value["query"]["options"] = public_options(value["query"].get("options", {}))
        return value
