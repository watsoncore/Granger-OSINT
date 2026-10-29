# Granger-OSINT: проверка 19 проектов

Дата: 30 октября 2026. Изучены **19 из 19** репозиториев по закреплённым
commit, исходникам, зависимостям и лицензиям. У **10 проектов** подключены
полезные ограниченные возможности без новых персональных ключей; **9 проектов**
исключены. Это не установка десяти полных сторонних приложений.

Общий реестр содержит **48 адаптеров**: прежние32 и16 новых операций, включая
независимый граф evidence, единый Visual GEOINT pipeline и Panoramax.
В текущем окружении **43 локально готовы**; из16 новых готовы15. Nuclei выключен
по умолчанию. Локальная готовность не гарантирует доступность внешнего API.
Существующие персональные подключения и gateway DeepSeek сохранены.

| Инструмент | Проверен | Нужен API/логин | Бесплатный режим | Реализован | Live test | Причина исключения / граница |
|---|---|---|---|---|---|---|
| ScopeSentry | Да | Нет ключа | Исключён | Нет | Нет | Standalone компонент не подтверждён; AGPL и дополнительные коммерческие условия. Свой DNS не выдаётся за ScopeSentry |
| kronikier | Да | Нет | `historical_contacts`, до3 архивных снимков | Выбранная capability | Snapshot200; CDX сбой | Настоящий snapshot HTTP200 дал исторический email; полная CDX-цепочка registry сталкивалась с timeout/503. Полный live успех не заявлен |
| MailAccess | Да | Для Pro | `mail_dns`: синтаксис, MX/SPF/DMARC | Выбранная capability | Да; см. ограничения | Реальные DNS и evidence. Ящик, владелец, recovery, SMTP и платные функции не проверяются |
| LinkedIn OSINT Toolkit | Да | Логин сбора | `role_classify`, локальные keyword rules | Выбранная capability | Локальный расчёт | Локальные тесты и настоящий вызов DeepSeek. Сбор LinkedIn и stealth не подключены |
| Steam Monitor | Да | Steam key | Исключён | Нет | Нет | Основной мониторинг требует ключ; независимая разрешённая операция не подтверждена |
| x-scraper | Да | X session | Исключён | Нет | Нет | Нет проверенного полезного анонимного режима; ограничения лицензии также отражены в аудите |
| X Tweet Fetcher | Да | Нет (Fx API) | `x_post`, `x_profile` | Выбранная capability | Да; см. ограничения | Настоящие пост и профиль ранее получены; позднее профиль вернул честный empty. Поиск, timeline и replies не подключены |
| insto | Да | Key/login | Исключён | Нет | Нет | Оба исследованных режима требуют внешний доступ |
| Osintgraph | Да | Login/Gemini | Исключён | Нет | Нет | Сбор/LLM backend не подключены. Собственный `evidence_graph` Granger не является интеграцией Osintgraph |
| TokIntel | Да | Apify key | Исключён | Нет | Нет | Основное получение TikTok-данных требует ключ; независимое полезное ядро не подтверждено |
| Arctic Shift | Да | Нет | `arctic_posts`, `arctic_comments` | Выбранная capability | Да; см. ограничения | Настоящие ограниченные архивные результаты и evidence. Архив неполный; были временные ошибки API |
| Bellingcat TikTok Date Extract | Да | Нет | `tiktok_timestamp` | Выбранная capability | Локальный расчёт | Точное integer-вычисление UTC, unit и реальный агент. Время из ID не является независимой проверкой публикации |
| Telegram Phone Number Checker | Да | API/session | Исключён | Нет | Нет | Проверка требует account/contact-import; чужие адресные книги и контакты не трогались |
| Instagram Location Search | Да | Cookies | Исключён | Нет | Нет | Проверенный текущий режим требует авторизацию; анонимный доступ не подтверждён |
| ShadowFinder | Да | Нет | `shadow_regions`, известные UTC/измерения | Выбранная capability | Локальный расчёт | Реальная солнечная геометрия, reference vectors и DeepSeek. Неизвестные время/высота не угадываются |
| Nuclei | Да | Нет | Optional CLI3.11.1, один собственный HEAD-template | Выбранная capability | CLI loopback | Реальный собственный loopback-сервер: ровно1 HEAD и отмена. Это наблюдение заголовков, не CVE-сканер; default off |
| VKAnalysis | Да | VK token | Исключён | Нет | Нет | Authenticated collector и legacy зависимости не подключены; полезный автономный режим не подтверждён |
| GeoCLIP | Да | Нет | Настоящий GeoCLIP1.3.0 + CLIP ViT-L/14 | Выбранная capability | CPU inference | Реальные Москва/Париж/кадр без ориентиров, отмена и offline restart. Координаты — некалиброванные гипотезы |
| Waypoint | Да | Нет выбранным стадиям | DINOv2+PLONK YFCC, DISK/LightGlue, отдельный Panoramax API | Выбранная capability | CPU inference | Настоящие ONNX CPU inference/matching и STAC records. StreetCLIP/OSV5M CC BY-NC исключены; весь Waypoint не переносился |

