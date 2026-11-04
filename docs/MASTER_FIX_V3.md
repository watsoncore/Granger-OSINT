# Master Fix V3 — отчёт A–L

4 ноября 2026. Отчёт относится к существующему Granger-OSINT, ветке `granger/chibi-reconstruction`.
Область и результаты каждой проверки указаны отдельно; публичные агрегаты — в
[validation-summary.json](validation/master-fix-v3/validation-summary.json).

## A. Root Cause Analysis

Исходный HEAD `4c9f64e8c2e1b00881b8632fc7f01e2a9ff6d47c`; рабочее дерево было чистым.
Gansar уже поддерживал 11 сетей, но manual identity использовал `evm|address`, а
root-goal мог создавать дополнительный кошелёк без известной сети. IP не отклонялся
до запуска worker. Общая Decimal-аналитика существовала; ручное полотно обходило
её проекцию. Incremental import заменял агрегат последним пакетом. При явном
refresh исчезнувшие из новой проекции переводы оставались активными.

Maigret ограничивался выборкой адаптера, generic registry cap и timeout. База была
установлена. Исходный HTTP checker отключал TLS verification. Дополнительно generic
redaction обрезала диагностику до 150 элементов, а durable evidence-путь — до 2000.

Canvas bridge возвращал `pending` до durable commit. Следующий запрос использовал
старую revision; busy-проверки могли отбросить blur/viewport. Все карточки имели
общую геометрию, media — маленький crop, порты были видны постоянно. Query form
и повторные заголовки отодвигали полезный graph примерно до 805 native px.

## B. Gansar Capability Matrix

[Полная матрица исходников, операций и ограничений](GANSAR_CAPABILITIES_V3.md).
BTC, DOGE, TON, Tron, Solana, Ethereum, BSC, Polygon, Arbitrum, Optimism, Avalanche.
`0x` требует явной сети; ID содержит сеть и канонический адрес. Typed capability
проверяется до worker; IP и недопустимые операции отклоняются. Сеть узла не
подменяется выбранным пользователем другим blockchain.

| Source-live | Время | Findings | HTTP | Результат |
|---|---:|---:|---:|---|
| BTC | 14.900 s | 135 | 16 | partial, 50 transactions, 74 counterparties |
| Tron | 14.046 s | 168 | 11 | partial, ошибка contract metadata сохранена |
| Solana | 14.366 s | 1105 | 15 | partial, RPC 429 сохранён |

Это registry/worker и сеть, отдельные профили. Cache roundtrip — 0 новых запросов;
число cache rows отличается из-за иной аналитической проекции. Остальные восемь
сетей проверены по исходникам и fixtures; новый успешный live для них не заявлен.

## C. Crypto Graph V2

Один evidence graph и одна модель фактов используются в автоматическом и ручном
представлениях. Обзор показывает wallets и агрегированные потоки; sources и raw
transactions раскрываются по требованию. Суммы — Decimal с network/asset/contract
identity, transaction IDs и provenance. Wallet/flow/counterparties/transactions/
paths/manual — проекции одних данных.

UTXO без достоверного pairwise DTO не превращается в выдуманные переводы.
`source_reports_counterparty` — ненаправленный source claim, без суммы и без
утверждения владельца/направления. Count — maximum source claim, не сумма дублей.

Incremental merge пересчитывает агрегаты по всей сохранённой выборке и не
восстанавливает удалённое membership при постороннем импорте. Refresh сохраняет
исходный proof и до 8 наблюдений. При полной новой проекции исчезнувшая tool-связь
с обновлённым evidence ID уходит из активного графа в `retired_tool_relations` того
же versioned документа, вместе с точным снимком и заметкой. Ручные связи, positions
и annotations узлов остаются. Повторное подтверждение восстанавливает заметку.
При truncated rebuild отсутствие связи не используется как доказательство удаления.

Projection 2000 observations / выбранный transaction budget остаётся явной защитой.
Summary/analytics выбираются первыми, категории — по кругу, с available/emitted/
omitted counts и partial status. Полный DTO отмечается сохранённым только после
успешной защищённой записи caller-ом. Полотно ограничено 5000 узлами / 20000 связями /
5000 evidence / 24 MB; превышение отвергается без перезаписи старой версии.

## D. Maigret

[Контракт движка и аудит остальных адаптеров](MAIGRET_ENGINE_V3.md).
Оригинальный Maigret 0.6.6, неизменённая база 3 221 408 bytes:
`25b734d93fb338c75b24f0149ae0251f6fca88d8fce2f9968a0875884421b343`.
8232 записи, 28 engines, 7508 enabled username entries.

| Режим | Selected | Scheduled после явной transport policy |
|---|---:|---:|
| Quick с mirrors | 16 | 12 |
| Standard | 509 | 365 |
| Full | 7508 | 6434 |

