# Автономный публичный поиск — проверенная Windows-сборка

Продолжен существующий Granger-OSINT. Исходная ревизия `79a2959`; DeepSeek,
спрайты, история, защищённое хранение и текущая архитектура сохранены.

## Исправления архитектуры

Прежний обычный поиск в панели при отсутствии CSE открывал Google во внешнем
браузере и не возвращал данные. Чат имел один запасной HTML-поиск; прямое чтение
не исполняло JS. Теперь панель запускает настоящий `public_web` adapter в прежнем
SearchController, а чат использует общие HTTP/parsing/evidence инструменты.

Добавлены отдельные рабочие адаптеры: `github_profile`, `github_users`,
`github_repositories`, `hn_profile`, `hn_search`, `openlibrary_search`,
`wikipedia_search`. У каждого фиксированный endpoint, строгий input/schema,
реальное извлечение полей, rate/cache/error/cancel и нормализация evidence.
**Все семь подтверждены живыми запросами**, а не доступностью главной страницы.

Без персонального ключа работает ограниченная федерация публичных источников.
Это не глобальная выдача Google. Настроенный CSE остаётся дополнительным:
при отказе публичный fallback создаёт новые клиенты без передачи ключа.
DuckDuckGo `/html` и `/lite` исключены по robots.txt. Archive search после
двух timeout исключён из активного реестра и стандартной федерации.

AgentRunner перед преждевременным завершением/паузой предлагает до трёх разных
публичных альтернатив для того же аргумента. Явное ограничение «только источник»,
бюджет, отмена и prohibition повторного запуска остаются в силе. Протокол
assistant/tool и checkpoints сохраняется. Fixture-тест отказа первого источника
и успеха второго отделён от live-проверок.

[Подробный контракт движка и источников](PUBLIC_SCRAPING_ENGINE.md).

## HTTP, HTML и browser rendering

Переиспользован DNS-pinned HTTPX/httpcore. Каждый hop повторно проверяется;
запрещены private/service IP, unsafe schemes и credentials URL. Есть scoped
cookies, encoding, GET/разрешённый POST формы, контролируемый GET retry,
лимиты размера/параллельности/глубины, отмена, TTL-кэш. robots.txt проверяется
для документа, redirect target и prefetched scripts; запрет не обходится.

Извлекаются title, description, canonical, OG, JSON-LD, текст, заголовки,
таблицы, ссылки, доступные author/date/HTML attributes; JSON/XML/RSS/Atom имеют
ограничения структуры и объёма. DTD/ENTITY отвергаются. ScrapeResult сохраняет
метод, requested/final URL, HTTP status, extraction status, warnings, время,
structured_data и настоящий evidence_id после нормализации.

JS запускается только после HTTP shell без login/challenge, в отдельном
network-disabled Qt-процессе. Нет WebChannel, профиля пользователя, секретов
или загрузки/запуска исполняемых файлов. Classic scripts заранее получены
через pinned HTTP. DOM condition, timeout/cancel, один renderer, Windows Job
Object с лимитом 1 ГиБ и V8 heap128 МиБ обеспечивают ограниченный жизненный цикл.
Оконный EXE использует собственные унаследованные anonymous pipes.

**Не универсальный браузер:** произвольные fetch/XHR, ES modules, сложные CSP,
login и CAPTCHA не поддерживаются/не обходятся. Если полезный DOM не получен,
страница не объявляется успешно прочитанной. Обработанная запись не становится
доказательством личности или истинности утверждения источника.

## Реальные примеры

- `solvnox`: три записи — одна GitHub и две HN; Wikipedia empty. Источники
  и отсутствия различимы. Совпадение строки не устанавливает владельца.
- GitHub `octocat`: реальная запись, имя The Octocat,8 публичных репозиториев
  на момент получения. Происхождение — API GitHub, не search snippet.
- `https://quotes.toscrape.com/js/`: HTTP-first + настоящие цитаты/авторы из
  browser DOM. Проверено в исходном и **в готовом EXE**.
- Nominatim default `London Bridge`:5 кандидатов без ключа и ручного endpoint.
- DeepSeek production AgentRunner самостоятельно выбрал `github_profile`,
  получил данные и выдал русский ответ:2 модельных запроса,1tool_call,
  **6583 фактически отчётных токена**,13checkpoint-записей, evidence сохранено.
  Ключи источников отсутствовали; использован существующий ключ ИИ-шлюза.