Полные первичные аудиты с SHA256 изученных файлов, лицензиями и exact commits:
[локальные и авторизуемые проекты](INTEGRATIONS19_LOCAL_AUDIT.json),
[публичные API/CLI](INTEGRATIONS19_PUBLIC_AUDIT.json),
[модели и веса](INTEGRATIONS19_VISUAL_AUDIT.json).

## Visual GEOINT и измерения

Основной Python и системный PATH не изменены. После явного согласия скачаны
23 модельных артефакта и47 wheels: **3375375772 байт**, все с проверкой SHA256.
Runtime занимает **4180888934 байт** с кэшем загрузок и site-packages. В основной
EXE веса не включены. Исполнение — offline CPU,2 потока, отдельный дочерний
процесс с memory job budget6GB; сеть в model worker запрещена.

Первичные source-измерения: GeoCLIP холодный вызов30.46с, тёплый1.69с;
Waypoint холодный9.33с, тёплый5.37с. Замеры frozen worker учитывают отдельный
запуск/распаковку EXE; точные stage timings и RSS/private bytes сохранены в QA.
При смене компонента процесс перезапускается, чтобы освобождать native arenas.
Пик frozen RSS: около2.87GB для GeoCLIP,1.72GB для Waypoint,3.12GB для matching;
private bytes matching около5.00GB. Это измерения на данной машине, не требования
всех сценариев.

На двух известных объектах минимальное расстояние среди кандидатов GeoCLIP
получилось примерно58м (Москва) и266м (Париж); Waypoint —764м и326м.
Ориентир — известный объект/позиция камеры из описания фото. Эти две фотографии
не являются оценкой общей точности. На малосодержательном кадре неба модели
вернули разрозненные неверные кандидаты, поэтому raw score/доля сэмплов нигде
не объявляются вероятностью. Сопоставление одного изображения с самим собой
дало реальные matches, но не является независимой street-level проверкой.

Тест с искусственно изменённым GPS у фото Парижа выявил6 расхождений с модельными
кандидатами; это сигнал проверки, не доказанная подделка. Настоящие EXIF/OCR,
кандидаты, сравнение и при известных параметрах тени сохраняются отдельными
evidence. Прерывание frozen inference после исправления blocked input pipe
заняло0.035с; дочерний процесс завершён, последующий offline restart прошёл.

