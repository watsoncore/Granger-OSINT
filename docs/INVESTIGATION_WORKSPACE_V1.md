# Investigation workspace v1 — реализация и протокол проверки

Старт 3 ноября 2026, HEAD 54f3f7f, чистое дерево, действующий EXE 428f3d02….
Новая работа не является выпуском до native acceptance.

## Контракты и зависимости

- Search.tsx сохраняет поиск/каталог и InvestigationWorkspace с Overview/Tree/Graph/Evidence.
- evidence_graph.build уже даёт стабильные ent_/rel_, typed relations, verification и provenance.
- ToolRegistry, InvestigationEvidence и InvestigationJournal уже сохраняют структурированные результаты и Gansar DTO.
- GraphViewStore — только представление автоматического расследования, не редактор сущностей.
- Существующий раздел canvas — редактор текстовых отчётов; его нельзя подменять новым графовым полотном.
- React Canvas renderer уже имеет culling, requestAnimationFrame, bounded thumbnails и layout worker. React Flow оценён по официальной документации https://reactflow.dev/learn/advanced-use/performance; на первом вертикальном пути сохраняется renderer без нового dependency/runtime. Бизнес-модель остаётся Python/JSON, без привязки к renderer.
- Gansar: существующий внешний Gansar-main/app/aggregator/analyzer, typed blockchain_gansar через isolated worker; wallet/profile/assets/transactions/NFT/identity/contracts/labels — только фактически поддержанные операции. Исходный Gansar не меняется. https://github.com/watsoncore/Gansar.

## План по зависимостям

1. Baseline: копия защищённых байтов всего текущего профиля, manifests art/Pet/Gansar/models и аудит записи. Историческую причину изменения диалога не угадывать.
2. Versioned ручное расследование с общими GraphEntity/GraphRelation/evidence, отдельными visual instances; CAS revision, cross-process writer lock, immutable encrypted revisions, atomic pointer, checksum, recovery, undo/redo. Никакой миграции старых dialogs/journals.
3. Вертикальный сценарий: Search → manual node → существующий ToolRegistry → preview → выбранные реальные evidence → общий graph builder → дедуп/merge без потери аннотаций → reopen.
4. Редактор: node/edge/note/media/groups, selection/copy/undo, layouts/filter/minimap, проекты/import/export, AI scope без автоматического изменения фактов.
5. Улучшить существующий автоматический renderer/layout/media на общей модели. Gansar, GEOINT и SOCMINT используют тот же путь импорта.
6. Waypoint empty clusters: отличить выполненное вычисление от пустого географического результата; source/native/frozen контракт.
7. Steam partial checkpoint/cursor/resume, scoped errors, source review без обхода ограничений.
8. Regression/stress 50/100/500/1000/5000; источник и native измерения отдельно. Build candidate, native A–F, hashes, public safe receipts; только затем promotion/ZIP/normal push.

## Сохранность

Private copy 87 файлов / 58070494 байта, каждый скопированный SHA проверен; все источники стабильны. Содержимое не расшифровывалось и не публиковалось. Полный hash baseline в ignored output/investigation-workspace-v1/baseline.

Исторический V2 mismatch остаётся неизвестной причины. Новый baseline содержит реальные bytes для восстановления, а не только хеши. Никакого автоматического восстановления.

## Текущий статус

4 ноября: production code 20f035a, canonical EXE bfe62a9a… поставлен по прежнему пути после проверок. Итоговое полотно: 28 native assertions, включая реальные инструменты, группу со скрытыми детьми, AI selected-node explain и restart. На предыдущем candidate 0027d25e…: native dialogs 6, automatic graph/tree 34, local models/OCR/EXIF 65, phone 15, provider/context 10, stress пять размеров. Между EXE изменился только grangerpet.research_canvas; 155 остальных application modules и 244 bundled resources совпали. Протоколы сохраняют настоящий SHA каждого прогона. Проверка canonical launcher/pet с чистым PATH прошла. Synthetic и live разделены в docs/validation/investigation-workspace-v1.

## A. Architecture Audit

Внутри прежнего Search добавлен ResearchCanvas, без изменения маршрута «Поиск» и прежнего текстового Canvas. Автоматические Overview/Tree/Graph/Evidence остаются отдельно. Общими являются GraphEntity/GraphRelation, стабильные ent_/rel_ ID, evidence_graph.build, ToolRegistry, InvestigationEvidence и journal/checkpoint. Ручное полотно хранит состав, представление и аннотации; копирование создаёт visual instance с ссылкой на исходную сущность, а не новый подтверждённый объект.

