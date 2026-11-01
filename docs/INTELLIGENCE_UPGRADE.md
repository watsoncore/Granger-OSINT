# Intelligence upgrade: аудит и ход реализации

Рабочая папка `C:\Users\Admin\Desktop\Hermi_osint`, baseline commit
`339dc29e530cec356f524c4fe3dfefb6ce01462c`, ветка `granger/chibi-reconstruction`.
Это журнал незавершённой модернизации; наличие записи в таблице не означает
готовую интеграцию или успешный live-тест.

## Зафиксированное состояние

До правок: 51 зарегистрированная операция, 46 локально доступных по проверке
без персональных ключей. Это readiness, не live-подтверждение источников.
Текущий EXE — 279015421 bytes, SHA-256
`2f39ef873aae31c5040ec220e47bd4cca11f993dd98afbeeda3c545fc1a33d4b`.
66 файлов профиля, 92 файла assets и 200 resources зафиксированы в приватном
снимке вне Git. Фигурка, сцены, scheduler и графический pipeline заморожены.

Baseline backend: 1538 passed, 1 failed, 1 skipped, 32 subtests. Единственная
ошибка — `PermissionError` чтения атомарно опубликованного временного ready-file
в process IPC harness; отдельный повтор всего `test_ipc.py` — 3 passed.
Сбой не приписывается новым адаптерам и не скрывается как успешный полный прогон.

Логический размер проекта: 37.24 GB. Output 13.92 GB, dist 11.95 GB,
ML/tool runtimes 6.11 GB, build 3.59 GB, основная venv 0.77 GB, Git 0.29 GB.
Это сумма размеров файлов, не выделенных кластеров диска. Ничего не удалено.
Основные кандидаты на будущую ручную очистку — старые QA-записи, повторные
build-каталоги и архивы релизов, после отдельной проверки нужных доказательств
и резервных копий. Модели, datasets, profile, vault и checkpoints не кандидаты
на автоматическую очистку.

## Архитектура и обнаруженные причины

`ToolRegistry` уже задаёт типизированные схемы, readiness, разрешения, evidence
и фиксированный dispatch. `AgentRunner` хранит протокол, semantic progress,
dedup, frontier, бюджеты и checkpoint. `InvestigationJournal` и ConversationLibrary
отделяют сохранённые расследования от архива сообщений. Расширение идёт через
эти контракты, без второго чата или второго OSINT-движка.

Проверенные пробелы:

- `route_goal` не выделяет IP/CIDR/ASN внутри обычной фразы. Общий поиск способен
  уйти в числовые совпадения вместо сетевых источников.
- `ip_lookup` выполняет только RIPEstat network-info; RDAP, PTR и история
  маршрутизации отсутствуют в базовом IP-профиле.
- Frontier охватывает GEOINT и некоторые Gansar-операции, но не независимые
  IP/domain/Steam-ветви. Общий fallback допускает Wikipedia для строкового запроса.
- Имеющийся `web_render_worker` — одноразовый сетево отключённый Qt JS renderer
  уже загруженного HTML. Он не является последовательным browser agent.
- `conversation_context` выбирает недавние сообщения; короткая бытовая реплика
  может получить прежние большие аналитические ответы в этом working context.

Gansar, GeoCLIP, Waypoint, Florence, карты и evidence graph уже присутствуют;
новыми источниками в этой работе они не считаются.

## Новые локальные источники: первоначальные решения

Проверены 12 ZIP и SteamRecon. Архивы читаются как данные, установщики не
выполняются. Исходники для статического просмотра находятся в игнорируемом
`output/intelligence-v1/audit-source`; пользовательские архивы остаются на месте.