Custom поддерживает точные sites/tags/engines; причины skips видны. Full в registry
не наследует cap 10/20/50 или timeout 90 s. Progress использует реальные счётчики;
findings передаются сразу, per-site statuses и remaining sites сохраняются при
cancel/timeout. TLS/DNS/redirect/body guards локальны worker-у, vendor не изменён.
Recovery/notification/POST/TOR и обход access gates не подключались.

Сравнение шести exact sites с original core API под одинаковым проверяемым transport:
3 found, 3 not_found, 0 расхождений. Это не массовый Full live scan.
2201-row fixture прошёл registry → sanitizer → manual workspace → encrypted checkpoint
→ journal → reopen/restore: 2201 findings/checks и 201 remaining name сохранены.
10 000-row структурный предел превышает установленную базу; он выдаёт ошибку,
а не скрытый slice. Resume — явный новый Custom-запуск оставшихся сайтов.

## E. Graph & Cards

Общие `graph-cards`, geometry и layout workers используют фактические размеры.
Типы различимы, есть semantic zoom, порты при hover/selection, крупные contain-media
с resize и native viewer оригинала. Server-owned media lookup не принимает client
path/URL; защищённые оригинальные bytes и SHA проверяются. EXIF ограничен allowlist.

Layout: manual/hierarchical/radial/types/communities/timeline и crypto-проекции;
pins, группы и ручные позиции сохраняются. Dijkstra использует heap, union-find —
path compression, большие раскладки — ограниченное число шагов. Worker payload
не дублирует media/evidence; progressive reveal и culling остаются явными.

## F. UI/UX Before/After

Manrope, compact/comfortable density, согласованные scrollbars и searchable selects.
При существующих результатах query form сворачивается в строку редактирования;
при первом поиске остаётся открытой. Убраны повторные заголовки. Inspector имеет
контекстные «Сведения / Основания / Действия», persistent width/open/tab.
Автоматические Overview/Tree/Graph/Evidence и ручное полотно разделены внутри
существующего Поиска; текстовый Canvas сохранён.

В native 1920×1020 при DPR 1.25 graph начинается около 488 px, видно около 532 px;
GEOINT metrics — около 428 px вместо 742. Steam использует собственный полезный
первый раздел «Таблица» (около 451 px), а не искусственный generic CTA.
100/125/150% DPI проверены в изолированных процессах предыдущего кандидата;
Windows settings не менялись. При 150% логическая ширина 1280, вертикальная
прокрутка остаётся необходимой; одинаковая высота graph на всех DPI не заявляется.

## G. Stability

[Подробный протокол commit и recovery](CANVAS_COMMIT_RECOVERY_V3.md).
Deferred ACK приходит после encrypted immutable revision. Одна frontend очередь
использует ACK revision, stable mutation IDs и bounded idempotency receipts.
Настоящий CAS сохраняется: конфликт не отключается, требует явного reload/rebase.
Retry/discard различаются; смена проекта не переносит действие другому владельцу.

Shutdown замораживает intake, дренирует accepted edits до 2.5 s и сохраняет остаток
защищённо. Несохранённый editor text захватывается только при shutdown как inert
intent. После restart требуется явный повтор; текст не превращается автоматически
в факты. Map на 300 dirty owners отказывает новому owner с объяснением, старые
не вытесняет. Pending guard: 1024 intents / 32 MB UTF-8; последние 128 durable
receipt IDs исключают повтор поздно завершённого commit. Обычный snapshot не
читает editor Map. Corrupt ciphertext сохраняется без переписывания.

Actual native-source dirty-note/close/reopen/retry + media: 24/24 PASS.
Gansar/Maigret отменяют только собственные workers; новый запуск после отмены проверяется.

## H. Performance

Последние frozen measurements: paint median/p95 и event-handler→paint median/p95,
ms; open + progressive reveal — s. Synthetic и actual saved observations разделены.

| Узлы | Происхождение | Paint ms | Event→paint ms | Open/reveal s |
|---:|---|---:|---:|---:|
| 50 | synthetic_fixture | 3.4 / 9 | 8.3 / 14.1 | 1.016 |
| 100 | synthetic_fixture | 3.0 / 4.9 | 9.4 / 19.3 | 0.711 |
| 500 | synthetic_fixture | 4.9 / 7.1 | 7.3 / 21.4 | 3.527 |
| 1000 | synthetic_fixture | 7.9 / 9.5 | 11.1 / 23.3 | 4.4 |
| 5000 | synthetic_fixture | 18.5 / 30.6 | 31.35 / 57.6 | 38.428 |
| 230 | provided_observed_result | 1.7 / 6.4 | 5.1 / 14.2 | 0.938 |

Метрики — actual Qt/WebEngine Canvas, с culling: 5000 — весь сохранённый набор,
а не 5000 одновременно подробных изображений. Reciprocal active interval исключает
паузы ≥100 ms и не равен whole-session FPS. Цель 60 FPS на 5000 не подтверждена.
На предыдущем кандидате 5000: paint p95 26.5 ms, event→paint p95 39.7 ms,
active reciprocal 14.03. Финальные значения выше относятся к своему EXE.