Полные bounded observations: `output/autonomous-qa/public-search-live.json`,
`solvnox-live.json`, `public-agent-live.json`, `exe-public/report.json` в ZIP.
Это публичные/синтетические QA-задачи; история/фотографии пользователя не читались.

## OSINT4ALL и количества

| Метрика | Фактический результат |
| --- | ---: |
| Извлечено href из заданного Start.me | 0:403/challenge |
| Полностью извлечена коллекция | Нет |
| Рассмотрено пунктов предоставленного перечня | 153 |
| Точный официальный/репозиторный URL установлен | 119 |
| Неоднозначные пункты без точного URL | 34 |
| Уникальных URL проверено HTTP | 113 |
| Дублирующихся URL | 6 |
| HTTP200 landing/docs | 71 — не proof API/search |
| Недоступных landing/docs в этой пробе | 20 |
| Страниц явной защиты | 5 |
| Подтверждённый контракт auth/key | 12 пунктов |
| Подтверждённый API без персонального ключа | 11 пунктов |
| Пунктов перечня с существующей узкой реализацией | 23 |
| Рабочих адаптеров всего | 32 |
| Локально готовы без source keys | 28 |
| Runtime live_verified в чистом offline catalog | 0 — не подставляется из QA |
| Добавлено адаптеров с живой проверкой | 7 |

[Таблица всех 153 пунктов и причины отбора](OSINT4ALL_AUDIT.md),
[машинный аудит](OSINT4ALL_AUDIT.json), [контракты 32 адаптеров](TOOL_MANIFESTS.json).
Нулевая выгрузка Start.me не заменяется придуманными URL или другой коллекцией.
Названия из текста не считаются извлечёнными href. Unsupported/ручные кандидаты
не отображаются как действующие инструменты. Прежние персональные подключения
сохранены как дополнительные функции в пределах своих операций.

## GEOINT

Пустой override теперь использует ограниченный public Nominatim/Overpass;
ручные endpoints находятся в закрытом разделе расширенных настроек. Последовательная
очередь, интервал≥1.1 с, кэш, quota, идентификация и OSM attribution сохранены.
Нет массового геокодирования, автодополнения, arbitrary Overpass QL и перебора
серверов после отказа. **Overpass live timeout** и при 12 с, и при 20 с; успех не заявлен.

OCR учитывает EXIF orientation, grayscale/autocontrast и установленные языки.
Низкая уверенность/пустые пиксели дают `low_confidence`, настоящие исходные
segments/confidence сохраняются как partial evidence. EXIF/GPS/GPI/локальное
сравнение и vault сохранены. [GEOINT details](GEOINT_ENGINE.md).

## Компоновка чата

Общая ширина до 920px для текста, evidence, статуса и composer. Header/composer
остаются на месте, основная прокрутка принадлежит переписке. Markdown имеет
согласованные интервалы; inline sources показываются по 6 без второго vertical
scroll. Продолжение checkpoint — компактная строка состояния. Вложения внутри
composer, форматы в tooltip, Enter/Shift+Enter и восстановление focus/черновика
проверены. При открытии/закрытии dock колонка действительно перераспределяется.

**304 случая /2992DOM-проверки**:5 размеров окна,80/100/125/150%zoom,4 темы,
dock open/closed, пустой и длинный диалог, code/table/120 источников, active/paused,
attachment. Это явно обозначенные UI fixtures, не реальные OSINT-результаты.
Физический Windows DPI не менялся, DPR среды 1.25; другие физические DPI **не проверены**.
[UI QA](CHAT_LAYOUT_PUBLIC_SEARCH.md).

## Проверки и сборка

- Python full: **892passed,1skipped,32subtests**,220.01 с. Skip — необязательный
  живой Ollama. После full добавлены robot-policy проверки; финальный узкий набор
  **157passed**,50.79 с. Полный прогон не выдаётся за 897 тестов.
- Frontend **85/85**,12 файлов; build успешен. Отдельные backend UI routing
  regression **97/97**, чистые GEOINT fixtures **52/52**.
- Настоящий EXE **41/41**: public GitHub, реальный JS DOM, OCR/GPS,4 темы,
  encrypted originals, visibility/restore, restart/theme/ciphertext/GPS/exit.
- CArchive: **73 модуля** совпали с исходниками, **137 проверок ресурсов** прошли.
  Все **12 защищённых ресурсов персонажа** неизменны.
- Launcher/Pet smoke с PATH=System32 прошёл, exit=0.

