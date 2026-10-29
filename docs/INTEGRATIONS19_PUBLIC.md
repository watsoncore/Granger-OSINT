# Проверка шести публичных/CLI проектов из запроса 19 интеграций

Проверено 30 октября 2026, Windows, Python 3.14.5. Машинный отчёт с pinned
коммитами, SHA256 изученных файлов и инвентарём MailAccess:
[INTEGRATIONS19_PUBLIC_AUDIT.json](INTEGRATIONS19_PUBLIC_AUDIT.json).
Исходники всех шести проектов клонированы в игнорируемый
`output/integrations19/upstream/`. Они не импортируются в основной Python и не
подменяют существующий движок Granger. Независимые адаптеры пользуются общим
`web_http.fetch_public`: DNS/IP pinning, запрет private/service IP, лимиты размера,
времени, параллелизма, отмена, ограничение частоты. Обязательных личных ключей,
cookies браузера и платных сервисов нет.

| Проект | Реальная подключённая возможность | Граница результата |
|---|---|---|
| ScopeSentry | Не установлен и не зарегистрирован | Отдельный пригодный для поставки пассивный компонент не подтверждён; полную серверную инфраструктуру не разворачивали |
| kronikier | `historical_contacts` — независимое ограниченное чтение CDX и снимков Wayback, извлечение email/международных телефонов | Живой raw snapshot дал один архивный email; полная цепочка через registry пока timeout/HTTP503 на CDX |
| MailAccess | `mail_dns` — независимая проверка синтаксиса, MX, SPF, DMARC | Проверка домена; существование ящика, владелец и доставляемость не доказаны |
| X Tweet Fetcher | `x_post`, `x_profile` — документированный FxTwitter/FxEmbed API | Один пост/публичные метаданные профиля; лента, replies и поиск не подключены |
| Arctic Shift | `arctic_posts`, `arctic_comments` — ограниченный поиск исторического Reddit | Сторонний неполный архив; отсутствие записи не доказывает отсутствие публикации |
| Nuclei | `nuclei_check` — optional pinned CLI, один harmless HEAD-template | По умолчанию выключен; отдельное подтверждение прав на точный origin; это не CVE-сканер |

## ScopeSentry

Изучены README, `go.mod`, Docker Compose, server entry point, CT Monitor plugin
и его зависимости. README ещё описывает FastAPI, однако проверенный текущий
сервер содержит Go/Gin; это расхождение отражено в JSON, README не принимался за
доказательство архитектуры. Compose запускает MongoDB, Redis, server и scanner.
Пассивный CT Monitor существует, не требует личного внешнего ключа, но использует
внутренний plugin context, MongoDB repository и Redis, запускает продолжительное
наблюдение CT logs. Его нельзя честно объявить готовым одиночным ограниченным
запросом Granger. Динамическая загрузка плагинов не включалась.

Лицензия заявлена как AGPL-3.0; README добавляет отдельное коммерческое разрешение
для компаний/организаций. Такой компонент не копировался и не включался в сборку.
Причина исключения не связана с обязательным платным API. Собственный DNS/CT-код
Granger не переименован в «ScopeSentry».

## kronikier / historical_contacts

MIT, Python >=3.10; upstream зависит от requests, BeautifulSoup, phonenumbers,
rich. Изучены CDX client, pipeline и extractors. В Granger добавлен независимый
узкий адаптер, а не полный CLI. Использован тот же публичный Wayback CDX/raw
snapshot протокол, что у upstream; обёртка поверх старого waybackpy не запускалась,
поскольку она не гарантирует общий DNS-pinned transport и отмену.

Вход: `{"domain":"example.org","max_snapshots":1}`. Разрешён публичный домен,
не URL/IP/порт. Максимум 10 CDX записей, 1–3 снимка, общий бюджет 25 секунд и до
8 секунд на снимок. Используются только действительно возвращённые архивом URL
того же домена/поддоменов. Каждый контакт содержит timestamp, original_url и
snapshot_url; `historical_only=true`. Извлекаются обычные/простые обфусцированные
email и валидные международные `+` телефоны. Неоднозначные местные номера не
угадываются. Индекс без прочитанного snapshot возвращает `partial` с пустыми
контактами. Timeout/503 никогда не превращается в «контакты не существуют».

