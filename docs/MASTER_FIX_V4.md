# Master Fix V4 — восстановление запуска инструментов

4 ноября 2026. Существующий Granger-OSINT, ветка `granger/chibi-reconstruction`.
Исходный HEAD `3576fa192ddb51dead7fd0a275bbf43780e182c2`; незакоммиченные изменения
предыдущей очистки сохранены. Очистка не считалась функциональной проверкой.
Точная сводка: [verification.json](validation/master-fix-v4/verification.json),
[native-live.json](validation/master-fix-v4/native-live.json).

## A. Critical Regression Root Causes

В старом каноническом EXE мышью создан `solvnox`. В encrypted документе его тип
был `username`, значение `solvnox`, не `public_profile`. Воспроизведена неверная
подпись карточки: `cardVariant` объединял username с social, а `cardBadge` без
platform писал «Публичный профиль». Прежняя гипотеза о неизбежной смене backend
типа не подтверждена; исправлен именно визуальный шаблон и добавлена проверка.

После полного catalog probe в старом EXE Maigret удалось выбрать мышью. Безусловная
поломка самого Radix picker не подтверждена. Фактические дефекты: initial tool был
`network_rdap` для любого узла; смена selection очищала draft, но не tool; до ответа
capability был оптимистический fallback. Backend формально привязывал к узлу только
Gansar, оставляя остальные target/query на доверии frontend. При добавлении runtime
статусов обнаружен и исправлен отдельный race: picker мог обновиться по catalog,
а callback отвергать выбор по старому cached `available=false`.

Отдельная неизбежная поломка worker Gansar в прежнем EXE не была подтверждена.
Устранены установленные рассогласования выбора, capability, target и stale tool;
новый путь запуска проверен реальными TON/BTC запросами, не только каталогом.

Теперь fingerprint готовности инструментов обновляет capability, устаревшие ответы
игнорируются. Machine fingerprint исключает thumbnails/balances: их загрузка не
сбрасывает выбранный режим. Ошибка discovery видна. Geo alias `coordinate` →
зарегистрированный kind `coordinates` исправлен; Panoramax привязан к обеим координатам.

## B. Entity Model

Явный выбранный тип больше не переписывается общей эвристикой target route.
Canonical aliases создания: nickname→username, crypto_address→blockchain_address,
ip→infrastructure_asset, location→coordinate. `label`, `value`, `original_identifier`,
username/address/url/chain отделены. Legacy документы остаются читаемыми, массовой
миграции нет. Импорт сохраняет тип и снижает claimed verification как прежде.

Fixture проверяет 13 случаев, включая aliases: username/nickname, public profile, email, phone, IP,
domain, wallet, transaction, organization, image, location, custom. JSON roundtrip,
encrypted reopen и annotation edit сохраняют тип/значение. Настоящий file-picker
экспорт всей матрицы отдельно не выполнялся; это не называется native export PASS.

## C. Capability Registry

`canvas_capabilities` используется и discovery, и server-owned execution binding.
Из `_SPECS` получаются ID/category/kind/schema/target parameter; catalog даёт runtime
availability/reason. Различаются ready/configuration_required/runtime_unavailable/
temporarily_unavailable/unsupported_entity/invalid_target. Label не подставляется
в target. Клиент не может заменить username/address чужим значением; mismatch
отклоняется до worker. Для геоточки locked latitude+longitude, геокодер топонимов
не выдаётся за обратный поиск координат.

При смене узла несовместимый tool и параметры сбрасываются; вызова без нажатия нет.
Маigret/Gansar конфигурируются существующими формами. Tests проверяют mouse radio
selection, runtime checking→ready, сохранение режима при media refresh и typed target.

## D. Maigret