От React Flow на этом этапе отказались после оценки существующей реализации и официальных рекомендаций: существующий Canvas уже имеет culling, worker и интеграцию Qt. Сравнительного FPS-бенчмарка двух библиотек не проводилось; ускорение относительно React Flow не заявляется. Новых npm/Python dependencies нет.

## B. Root Causes

- Graph cards рисовали одну строку, различие типов было слабым; медиа загружались преимущественно по выбору узла. Добавлены двухстрочные заголовки, иконки, статус, ограниченная загрузка первых шести видимых изображений, minimap.
- Ручных проектов не было: GraphViewStore хранил только позиции автоматически построенного графа.
- Waypoint при 8 samples мог отдать completed + []: DBSCAN с min_samples >= 3 маркировал все точки шумом. Успех вычисления не равен успеху геолокации. Исправлен adapter и replay старых checkpoint; сами веса/runtime/кластеризация не менялись.
- У Steam промежуточные страницы жили в worker до финального ответа. При принудительной отмене терялись полученные страницы. Новый зашифрованный page checkpoint читается родителем при timeout/cancel.
- Registry.receive отбрасывал результаты после сигнала отмены. Для проверенного partial Steam inventory введено сохранение уже полученных наблюдений при сохранении статуса cancelled/timeout.
- UiJob.cancel подавлял callback. Теперь отдельный сигнал инструмента и generation guard: новый поиск доступен, старый результат сохраняется отдельно и не переопределяет новую задачу. Запись ручного journal вынесена из GUI-потока.
- Перенос сохранённого поиска запускал UI timer из worker. Подготовка preview теперь не уведомляет UI из фонового потока; результат публикуется queued callback на GUI thread.
- Новые native dialogs отсутствовали в списке действий, ожидающих пользовательский ввод без 30-секундного timeout. Исправлено; настоящий диалог оставался открыт 45 секунд без ложной ошибки.
- Вызов string tools зависел от редактируемой подписи. Теперь query берётся из исходного address/value/url; подпись остаётся аннотацией.
- Renderer рассчитывал samples всех кривых до отсечения. Добавлены conservative curve bounds перед семплированием, включая self loops и связи с двумя невидимыми концами, пересекающие viewport.
- Скрытые/свёрнутые члены группы отсутствовали в renderer projection и не получали delta при drag. Backend теперь переводит отсутствующих потомков один раз; явно присланные позиции имеют приоритет. Также проверяются parent/cycle у visual instances и отсоединение после удаления группы.

## C. Implemented Changes

Основные новые файлы: grangerpet/research_canvas.py, grangerpet/research_canvas_bridge.py, frontend/src/components/ResearchCanvas.tsx, research-layout.ts и worker, research-canvas.css. Изменены existing DesktopBridge, InvestigationWorkspace, graph renderer/layout/store, visual_models/tools.py и observations.py, Steam collector/worker и registry cancellation boundary. Новые tests, scripts/qa_research_canvas.py, qa_canvas_stress.py, qa_workspace_steam.py, audit_workspace_release.py, curate_workspace_validation.py. [Полный список прикладных исходников, тестов и QA scripts](validation/investigation-workspace-v1/changed-files.json).

## D. Graph UX

Общий renderer поддерживает typed badges, status dots, двухстрочное имя, ограниченный thumbnail cache, viewport culling и minimap. Tree остаётся branching hierarchy. У Graph добавлены semantic/hierarchy/radial/types/connected-components/time/manual layouts, отдельные manual positions и source filter. Другие раскладки и позиции не смешиваются с ручным полотном. Старые sidecar bytes перед расширением layout сохраняются в workspace-v1-backup. Публичные изображения идут только через existing MediaStore; недоступность не заменяется придуманным avatar.

Группировка по связям означает connected components, не доказанное социальное сообщество. Timeline группирует только фактические timestamp/first_seen, неизвестные даты отдельно. Полная одновременная читаемость 5000 подписей не обещается: применяется progressive expansion.

## E. Interactive Canvas