Тестовые фото: [Tsy1980, Москва, CC BY-SA4.0](https://commons.wikimedia.org/wiki/File:Saint_Basil%27s_Cathedral_in_Moscow.jpg),
[Benh LIEU SONG, Париж, CC BY-SA3.0](https://commons.wikimedia.org/wiki/File:Tour_Eiffel_Wikimedia_Commons.jpg).
Для теста удалены метаданные при JPEG re-encoding; малосодержательный кадр —
узкий crop неба. Эти изображения не встроены в приложение и не отправлялись LLM.

## Агент, отношения и ограничения

Настоящий DeepSeek выполнил локальные TikTok/role calls с2 evidence и15 checkpoint,
затем Visual GEOINT+graph с6 evidence и русским итогом. Отдельная публичная проба
вызвала mail_dns, x_profile, arctic_posts, shadow_regions и map_panoramax:
четыре источника дали evidence, X вернул empty, который не превращён в находку.
Nuclei default off и полная историческая CDX-цепочка не объявляются прошедшими
реальную агентную проверку. Доступ через schemas и выполнение — разные статусы.

Граф хранит типизированные сущности, направленные отношения, evidence_ids,
основания и статус проверки; поддерживает соседей/фильтры/пагинацию. Никнеймы
разных платформ не объединяют личность; CryptoBot/Bybit остаются метками источника.
Точки на карте — локальная SVG координатная схема, без внешнего tile-сервиса.

Ограничения Waypoint: выбран YFCC pipeline; автоматические массовые street-image
downloads, ranking всех Panoramax снимков и исходный7-point estimator не перенесены.
Есть DISK LightGlue и собственный8-point RANSAC. OSM и тени поступают из общих
инструментов Granger, не выдаются за воспроизведение всех весов/стадий upstream.
Полная численная эквивалентность PyTorch↔ONNX не заявляется; preprocessing,
schedule, RNG и geometry проверены отдельно. Исходные фотографии обучающих датасетов не скачиваются и не поставляются. Для inference используется опубликованная внутри GeoCLIP wheel координатная GPS-gallery100k; она остаётся частью отдельного optional runtime, не EXE/Git/source ZIP.

Итоговая сборка: **276626324 байт**, SHA256 `3a3fabd4db0d5388956fccc3b2d5b3bdf0cf2aa5658b73774202567466641ccf`.
Python **1150 passed /1 skipped /32 subtests**; frontend **105/105**.
Готовый EXE прошёл **58/58 GUI/tool/restart проверок**; Launcher/Pet smoke
прошёл с PATH=System32. Сравнение bytecode подтвердило88 модулей,137 проверок
ресурсов прошли. Персонаж и его исходные ассеты сохранены. В финальном GUI реально
вызваны TikTok, classifier, DNS, Panoramax, ShadowFinder, Visual GEOINT, graph,
EXIF/OCR, публичный GitHub API и JS renderer. X/Arctic и исторический snapshot
проверены отдельно через source registry; их отдельное сетевое выполнение именно
в финальном GUI не заявляется. Nuclei — отдельный owned-loopback CLI smoke.

Реальные QA-отчёты упакованы в source ZIP только по публичному allowlist; профили,
ключи, пользовательская история и зашифрованные вложения в архив не включаются.


## Изменённые файлы

- `grangerpet/agent_tools.py`, `tool_manifest.py`, `tool_inputs.py`, `agent.py`:
  один реестр, типизированные аргументы, выбор релевантных инструментов, CPU timeout
  и компактный контекст без отправки превью/пикселей в LLM.
- `grangerpet/integrations19/`: локальные алгоритмы, публичные API, Panoramax
  и restricted Nuclei; upstream приложения целиком не импортируются.
- `grangerpet/visual_models/`: pinned manifest, согласованная загрузка/удаление,
  изолированный CPU worker, manager и общий последовательный pipeline.
- `evidence_graph.py`, `agent_evidence.py`, `geoint/images.py`: provenance,
  связи, границы GeoJSON и доступ к выбранным защищённым вложениям.
- `desktop_bridge.py`, `config.py`: существующие настройки, ручные structured
  arguments и async состояния. `message_view.py`: lifetime контекст Qt timer,
  чтобы callback не обращался к уже удалённому виджету.
- `frontend/src/components/` и `tool-presentation.ts`, `types.ts`: формы по схемам,
  карточки вычислений/графа/моделей, SVG координатная схема и optional runtime.
- `main.py`, обе `.spec`: same-EXE child и необходимые stdlib/data resources.
  `engine/runtime.py`: допустимый предел собственного Windows Job до8GB,
  конкретный visual budget6GB; старые defaults не изменены.
- `scripts/setup_*.py`, `scripts/qa_*.py`, `tests/test_*`, `docs/INTEGRATIONS19_*`,
  `resources/third-party/`: установка, реальные и fixture проверки, аудит/лицензии.

Полный финальный прогон после исправления выбора X/изображений и статусов моделей:1150 тестов прошли,1 optional Ollama пропущен. Дополнительные77 и76 целевых regression проверок также прошли. Все88 модулей финального EXE
совпадают с исходниками. Отдельная копия EXE без optional models/tools также
прошла Launcher/Pet smoke. Простой реального model worker освободил процесс за
20.07с; это проверено после inference. Настоящие runtime-файлы не удалялись.
