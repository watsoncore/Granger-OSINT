"""Headless adapters for the user's existing public-platform source checkouts.

Executed by the isolated worker, never imported into the desktop Qt process.
Credentials arrive only through the worker's stdin options; no login UI,
cookie extraction, pickle session loading, private access or CAPTCHA solving.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import importlib
import ipaddress
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

VENDORS = {"instagram": "instaloader-master", "telegram": "Telethon-1",
           "vk": "vk_api-master", "wayback": "waybackpy-master"}


def _out(source, status, results=None, message=""):
    return {"source": source, "status": status, "results": results or [], "message": message}


def _item(source, identifier, title, kind, platform, url, description="", details=None, date=None):
    return {"id": str(identifier), "title": str(title), "type": kind, "platform": platform,
            "url": str(url), "description": str(description or "")[:4000], "date": date,
            "details": details or {}, "status": "verified", "sources": [source]}


def _root(options):
    return Path(options.get("tools_root") or options.get("source_root") or Path(__file__).resolve().parents[2]).resolve()


def _load(source, module, options):
    vendor = _root(options) / VENDORS[source]
    if not vendor.is_dir():
        raise FileNotFoundError(f"Missing local source: {VENDORS[source]}")
    # Telethon's source archive omits generated TL modules. setup_sources builds
    # them in a temporary copy and installs that exact checkout into the env.
    if source != "telegram" or (vendor / "telethon" / "tl" / "types").is_dir():
        sys.path.insert(0, str(vendor))
    return importlib.import_module(module)


def _secret(options, name):
    nested = options.get("secrets", {})
    return str(nested.get(name, options.get(name, "")) or "").strip()


def _timeout(query):
    return max(3.0, min(float(query.get("timeout", 20)), 30.0))


def _username(value, platform):
    text = value.strip()
    prefixes = {"instagram": ("instagram:", "ig:"), "telegram": ("telegram:", "tg:"), "vk": ("vk:",)}
    for prefix in prefixes[platform]:
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
    if "://" in text or text.lower().startswith(("t.me/", "telegram.me/", "vk.com/", "m.vk.com/", "vk.ru/", "m.vk.ru/", "instagram.com/", "www.instagram.com/")):
        parsed = urlsplit(text if "://" in text else "https://" + text)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        allowed = {"telegram": {"t.me", "telegram.me"}, "vk": {"vk.com", "m.vk.com", "vk.ru", "m.vk.ru"}, "instagram": {"instagram.com"}}
        if host not in allowed[platform] or parsed.username or parsed.password:
            raise ValueError("Нужна публичная ссылка выбранной платформы.")
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if platform == "telegram" and parts[:1] == ["s"]:
            parts = parts[1:]
        text = parts[0] if parts else ""
    text = text.lstrip("@")
    pattern = r"[A-Za-z0-9_.]{1,64}" if platform != "telegram" else r"[A-Za-z][A-Za-z0-9_]{3,31}"
    if not re.fullmatch(pattern, text) or text in {"c", "joinchat", "p", "reel", "stories", "accounts"}:
        raise ValueError("Укажите публичное имя аккаунта или канала, а не приватное приглашение.")
    return text


def _public_url(value):
    text = value.strip()
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    parsed = urlsplit(text)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        raise ValueError("Нужен публичный HTTP(S) URL.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.lower().endswith((".local", ".localhost", ".internal")):
            raise ValueError("Нужен адрес публичного сайта.")
    else:
        if not address.is_global:
            raise ValueError("Локальные и частные адреса не поддерживаются.")
    return text


def _instagram(query, options):
    name = _username(query["text"], "instagram")
    module = _load("instagram", "instaloader", options)
    loader = module.Instaloader(quiet=True, sleep=False, max_connection_attempts=1,
                               request_timeout=min(_timeout(query), 12), download_pictures=False,
                               download_videos=False, download_video_thumbnails=False,
                               download_geotags=False, download_comments=False, save_metadata=False)
    try:
        cookies = _secret(options, "instagram_session")
        if cookies:
            try:
                data = json.loads(cookies)
            except ValueError:
                return _out("instagram", "auth_required", message="Сессия Instagram должна быть JSON-словарём cookies собственной авторизованной сессии.")
            if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()) or not data.get("csrftoken") or not data.get("sessionid"):
                return _out("instagram", "auth_required", message="В cookies Instagram необходимы sessionid и csrftoken; файлы pickle не поддерживаются.")
            loader.load_session(_secret(options, "instagram_username") or "authorized-session", data)
        profile = module.Profile.from_username(loader.context, name)
        details = {"username": profile.username, "userid": str(profile.userid), "full_name": profile.full_name,
                   "followers": profile.followers, "following": profile.followees, "posts": profile.mediacount,
                   "private": profile.is_private, "verified_badge": profile.is_verified,
                   "external_url": profile.external_url}
        return _out("instagram", "complete", [_item("instagram", f"instagram:{profile.userid}",
                    profile.full_name or profile.username, "profile", "Instagram",
                    f"https://www.instagram.com/{profile.username}/", profile.biography, details)],
                    "Получены доступные метаданные профиля. Приватные публикации не запрашивались.")
    finally:
        loader.close()


async def _telegram_async(query, options):
    name = _username(query["text"], "telegram")
    api_id, api_hash, session = (_secret(options, key) for key in ("telegram_api_id", "telegram_api_hash", "telegram_session"))
    if not api_id.isdigit() or not api_hash or not session:
        return _out("telegram", "auth_required", message="Подключите Telegram API ID, API hash и уже авторизованную StringSession в настройках источников.")
    module = _load("telegram", "telethon", options)
    from telethon.sessions import StringSession
    client = module.TelegramClient(StringSession(session), int(api_id), api_hash,
                                   timeout=min(_timeout(query), 10), request_retries=0,
                                   connection_retries=0, retry_delay=0, auto_reconnect=False,
                                   flood_sleep_threshold=0, receive_updates=False)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return _out("telegram", "auth_required", message="Сессия Telegram не авторизована или отозвана. Обновите свою StringSession.")
        entity = await client.get_entity(name)
        username = getattr(entity, "username", None)
        if not username:
            return _out("telegram", "empty", message="Публичное имя не найдено. Приватные чаты не исследуются.")
        title = getattr(entity, "title", None) or " ".join(filter(None, (getattr(entity, "first_name", ""), getattr(entity, "last_name", "")))) or username
        details = {"id": str(entity.id), "username": username, "verified_badge": bool(getattr(entity, "verified", False)),
                   "scam_label": bool(getattr(entity, "scam", False)), "kind": type(entity).__name__}
        results = [_item("telegram", f"telegram:{type(entity).__name__}:{entity.id}", title,
                         "channel" if hasattr(entity, "broadcast") else "profile", "Telegram", f"https://t.me/{username}", details=details)]
        parsed = urlsplit(query["text"] if "://" in query["text"] else "https://" + query["text"])
        path = [part for part in parsed.path.split("/") if part]
        if path[:1] == ["s"]:
            path = path[1:]
        requested_message = int(path[1]) if len(path) == 2 and path[1].isdigit() else None
        if requested_message:
            message = await client.get_messages(entity, ids=requested_message)
            if message and getattr(message, "message", None):
                results.append(_item("telegram", f"telegram:{entity.id}:{message.id}", f"{title} · публикация {message.id}",
                    "post", "Telegram", f"https://t.me/{username}/{message.id}", message.message,
                    {"views": getattr(message, "views", None)}, message.date.isoformat() if message.date else None))
        elif hasattr(entity, "broadcast"):
            limit = max(1, min(int(query.get("limit", 3)), 3))
            async for message in client.iter_messages(entity, limit=limit):
                if not getattr(message, "message", None):
                    continue
                results.append(_item("telegram", f"telegram:{entity.id}:{message.id}", f"{title} · публикация {message.id}",
                    "post", "Telegram", f"https://t.me/{username}/{message.id}", message.message,
                    {"views": getattr(message, "views", None)}, message.date.isoformat() if message.date else None))
        return _out("telegram", "complete", results, "Получены только сведения публичного объекта и доступные публичные публикации.")
    finally:
        await client.disconnect()


def _vk(query, options):
    name = _username(query["text"], "vk")
    token = _secret(options, "vk_token")
    if not token:
        return _out("vk", "auth_required", message="Добавьте действующий VK access token в настройках источников.")
    module = _load("vk", "vk_api", options)
    import requests
    from jconfig import MemoryConfig

    class BoundedSession(requests.Session):
        def request(self, method, url, **kwargs):
            # Official request format documents Authorization: Bearer. Remove
            # the library's legacy form token before creating the request;
            # neither the URL nor the form body may contain this credential.
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or parsed.hostname not in ('api.vk.com','api.vk.ru') or not parsed.path.startswith('/method/') or parsed.query:
                raise ValueError('Недопустимый адрес официального VK API.')
            data = dict(kwargs.get('data') or {})
            data.pop('access_token', None)
            kwargs['data'] = data
            kwargs['headers'] = {**(kwargs.get('headers') or {}), 'Authorization': 'Bearer ' + token}
            kwargs['allow_redirects'] = False
            kwargs.setdefault("timeout", (3, min(_timeout(query), 10)))
            return super().request(method, url, **kwargs)
    with BoundedSession() as session:
        client = module.VkApi(token=token, api_version="5.199", session=session, config=MemoryConfig)
        client.error_handlers = {}  # Never auto-solve CAPTCHA or retry access restrictions.
        numeric = re.fullmatch(r'(?:id)?([1-9][0-9]{0,18})', name)
        community = re.fullmatch(r'(?:club|public|event)([1-9][0-9]{0,18})', name)
        resolved = ({'object_id':int(numeric[1]),'type':'user'} if numeric else
                    {'object_id':int(community[1]),'type':'group'} if community else
                    client.method("utils.resolveScreenName", {"screen_name": name}))
        if not isinstance(resolved, dict) or not resolved.get("object_id"):
            return _out("vk", "empty", message="Публичный объект ВКонтакте не найден.")
        identifier, kind = resolved["object_id"], resolved.get("type")
        if kind == "user":
            rows = client.method("users.get", {"user_ids": identifier, "fields": "screen_name,status,sex,country,photo_max_orig,city,site,verified"})
            if not isinstance(rows,list) or any(not isinstance(value,dict) for value in rows):
                return _out('vk','error',message='VK API вернул неизвестную структуру users.get; сведения не приняты.')
            row = rows[0] if rows else {}
            title = " ".join(filter(None, (row.get("first_name"), row.get("last_name"))))
            url = "https://vk.com/" + str(row.get("screen_name") or f"id{identifier}")
            description = row.get("status", "")
        elif kind in ("group", "page", "event"):
            rows = client.method("groups.getById", {"group_id": identifier, "fields": "description,members_count,site,verified"})
            if isinstance(rows, dict):
                rows = rows.get("groups", [])
            row = rows[0] if rows else {}
            title, description = row.get("name", name), row.get("description", "")
            url = "https://vk.com/" + str(row.get("screen_name") or f"club{identifier}")
        else:
            return _out("vk", "empty", message="Тип публичного объекта не поддерживается.")
        if not row:
            return _out("vk", "empty", message="VK API не вернул публичные сведения об объекте.")
        if not isinstance(row,dict) or type(row.get('id')) is not int:
            return _out('vk','error',message='VK API вернул неполные сведения без идентификатора.')
        if row.get('deactivated'):
            return _out('vk','empty',message='Профиль удалён или заблокирован. Закрытые сведения не запрашивались.')
        # Retain only documented public profile fields, never arbitrary vendor
        # echoes (request_params/error payloads may contain a reflected token).
        row={key:value for key,value in row.items() if key in {
            'id','first_name','last_name','screen_name','status','sex','country','photo_max_orig','city','site','verified',
            'is_closed','can_access_closed','name','description','members_count'}}
        row.update(api_method='users.get' if kind=='user' else 'groups.getById',api_version='5.199',
                   acquisition='official_api', access='public_fields_only')
        if row.get('is_closed'):
            description = (description + '\nПрофиль закрыт; возвращены только доступные токену публичные поля.').strip()
        return _out("vk", "complete", [_item("vk", f"vk:{kind}:{identifier}", title or name, "profile" if kind == "user" else "community",
                    "ВКонтакте", url, description, row)], "Данные получены официальным VK API в пределах прав токена.")


def _wayback(query, options):
    target = _public_url(query["text"])
    module = _load("wayback", "waybackpy", options)
    import requests
    import waybackpy.cdx_api as cdx_api
    from waybackpy.cdx_utils import check_for_blocked_site
    from unittest.mock import patch
    # The upstream CDX helper has no timeout and retries five times. Replace
    # only its HTTP transport; actual CDX request construction/parser stay local.
    def bounded_get(url, headers=None, **_):
        response = requests.get(url, headers=headers, timeout=(3, min(_timeout(query), 12)))
        response.raise_for_status()
        check_for_blocked_site(response, target)
        return response
    count = max(1, min(int(query.get("limit", 5)), 10))
    api = module.WaybackMachineCDXServerAPI(target, user_agent="GrangerPet/2.0 public archive lookup",
                filters=["statuscode:200"], collapses=["timestamp:6"], limit=str(count), max_tries=1, use_pagination=False)
    results = []
    with patch.object(cdx_api, "get_response", bounded_get):
        for snapshot in api.snapshots():
            results.append(_item("wayback", f"wayback:{snapshot.timestamp}:{snapshot.original}",
                f"Архив · {snapshot.original}", "archive", "Internet Archive", snapshot.archive_url,
                f"Сохранённая версия · {snapshot.mimetype} · HTTP {snapshot.statuscode}",
                {"original_url": snapshot.original, "timestamp": snapshot.timestamp, "statuscode": snapshot.statuscode,
                 "digest": snapshot.digest, "mimetype": snapshot.mimetype}, snapshot.datetime_timestamp.isoformat()))
            if len(results) >= count:
                break
    return _out("wayback", "complete" if results else "empty", results,
                "Получены существующие архивные снимки. Новое архивирование не запускалось." if results else "Архивные снимки не найдены.")


def run_adapter(source: str, query: dict, options: dict) -> dict:
    try:
        if source == "instagram":
            return _instagram(query, options)
        if source == "telegram":
            async def bounded():
                return await asyncio.wait_for(_telegram_async(query, options), _timeout(query))
            return asyncio.run(bounded())
        if source == "vk":
            return _vk(query, options)
        if source == "wayback":
            return _wayback(query, options)
        return _out(source, "unavailable", message="Неизвестный адаптер источника.")
    except (ImportError, FileNotFoundError) as error:
        return _out(source, "unavailable", message=f"Не подготовлен локальный источник или его зависимости: {type(error).__name__}. Запустите setup_sources.py.")
    except (TimeoutError, asyncio.TimeoutError):
        return _out(source, "timeout", message="Источник не ответил за отведённое время.")
    except ValueError as error:
        return _out(source, "error", message=str(error)[:300])
    except Exception as error:
        name = type(error).__name__
        if source == "instagram" and name == "ConnectionException":
            reason = str(error).lower()
            if "401" in reason or "login_required" in reason or "login required" in reason:
                return _out(source, "auth_required", message="Instagram отклонил анонимный запрос. Подключите свою разрешённую сессию; приватные данные не запрашиваются.")
            if "429" in reason or "too many" in reason or "please wait" in reason:
                return _out(source, "unavailable", message="Instagram временно ограничил запросы. Повторите позже; автоматического обхода нет.")
            return _out(source, "unavailable", message="Публичный endpoint Instagram недоступен или отклонил запрос. Проверьте подключение и разрешённую сессию.")
        if name in {"ProfileNotExistsException", "QueryReturnedNotFoundException", "UsernameNotOccupiedError", "NoCDXRecordFound"}:
            return _out(source, "empty", message="Публичный объект или архивная запись не найдены.")
        if any(word in name for word in ("Login", "Auth", "Credentials", "Session", "Forbidden", "Private", "Unauthorized")):
            return _out(source, "auth_required", message="Источник требует действующей авторизованной сессии или не разрешает доступ к этому объекту.")
        if source == "vk" and hasattr(error, "code"):
            code = int(error.code)
            state,message={5:('auth_required','VK отклонил токен. Сохраните новый действующий токен.'),
                7:('auth_required','VK не разрешает этот метод вашему токену.'),
                15:('auth_required','VK ограничил доступ к объекту или требуется токен с подходящими правами.'),
                18:('empty','Профиль VK удалён или заблокирован.'),
                30:('unavailable','VK ограничил доступ настройками приватности.'),
                6:('rate_limited','VK ограничил частоту запросов. Повторите позже.'),
                9:('rate_limited','VK временно ограничил этот метод. Повторите позже.'),
                29:('rate_limited','Достигнут лимит запросов VK API.'),
                14:('unavailable','VK запросил CAPTCHA. Автоматического обхода нет.'),
                10:('unavailable','Временная ошибка VK. Повторите позже.'),
                100:('error','VK отклонил параметры идентификатора.'),
                113:('empty','Пользователь VK не найден.')}.get(code,('unavailable','VK API отклонил запрос. Проверьте права токена.'))
            return _out(source,state,message=f'{message} Код VK: {code}.')
        if any(word in name for word in ("Flood", "TooMany", "RateLimit", "Blocked")):
            return _out(source, "unavailable", message="Источник ограничил запросы или доступ. Повторите позже; автоматического обхода нет.")
        return _out(source, "error", message=f"Источник не выполнил запрос ({name}); сведения не подменялись.")