Ранние failed harness receipts сохранены: open до viewport ACK, вытесненный metrics
snapshot и неверное сравнение full evidence с compact IPC preview. Comparator
теперь читает настоящий encrypted CanvasStore. Первоначальный холодный 50-node
paint max 1377.3 ms не заменяется более быстрым повтором. Отдельный реальный Tron
контроль подтвердил selected-flow drill 10→11 visible при 82 сохранённых tx и
неизменном evidence SHA; первоначальный no-op флаг не считается успехом.

## I. Data Preservation

185 исходных profile ciphertexts скопированы побайтно в private baseline без
расшифровки. Сверяются assets92/resources202/Gansar509/Maigret207, visual_cpu23387,
scene_vision25, Maigret runtime9796 и 16 Pet runtime modules. Итоговый read-only
hash report находится в public validation summary. Исторические изменения
шифрованных диалогов прежних задач не откатывались и не приписывались пользователю.

Старый EXE 279283981 bytes, SHA `bfe62a9a5e37ddbf9b51c87b869d607899e3f89db22cde418e8f5156c5a84ff2`;
старый ZIP SHA `0e261db8525ab5a124c69f2a69bc0a16de9d34fad2ab3a94aea148187ab2460a`.
Оба сохранены в `dist/archive/before-master-fix-v3/`. Работающий canonical EXE не
останавливался; новая поставка отделена. Pet artwork/phone/scheduler не правились.

## J. Tests

Финальный полный source backend: `1953 passed, 2 skipped, 32 subtests passed in 359.92s (0:05:59)`.
Frontend: 175 tests / 27 suites PASS, TypeScript и production build PASS.
После позднего refresh fix: 76 targeted backend PASS, включая encrypted reopen.
Fixtures проверяют CAS/concurrency/cancel/partial, UTF-8, 300 full-length Unicode
черновиков + 724 queue intents, 2201 Maigret outcomes, networks и budgets.

| Финальный EXE | Результат / область |
|---|---|
| Manual canvas | 34/34 PASS; реальные RDAP/TON/cache/cancel, drag/ports/group/restart/draft/media |
| Media / дополнительный restart | 25/25 PASS; видимая крупная карточка и original viewer |
| Maigret | 7/7 PASS; 6 exact live sites |
| PE smoke | 2/2 PASS; launcher + pet, restricted PATH, fresh profile |
| Automatic | 32/32 PASS; saved actual TON/GEOINT/Steam/network, не новый network/inference |
| Stress | 3/3 PASS; пять synthetic sizes + actual saved Tron |
| Phone | 15/15 PASS; interruptions/restart, исходный Pet код |

Source-live, native-source и frozen-live не подменяют друг друга. Все GUI QA имеют
отдельные APPDATA/IPC/vault и проверяют собственный PID. Пользовательский чат не
открывался и ключи не подставлялись. Новый DeepSeek-запрос этой V3 не заявлен.
Полные локальные logs/findings/profile snapshots не публикуются. В public subset
попадают только allowlisted aggregates и отдельно просмотренные собственные QA PNG.

## K. Release

EXE: `dist/master-fix-v3-complete/Granger-OSINT.exe`, 279378959 bytes.
SHA-256: `4d07eb036a7f0366a48777663b99508027b0ad5404267b889063938cc5b8eff7`.
Сборка PyInstaller; source/PYZ и data/resources сверяются отдельными скриптами.
Source ZIP и manifest создаются `scripts/package_release.py --dist-dir
 dist/master-fix-v3-complete --qa output/master-fix-v3/public-release`.
Commit/branch/publication — в `git-publication.json` рядом с поставкой и в ZIP;
список изменённых файлов и hashes — в public release receipts. Promotion старого
canonical EXE не выполняется, пока он работает. Перед запуском новой версии
закройте старую через её обычный выход; иначе single-instance IPC активирует старую.

## L. Unresolved Issues

- 60 FPS на 5000 не достигнуты; cold-start/reveal могут занимать десятки секунд.
- Восемь Gansar сетей без нового live; публичные провайдеры могут давать 429/timeout/partial.
- Full Maigret 6434-site live не запускался. Policy исключает небезопасные transports;
  полное равенство с unsafe original CLI defaults не заявляется.
- Legacy native SearchController вне основного React registry-пути сохраняет query.limit;
  Full поддерживается существующим React `tool_run`/registry и manual Maigret settings.
- Blackbird/Snoop/SocialAnalyzer/Holehe/PhoneInfoga/Steam имеют ограничения из
  [аудита](MAIGRET_ENGINE_V3.md); они не объявляются полной оригинальной интеграцией.
- GEOINT screenshots показывают сохранённые наблюдения, не доказывают точную камеру.
  Свежая Steam price collection, VK/TikTok access-gated content не заявлены.
- CPU models/browser/tool runtimes остаются внешними и не устанавливаются одним EXE.
- Конечные bounds и bounded history документированы; ни бесконечная история,
  ни отсутствие любых возможных races не обещаются.