В «Поиске» → «Мои расследования» → новое или сохранённое. Есть название/описание, несколько проектов, дублирование проекта, JSON import/export, подтверждаемое логическое удаление с сохранением encrypted revisions. Узлы/свои типы, ручные связи с типом/направлением, Markdown, локальные изображения, группы и вложенность, multi-select/рамка, drag, connection ports, clipboard внутри редактора, undo/redo, hide/remove/delete с разной семантикой. Ручная гипотеза не может стать verified из editor.

Свойства можно скрыть, редактор разворачивается внутри Search. Ctrl+F — поиск, Ctrl+Z/Y — история текущей сессии (40 операций), Delete — убрать из представления. JSON granger-investigation/1 содержит entities/relations/evidence/annotations/view; export намеренно открытый, с явным предупреждением. Import получает новый project ID, сохраняет common entity IDs и маркирует внешние данные imported_unverified. Это не заверенная независимая проверка экспортированных фактов. Локальные originals остаются в existing encrypted AttachmentStore; JSON содержит references/previews, не полный перенос каталога originals на другой компьютер.

Инструмент запускается из выбранного узла существующим registry. Сначала preview с фактическим status/limitations, затем пользователь выбирает evidence для вставки. Повторный импорт deduplicates common IDs, сохраняя ручные annotations и positions. Результаты поиска можно так же открыть для выбора. AI получает ограниченный подграф без пикселей; explain/compare/next/report запрещают инструменты явно, действия исследования остаются отдельным намерением. AI не меняет полотно автоматически.

## F. Gansar

В native-source вызван настоящий blockchain_gansar profile/quick для публичного TON address из контрольных сценариев. Во втором прогоне: partial, 71 rows, 16.82 s; выполнено восемь collector providers / 34 HTTP requests по наблюдению интерфейса. Это не полная проверка всех операций и сетей. Транзакции, адреса, активы, NFT/collection/contract/identity и labels обрабатываются существующими typed adapters и evidence_graph. Flow не означает общий владелец. Основной Gansar checkout не изменялся.

В финальном EXE повторены настоящий profile/quick и cached quick/limit=5. Live: partial, 71 observations; cached: 69 observations, новых HTTP requests 0. Число объектов осталось 111; повторная вставка cached observations ничего не продублировала. Более широкий cached scope способен показать дополнительные уже сохранённые данные и поэтому не обязан иметь тот же node count. Проверены 12 sent_from/sent_to relations по typed полям источников; все автоматические tool relations имеют evidence, ни один wallet не получил owner_verified=true.

## G. GEOINT / SOCMINT

Сохранены EXIF/OCR/Florence/GeoCLIP/Waypoint/DEM/OHM/STAC и competing-region logic V2. no_candidates — сохранённое наблюдение с computation_status=completed, а не гипотеза координат. Старый completed-empty checkpoint replay исправлен без изменения его байтов. Подставных координат нет.

Steam: next_cursor и исходные page receipts сохраняются; новый page checkpoint не превращает 748/795 в полный inventory. Старая цена остаётся наблюдением своего времени. 4 ноября настоящий frozen запрос двух страниц вернул 200 item records; следующая операция с полученным cursor увеличила сохранённую выборку до 393. UI завершил обе операции без зависания; после выхода 0 owned processes. Это частичный inventory, price_limit=0, свежие цены не проверялись. Отмена реального subprocess/DPAPI после полученной страницы проверена на явной fixture page; её не выдаём за live cancellation. VK/TikTok public collector protections и nullable fields сохранены, login/CAPTCHA не обходятся.

Waypoint: в frozen EXE воспроизведён case-09 с samples=8/seed=0 → no_candidates, computation_status=completed, candidate_count=0, predictions=[]; place не установлен. Затем все три заранее выбранные licensed фотографии прошли GeoCLIP/Waypoint с samples=32. Полный local-model/OCR/EXIF/restart/exit control — 65 assertions. Расстояния до архивной камеры сохранены в local-models receipt; наличие predictions не означает точную геолокацию.

| Контроль, 32 samples | GeoCLIP top-1 / лучший top-3, m | Waypoint top-1 / лучший top-3, m |
|---|---:|---:|
| case-03, природный ландшафт | 262 / 68 | 110289 / 110289 |
| case-09, городская улица | 363 / 20 | 404005 / 12393 |
| case-10, архитектурный объект | 249082 / 80859 | 20262 / 20262 |