| Проект | Лицензия / фактические особенности | Решение до интеграции |
|---|---|---|
| SteamRecon | MIT; нормализация ID, Steam XML, aliases, открытые страницы; дополнительные keyed источники | Кандидат: аудит ограниченного public subset и отдельный runtime |
| steam-osint | Лицензия не найдена; Steam API key, запуск Chrome/debug и получение cookies; эвристические проценты связей | Не запускать полный проект, не дублировать SteamRecon и не забирать cookies |
| discordlookup | AGPL-3.0; Node/Nuxt приложение, snowflake и публичные lookup-функции | Отдельно проверить публичные операции; не выдавать snowflake timestamp за профиль |
| theHarvester master | GPL-2.0; пассивные и активные модули, множество optional API keys | Проверить только пассивный allowlist в изолированном worker |
| theHarvester 4.11.1 | GPL-2.0; другая версия того же инструмента | Версия-дубликат, не отдельный источник/capability |
| SpiderFoot | MIT; множество модулей, включая keyed и активные | Не запускать все модули; сопоставить passive subset с существующими источниками |
| Butcher Tools | GPL-3.0; shell при импорте, token/webhook/массовые DM-функции и OSINT меню | Полный запуск исключён; опасные операции не входят в исследовательский allowlist |
| Reconnaissance | Лицензия не найдена; GUI, Shodan key, port scan | Полный запуск исключён, пассивные источники учитывать без копирования нелицензированного кода |
| instagram-email-scraper | MIT; общий HTML scraper, proxy rotation, не самостоятельный Instagram API | Не объявлять полноценной Instagram-интеграцией; проверить извлечение реальных полей |
| TokIntel | MIT; ApifyClient, обязательный token, запись token в `.env` | Необязательный keyed кандидат; не переносить plaintext-хранение в приложение |
| pytok | PolyForm Noncommercial; camoufox/browser, login/session/cookies | Не обязательный компонент; не применять обход ограничений или пользовательские cookies |
| TikTok Content Scraper | PolyForm Noncommercial; cookies/proxy/browser, массовая выгрузка | Не включать массовый scraper по умолчанию; публичные разрешённые операции проверить отдельно |
| X-IG OSINT | MIT; публичные fetch и heuristic scores, username совпадения и link-only pivots | Не переносить необоснованные risk/identity scores; пересечение с текущими X/Instagram проверками |

Ни один проект не объявляется безопасным по одному README. Статический отчёт
фиксирует entry points, manifests, license SHA и места process/network/session/
dynamic-execution индикаторов. Наличие индикатора само по себе не доказывает
вредоносность, отсутствие — безопасность. Выполнение разрешается только после
проверки конкретного пути и контракта адаптера.

[Baseline capabilities](validation/intelligence-v1/baseline-capabilities.json) ·
[Новые проекты и статические признаки](validation/intelligence-v1/source-audit.json) ·
[Дисковый аудит](validation/intelligence-v1/disk-audit.json).

## Последующие этапы

1. Сетевые операции, literal routing и релевантный frontier, unit/fixture/live.
2. Проверенный Steam/social subset и capabilities с реальным evidence.
3. Изолированное последовательное управление браузером, разрешения и UI-действия.
4. Контекст/персона, восстановление провайдера, GEOINT ranking и граф.
5. Backend/frontend/native EXE, публичная live-матрица и поставка.

Финальная приёмка, точные количества работающих источников, новый EXE и
демонстрация возможностей ещё не выполнены. Проверки каждого этапа будут
добавляться с явным разделением fixtures и live.

## Сетевой этап: реализовано и проверено отдельно

Добавлены семь операций существующего registry: `network_rdap`,
`network_routing`, `network_reverse_dns`, `network_reputation`, `domain_dns`,
`domain_rdap`, `domain_certificates`. Всего теперь 58 зарегистрированных
операций; это не 58 независимых источников. Исправлены literal IPv4/IPv6/CIDR/ASN
внутри фразы и ручной auto-поиск IP/domain. Frontier охватывает независимые
сетевые направления, общий Wikipedia/HN fallback для этих целей отключён.

Использован прежний `fetch_public`: DNS pinning, проверка каждого redirect,
ограничение размера и отмена; внешние ключи этим операциям не передаются.
RDAP получает сервер из официального IANA bootstrap. DNS SERVFAIL и пустой
DROP не выдаются за отрицательный результат. Тайм-аут одного routing endpoint
сохраняет данные остальных; кэш сохраняет исходное время наблюдения.

Найдена дополнительная причина поверхностной выдачи: итоговый synthesis
не получал сетевые поля, а relevance отбрасывал prefix endpoints как technical
URL до проверки точного IP в структурированных данных. Исправлены оба пути.
Добавлен читаемый сетевой профиль и реальные DNS/PTR/BGP/registry рёбра;
они не устанавливают общего владельца. Технический API URL больше не скрывает
сам IP/ASN/организацию в графе.

