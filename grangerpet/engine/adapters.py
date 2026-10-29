from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .runtime import run_worker

SOURCE_META = {
    "maigret": ("Публичные профили", ("username",)),
    "blackbird": ("Проверка профилей", ("username",)),
    "snoop": ("Дополнительные профили", ("username",)),
    "social_analyzer": ("Анализ страниц профилей", ("username",)),
    "holehe": ("Проверка email", ("email",)),
    "phoneinfoga": ("Сведения о номере", ("phone",)),
    "telegram": ("Telegram", ("telegram",)), "vk": ("VK", ("vk",)),
    "instagram": ("Instagram", ("instagram",)), "wayback": ("Веб-архив", ("web",)),
    "blockchain": ("Блокчейн · Gansar", ("blockchain",)), "google": ("Поиск в интернете", ("dork",)),
}


@dataclass
class SourceAdapter:
    id: str
    label: str
    kinds: tuple

    def run(self, query, context):
        if self.id == "google":
            return google_outcome(query, context.options)
        required = {"telegram": ("telegram_api_id", "telegram_api_hash", "telegram_session"), "vk": ("vk_token",)}.get(self.id, ())
        secrets = context.options.get("secrets", {})
        if required and not all(secrets.get(name) or context.options.get(name) for name in required):
            return {"source": self.id, "status": "auth_required", "results": [],
                    "message": "Для этого источника нужна авторизация. Откройте настройки подключения."}
        return run_worker(self.id, query.to_dict(), context.options, context.cancelled, context.event)


def google_outcome(query, options):
    from ..search import SearchError, search_google
    key, cx = options.get("google_api_key", ""), options.get("google_cx", options.get("api_cx", ""))
    if not key or not cx:
        return {"source": "google", "status": "auth_required", "results": [],
                "message": "Для выдачи внутри приложения подключите Google API. Запрос можно открыть в браузере."}
    try:
        results = search_google(query.text, key, cx, timeout=min(15, query.timeout))
    except SearchError as exc:
        return {"source": "google", "status": "error", "results": [], "message": str(exc)}
    return {"source": "google", "status": "complete" if results else "empty", "results": [
        {"id": item.url, "title": item.title, "type": "web", "platform": urlsplit(item.url).hostname or "Web",
         "url": item.url, "description": item.snippet, "details": {"query": item.query},
         "status": "indexed", "sources": ["google"]} for item in results]}


def default_adapters(options=None):
    return [PublicSearchAdapter('public_web','Публичные источники без ключа',('username','web','dork')),
            *[SourceAdapter(source, label, kinds) for source, (label, kinds) in SOURCE_META.items() if source!='google']]


class PublicSearchAdapter(SourceAdapter):
    def run(self,query,context):
        import time
        deadline=time.monotonic()+query.timeout
        if query.kind=='web':
            from ..agent_browser import PublicPageReader
            reader=PublicPageReader(max_pages=2,max_depth=1)
            reader.seed_urls_from_user(query.text)
            result=reader.read(query.text,cancel_event=context.cancelled,deadline=deadline)
        else:
            from ..agent_web import WebSearchProvider
            result=WebSearchProvider(options=context.options).search(query.text,limit=min(10,query.limit),cancel_event=context.cancelled,deadline=deadline)
        result['source']=self.id
        result['message']=' · '.join(result.get('limitations',[]))[:1000]
        return result


def select_adapters(query, options, adapters=None, *, verify_runtime=True, cancelled=None):
    """Route to compatible sources, not all engines for every text.

    Username catalogs substantially overlap. The default plan uses ONE ready
    engine (Maigret, then Blackbird, then Social Analyzer/Snoop). An explicit
    source selection remains possible for diagnostics; it isn't automatic.
    """
    adapters = list(adapters if adapters is not None else default_adapters(options))
    selected = query.options.get("sources", options.get("sources"))
    disabled = set(options.get("disabled_sources", []))
    candidates = [item for item in adapters if query.kind in item.kinds and item.id not in disabled
                  and (not selected or item.id in selected)
                  and (item.id != "snoop" or options.get("enable_snoop") or selected and "snoop" in selected)]
    if query.kind != "username" or selected or not verify_runtime:
        return candidates
    from .readiness import runtime_readiness
    preferred = sorted(candidates, key=lambda item: ["maigret", "blackbird", "social_analyzer", "snoop"].index(item.id)
                       if item.id in {"maigret", "blackbird", "social_analyzer", "snoop"} else 10)
    builtins=[item for item in preferred if item.id=='public_web']
    for item in preferred:
        if item.id=='public_web':continue
        if cancelled is not None and cancelled.is_set():
            return []
        if runtime_readiness(item.id, options, cancelled)["runtime_ready"]:
            return builtins+[item]
    # A real source invocation will return a truthful unavailable diagnostic.
    return builtins or preferred[:1]
