# Investigation workspace v1 — план и архитектурный аудит

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

Audit/baseline начат. Реализация и A–F ещё не подтверждены. Публичные протоколы будут в docs/validation/investigation-workspace-v1. Тестовые данные не выдаются за live.

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

## C. Implemented Changes

Основные новые файлы: grangerpet/research_canvas.py, grangerpet/research_canvas_bridge.py, frontend/src/components/ResearchCanvas.tsx, research-layout.ts и worker, research-canvas.css. Изменены existing DesktopBridge, InvestigationWorkspace, graph renderer/layout/store, visual_models/tools.py и observations.py, Steam collector/worker и registry cancellation boundary. Новые tests и scripts/qa_research_canvas.py / qa_canvas_stress.py. Список окончательных файлов будет дополнен после native acceptance.

## D. Graph UX

Общий renderer поддерживает typed badges, status dots, двухстрочное имя, ограниченный thumbnail cache, viewport culling и minimap. Tree остаётся branching hierarchy. У Graph добавлены semantic/hierarchy/radial/types/connected-components/time/manual layouts, отдельные manual positions и source filter. Другие раскладки и позиции не смешиваются с ручным полотном. Старые sidecar bytes перед расширением layout сохраняются в workspace-v1-backup. Публичные изображения идут только через existing MediaStore; недоступность не заменяется придуманным avatar.

Группировка по связям означает connected components, не доказанное социальное сообщество. Timeline группирует только фактические timestamp/first_seen, неизвестные даты отдельно. Полная одновременная читаемость 5000 подписей не обещается: применяется progressive expansion.

## E. Interactive Canvas

В «Поиске» → «Мои расследования» → новое или сохранённое. Есть название/описание, несколько проектов, дублирование проекта, JSON import/export, подтверждаемое логическое удаление с сохранением encrypted revisions. Узлы/свои типы, ручные связи с типом/направлением, Markdown, локальные изображения, группы и вложенность, multi-select/рамка, drag, connection ports, clipboard внутри редактора, undo/redo, hide/remove/delete с разной семантикой. Ручная гипотеза не может стать verified из editor.

Свойства можно скрыть, редактор разворачивается внутри Search. Ctrl+F — поиск, Ctrl+Z/Y — история текущей сессии (40 операций), Delete — убрать из представления. JSON granger-investigation/1 содержит entities/relations/evidence/annotations/view; export намеренно открытый, с явным предупреждением. Import получает новый project ID, сохраняет common entity IDs и маркирует внешние данные imported_unverified. Это не заверенная независимая проверка экспортированных фактов. Локальные originals остаются в existing encrypted AttachmentStore; JSON содержит references/previews, не полный перенос каталога originals на другой компьютер.

Инструмент запускается из выбранного узла существующим registry. Сначала preview с фактическим status/limitations, затем пользователь выбирает evidence для вставки. Повторный импорт deduplicates common IDs, сохраняя ручные annotations и positions. Результаты поиска можно так же открыть для выбора. AI получает ограниченный подграф без пикселей; explain/compare/next/report запрещают инструменты явно, действия исследования остаются отдельным намерением. AI не меняет полотно автоматически.

## F. Gansar

В native-source вызван настоящий blockchain_gansar profile/quick для публичного TON address из контрольных сценариев. Во втором прогоне: partial, 71 rows, 16.82 s; выполнено восемь collector providers / 34 HTTP requests по наблюдению интерфейса. Это не полная проверка всех операций и сетей. Транзакции, адреса, активы, NFT/collection/contract/identity и labels обрабатываются существующими typed adapters и evidence_graph. Flow не означает общий владелец. Основной Gansar checkout не изменялся.

Повторная вставка одних и тех же наблюдений не создала новых сущностей. Native frozen повторный запуск/cached status и направления связей ещё проверяются отдельно.

## G. GEOINT / SOCMINT

Сохранены EXIF/OCR/Florence/GeoCLIP/Waypoint/DEM/OHM/STAC и competing-region logic V2. no_candidates — сохранённое наблюдение с computation_status=completed, а не гипотеза координат. Старый completed-empty checkpoint replay исправлен без изменения его байтов. Подставных координат нет.

Steam: next_cursor и исходные page receipts сохраняются; новый page checkpoint не превращает 748/795 в полный inventory. Старая цена остаётся наблюдением своего времени. Отмена реального subprocess/DPAPI проверена на явной fixture page; это не live Steam. VK/TikTok public collector protections и nullable fields сохранены, login/CAPTCHA не обходятся. Свежие live результаты указываются только после фактического прогона.

## H. Performance

Source algorithm controls прошли на 50/100/500/1000/5000 mixed nodes; реальные native input/paint/resource controls подготовлены отдельно. Это разные виды измерений. Приводить эти результаты как 60 FPS EXE нельзя. Во время этой работы full Qt regressions, build и тяжёлые EXE идут последовательно. Одна первая source QA зависла на ожидании из-за неверного harness payload для string tool; код приложения не объявлялся неисправным по этой ошибке.

## I. Data Preservation

До начала сохранены реальные защищённые bytes всех 87 файлов профиля, manifests ресурсов/Pet/Gansar/моделей. Промежуточная повторная сверка: 87/87 совпали. QA имеет собственные APPDATA, IPC namespace и credential namespace. Пользовательские conversations не расшифровывались/не публиковались.

Историческая причина V2 mismatch не доказана. Статический аудит показывает atomic replacement ChatArchive и ConversationLibrary.seal, но отсутствие исторической трассировки не позволяет назвать виновную операцию. Повторное DPAPI шифрование может менять bytes при том же plaintext, поэтому один SHA не доказывает содержательную потерю; это также не доказательство причины прошлого события. Отката не было.

Новые canvas writes используют CAS revision, cross-process QLockFile, immutable encrypted compressed revisions, bounded decompression, checksum, fsync/atomic replace. Head — только метаданные; recovery выбирает новейшую валидную ревизию без удаления повреждённых. Каждая ревизия сохраняется; частота записей — после жеста, не каждого pointermove. Предыдущие профили и release не мигрируются.

## J. Testing

Native-source vertical: 13 checks, настоящие RDAP и Gansar, explicit insert/dedupe/restart. Скриншот после рестарта просмотрен; на его основе добавлены expanded editor и исправления ручных labels, media и groups. Это ещё не frozen acceptance.

Frontend: 144 passed. Первый полный Python: 1769 passed, 2 skipped, 32 subtests, один regression failure отмены; причина исправлена. Затем focused Qt/backend: 92 passed. Финальные полные прогоны и frozen QA продолжаются; ранние failures сохраняются в ignored output и не засчитываются как успех.

## K. Release

Действующий dist/Granger-OSINT.exe пока остаётся V2 (428f3d02…). Непроверенная сборка его не заменяет. Новый candidate, его SHA и проверка встроенного кода будут записаны отдельно. Текущая работа не называется финальным релизом до проверок A–F.

## L. Outstanding Acceptance

- Конечные full regression, frozen build/code-resource verification.
- Реальные native mouse drag/connection, import/export, A–F и large-graph metrics.
- Повторный Gansar/tool context/cancellation в frozen app.
- Свежий Steam access/coverage/resume без выдуманного успеха; scoped external blockers.
- Конечная preservation/secret/ZIP audit и нормальная публикация в существующую ветку.
- Исторический V2 dialog mismatch остаётся неизвестной причины независимо от нового canvas.
