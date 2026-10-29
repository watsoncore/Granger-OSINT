"""Deterministic query validation and routing, independent of Qt and any LLM.

TON representation validation is an independently implemented bundled stdlib
validator. The optional Gansar analytical engine stays external.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import unquote, urlsplit, urlunsplit

from ..validators.ton_address import parse_ton_address

KINDS = ("auto", "username", "email", "phone", "telegram", "vk", "instagram", "web", "blockchain", "dork")
PROFILE_CHOICES = (("Публичные профили", "username"), ("Упоминания", "dork"))
DOMAIN_TLDS = frozenset("com org net edu gov mil int io ai dev app me info biz pro online site cloud tech ru su kz by ua uk us de fr es it nl pl cz ca au jp cn in ch at eu co tv xyz name museum travel mobi xn--p1ai".split())


@dataclass(frozen=True)
class QueryResolution:
    text: str
    kind: str = "auto"
    label: str = ""
    source_label: str = ""
    choices: tuple = ()
    valid: bool = True
    requires_clarification: bool = False
    error: str = ""
    adapter_ids: tuple = ()
    chain: str = ""

    @property
    def normalized(self):
        return self.text


def _resolution(text, kind, label, source, adapters, *, chain=""):
    return QueryResolution(text, kind, label, source, adapter_ids=tuple(adapters), chain=chain)


def _error(text, message, kind="auto", label=""):
    return QueryResolution(text, kind, label=label, valid=False, error=message)


def validate_ton(text: str, options=None):
    """Normalize TON representation without requiring an optional tool checkout."""
    return parse_ton_address(text)


def normalize_email(text):
    if text.count("@") != 1:
        raise ValueError("Введите email в формате name@example.org.")
    local, domain = text.rsplit("@", 1)
    if (not 1 <= len(local) <= 64 or local.startswith(".") or local.endswith(".") or ".." in local
            or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)):
        raise ValueError("Проверьте имя в email: пробелы и повторяющиеся точки недопустимы.")
    domain = _domain(domain)
    value = local + "@" + domain
    if len(value) > 254:
        raise ValueError("Email слишком длинный.")
    return value


def normalize_phone(text):
    import phonenumbers
    value = text.strip()
    if value.startswith("00"):
        value = "+" + value[2:]
    if not value.startswith("+"):
        raise ValueError("Укажите международный телефон с кодом страны, например +7 или +44.")
    try:
        number = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException:
        raise ValueError("Телефон не распознан. Проверьте международный формат.") from None
    if not phonenumbers.is_possible_number(number) or not phonenumbers.is_valid_number(number):
        raise ValueError("Номер не соответствует действующему плану нумерации.")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def _domain(value):
    try:
        domain = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValueError("Некорректный домен.") from None
    if len(domain) > 253 or "." not in domain or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in domain.split(".")):
        raise ValueError("Укажите полный домен сайта.")
    return domain


def _url(value):
    parsed = urlsplit(value if "://" in value else "https://" + value)
    if parsed.scheme.lower() not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Нужна публичная HTTP(S) ссылка без учётных данных.")
    host = parsed.hostname.lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        host = _domain(host)
        if host.endswith((".local", ".localhost", ".internal")):
            raise ValueError("Укажите публичный сайт.")
    else:
        if not address.is_global:
            raise ValueError("Укажите публичный сайт; локальные адреса не исследуются.")
    port = parsed.port
    suffix = f":{port}" if port and (parsed.scheme.lower(), port) not in (("https", 443), ("http", 80)) else ""
    hostpart = f"[{host}]" if ":" in host else host
    return parsed, host, urlunsplit((parsed.scheme.lower(), hostpart + suffix, parsed.path or "/", parsed.query, ""))


def _platform(value, kind):
    if "://" not in value and "/" not in value:
        name = value.lstrip("@")
        if kind == "telegram":
            value = "https://t.me/" + name
        elif kind == "vk":
            value = "https://vk.com/" + name
        else:
            value = "https://www.instagram.com/" + name
    parsed, host, normalized = _url(value)
    aliases = {"telegram": {"t.me", "telegram.me", "www.t.me"},
               "vk": {"vk.com", "m.vk.com", "vk.ru", "m.vk.ru", "www.vk.com"},
               "instagram": {"instagram.com", "www.instagram.com"}}
    if host not in aliases[kind]:
        raise ValueError("Ссылка относится к другой платформе.")
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if kind == "telegram" and parts[:1] == ["s"]:
        parts = parts[1:]
    if not parts or parts[0].startswith("+") or parts[0] in {"c", "joinchat", "p", "reel", "stories", "accounts"}:
        raise ValueError("Нужна публичная ссылка на аккаунт, канал или доступную публикацию.")
    name = parts[0]
    pattern = r"[A-Za-z][A-Za-z0-9_]{3,31}" if kind == "telegram" else r"[A-Za-z0-9_.]{1,64}"
    if not re.fullmatch(pattern, name) or len(parts) > (2 if kind == "telegram" else 1) or len(parts) == 2 and not parts[1].isdigit():
        raise ValueError("Проверьте публичное имя или ссылку на публикацию.")
    canonical_host = {"telegram": "t.me", "vk": "vk.com", "instagram": "www.instagram.com"}[kind]
    normalized = "https://" + canonical_host + "/" + "/".join(parts)
    return normalized


def detect_query(text, chosen_kind=None, options=None):
    """Resolve only validated formats. Plain names deliberately require a choice."""
    value = str(text or "").strip()
    if not value:
        return _error(value, "Введите запрос.")
    if len(value) > 1500 or any(ord(char) < 32 for char in value):
        return _error(value, "Запрос: до 1500 символов без управляющих символов.")
    chosen = chosen_kind if chosen_kind not in (None, "auto") else None
    if chosen and chosen not in KINDS:
        return _error(value, "Неизвестное направление поиска.")
    lower = value.lower()
    try:
        if chosen == "dork" or not chosen and re.search(r"(?:^|\s)-?(?:site|filetype|intitle|inurl|intext):", value, re.I):
            from ..dorks import validate_custom
            return _resolution(validate_custom(value), "dork", "Поисковый запрос", "Поиск упоминаний", ("public_web",))
        if chosen == "username":
            name = value.lstrip("@")
            if not re.fullmatch(r"[\w.-]{1,64}", name, re.UNICODE):
                raise ValueError("Введите один никнейм без пробелов.")
            return _resolution(name, "username", "Никнейм", "Поиск публичных профилей", ("public_web", "maigret", "blackbird", "social_analyzer", "snoop"))
        if chosen == "email" or not chosen and "@" in value and not value.startswith("@"):
            return _resolution(normalize_email(value), "email", "Email", "Проверка публичных регистраций", ("holehe",))
        if chosen == "phone" or not chosen and re.fullmatch(r"(?:\+|00)[\d ()-]{6,24}", value):
            return _resolution(normalize_phone(value), "phone", "Телефон", "Сведения о номере", ("phoneinfoga",))
        # Valid friendly forms include -1 workchain/test tags and standard-base64
        # variants too. The real parser decides validity, not only EQ/UQ regex.
        possible_friendly = bool(re.fullmatch(r"[A-Za-z0-9_+/=-]{48}", value))
        parsed_friendly = validate_ton(value, options) if possible_friendly else None
        ton_like = bool(parsed_friendly or re.fullmatch(r"-?\d+:[0-9A-Za-z]{50,70}", value)
                        or value.startswith(("EQ", "UQ", "Ef", "Uf", "kQ", "0Q", "kf", "0f")) and len(value) >= 40)
        if ton_like or chosen == "blockchain" and (":" in value or len(value) == 48):
            parsed = parsed_friendly or validate_ton(value, options)
            if not parsed:
                return _error(value, "Невалидный TON-адрес: проверьте структуру, tag и checksum.", "blockchain", "TON")
            if parsed.get("test_only"):
                return _error(value, "Это TON testnet-адрес. Текущий Gansar использует mainnet; тестовая сеть не подключена.", "blockchain", "TON testnet")
            return _resolution(parsed["raw"], "blockchain", "TON-адрес", "TON · Gansar", ("blockchain",), chain="ton")
        if lower.endswith(".ton"):
            return _error(value, "В текущем Gansar нет прямого разрешения TON DNS. Вставьте EQ/UQ или raw адрес.", "blockchain", "TON DNS")
        if chosen in ("telegram", "vk", "instagram"):
            return _resolution(_platform(value, chosen), chosen, {"telegram": "Telegram-ссылка", "vk": "VK-ссылка", "instagram": "Instagram-ссылка"}[chosen],
                               {"telegram": "Telegram", "vk": "ВКонтакте", "instagram": "Instagram"}[chosen], (chosen,))
        host_prefix = value.split("/", 1)[0].rsplit(":", 1)[0]
        plain_url = "/" in value and " " not in value and "." in host_prefix and host_prefix.rsplit(".", 1)[-1].lower() in DOMAIN_TLDS
        looks_url = "://" in value or plain_url or bool(re.match(r"^(?:(?:www|m)\.)?(?:t\.me|telegram\.me|vk\.com|vk\.ru|instagram\.com)/", lower))
        if not chosen and looks_url:
            _, host, normalized = _url(value)
            kind = "telegram" if host in {"t.me", "telegram.me", "www.t.me"} else "vk" if host in {"vk.com", "m.vk.com", "vk.ru", "m.vk.ru", "www.vk.com"} else "instagram" if host.removeprefix("www.") == "instagram.com" else "web"
            if kind != "web":
                return detect_query(normalized, kind, options)
            return _resolution(normalized, "web", "Веб-ссылка", "Чтение публичной страницы и архив", ("public_web", "wayback"))
        if not chosen and re.fullmatch(r"(?:id|club|public|event)\d+", value, re.I):
            return detect_query(value, "vk", options)
        blockchain_shape = (bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", value)) or bool(re.fullmatch(r"(?:bc1|[13])[A-Za-z0-9]{25,90}", value))
                            or bool(re.fullmatch(r"[TD9A][1-9A-HJ-NP-Za-km-z]{25,43}", value)) or bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", value)) or lower.endswith(".eth"))
        if chosen == "blockchain" or not chosen and blockchain_shape:
            return _resolution(value, "blockchain", "Блокчейн-адрес / имя", "Gansar · проверка поддерживаемой сети", ("blockchain",))
        if chosen == "web":
            _, _, normalized = _url(value)
            return _resolution(normalized, "web", "Веб-ссылка", "Чтение публичной страницы и архив", ("public_web", "wayback"))
        if "." in value and "/" not in value and " " not in value:
            try:
                domain = _domain(value)
            except ValueError:
                domain = ""
            if domain and domain.rsplit(".", 1)[1] in DOMAIN_TLDS:
                return _resolution("https://" + domain + "/", "web", "Домен", "Чтение публичной страницы и архив", ("public_web", "wayback"))
            if domain:
                return QueryResolution(value, choices=(("Веб-архив", "web"),) + PROFILE_CHOICES, label="Неоднозначный текст", requires_clarification=True)
        if re.fullmatch(r"@?[\w.-]{1,64}", value, re.UNICODE):
            return QueryResolution(value, label="Возможный никнейм или упоминание", source_label="Что искать?", choices=PROFILE_CHOICES, requires_clarification=True)
        if re.fullmatch(r"\d[\d ()-]{5,24}", value):
            return QueryResolution(value, label="Номер без кода страны или текст", choices=PROFILE_CHOICES, requires_clarification=True)
        return _resolution(value, "dork", "Поисковый текст", "Поиск упоминаний", ("public_web",))
    except (ValueError, TypeError, OverflowError) as exc:
        return _error(value, str(exc))