Это расстояние до архивной позиции камеры трёх заранее выбранных изображений, а не общая accuracy модели. Ground truth/лицензия/source URL и SHA оригинала указаны в receipt. Пиксели перед inference очищены от EXIF. Ошибки в десятки и сотни километров сохранены без замены более удачными изображениями.

## H. Performance

Source algorithm controls прошли на 50/100/500/1000/5000 mixed nodes. Медиана самого дорогого layout на 5000: connected components 522.458 ms; hierarchy 313.288 ms, radial 4.216 ms, types 2.695 ms, timeline 6.235 ms. Это Node/algorithm timings, не EXE FPS.

Frozen candidate 0027d25e…, Windows Qt/WebEngine; synthetic mixed nodes/images/groups, N−1 relations, 12 жестов drag и 4 wheel. Метрики фактического renderer и ресурсов дерева процессов:

Машина: AMD Ryzen 5 5600H, 6 cores / 12 logical processors. Builder Python 3.14.5, PySide6/Qt 6.11.1; runtime не обновлялся. Финальный EXE имеет тот же frontend и renderer bytecode/resources; таблица сохраняет SHA действительно измеренного candidate, не переименовывается в новый замер.

| Узлы | Open + progressive expand, s | Paint median / p95, ms | JS input → paint median / p95, ms | 1000 / median active interval | RSS sum, MiB | Private commit sum, MiB | CPU machine, % |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 1.044 | 3.4 / 6.6 | 5.5 / 11.0 | 40.08 | 627 | 751 | 19.27 |
| 100 | 0.737 | 3.6 / 4.9 | 4.85 / 7.3 | 69.44 | 601 | 783 | 4.49 |
| 500 | 2.754 | 4.7 / 5.8 | 5.35 / 6.6 | 61.35 | 682 | 879 | 4.91 |
| 1000 | 3.333 | 6.8 / 7.8 | 8.1 / 9.5 | 51.95 | 851 | 1067 | 7.34 |
| 5000 | 25.652 | 16.4 / 27.9 | 25.25 / 32.5 | 14.37 | 991 | 1117 | 13.76 |

Столбец active interval — частота только соседних paint с интервалом <100 ms; включает coalescing Qt/QTest/Chromium и не является whole-session или display FPS. Input latency начинается в JS pointer handler, а не в устройстве ввода. RSS sum повторно считает shared pages; PrivateUsage — private commit, не private working set. CPU — медиана измеренных активных интервалов всего дерева, не idle. Измерения не дают обещания 60 FPS: особенно на 5000 цель не достигнута. Полотно по умолчанию раскрывает 100 объектов и позволяет работать с меньшей областью.

На 1000 прошли native поиск/восстановление и переключение всех шести layout с точным возвратом manual positions. После пяти наборов parent exit 0, owned processes left 0. Тяжёлые EXE QA не запускались параллельно. Первый source QA ожидал неверно переданный string-tool query; его ошибка сохранена отдельно.

## I. Data Preservation

До начала сохранены реальные защищённые bytes всех 87 файлов профиля, manifests ресурсов/Pet/Gansar/моделей. Промежуточная повторная сверка: 87/87 совпали. QA имеет собственные APPDATA, IPC namespace и credential namespace.

При возобновлении 4 ноября: 85/87 исходных файлов совпали; исчез один transient lock, изменился ciphertext одного диалога. Основной EXE уже не работал. Пользователь ответил, что приложение не трогал. Обе encrypted версии сохранены отдельно. Для проверки потери данных только эти два экземпляра расшифрованы в памяти: plaintext bytes полностью совпали; сообщения и их plaintext hashes не выводились и не экспортировались. Содержательная потеря в этом сравнении исключена. Инициатор повторной записи не установлен; историческое V2 исключение этим не объясняется.

Историческая причина V2 mismatch не доказана. Статический аудит показывает atomic replacement ChatArchive и ConversationLibrary.seal, но отсутствие исторической трассировки не позволяет назвать виновную операцию. Повторное DPAPI шифрование может менять bytes при том же plaintext, поэтому один SHA не доказывает содержательную потерю; это также не доказательство причины прошлого события. Отката не было.

Новые canvas writes используют CAS revision, cross-process QLockFile, immutable encrypted compressed revisions, bounded decompression, checksum, fsync/atomic replace. Head — только метаданные; recovery выбирает новейшую валидную ревизию без удаления повреждённых. Каждая ревизия сохраняется; частота записей — после жеста, не каждого pointermove. Предыдущие профили и release не мигрируются.

