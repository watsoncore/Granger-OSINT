"""Official Google Programmable Search JSON API, executed off the GUI thread."""
from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


class SearchError(RuntimeError):
    """A safe message for the UI, deliberately excluding credentials and request URLs."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    query: str


def parse_results(payload: object, query: str) -> list[SearchResult]:
    if not isinstance(payload, dict):
        raise SearchError("Поисковый API вернул некорректный ответ.")
    if "error" in payload:
        err = payload["error"]
        code = err.get("code", "") if isinstance(err, dict) else ""
        if code in (401, 403):
            raise SearchError("Google отклонил запрос. Проверьте API-ключ, ID поисковой системы, доступ к API и квоту.")
        if code == 429:
            raise SearchError("Достигнуто ограничение запросов Google. Повторите позже или откройте поиск в браузере.")
        raise SearchError("Google не смог выполнить запрос. Повторите позже или используйте браузер.")
    if "items" not in payload:
        if "searchInformation" not in payload and "queries" not in payload:
            raise SearchError("В ответе API нет данных поисковой выдачи.")
        return []
    items = payload["items"]
    if not isinstance(items, list):
        raise SearchError("API вернул некорректный список результатов.")
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link = item.get("link", "")
        if not isinstance(link, str):
            continue
        try:
            parsed = urlsplit(link)
        except ValueError:
            continue
        if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.username or parsed.password:
            continue
        title, snippet = item.get("title"), item.get("snippet")
        results.append(SearchResult(title if isinstance(title, str) else link, link,
                                    snippet if isinstance(snippet, str) else "Описание не предоставлено источником.", query))
    return results


def search_google(query: str, api_key: str, api_cx: str, *, opener=None, timeout=15) -> list[SearchResult]:
    if not api_key.strip() or not api_cx.strip():
        raise SearchError("Для результатов внутри приложения нужны API-ключ и ID поисковой системы Google.")
    address = "https://www.googleapis.com/customsearch/v1?" + urlencode(
        {"key": api_key.strip(), "cx": api_cx.strip(), "q": query, "num": 10, "hl": "ru"})
    request = Request(address, headers={"Accept": "application/json", "User-Agent": "GrangerPet/1.0"})
    try:
        with (opener or urlopen)(request, timeout=timeout) as response:
            raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise SearchError("Ответ поискового API превышает допустимый размер.")
            payload = json.loads(raw.decode("utf-8"))
        return parse_results(payload, query)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise SearchError("Нет доступа к Google API. Проверьте ключ, ID поисковой системы, разрешения и квоту.") from None
        if exc.code == 429:
            raise SearchError("Квота Google исчерпана. Повторите позже или откройте поиск в браузере.") from None
        raise SearchError(f"Ошибка Google API (HTTP {exc.code}). Можно открыть поиск в браузере.") from None
    except (TimeoutError, URLError, OSError):
        raise SearchError("Не удалось связаться с Google API. Проверьте интернет-соединение и повторите запрос.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise SearchError("Поисковый API вернул ответ в неизвестном формате.") from None