Живая проба CDX ранее вернула HTTP200 с реальными временными метками example.org.
Полная проба через registry закончилась timeout; повтор адаптера получил HTTP503
и `rate_limited`. После backoff выполнена ровно одна bounded raw-snapshot проба по timestamp, ранее
полученному из настоящего CDX: снимок example.org от 2002-01-21 вернул HTTP200,
6814 байт и один реальный исторический email. Это подтверждает snapshot transport
и extractor; полная операция historical_contacts через registry ещё не
подтверждена из-за сетевого/CDX сбоя. Provenance и дополнительные варианты
извлечения проверены явно обозначенными локальными fixtures. Блокировки и
авторизация не обходились.

## MailAccess / mail_dns

MIT, исходный пакет требует FastAPI/uvicorn, SQLAlchemy, dnspython и другие
зависимости, имеет много сетевых account/breach/paid модулей. Изучены полный
инвентарь Python-модулей, `docs/modules.md`, DNS module и email/domain validation.
Наличие `requires_key=false` само по себе не разрешает account probing.

В Granger установлена независимая бесплатная функция: существующий нормализатор
email плюс три публичных DNS-over-HTTPS запроса MX/TXT/_dmarc.TXT. Никаких SMTP,
recovery/signup форм, рассылки, MailAccess Index account key, Pro, leak/stealer
баз, тысяч проверок или нового backend. Полный MailAccess не устанавливался.
`mailbox_existence_checked=false`, `messages_sent=false` сохраняются в evidence.
Null MX и NXDOMAIN сохраняются как наблюдения DNS, не как найденный аккаунт.

Живой `mail_dns(info@example.org)` через ToolRegistry: `complete`, одна сохранённая
evidence-запись. Русский текст и строгие ошибки проверены fixtures.

## X Tweet Fetcher / FxTwitter