## J. Testing

Native-source vertical: 13 checks, настоящие RDAP и Gansar, explicit insert/dedupe/restart. Итоговый EXE: 28 assertions, включая реальную отмену Gansar и следующий RDAP, перенос сохранённого поиска, cached Gansar с тем же mode/limit, node/port/collapsed-group drag, reopen и настоящий AI explain выбранного узла без инструментов. Все поля фактов/позиции совпали до и после ответа; асинхронный thumbnail cache проверяется отдельно. Native export/import: 6 assertions, в том числе ожидание 45 секунд без ложного timeout. Автоматические Tree/Graph: 34 assertions на synthetic-1000 и сохранённых реальных GEOINT/Steam/network observations; два screenshots просмотрены отдельно. Сценарий отменён до получения первых findings: в его результате 0 retained records. Сохранение уже полученных Steam pages подтверждено отдельным real-child/DPAPI fixture, не выдаётся за live Steam.

Frontend: 150 passed, TypeScript/production build passed. Полный Python 03: 1772 passed, 2 skipped, 32 subtests; после последних canvas fixes — 23 focused tests passed. Ранние failures сохранены в ignored output. Cached control сначала сравнивал live quick/limit=5 с cached standard/limit=200: более широкая сохранённая выборка закономерно добавила новые объекты. Контроль исправлен на одинаковый scope и повторную вставку одних observations. Первый stress оборвался на IPC при 1000: причина не доказана; повторный frozen прогон прошёл все размеры без orphans. Первый provider control остановил ещё выполнявшуюся проверку через 65 s: два последовательных client этапа имеют суммарную границу около 91 s. При ожидании 105 s прошли connection, восемь chat turns и 10 assertions. Первый AI immutable control поймал только завершившиеся media previews, не изменение фактов; повтор с явно выделенным presentation cache прошёл. Ранние отказы не засчитаны как passed.

## K. Release

Production code commit 20f035a; ветка granger/chibi-reconstruction. Canonical dist/Granger-OSINT.exe: 279283981 bytes, SHA-256 bfe62a9a5e37ddbf9b51c87b869d607899e3f89db22cde418e8f5156c5a84ff2. Delivery PyInstaller build 194.645 s; 156 packaged modules и 222 resource checks совпали. 28 native canvas assertions прошли именно на delivery bytes. Provider/phone/models/automatic graphs/stress/dialog receipts — на 0027d25e…, их незатронутые модули/ресурсы сверены отдельно. Canonical PE AMD64/PE32+/GUI, launcher + pet с чистым PATH passed. Старые EXE/source ZIP и сопутствующие файлы сохранены с SHA в dist/archive/before-investigation-workspace-v1. Source ZIP/hash и окончательный normal push фиксируются отдельными release receipts, без force.

Secret audit: точные bytes трёх доступных сохранённых credentials не найдены в 6799 проверенных payloads исходников/Git/extracted frozen resources/PYZ. Есть два неизменённых stock Qt/Chromium ресурса с публичным Chrome UX Report client identifier и фрагментом URL, похожими на API-token regex; их полные SHA совпали с установленным Qt и старым проверенным EXE. Они классифицированы отдельно, без вывода строк. Exact user-secret detection применяется и к ним. ZIP audit выполняется после упаковки.

## L. Unresolved Issues and Scope

- На 5000 узлах цель около 60 FPS не достигнута; развёртывание ограничено/последовательно, значения приведены без обещания плавности для всех объектов сразу.
- Fresh Steam — частичная выборка 393/795; проверен cursor continuation, не полное завершение inventory и не свежие цены/float каждого предмета.
- Нет live-проверки всех 75 операций/всех Gansar сетей. Source restrictions VK/TikTok, nullable fields и точность моделей не устранены выдуманными значениями.
- JSON экспорт переносит previews/references локальных изображений; originals не становятся переносимым каталогом вложений на другом ПК.
- Undo/redo ограничен текущей сессией 40 операций; encrypted revisions для восстановления сохраняются отдельно. Connected components не означают доказанное социальное сообщество.
- Старые группы/автоматические наблюдения не мигрируются в новый формат без явного пользовательского импорта.
- Исторический V2 dialog mismatch остаётся неизвестной причины независимо от нового canvas.
