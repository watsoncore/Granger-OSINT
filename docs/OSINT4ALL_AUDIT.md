# OSINT4ALL: технический аудит источников

Проверена именно [заданная коллекция](https://start.me/p/L1rEYQ/osint4all), 29 октября 2026 года. HTTP вернул 403 с Cloudflare challenge, web-reader —0 строк. Защиты не обходились. Ответ 403/challenge терминален и не передаётся браузеру для обхода.

**Полная коллекция не извлечена.** Другая страница Start.me не используется вместо неё. [Официальный экспорт](https://blog.start.me/export-bookmarks/) описывает меню пользователя; анонимный экспорт именно этой коллекции не получен. Все 153 пункта раздела 3.2 задания рассмотрены как отдельный частичный перечень. Это имена из текста, а не href заблокированной коллекции.

## Количества

| Метрика | Количество |
| --- | ---: |
| Записей извлечено из Start.me | 0 |
| Пунктов предоставленного перечня рассмотрено | 153 |
| Пунктов сопоставлено с явной официальной/репозиторной ссылкой | 119 |
| Пунктов без установленного точного URL | 34 |
| Дублирующихся URL | 6 |
| Уникальных URL проверено HTTP | 113 |
| Ответов HTTP200 на landing/docs GET | 71 |
| Недоступно в этой пробе:4xx/5xx/DNS/TLS/timeout | 20 |
| Страниц явной защиты | 5 |
| Пунктов с подтверждённым контрактом авторизации | 12 |
| Пунктов с подтверждённым API без персонального ключа | 11 |
| Конкретных scraping-операций из перечня проверено | 0 |
| Пунктов с реализованной узкой операцией | 23 |
| Интегрировано по извлечённым записям Start.me | 0 |
| Live-проверено по извлечённым записям Start.me | 0 |

HTTP200 не означает работающий поиск или разрешение scraping. Недоступность в одном пробном GET не доказывает закрытие сайта. Совпадающий домен не считается дубликатом: дубли фиксируются по одинаковому исследованному URL. Неизвестное API-поведение не объявляется обязательным платным доступом. Несколько пунктов могут относиться к одному прежнему адаптеру.

HN Algolia и Open Library дополнительно исследованы вне 153 пунктов и отмечены `from_catalog:false`. Кандидаты не выводятся в рабочий каталог как функциональность. Результаты реальных production-адаптеров сохраняются отдельно; этот landing-аудит не присваивает им `live_verified`.

## Отбор и официальные контракты

- Открытая поисковая форма сама по себе не разрешает автоматизацию. [Robots DuckDuckGo](https://duckduckgo.com/robots.txt) запрещает `/html` и `/lite`; эти пути не используются как backend. CAPTCHA, авторизация и ограничения не обходятся.
- [GitHub users](https://docs.github.com/en/rest/users/users#get-a-user), [search](https://docs.github.com/en/rest/search/search), [rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api): без авторизации 60 REST-запросов/час/IP и 10 search-запросов/мин; учитываются 403/429/Reset.
- [Hacker News Algolia API](https://hn.algolia.com/api): query/tags/hitsPerPage и документированный предел 10000/час/IP. Приложение использует существенно меньше.
- [Open Library Search](https://openlibrary.org/dev/docs/api/search), [правила API](https://openlibrary.org/developers/api): идентифицирующий User-Agent, cache, консервативно 1 запрос/с. Персональный ключ не нужен.
- [Internet Archive Advanced Search](https://archive.org/advancedsearch.php) описывает JSON/XML/RSS, query/fields/rows. [Automated Access](https://archive.org/developers/bots.html) требует UA с названием/версией инструмента, для AI — моделью, cache и Retry-After. `/developers/search.html` является поиском по документации, а не описанием Advanced Search.
- [MediaWiki Search](https://www.mediawiki.org/wiki/API:Search), [Etiquette](https://www.mediawiki.org/wiki/API:Etiquette): описательный UA, последовательные запросы, cache, API errors. Это ограниченные индексы, не полный интернет.
- [Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/): только отдельные пользовательские запросы, без autocomplete/bulk, UA и атрибуция, максимум 1 запрос/с. Приложение дополнительно ограничивает 30 новых запросов/час.
- [Overpass quotas](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html): небольшие query, cache/backoff, без массового backend. Реализован фиксированный запрос 500 м/20 объектов/1 МиБ/10 с server timeout.
- [GeoSeer API](https://www.geoseer.net/api.php) платный; GeoNames требует собственного username, Mapillary — токена. Публичная главная страница не означает бесплатный API.

Telegago найден как официальный Telegram-бот; TelegramDB описывает аккаунтные и бот-операции. Они не объявлены анонимными HTTP API. Для неоднозначных Telegram Search, GEOINT Search, GeoIP Tracker, Bitcoin Explorer, YouTube metadata tools и общих направлений сохраняется пустой URL, если точный первичный адрес не установлен. Прежние Telegram/VK/Instagram/VirusTotal/Gansar/CLI остаются только в пределах своих реализованных операций.

## Реальные примеры

Default Nominatim-запрос `London Bridge` вернул 5 кандидатов без ключа/override. Например, OSM way `378493707`:51.508049,-0.0876715. Это географический кандидат, не установленное место съёмки. Отчёт: `output/autonomous-qa/geoint-defaults-live.json`.

Default Overpass завершился timeout12 с; отдельный ограниченный повтор с read timeout20 с также timeout (`overpass-defaults-recheck.json`). Перебора серверов и объявления успеха не было.

Локальный Tesseract проверен на настоящих пикселях rus/eng, EXIF rotation, пустом изображении с `low_confidence` и единственном установленном языковом пакете. Эти проверки не используют сайты или персональные API. Примеры новых root-адаптеров проверяются отдельно в production live-прогоне.

## Все 153 пункта

Полные поля Category, Name, Actual URL, Domain, Original Catalog URL, Access, Public API, Permitted Scraping, JS, Test, Reason, Adapter, Input, Output и Last Checked находятся в [OSINT4ALL_AUDIT.json](OSINT4ALL_AUDIT.json). Ниже — сокращённая матрица. `not_verified` означает отсутствие подтверждённого контракта, а не запрет.

| ID | Категория / имя | Исследованный URL | Доступ / API | HTTP-проба | Решение / адаптеры |
| --- | --- | --- | --- | --- | --- |
| supplied_001 | Поисковики и общий веб-поиск · **Google Search** | [www.google.com](https://www.google.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_002 | Поисковики и общий веб-поиск · **Bing** | [www.bing.com](https://www.bing.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_003 | Поисковики и общий веб-поиск · **Yandex** | [yandex.com](https://yandex.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_004 | Поисковики и общий веб-поиск · **DuckDuckGo** | [duckduckgo.com](https://duckduckgo.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_005 | Поисковики и общий веб-поиск · **Brave Search** | [search.brave.com](https://search.brave.com/) | public_website_or_unresolved / not_verified | HTTP429 | operation_permission_or_parser_not_verified; — |
| supplied_006 | Поисковики и общий веб-поиск · **Startpage** | [www.startpage.com](https://www.startpage.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_007 | Поисковики и общий веб-поиск · **Mojeek** | [www.mojeek.com](https://www.mojeek.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_008 | Поисковики и общий веб-поиск · **Yahoo Search** | [search.yahoo.com](https://search.yahoo.com/) | public_website_or_unresolved / not_verified | HTTP500 | operation_permission_or_parser_not_verified; — |
| supplied_009 | Поисковики и общий веб-поиск · **Baidu** | [www.baidu.com](https://www.baidu.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_010 | Поисковики и общий веб-поиск · **Qwant** | [www.qwant.com](https://www.qwant.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_011 | Поисковики и общий веб-поиск · **Searx / SearXNG** | [docs.searxng.org](https://docs.searxng.org/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_012 | Поисковики и общий веб-поиск · **Ecosia** | [www.ecosia.org](https://www.ecosia.org/) | public_website_or_unresolved / not_verified | HTTP403 | operation_permission_or_parser_not_verified; — |
| supplied_013 | Поисковики и общий веб-поиск · **Dogpile** | [www.dogpile.com](https://www.dogpile.com/) | public_website_or_unresolved / not_verified | HTTP202 | operation_permission_or_parser_not_verified; — |
| supplied_014 | Поисковики и общий веб-поиск · **Swisscows** | [swisscows.com](https://swisscows.com/) | public_website_or_unresolved / not_verified | HTTP307 | operation_permission_or_parser_not_verified; — |
| supplied_015 | Поисковики и общий веб-поиск · **Google Custom Search** | [developers.google.com](https://developers.google.com/custom-search/v1/overview) | public_api_or_documentation / documented_auth_or_key | HTTP200 | optional_auth_or_paid_api_not_basic_search; — |
| supplied_016 | Поисковики и общий веб-поиск · **Google Advanced Search** | [www.google.com](https://www.google.com/advanced_search) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_017 | Username / SOCMINT · **Maigret** | [github.com](https://github.com/soxoj/maigret) | local_project / not_verified | HTTP200 | existing_or_implemented_scoped_adapter; username_maigret |
| supplied_018 | Username / SOCMINT · **Sherlock** | [github.com](https://github.com/sherlock-project/sherlock) | local_project / not_verified | HTTP200 | local_project_not_integrated; — |
| supplied_019 | Username / SOCMINT · **Social Analyzer** | [github.com](https://github.com/qeeqbox/social-analyzer) | local_project / not_verified | HTTP200 | existing_or_implemented_scoped_adapter; username_social_analyzer |
| supplied_020 | Username / SOCMINT · **WhatsMyName** | [github.com](https://github.com/WebBreacher/WhatsMyName) | local_project / not_verified | HTTP200 | local_project_not_integrated; — |
| supplied_021 | Username / SOCMINT · **Namechk** | [namechk.com](https://namechk.com/) | public_website_or_unresolved / not_verified | HTTP403 | blocked_or_challenge_no_bypass; — |
| supplied_022 | Username / SOCMINT · **Reddit** | [www.reddit.com](https://www.reddit.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_023 | Username / SOCMINT · **Reddit Search** | [www.reddit.com](https://www.reddit.com/search/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_024 | Username / SOCMINT · **Reddit Archive** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_025 | Username / SOCMINT · **Pushshift** | [pushshift.io](https://pushshift.io/) | public_website_or_unresolved / not_verified | HTTP307 | operation_permission_or_parser_not_verified; — |
| supplied_026 | Username / SOCMINT · **GitHub** | [docs.github.com](https://docs.github.com/en/rest/users/users#get-a-user) | public_api_or_documentation / documented_no_personal_key | HTTP200 | existing_or_implemented_scoped_adapter; github_repository, github_profile, github_users, github_repositories |
| supplied_027 | Username / SOCMINT · **TikTok** | [developers.tiktok.com](https://developers.tiktok.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_028 | Username / SOCMINT · **YouTube** | [developers.google.com](https://developers.google.com/youtube/v3) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_029 | Username / SOCMINT · **Steam Community** | [steamcommunity.com](https://steamcommunity.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_030 | Username / SOCMINT · **Twitch** | [dev.twitch.tv](https://dev.twitch.tv/docs/api/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_031 | Username / SOCMINT · **Mastodon** | [docs.joinmastodon.org](https://docs.joinmastodon.org/methods/accounts/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_032 | Username / SOCMINT · **Discord** | [discord.com](https://discord.com/developers/docs/intro) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_033 | Username / SOCMINT · **Telegram** | [core.telegram.org](https://core.telegram.org/api) | public_api_or_documentation / documented_auth_or_key | HTTP200 | existing_or_implemented_scoped_adapter; telegram_public |
| supplied_034 | Username / SOCMINT · **VK** | [dev.vk.com](https://dev.vk.com/ru/reference) | public_api_or_documentation / documented_auth_or_key | PageReadError | existing_or_implemented_scoped_adapter; vk_public |
| supplied_035 | Username / SOCMINT · **Facebook** | [developers.facebook.com](https://developers.facebook.com/docs/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_036 | Username / SOCMINT · **Instagram** | [developers.facebook.com](https://developers.facebook.com/docs/instagram-platform/) | public_api_or_documentation / documented_auth_or_key | HTTP301 | existing_or_implemented_scoped_adapter; instagram_public |
| supplied_037 | Username / SOCMINT · **LinkedIn** | [learn.microsoft.com](https://learn.microsoft.com/en-us/linkedin/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_038 | Telegram · **Telegago** | [t.me](https://t.me/TelegagoBot) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_039 | Telegram · **Telegram Search** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_040 | Telegram · **Telegram Search for Posts** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_041 | Telegram · **Search.buzz.im** | [search.buzz.im](https://search.buzz.im/) | public_website_or_unresolved / not_verified | PageReadError | operation_permission_or_parser_not_verified; — |
| supplied_042 | Telegram · **Telegram Usernames Finder** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_043 | Telegram · **Telegram Channels List** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_044 | Telegram · **Readergram** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_045 | Telegram · **Tgstat-подобные публичные источники, если они реально доступны** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_046 | Telegram · **TelegramDB** | [github.com](https://github.com/TelegramDB/TelegramDB) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_047 | Telegram · **Telegram Search Engine** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_048 | Telegram · **существующий Telegram-адаптер Granger-OSINT** | [core.telegram.org](https://core.telegram.org/api) | public_api_or_documentation / documented_auth_or_key | HTTP200 | existing_or_implemented_scoped_adapter; telegram_public |
| supplied_049 | Домены, IP, DNS и инфраструктура · **RDAP** | [www.iana.org](https://www.iana.org/assignments/rdap-dns/rdap-dns.xhtml) | public_api_or_documentation / documented_no_personal_key | HTTP302 | existing_or_implemented_scoped_adapter; domain_lookup |
| supplied_050 | Домены, IP, DNS и инфраструктура · **WHOIS** | [www.icann.org](https://www.icann.org/rdap) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_051 | Домены, IP, DNS и инфраструктура · **DNS lookup** | [developers.google.com](https://developers.google.com/speed/public-dns/docs/doh/json) | public_api_or_documentation / documented_no_personal_key | HTTP200 | existing_or_implemented_scoped_adapter; domain_lookup |
| supplied_052 | Домены, IP, DNS и инфраструктура · **SecurityTrails** | [docs.securitytrails.com](https://docs.securitytrails.com/) | public_website_or_unresolved / not_verified | HTTP302 | operation_permission_or_parser_not_verified; — |
| supplied_053 | Домены, IP, DNS и инфраструктура · **Shodan** | [developer.shodan.io](https://developer.shodan.io/api) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_054 | Домены, IP, DNS и инфраструктура · **Censys** | [docs.censys.com](https://docs.censys.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_055 | Домены, IP, DNS и инфраструктура · **GreyNoise** | [docs.greynoise.io](https://docs.greynoise.io/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_056 | Домены, IP, DNS и инфраструктура · **ONYPHE** | [www.onyphe.io](https://www.onyphe.io/) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_057 | Домены, IP, DNS и инфраструктура · **ViewDNS** | [viewdns.info](https://viewdns.info/api/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_058 | Домены, IP, DNS и инфраструктура · **DomainBigData** | [domainbigdata.com](https://domainbigdata.com/) | public_website_or_unresolved / not_verified | HTTP530 | operation_permission_or_parser_not_verified; — |
| supplied_059 | Домены, IP, DNS и инфраструктура · **Domain Codex** | [domaincodex.com](https://domaincodex.com/) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_060 | Домены, IP, DNS и инфраструктура · **DNSlytics** | [dnslytics.com](https://dnslytics.com/api) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_061 | Домены, IP, DNS и инфраструктура · **FOFA** | [en.fofa.info](https://en.fofa.info/api) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_062 | Домены, IP, DNS и инфраструктура · **Netlas** | [docs.netlas.io](https://docs.netlas.io/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_063 | Домены, IP, DNS и инфраструктура · **crt.sh и доступные данные сертификатов** | [crt.sh](https://crt.sh/) | public_website_or_unresolved / not_verified | HTTP502 | operation_permission_or_parser_not_verified; — |
| supplied_064 | Домены, IP, DNS и инфраструктура · **публичные RDAP-серверы** | [www.iana.org](https://www.iana.org/assignments/rdap-dns/rdap-dns.xhtml) | public_api_or_documentation / documented_no_personal_key | HTTP302 | existing_or_implemented_scoped_adapter; domain_lookup |
| supplied_065 | GEOINT · **OpenStreetMap** | [www.openstreetmap.org](https://www.openstreetmap.org/) | public_website_or_unresolved / not_verified | HTTP200 | existing_or_implemented_scoped_adapter; map_overpass, map_geocode |
| supplied_066 | GEOINT · **Overpass** | [dev.overpass-api.de](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html) | public_api_or_documentation / documented_no_personal_key | HTTP200 | existing_or_implemented_scoped_adapter; map_overpass |
| supplied_067 | GEOINT · **Nominatim** | [operations.osmfoundation.org](https://operations.osmfoundation.org/policies/nominatim/) | public_api_or_documentation / documented_no_personal_key | HTTP200 | existing_or_implemented_scoped_adapter; map_geocode |
| supplied_068 | GEOINT · **GeoNames** | [www.geonames.org](https://www.geonames.org/export/web-services.html) | public_api_or_documentation / documented_auth_or_key | HTTP200 | optional_auth_or_paid_api_not_basic_search; — |
| supplied_069 | GEOINT · **Mapillary** | [www.mapillary.com](https://www.mapillary.com/developer/api-documentation/) | public_api_or_documentation / documented_auth_or_key | HTTP302 | optional_auth_or_paid_api_not_basic_search; — |
| supplied_070 | GEOINT · **Wikimedia Commons** | [www.mediawiki.org](https://www.mediawiki.org/wiki/Extension:GeoData) | public_api_or_documentation / documented_no_personal_key | HTTP200 | existing_or_implemented_scoped_adapter; map_wikimedia |
| supplied_071 | GEOINT · **GeoSeer** | [www.geoseer.net](https://www.geoseer.net/about.php) | public_api_or_documentation / documented_auth_or_key | HTTP200 | optional_auth_or_paid_api_not_basic_search; — |
| supplied_072 | GEOINT · **GEOINT Search** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_073 | GEOINT · **GeoIP Tracker** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_074 | GEOINT · **FAO Map Catalog** | [data.apps.fao.org](https://data.apps.fao.org/map/catalog/) | public_website_or_unresolved / not_verified | HTTP502 | operation_permission_or_parser_not_verified; — |
| supplied_075 | GEOINT · **ArcGIS Open Data** | [developers.arcgis.com](https://developers.arcgis.com/rest/users-groups-and-items/search-reference/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_076 | GEOINT · **доступные публичные географические каталоги** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_077 | Карты · **Google Maps** | [developers.google.com](https://developers.google.com/maps/documentation) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_078 | Карты · **Bing Maps** | [learn.microsoft.com](https://learn.microsoft.com/en-us/bingmaps/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_079 | Карты · **Yandex Maps** | [yandex.com](https://yandex.com/maps-api/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_080 | Карты · **OpenStreetMap** | [www.openstreetmap.org](https://www.openstreetmap.org/) | public_website_or_unresolved / not_verified | HTTP200 | existing_or_implemented_scoped_adapter; map_overpass, map_geocode |
| supplied_081 | Карты · **MapQuest** | [developer.mapquest.com](https://developer.mapquest.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_082 | Карты · **Mapillary** | [www.mapillary.com](https://www.mapillary.com/developer/api-documentation/) | public_api_or_documentation / documented_auth_or_key | HTTP302 | duplicate_technical_entry; — |
| supplied_083 | Карты · **Waze** | [developers.google.com](https://developers.google.com/waze) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_084 | Карты · **GeoNames** | [www.geonames.org](https://www.geonames.org/export/web-services.html) | public_api_or_documentation / documented_auth_or_key | HTTP200 | duplicate_technical_entry; — |
| supplied_085 | Карты · **DigitalGlobe** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_086 | Карты · **Satellites.pro** | [satellites.pro](https://satellites.pro/) | public_website_or_unresolved / not_verified | HTTP403 | blocked_or_challenge_no_bypass; — |
| supplied_087 | Карты · **Windy** | [api.windy.com](https://api.windy.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_088 | Карты · **ArcGIS Living Atlas** | [livingatlas.arcgis.com](https://livingatlas.arcgis.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_089 | Карты · **FIRMS** | [firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/api/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_090 | Карты · **OpenStreetMap-based services** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_091 | Архивы и новости · **Internet Archive** | [archive.org](https://archive.org/advancedsearch.php) | public_api_or_documentation / documented_no_personal_key | PageReadError | operation_not_live_verified; исключён из рабочего реестра после двух timeout |
| supplied_092 | Архивы и новости · **Wayback Machine** | [archive.org](https://archive.org/help/wayback_api.php) | public_api_or_documentation / documented_no_personal_key | PageReadError | existing_or_implemented_scoped_adapter; web_archive |
| supplied_093 | Архивы и новости · **Google News** | [news.google.com](https://news.google.com/) | public_website_or_unresolved / not_verified | HTTP302 | operation_permission_or_parser_not_verified; — |
| supplied_094 | Архивы и новости · **NewsLookup** | [www.newslookup.com](https://www.newslookup.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_095 | Архивы и новости · **Newspapers.com** | [www.newspapers.com](https://www.newspapers.com/) | public_website_or_unresolved / not_verified | HTTP403 | blocked_or_challenge_no_bypass; — |
| supplied_096 | Архивы и новости · **Newspaper Archive** | [newspaperarchive.com](https://newspaperarchive.com/) | public_website_or_unresolved / not_verified | HTTP403 | blocked_or_challenge_no_bypass; — |
| supplied_097 | Архивы и новости · **Paperball** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_098 | Архивы и новости · **NewsNow** | [www.newsnow.com](https://www.newsnow.com/) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_099 | Архивы и новости · **публичные RSS** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_100 | Архивы и новости · **Wikimedia / Wikipedia** | [www.mediawiki.org](https://www.mediawiki.org/wiki/API:Search) | public_api_or_documentation / documented_no_personal_key | HTTP200 | existing_or_implemented_scoped_adapter; wikipedia_search |
| supplied_101 | Архивы и новости · **открытые новостные архивы** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_102 | Threat Intelligence · **VirusTotal** | [docs.virustotal.com](https://docs.virustotal.com/reference/overview) | public_api_or_documentation / documented_auth_or_key | HTTP200 | existing_or_implemented_scoped_adapter; hash_virustotal |
| supplied_103 | Threat Intelligence · **AlienVault OTX** | [otx.alienvault.com](https://otx.alienvault.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_104 | Threat Intelligence · **FortiGuard** | [www.fortiguard.com](https://www.fortiguard.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_105 | Threat Intelligence · **Cisco Talos** | [talosintelligence.com](https://talosintelligence.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_106 | Threat Intelligence · **ThreatMiner** | [www.threatminer.org](https://www.threatminer.org/api.php) | public_website_or_unresolved / not_verified | PageReadError | operation_permission_or_parser_not_verified; — |
| supplied_107 | Threat Intelligence · **ThreatButt** | [threatbutt.com](https://threatbutt.com/about) | public_website_or_unresolved / not_verified | gaierror | operation_permission_or_parser_not_verified; — |
| supplied_108 | Threat Intelligence · **URLhaus-подобные публичные индикаторные источники, если обнаружены** | [urlhaus.abuse.ch](https://urlhaus.abuse.ch/api/) | public_api_or_documentation / documented_auth_or_key | HTTP200 | optional_auth_or_paid_api_not_basic_search; — |
| supplied_109 | Threat Intelligence · **публичные malware/IOC feeds** | [feodotracker.abuse.ch](https://feodotracker.abuse.ch/blocklist/) | public_api_or_documentation / documented_no_personal_key | HTTP200 | existing_or_implemented_scoped_adapter; threat_feodo |
| supplied_110 | Публичные данные · **Data.gov** | [data.gov](https://data.gov/developers/apis/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_111 | Публичные данные · **Kaggle Datasets** | [github.com](https://github.com/Kaggle/kaggle-api) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_112 | Публичные данные · **Google Dataset Search** | [datasetsearch.research.google.com](https://datasetsearch.research.google.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_113 | Публичные данные · **OpenDataSoft** | [help.opendatasoft.com](https://help.opendatasoft.com/apis/ods-search-v2/) | public_website_or_unresolved / not_verified | HTTP404 | operation_permission_or_parser_not_verified; — |
| supplied_114 | Публичные данные · **Socrata** | [dev.socrata.com](https://dev.socrata.com/docs/other/discovery/) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_115 | Публичные данные · **data.world** | [apidocs.data.world](https://apidocs.data.world/) | public_website_or_unresolved / not_verified | HTTP302 | operation_permission_or_parser_not_verified; — |
| supplied_116 | Публичные данные · **OpenSanctions** | [www.opensanctions.org](https://www.opensanctions.org/docs/api/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_117 | Публичные данные · **государственные открытые реестры** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_118 | Публичные данные · **корпоративные реестры** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_119 | Публичные данные · **опубликованные документы** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_120 | Blockchain · **Bitcoin Explorer** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_121 | Blockchain · **Ethereum Block Explorer** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_122 | Blockchain · **Blockchain Explorer** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_123 | Blockchain · **Blockchair** | [blockchair.com](https://blockchair.com/api/docs) | public_website_or_unresolved / not_verified | HTTP401 | operation_permission_or_parser_not_verified; — |
| supplied_124 | Blockchain · **FlowScan** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_125 | Blockchain · **существующий Gansar** | [github.com](https://github.com/watsoncore/Granger-OSINT) | local_project / not_verified | HTTP404 | existing_or_implemented_scoped_adapter; blockchain_gansar |
| supplied_126 | Blockchain · **другие публичные explorer endpoints, если доступны** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_127 | Изображения и метаданные · **Google Images** | [images.google.com](https://images.google.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_128 | Изображения и метаданные · **Yandex Images** | [yandex.com](https://yandex.com/images/) | public_website_or_unresolved / not_verified | HTTP302 | operation_permission_or_parser_not_verified; — |
| supplied_129 | Изображения и метаданные · **Bing Images** | [www.bing.com](https://www.bing.com/images/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_130 | Изображения и метаданные · **FotoForensics** | [fotoforensics.com](https://fotoforensics.com/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_131 | Изображения и метаданные · **Forensically** | [29a.ch](https://29a.ch/photo-forensics/) | local_project / not_verified | HTTP200 | local_project_not_integrated; — |
| supplied_132 | Изображения и метаданные · **EXIF viewers** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_133 | Изображения и метаданные · **доступные инструменты обработки изображений** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_134 | Изображения и метаданные · **локальные EXIF/OCR/CV-инструменты Granger-OSINT** | [github.com](https://github.com/watsoncore/Granger-OSINT) | local_project / not_verified | HTTP404 | existing_or_implemented_scoped_adapter; image_metadata, image_ocr, image_compare |
| supplied_135 | Авиация и транспорт · **ADS-B Exchange** | [www.adsbexchange.com](https://www.adsbexchange.com/data/) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_136 | Авиация и транспорт · **FlightAware** | [www.flightaware.com](https://www.flightaware.com/commercial/aeroapi/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_137 | Авиация и транспорт · **Flightradar24** | [fr24api.flightradar24.com](https://fr24api.flightradar24.com/docs) | public_website_or_unresolved / not_verified | HTTP302 | operation_permission_or_parser_not_verified; — |
| supplied_138 | Авиация и транспорт · **PlaneSpotters** | [www.planespotters.net](https://www.planespotters.net/) | public_website_or_unresolved / not_verified | HTTP403 | blocked_or_challenge_no_bypass; — |
| supplied_139 | Авиация и транспорт · **SkyScanner** | [developers.skyscanner.net](https://developers.skyscanner.net/) | public_website_or_unresolved / not_verified | HTTP200 | operation_permission_or_parser_not_verified; — |
| supplied_140 | Авиация и транспорт · **RadarBox** | [www.radarbox.com](https://www.radarbox.com/) | public_website_or_unresolved / not_verified | HTTP301 | operation_permission_or_parser_not_verified; — |
| supplied_141 | Авиация и транспорт · **публичные транспортные реестры и открытые данные** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_142 | YouTube · **YouTube metadata tools** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_143 | YouTube · **yt-dlp** | [github.com](https://github.com/yt-dlp/yt-dlp) | local_project / not_verified | HTTP200 | local_project_not_integrated; — |
| supplied_144 | YouTube · **поиск видео** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_145 | YouTube · **поиск каналов** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_146 | YouTube · **поиск публичных описаний и комментариев при наличии разрешённого интерфейса** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_147 | YouTube · **инструменты анализа метаданных публикаций** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_148 | GitHub/локальные инструменты · **CyberChef** | [github.com](https://github.com/gchq/CyberChef) | local_project / not_verified | HTTP200 | local_project_not_integrated; — |
| supplied_149 | GitHub/локальные инструменты · **theHarvester** | [github.com](https://github.com/laramies/theHarvester) | local_project / not_verified | HTTP200 | local_project_not_integrated; — |
| supplied_150 | GitHub/локальные инструменты · **Holehe** | [github.com](https://github.com/megadose/holehe) | local_project / not_verified | HTTP200 | existing_or_implemented_scoped_adapter; email_holehe |
| supplied_151 | GitHub/локальные инструменты · **PhoneInfoga** | [github.com](https://github.com/sundowndev/phoneinfoga) | local_project / not_verified | HTTP200 | existing_or_implemented_scoped_adapter; phone_metadata |
| supplied_152 | GitHub/локальные инструменты · **существующие локальные инструменты** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |
| supplied_153 | GitHub/локальные инструменты · **другие подходящие open-source проекты из каталога** | Не установлен | public_website_or_unresolved / not_verified | Не live | unresolved_source_or_direction; — |

## Воспроизводимость

`scripts/audit_osint_catalog.py --request-file <текст задания>` пересобирает решения из зафиксированных проб без сети. `--probe-missing` проверяет только новые явные ссылки; `--live` явно повторяет GET-пробы. Карта URL задана после рассмотрения первичных источников, адреса не создаются из названий.

HTTP-пробы используют DNS-pinned SSRF-проверку, максимум 200 КиБ, timeout7 с, без переходов по редиректам и без JS. Обновлённый сборщик ограничен 5 общими и 1 per-domain слотами с паузой 1.1 с. Первоначальный landing-прогон имел 5 общих слотов. Пересборка из cache не называется новым HTTP-запросом. Сохраняются публичные title/status/hash, без cookies, паролей или профилей пользователя.

Не выполнены: полный экспорт Start.me, операции коммерческих сервисов без доступа, подтверждение scraping неизвестных форм и идентификация неоднозначных названий без ссылок. Это не блокирует независимые разрешённые операции других источников.