MIT, upstream основной backend использует stdlib; browser mode опциональный.
Изучены `src/xtf/backends/fxtwitter.py`, модели и public provider docs
[FxEmbed Public API](https://docs.fxembed.com/). Granger независимо обращается к
тому же документированному публичному API через общий транспорт, без установки
чужого CLI и его browser drivers.

`x_post({"url":"https://x.com/jack/status/20"})` читает один конкретный пост:
текст, returned author, дата, публичные счётчики, до 10 media URLs. ID ответа
сверяется с запросом; приватные/удалённые посты не обходятся. Медиа не скачиваются.
`x_profile({"username":"jack"})` возвращает публичные поля: ID, bio, имя,
self-reported location, joined, counters и ссылки на avatar/banner. Имя и место
не являются установленной личностью. Схема/типы/размеры строго проверяются.

Живые пробы обоих адаптеров: `complete`, по одной записи. `x_post` подтверждён
также через registry с evidence. `x_profile` через registry также дал complete/1
evidence. Nitter instance не настроен/не проверен, поэтому
timeline/replies/search отсутствуют. Camofox, маскировка отпечатка браузера,
сессии, CAPTCHA/403 bypass не подключались. FxTwitter является сторонним сервисом,
не официальным X API; доступность/свежесть не гарантированы.

## Arctic Shift

Изучены README и [документированный API](https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md).
В проверенном дереве отдельная лицензия исходников не найдена: код/дампы не
копировались и не распространяются. Используется независимый клиент публичного
API без ключей. Огромные Reddit dumps и zstandard не скачивались.

Оба инструмента требуют author либо subreddit; query необязателен, даты UTC
`YYYY-MM-DD`, лимит 1–20. Один API-запрос, без обхода пагинации/массового сбора.
В ответе source URL/ID, author, subreddit, created_utc, текст и ранние архивные
счётчики; `[removed]`/`[deleted]` отмечаются. Значения даты и счётчиков проверяются,
текст ограничен 12000 символами. API не принимает `permalink` как selectable field:
это обнаружено реальной пробой и исправлено; post permalink выводится из ID,
для comment сохраняется документированный archive ID endpoint.

`arctic_comments` через registry дал `complete`, две evidence-записи. Первая проба
`arctic_posts` дала unavailable; отдельный повтор через registry дал `complete`,
две evidence-записи. Неудачный отчёт сохранён. API не обещает uptime, полноту
архива и окончательные scores; 429/503 дают backoff, 401/403 не обходятся.

## Nuclei: optional runtime

MIT ProjectDiscovery. Официальный Windows amd64 release **v3.11.1**, исходный tag
`a8c88feb4a1c8e961b7902534ce3af97e9d524a4`. Проверены реальные CLI flags и код
запрета update/download, config и process transport. ZIP 46067128 байт сверён с
опубликованным SHA256; отдельно pinned SHA256 EXE. Значения в JSON и wrapper.

Установка без стороннего installer script:

```powershell
.venv\Scripts\python.exe scripts\setup_nuclei.py
# Либо ранее скачанный официальный ZIP с тем же pinned SHA256:
.venv\Scripts\python.exe scripts\setup_nuclei.py --archive path\to\nuclei_3.11.1_windows_amd64.zip
```

Скрипт не исполняет ничего из архива, извлекает только проверенные `nuclei.exe` и
MIT LICENSE. Локальный runtime: `.toolenvs/nuclei/3.11.1/`. Optional sidecar для
сборки: `<EXE directory>/tools/nuclei/3.11.1/` с EXE/LICENSE/manifest. Бинарник
144920576 байт **не добавлен в ресурсы основного EXE**; пакетирование sidecar
проверяется основной сборкой отдельно. Произвольный PATH/CLI path не принимается.

Для запуска нужны `Settings.nuclei_enabled=true`, отдельное `approved=True` и
`{"target":"https://owned.example.org/","authorized_scope":"https://owned.example.org/"}`.
`target` и подтверждённый scope должны совпадать точно. Только публичный http(s)
origin на стандартном порту, без path/query/учётных данных. Private/loopback IP
запрещены в production gate. DNS проверяется и IP передаётся в CLI буквально;
Host/SNI сохраняют исходный hostname. SHA EXE проверяется перед каждым запуском.

Только встроенный собственный template: **один HEAD /**, status и booleans наличия
HSTS/CSP. Нет произвольных templates/flags, CVE, brute force, TCP, code, headless,
fuzzing, credentials, OAST или cloud upload. Redirects отключены. Ключевые и
proxy environment variables не наследуются; config/cache/home — временные
папки. Updates и все public/custom template downloads отключены. CLI может
кратковременно открывать собственный localhost metrics listener на ephemeral
порту (`-mp 0`); он заканчивается с процессом. Конкурентность1/rate1, timeout4
на запрос/20 на операцию, JSONL <=256KiB, memory job budget768MiB при доступном
Windows Job Object. Отмена завершает свой процесс. В evidence экспортируются
только три строго разрешённых поля; raw requests/responses/curl/local paths не
передаются. Проверка доверия TLS-сертификата не объявляется возможностью Nuclei.

Реальная QA выполнялась исключительно на только что созданном собственном
ThreadingHTTPServer `127.0.0.1:ephemeral`: ровно один HEAD, status200/CSP true/HSTS
false, успешная отмена CLI во время медленного ответа, private production target
отклонён. Внутренняя worker-функция вызывается QA-скриптом напрямую; registry не
получает опции ослабления private-IP проверки. Чужие цели не сканировались.

## Проверки и границы готовности

```powershell
.venv\Scripts\python.exe -m pytest tests\test_integrations19_public.py tests\test_integrations19_nuclei.py -q
.venv\Scripts\python.exe -X utf8 scripts\verify_public19.py --live
.venv\Scripts\python.exe -X utf8 scripts\verify_nuclei.py --live
```

Последний полный прогон: 66 unit tests и 25 существующих registry tests прошли.

Unit tests используют fixtures и MockTransport; они не являются live/public
verification. Проверяются строгие аргументы, UTF-8, DNS SSRF, redirects, 401/403/
429/503, malformed JSON/schema, backoff, cancellation/deadline, cache с сохранением
первоначального времени, archive timestamps/provenance и index-only partial,
default-off/approval/scope Nuclei, binary integrity, isolated environment,
allowlist полей JSONL и неожиданные template IDs/targets.

Живые отчёты: `output/integrations19/registry-live/*.json`,
`public-live/x_profile-verified.json`, `historical-single-snapshot-probe.json`,
`nuclei-loopback-verified.json`.
Ни один отчёт не содержит ключей. Неудачи сохранены; PACKAGED/AGENT_READY не
выводятся из одного успешного HTTP-ответа. Сетевой источник может стать недоступен
после проверки; readiness сообщает о наличии адаптера/runtime, а фактическая
операция отдельно возвращает complete/partial/timeout/blocked/rate_limited.
