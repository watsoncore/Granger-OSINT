"""Documented candidates, deliberately outside the executable ToolRegistry.

No import or catalog read performs network access, reads credentials, or upgrades
an entry to installed/configured/verified. These are research records only.
"""
from __future__ import annotations

from copy import deepcopy


OSINT4ALL_AUDIT = {
    'url': 'https://start.me/p/L1rEYQ/osint4all',
    'checked_at': '2026-10-29',
    'extracted_candidates': 0,
    'status': 'content_unavailable',
    'reason': 'Прямой HTTP-запрос получил 403/challenge; web-reader вернул 0 строк. '
              'Индексированные страницы с другими ID не подменяют указанную коллекцию. Ограничения не обходились.',
}


def _candidate(identifier, name, category, description, inputs, url, docs, mode,
               *, auth=(), limits='', reason='', runtime_mode='unavailable'):
    return {
        'id': 'candidate_' + identifier, 'name': name, 'category': category,
        'description': description, 'accepted_inputs': list(inputs),
        'source_url': url, 'documentation_url': docs, 'access_mode': mode,
        'auth_requirements': list(auth), 'rate_limit_policy': limits,
        'status': 'catalog_only', 'state': 'catalog_only', 'readiness_status': 'catalog_only',
        'implemented': False, 'available': False, 'live_verified': False,
        'runtime_mode': runtime_mode, 'reason': reason,
        'provenance': 'official_documentation', 'checked_at': '2026-10-29',
        'from_osint4all': False,
    }


_CANDIDATES = (
    _candidate('google_lens', 'Google Lens', 'geoint',
        'Ручной обратный поиск по изображению через официальный интерфейс Google.', ('image',),
        'https://lens.google/', 'https://support.google.com/websearch/answer/1325808', 'MANUAL_ONLY',
        reason='Официальная справка описывает ручную загрузку; программный Lens API в Granger-OSINT не подключён. '
               'Фотография автоматически не передаётся.', runtime_mode='manual_handoff'),
    _candidate('yandex_images', 'Yandex Images', 'geoint',
        'Ручной поиск копий и похожих изображений.', ('image',),
        'https://yandex.com/images/', 'https://yandex.ru/support/browser/en/search-and-browse/search-image', 'MANUAL_ONLY',
        reason='Доступен ручной интерфейс. Автоматизация загрузки и обход ограничений не реализованы.', runtime_mode='manual_handoff'),
    _candidate('bing_visual_search', 'Bing Visual Search API (закрыт)', 'geoint',
        'Исторический API обратного поиска; сохранён как явно неподдерживаемый кандидат.', ('image',),
        'https://www.microsoft.com/en-us/bing/apis/bing-visual-search-api',
        'https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement', 'NOT_SUPPORTED',
        reason='Microsoft объявила прекращение Bing Search APIs 11 августа 2025 года. '
               'Этот API не предлагается как доступная интеграция.'),
    _candidate('tineye', 'TinEye', 'geoint',
        'Обратный поиск изображения; отдельный API-доступ требует учётной записи провайдера.', ('image',),
        'https://tineye.com/', 'https://help.tineye.com/article/184-using-the-tineye-api-web-interface', 'OFFICIAL_API',
        auth=('отдельная учётная запись/API-доступ TinEye',),
        reason='Существование отдельного API подтверждено официальной справкой; его ключ, тариф, '
               'текущий программный протокол и выполнение в Granger-OSINT не проверены. Сейчас только ручной переход.',
        runtime_mode='manual_handoff'),
    _candidate('geonames', 'GeoNames', 'geoint',
        'Географический справочник и поиск ближайших населённых пунктов по заданным координатам.', ('coordinates','place'),
        'https://www.geonames.org/', 'https://www.geonames.org/export/web-services.html', 'OFFICIAL_API',
        auth=('собственное имя пользователя GeoNames с включённым Web Service',),
        limits='Квота зависит от аккаунта и метода. Нужна атрибуция GeoNames; demo-аккаунт запрещён для приложения/тестов.',
        reason='Документация изучена. Собственный аккаунт не предоставлен, исполняемый адаптер не реализован.'),
    _candidate('mapillary', 'Mapillary', 'geoint',
        'Уличные фотографии и географические объекты через документированный Graph API.', ('coordinates','image_id'),
        'https://www.mapillary.com/',
        'https://mapillary.github.io/mapillary-python-sdk/docs/mapillary.models/mapillary.models.client/', 'OFFICIAL_API',
        auth=('клиентский или пользовательский access token Mapillary',),
        limits='Нужны действующие права приложения, условия провайдера и лимиты аккаунта.',
        reason='Официальная документация SDK подтверждает токены; основная API-страница требует входа. '
               'Токен не предоставлен, адаптер и live-запрос не реализованы.'),
    _candidate('leakcheck', 'LeakCheck', 'personal',
        'Кандидат для проверки факта появления разрешённого идентификатора в источниках утечек.', ('email','username'),
        'https://leakcheck.io/', 'https://docs.leakcheck.io/overview', 'OFFICIAL_API',
        auth=('Public API: без ключа; Pro API: собственный ключ и платный доступ',),
        limits='Public API: 1 запрос/с, атрибуция. Pro: лимит и разрешённые операции зависят от плана.',
        reason='Public API документирован для источников и категорий утечки; Pro может возвращать чувствительные поля. '
               'Адаптер не реализован, чужие данные и сырые секреты не запрашивались.'),
    _candidate('urlhaus', 'URLhaus', 'threat_intelligence',
        'Кандидат для сверки URL и хешей с индикаторами распространения вредоносного ПО.', ('url','hash','domain'),
        'https://urlhaus.abuse.ch/', 'https://urlhaus.abuse.ch/api/', 'OFFICIAL_API',
        auth=('собственный abuse.ch Auth-Key',),
        limits='Fair use; коммерческое использование может требовать подписки. Выгрузки не чаще опубликованного интервала.',
        reason='Документация требует Auth-Key. Ключ не предоставлен, адаптер не реализован; '
               'вредоносные файлы не загружаются и не выполняются.'),
    _candidate('threatfox', 'ThreatFox', 'threat_intelligence',
        'Кандидат для чтения опубликованных IOC и поиска по заданному индикатору.', ('ip','domain','hash'),
        'https://threatfox.abuse.ch/', 'https://threatfox.abuse.ch/api/', 'OFFICIAL_API',
        auth=('собственный abuse.ch Auth-Key',),
        limits='Fair use; коммерческий доступ может требовать подписки. Старые IOC могут отсутствовать в API.',
        reason='Официальные read-only методы документированы. Ключ не предоставлен, адаптер и live-проверка не реализованы.'),
)


def catalog_candidates():
    return deepcopy(list(_CANDIDATES))


def catalog_audit():
    return deepcopy(OSINT4ALL_AUDIT)