Команды: `npm.cmd run build` в frontend;
`.venv\Scripts\python.exe -m PyInstaller --noconfirm Granger-OSINT.spec`;
`scripts/qa_reconstruction_exe.py --public-tools --output <новая папка>`;
`scripts/smoke_exe.py` и frozen verifiers. Переустановка Windows/Python/Node для
готового EXE не требуется. Новых runtime-зависимостей не добавлено.

EXE `dist/Granger-OSINT.exe`: **275538501 байт**, SHA-256:
`37fffea2c33bdd929503b15ed019020ecb7f5b25dc06891f1d0c323d98fb4ecf`.

## Изменённые файлы

- Core: `agent_browser.py`, `web_http.py`, `web_scraping.py`, `web_render.py`,
  `web_render_worker.py`, `engine/runtime.py`, `main.py`.
- Поиск/агент: `public_sources.py`, `agent_web.py`, `agent_tools.py`, `agent.py`,
  `agent_evidence.py`, `engine/adapters.py`, `engine/router.py`, `panel.py`,
  `desktop_bridge.py`, `tool_manifest.py`.
- GEOINT: `geoint/images.py`, `geoint/mapping.py`, `geoint_tools.py`.
- UI: `frontend/src/components/{Chat,AttachmentComposer,Sources,ToolCatalog,ConnectionSettings}.tsx`,
  `frontend/src/{themes.css,types.ts}` и относящиеся тесты.
- QA: `qa_public_search.py`, `qa_public_agent.py`, `qa_chat_layout.py`,
  `qa_geoint_defaults.py`, `audit_osint_catalog.py`, `qa_reconstruction_exe.py`,
  новые и обновлённые backend/frontend tests, README/документы.

Фигурные скобки перечисляют файлы в одной папке; Python-пути — внутри grangerpet,
QA-пути — внутри scripts. Полные diff/commits находятся в GitHub.

## Git и сохранность

Обычные push без force: `c95cb0c` (движок),`95a458b` (источники/агент),
`c9393ec` (GEOINT/аудит),`54da669` (чат),`74cd749` (robots/EXE QA).
Итоговые docs/QA commits и совпадение local/remote HEAD записаны в
`output/autonomous-qa/git-publication.json` в source ZIP.

Исходные пользовательские данные не удалялись/не перезаписывались; тесты
используют изолированные профили. Предыдущие EXE/ZIP сохранены в
`dist/archive/before-autonomous-search`. Пароли/ключи не включаются в исходники,
логи и публичный архив. Изменения других приложений, Windows services/registry,
глобальных GPU/driver/security settings не выполнялись.

## Ограничения

Полный Start.me, недоступные коммерческие операции, полноценный произвольный JS
браузер, физические дополнительные DPI и другие ОС **не проверены/не реализованы**.
Overpass и Archive timeout сохранены. Семантическое определение города/улицы по
фото не добавлено. Причина прежней вариативности native WebEngine CPU не установлена;
обновление не объявляется исправлением микролагов других приложений.

## Производительность

Сопоставимый сценарий:1000 синтетических сообщений,3×6 с, freshprofile, тот же скрипт;100%CPU означает одно логическое ядро (12 логических CPU). RSS суммирует sharedpages и не является private working set.

| Сценарий | До CPU | После CPU | До RSS sum, МиБ | После RSS sum, МиБ |
| --- | ---: | ---: | ---: | ---: |
| Видимый неактивный длинный чат | 5.4099% | 6.1784% | 486.82 | 459.05 |
| Свёрнутый чат | 6.1830% | 5.4117% | 486.89 | 459.12 |

В видимых trial обоих EXE собственные окна были неактивны: foreground=false до/после каждой выборки. Это измерение видимого неактивного окна; CPU активного foreground-чата отдельно в этом обновлении не измерен. После полного выхода у обоих 0 собственных процессов. Небольшое отличие CPU этого короткого прогона не считается ни доказанным ускорением, ни причинным объяснением микролагов. В отдельных прежних запусках WebEngine показывал существенно больший CPU; причина вариативности остаётся неустановленной. Все исходные отчёты сохранены. Активное расследование/стриминг отдельно поCPU после этой сборки **не измерено**. UI-to-tool completion в настоящемEXE:GitHub1379 мс, JSстраница 6137 мс (включая сеть/renderer/IPC), OCR1180 мс; это не чистая длительность алгоритмов.

Данные: `output/autonomous-qa/performance-before/report.json`, `performance-new/report.json`, `exe-public/report.json`.