Проверки: большой gate 223 passed; после уточнений сетевых ошибок и relevance
дополнительно 81 и 79 passed (пересекающиеся наборы, не сумма уникальных тестов).
Frontend 125 passed, production build прошёл. Baseline-ассеты/resources/profile
92/200/66 файлов остаются побайтно прежними.

Live 1 ноября 2026, через настоящий registry, без LLM и сохранённых ключей:
восемь проверок с данными из девяти. IP `66.249.67.41`: ARIN сообщает
GOOGLE / Google LLC, диапазон `66.249.64.0—66.249.95.255`; RIPE RIS —
префикс `66.249.64.0/20`, AS15169 и исторические интервалы; PTR —
`crawl-66-249-67-41.googlebot.com`. Spamhaus DROP и Feodo проверены отдельно;
несовпадение не означает безопасность. `example.org`: расширенный DNS и
авторитетный доменный RDAP вернули данные. crt.sh дал timeout — CT **не**
засчитан работающим live и не представлен как отсутствие сертификатов.

[Live-матрица](validation/intelligence-v1/network-live/report.json) ·
[Профиль по сохранённым live-наблюдениям](validation/intelligence-v1/network-live/ip-profile.md).
Это пока CLI/source-проверка; новая сборка EXE и LLM-led приёмка впереди.

Основные первичные документы:
[RIPE network-info](https://stat.ripe.net/docs/data-api/api-endpoints/network-info.html),
[IANA RDAP](https://data.iana.org/rdap/),
[RFC9224](https://www.rfc-editor.org/rfc/rfc9224.html),
[Spamhaus DROP](https://www.spamhaus.org/blocklists/do-not-route-or-peer/).
SSLMate допускает limited unauthenticated evaluation, но просит регистрацию
для production: такой доступ не включён как автоматическая бесплатная замена
[CT Search API](https://sslmate.com/help/reference/ct_search_api_v1).

## SteamRecon: проверенный публичный subset

Добавлены `steam_profile`, `steam_aliases`, `steam_friends` в прежний registry,
manual auto-search, типизацию целей и frontier. Всего 61 операция. Используется
реальный код MIT-нормализатора SteamRecon и четыре проверенных XML-метода;
HTTP client, CLI, настройки, keyed APIs и сбор cookies исходного проекта не
перенесены. Точные исходники/SHA и изменения перечислены в
`grangerpet/research_vendor/steamrecon-provenance.json`, MIT notice включён.

Исполнение — отдельный собственный процесс, ограниченный временем, числом
процессов и Windows Job memory budget 384 MiB; окружение очищено от ключей.
HTTP выполняется прежним DNS-pinned transport, без пользовательской сессии.
Это ограничение процесса и проверенный код, а не заявление о полноценной
изоляции прав пользователя средствами ОС.

127 unit/fixture checks прошли. Live: публичный контрольный профиль Robin
разрешён в SteamID64, получены XML-поля и прежние имена. Первая проверка друзей
выявила устаревший class selector; исправлен по `_parse_friends` SteamRecon и
реальной странице. Повтор обнаружил 294 опубликованные ссылки, сохранил
ограниченную выборку20. Остальные разделы и закрытые данные не объявляются
проверенными. В public receipts чужие friend identifiers и raw profile не входят.

[Live receipts Steam](validation/intelligence-v1/steam-live.json).
Нормализация URL защищена от spoofed host, не принимает session query и
непубличные Steam universes. Steam-поля, aliases и опубликованные связи
сохраняются в context для итогового анализа; имена не объединяют личности.
Интеграция всего 37-source проекта SteamRecon не заявляется.

## Browser runtime: подготовка, ещё не готовая интеграция

В отдельной `.toolenvs/research-browser` установлен официальный PyPI wheel
Playwright 1.64.1 (38,801,836 bytes, SHA-256
`5e240a79464434c9260957b9ef59a5808e02e96e3fcabdc717fd7485260b9730`),
greenlet3.5.6, pyee14.0.0, typing-extensions4.16.0. Только binary wheels;
основная `.venv` не изменялась. Будет использован установленный Microsoft Edge,
другая копия Chromium не скачивалась. Этот факт сам по себе не считается
функциональным browser agent или успешным browser live-сценарием.