Оригинальный runtime 0.6.6, база 8232 записей / 28 engines; 7508 активных username
entries, Full планирует 6434 после явно объявленной transport policy. Это реальные
числа установленной базы, не константа «8600+». SHA базы:
`25b734d93fb338c75b24f0149ae0251f6fca88d8fce2f9968a0875884421b343`.
Quick/Standard/Full/Custom сохранены. Новая native проверка выбирает Custom шесть
exact sites, наблюдает progress, реальные профили и вставляет выбранные в граф.
Full отдельно реально запускается до плана и отменяется; это не completed Full scan.
Оригинальный core API и адаптер сравнены на одинаковых шести сайтах: 0 status differences.
Verified TLS/public-only policy сохранена, авторизация/CAPTCHA не обходились.

## E. Gansar

Установленные сети: BTC/DOGE/TON/Tron/Solana и ETH/BSC/Polygon/Arbitrum/Optimism/
Avalanche. Матрица операций — [GANSAR_CAPABILITIES_V3.md](GANSAR_CAPABILITIES_V3.md),
фактический внешний проект — [watsoncore/Gansar](https://github.com/watsoncore/Gansar).
Runtime/checkout не изменён. Разные сети имеют разные canonical IDs; EVM Auto требует
выбора, TON friendly/raw валидируются checksum/форматом. Транзакционный hash и IP
не превращаются в адрес кошелька.

В итоговом EXE мышью созданы TON `dsdsd` и Bitcoin. Gansar выбран через picker,
запущены реальные workers, сохранены result/provenance, выполнена вставка. TON status:
`partial`, 236 records; BTC status:
`partial`, 60 records.
Partial не переименован в complete. Остальные 9 сетей не получили нового live в V4.

## F. Graph Enrichment

Identifier → returned_for_query → account не утверждает общего владельца:
`owner_verified=false`. Повторный insert дедуплицирует evidence/nodes.
Crypto insertion выбирает wallet-centric view и сохраняет ID исследуемого wallet
даже в смешанном проекте, где первым был username. Raw evidence не удаляются.
Обзор начинается с 12 объектов; доступно явное расширение. Source/tx карточки скрыты
на обзорном уровне. Decimal/network/asset aggregation, exact provenance и UTXO
ограничения сохранены. Explicit transaction drill добавляет выбранные tx сверх
обзорного лимита, не вытесняя кошельки. Layout после durable ACK вписывается в окно.

## G. UI/UX

Карточка username имеет собственную подпись «Никнейм» и не маскируется под профиль.
Ручная форма принимает отдельные display name и machine value. Tool picker объясняет
несовместимость/готовность, поддерживает поиск по названию и ID, клавиатуру и мышь.
Действующие Manrope/кириллица, compact/comfortable, scrollbars, contextual inspector,
resizable media и original viewer сохранены. Новой оболочки/чатов/вкладок нет.
Широкий wallet layout раньше мог увести root из viewport; теперь выполняется fit.
Это не заявление о полном новом редизайне всех типов карточек.

## H. Persistence

CAS, immutable encrypted revisions, stable mutation IDs, serial queue и recovery
не отключались. Results остаются preview до выбранного insert, включая cancel/partial.
Native restart подтвердил типы, значения, annotations, evidence и позиции. Сравнение
фактов исключает только presentation cache `attributes.media`. Проверки stale kind,
реального CAS и недопустимых targets выполняются до runner.
Полный Full Maigret запускается/отменяется без автоматической вставки в граф.

## I. Tests и performance

Полный backend после последних исправлений: `2009 passed, 1 skipped, 32 subtests passed in 355.70s (0:05:55)`. Отдельные targeted runs,
включая 40 routing/bridge/build checks, 73 geo/crypto и 16 harness/build checks, не дополнительные
уникальные tests поверх full count. Frontend: **180 PASS**, TypeScript/build PASS.
Frozen: **163 modules / 239 resources**;
native smoke **22**, live/interaction **31** checks.
Синтетика не выдаётся за сеть; local metadata не выдаётся за OSINT live; stress
переиспользует отдельно реальные TON observations без новых HTTP.

| Nodes | Origin | Paint median/p95 ms | Event→paint median/p95 ms | Open/reveal s |
|---:|---|---:|---:|---:|
| 50 | synthetic_fixture | 3.8 / 13.9 | 9.65 / 23 | 1.016 |
| 100 | synthetic_fixture | 3.25 / 4.7 | 7.75 / 25.7 | 0.724 |
| 500 | synthetic_fixture | 5.25 / 7.7 | 8.0 / 9.2 | 3.551 |
| 1000 | synthetic_fixture | 8.2 / 10.9 | 11.6 / 23.9 | 7.359 |
| 5000 | synthetic_fixture | 17.15 / 30.2 | 33.9 / 48.3 | 47.719 |
| 424 | provided_observed_result | 1.1 / 3.2 | 3.6 / 19.1 | 1.109 |

Метрики actual Qt/WebEngine с culling; event latency начинается в JS handler,
не включает время IPC. Active interval не выдаётся за whole-session FPS. CPU/RSS/GPU
числа сохранены в JSON. 5000 одновременно подробных картинок не рисовались.
60 FPS на 5000 не подтверждены; значения и максимумы не скрываются.

Один полный прогон параллельно со сборкой дал 2008 PASS / 1 FAIL / 1 SKIP,
32 subtests PASS: существующий OCR integration превысил wait 12 seconds. Отдельный
повтор прошёл за 6.63 s; блок GEOINT/OCR отдельно — 38/38 за 24.63 s. Вторая попытка
дала тот же OCR timeout и 99 setup errors отсутствующего pytest temp root при
перекрытии тестовых процессов. Это дефекты/ограничения тестового прогона, не PASS.
Наконец полный набор в изолированном окружении с диагностическим hook прошёл
2009/2009 (ещё 1 SKIP), OCR case 5.08 s; итог указан выше. Конкретная причина
первоначальной задержки OCR не доказана, поэтому не объявляется исправленной.
Тайм-аут теста и production-код OCR ради этого не изменялись.

После установки канонический EXE отдельно прошёл ещё 22/22 native checks.
Secret scan: 6897 payloads (история Git, исходники,
извлечённые PE/PYZ), утечек не найдено; значение ключа не сохранялось.

Неуспешные ранние harness-прогоны выявили clipped hit areas, совпадение текста
trigger/radio, допустимый portal input у верхнего края и ожидание disabled во время async validation; тест исправлен,
а failures не объявлены PASS. Один кандидат прошёл core live, но после ревью
потребовал новой сборки; финальная сверка повторяется непосредственно перед install.

## J. Master Fix V3 acceptance matrix

| Requirement | Code evidence | Test evidence | Status |
|---|---|---|---|
| Username ≠ account, explicit type | research_canvas, graph-cards | 13-case reopen + mouse create | Implemented and verified |
| Tool picker / stale RDAP / typed target | ResearchCanvas, canvas_capabilities, bridge | mouse Maigret/Gansar, readiness tests | Implemented and verified |
| Original Maigret / full DB | engine/maigret_* | DB hash, original comparison, Full plan/cancel | Implemented and verified |
| Completed Full Maigret live | existing Full worker | no whole-database sweep | Implemented but not verified |
| 11 Gansar networks/operations | crypto_targets, blockchain_* | all-network unit; TON/BTC frozen-live | Partial |
| Crypto aggregation/provenance/dedup | evidence_graph, ResearchCanvasBridge | live insertion/repeat + fixtures | Implemented and verified |
| Wallet overview/source hiding/drill | graph-model, ResearchCanvas | low-budget drill test + real crypto stress | Implemented and verified |
| Every NFT/profile/media/card variant | graph-cards / existing renderer | core native; not all variants re-reviewed | Partial |
| Local original image/resize/viewer | canvas_media, media_viewer | native smoke/local SHA | Implemented and verified |
| Public media loading/access gates | public_media | bounded guards/unit, not every provider | Partial |
| Fonts/density/scrollbars/inspector | workbench.css/shared components | current native core shots; V3 prior DPI | Partial |
| CAS/drafts/cancel/persistence | canvas mutation queue/store | full tests + actual restart/cancel | Implemented and verified |
| 50/100/500/1000/5000 + crypto metrics | qa_canvas_stress | actual final frozen measurements | Implemented and verified |
| 60 FPS at 5000 | existing renderer | not achieved/confirmed | Partial |
| Other tool caps | MAIGRET_ENGINE_V3 audit | limits documented, not rewritten | Partial |
| GEOINT/Steam/SOCMINT/DeepSeek services | existing unchanged adapters | backend regression; no fresh all-service live | Partial |
| Canonical EXE/QA lifecycle | build_release/qa_clean_release | verified stage→atomic install→single path | Implemented and verified |

## K. Release

Единственный путь: `dist/Granger-OSINT.exe`, **279386861 bytes**.
SHA-256: `45ef168638da469a31408f899453d469a31b1ca6d3462beb47d4fd88760633d1`. Код соответствует текущим исходникам/PYZ, frontend и
ресурсам. Временные EXE/work/cache/profiles удалены автоматически. Работающий чужой
процесс не останавливался. Код и проверочные материалы опубликованы обычным
push в `granger/chibi-reconstruction`, commit
[`b93c1ca132ab6714d1b44893b0a05e65e76bcd66`](https://github.com/watsoncore/Granger-OSINT/commit/b93c1ca132ab6714d1b44893b0a05e65e76bcd66).
EXE установлен локально; отдельный GitHub Release/ZIP не создавался.
Следующий documentation-only commit фиксирует этот receipt; runtime не меняется.
Данные очистки сохранены как отдельная прежняя операция, не как доказательство V4.

Основные изменённые файлы: `grangerpet/research_canvas.py`,
`grangerpet/canvas_capabilities.py`, `grangerpet/research_canvas_bridge.py`,
`frontend/src/components/ResearchCanvas.tsx`, `SearchableSelect.tsx`, `GansarFields.tsx`,
`frontend/src/graph-cards.ts`, `graph-model.ts`, `types.ts`, QA-метаданные в `app.py`.
Поставка: `scripts/build_release.py`, `qa_clean_release.py`, `qa_v4_investigation.py`,
spec/build/CI и тесты. Перечень всех изменений, включая прежние удаления производных
QA-картинок, доступен в commit; оригинальные assets/resources не менялись.

## L. Unresolved Issues

- 60 FPS/быстрое полное раскрытие 5000 не подтверждены; подробные метрики выше.
- Full Maigret whole-database completion и 9 других Gansar сетей не проверены новым live.
- Оригинальные источники могут отвечать 429/403/timeout; partial остаётся partial.
- Полный новый redesign всех типов, повторный DPI sweep, внешние GEOINT/Steam/VK/
  TikTok/DeepSeek не объявляются закрытыми этим core regression fix.
- Реальный file-picker export/import/duplicate всех 13 типов отдельно не проходил
  весь native matrix; schema/encrypted roundtrip и сохранение покрыты tests.
- Внешние runtimes остаются необходимыми, EXE не устанавливает их заново.
- OCR integration иногда превышал тестовое ожидание 12 seconds в полном наборе;
  окончательный full и отдельные повторы прошли. Причина задержки не доказана.
- Каталог диагностики этой работы оставлен в Windows Temp: автоматическая проверка
  отклонила его удаление с причиной «blocked by policy», без подробностей. В нём
  нет дополнительных EXE; временные сборки и native QA-профили удалены штатно.

Сохранность: 313/313 текущих
файлов профиля и все проверенные assets/resources совпали; содержимое/имена
частных диалогов и ключи в отчёт не включены. Hermione/phone artwork не менялись.
