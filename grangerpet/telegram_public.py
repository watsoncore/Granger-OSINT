"""Public Telegram pages/previews through the existing restricted HTTP reader.

No session, private channel, contact import, challenge or guessed owner lookup.
The optional authorized operation remains in the existing isolated adapter.
"""
from copy import deepcopy
import re
from urllib.parse import urlsplit
from .engine.router import _platform

INPUT_SCHEMA = {'type': 'object', 'properties': {
    'username': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
    'access_mode': {'type': 'string', 'enum': ['public', 'authorized']},
    'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20}},
    'required': ['username'], 'additionalProperties': False}


def execute(value, *, reader, limit=20, cancel_event=None, deadline=None):
    try:
        canonical = _platform(value, 'telegram')
    except ValueError:
        return {'status': 'invalid_arguments', 'results': [], 'error_code': 'invalid_public_telegram_target'}
    parts = [p for p in urlsplit(canonical).path.split('/') if p]
    username = parts[0]
    base = 'https://t.me/' + username
    urls = [canonical, 'https://t.me/s/' + username]
    records, warnings, failures = [], [], []
    for url in dict.fromkeys(urls):
        if cancel_event and cancel_event.is_set():
            return {'status': 'cancelled', 'results': records, 'limitations': warnings}
        reader.allow_url(url, depth=0)
        outcome = reader.read(url, cancel_event=cancel_event, deadline=deadline)
        if outcome.get('status') not in ('complete', 'partial'):
            failures.append(outcome)
            warnings.extend(outcome.get('limitations', []))
            if outcome.get('status') in ('cancelled', 'timeout', 'blocked', 'limit_reached'):
                break
            continue
        for raw in outcome.get('results', [])[:1]:
            row = deepcopy(raw)
            details = row.get('details') or {}
            metadata = details.get('metadata') or {}
            links = details.get('links') or []
            posts = [link['url'] for link in links if isinstance(link, dict) and isinstance(link.get('url'), str)
                     and re.fullmatch(r'https://t\.me/' + re.escape(username) + r'/\d+', link['url'], re.I)]
            is_preview = urlsplit(row.get('url', '')).path.startswith('/s/')
            channel = is_preview and bool(posts)
            title = metadata.get('og:title') if isinstance(metadata, dict) else None
            row.update(platform='Telegram', title=title or row['title'],
                       type='community' if channel else 'web', status='content_observed')
            row['details'] = {**details, 'username': username, 'canonical_url': base,
                'platform': 'telegram', 'entity_type': 'telegram_channel' if channel else 'public_channel_or_profile',
                'object_type_verified': channel, 'identity_verified': False, 'public_post_urls': posts[:20],
                'access_mode': 'public', 'requires_session': False,
                'preview': is_preview, 'existence_verified': channel,
                'verification': 'Наблюдалось только доступное публичное содержимое Telegram; владелец не установлен.'}
            records.append(row)
            if len(records) >= limit:
                break
        if len(records) >= limit:
            break
    warnings += ['Публичная страница не устанавливает владельца. Тип канала подтверждается только доступным превью с публикациями; личные и закрытые данные не запрашиваются.']
    status = 'partial' if records and failures else 'complete' if records else (failures[-1].get('status', 'empty') if failures else 'empty')
    result = {'status': status, 'results': records, 'limitations': list(dict.fromkeys(warnings))[:12]}
    if failures and not records:
        result['error_code'] = failures[-1].get('error') or failures[-1].get('error_code') or 'telegram_public_unavailable'
    return result
