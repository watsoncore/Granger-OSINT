"""Validated Google dork construction; no network or fabricated search data."""
from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
from urllib.parse import urlencode, urlsplit


class DorkError(ValueError):
    pass


def normalize_domain(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        candidate = urlsplit(value if "://" in value else "https://" + value)
    except ValueError as exc:
        raise DorkError("Некорректный домен.") from exc
    if candidate.scheme not in ("http", "https") or candidate.username or candidate.password:
        raise DorkError("Введите домен сайта, например example.org.")
    if candidate.path not in ("", "/") or candidate.query or candidate.fragment:
        raise DorkError("Укажите только домен, без пути, параметров и фрагмента URL.")
    try:
        if candidate.port is not None:
            raise DorkError("Укажите домен без номера порта.")
        domain = (candidate.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
    except (ValueError, UnicodeError) as exc:
        raise DorkError("Некорректный домен.") from exc
    if len(domain) > 253 or "." not in domain or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in domain.split(".")
    ):
        raise DorkError("Введите корректный полный домен, например example.org.")
    return domain


def _clean(value: str) -> str:
    return " ".join(value.replace("\x00", "").split())


def quote_phrase(value: str) -> str:
    value = _clean(value)
    if '"' in value or "“" in value or "”" in value:
        raise DorkError("Введите фразу без кавычек: конструктор добавит их сам.")
    return f'"{value}"' if value else ""


def _operator(name: str, value: str) -> str:
    value = _clean(value)
    if not value:
        return ""
    if '"' in value:
        raise DorkError(f"Введите значение {name}: без кавычек.")
    return f"{name}:{quote_phrase(value) if any(c.isspace() for c in value) else value}"


@dataclass(frozen=True)
class DorkSpec:
    mode: str = "domain"
    text: str = ""
    domain: str = ""
    filetype: str = "pdf"
    title: str = ""
    url: str = ""
    intext: str = ""
    exact: bool = False
    exclude: str = ""


def validate_custom(query: str) -> str:
    query = _clean(query)
    quoted = False
    parens = 0
    for char in query:
        if char == '"':
            quoted = not quoted
        elif not quoted and char == "(":
            parens += 1
        elif not quoted and char == ")":
            parens -= 1
            if parens < 0:
                raise DorkError("Проверьте круглые скобки в запросе.")
    if quoted or parens:
        raise DorkError("Закройте кавычки и круглые скобки в запросе.")
    if re.search(r"(?:^|\s)-?(?:site|filetype|intitle|inurl|intext):(?:\s|$)", query):
        raise DorkError("После поискового оператора должно быть значение без пробела после двоеточия.")
    return query


def build_query(spec: DorkSpec) -> str:
    if spec.mode == "custom":
        query = validate_custom(spec.text)
    else:
        if spec.mode not in ("web", "domain", "documents", "mentions"):
            raise DorkError("Неизвестный тип поиска.")
        domain = normalize_domain(spec.domain)
        if spec.mode in ("domain", "documents") and not domain:
            raise DorkError("Укажите домен сайта.")
        text = _clean(spec.text)
        if spec.mode == "mentions" and not text:
            raise DorkError("Введите название организации, имя или никнейм.")
        parts = [f"site:{domain}" if domain else ""]
        if spec.mode == "documents":
            kind = spec.filetype.lower().strip().lstrip(".")
            if kind not in ("pdf", "docx", "xlsx"):
                raise DorkError("Поддерживаются документы PDF, DOCX и XLSX.")
            parts.append(f"filetype:{kind}")
        if text:
            parts.append(quote_phrase(text) if spec.exact or spec.mode == "mentions" else validate_custom(text))
        parts.extend((_operator("intitle", spec.title), _operator("inurl", spec.url), _operator("intext", spec.intext)))
        try:
            exclusions = shlex.split(spec.exclude)
        except ValueError as exc:
            raise DorkError('Закройте кавычки в исключениях. Пример: вакансии "старый отчёт".') from exc
        for word in exclusions:
            word = word.lstrip("-")
            if word:
                parts.append("-" + (quote_phrase(word) if " " in word else word))
        query = " ".join(p for p in parts if p)
    if not query:
        raise DorkError("Введите поисковый запрос.")
    if len(query) > 1500:
        raise DorkError("Запрос слишком длинный: максимум 1500 символов.")
    return query


def google_url(query: str) -> str:
    return "https://www.google.com/search?" + urlencode({"q": query})
