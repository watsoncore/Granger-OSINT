# 19 проектов: локальные возможности и исключённые авторизованные режимы

Проверены 11 назначенных проектов; остальные 8 исследуются отдельно. Для каждого получены README, структура исходников, условия установки, лицензия и закреплённый commit. Полные поля с permalink и SHA-256 конкретных прочитанных файлов: [INTEGRATIONS19_LOCAL_AUDIT.json](INTEGRATIONS19_LOCAL_AUDIT.json). Это аудит репозиториев, а не заявление, что 11 сетевых инструментов установлены.

В основной Python3.14 не добавлены NumPy, Cartopy, Neo4j, Selenium, Playwright, Groq, Gemini, Apify, HikerAPI, Caffe или старый PyQt. Авторизация в аккаунтах, импорт контактов и чтение browsercookies не выполнялись. Исключённые инструменты не получают карточек «Укажите ключ». Существующие персональные интеграции Granger сохранены.

## Реальные независимые capabilities

### tiktok_timestamp

Адаптирован локальный MIT-алгоритм [Bellingcat](https://github.com/bellingcat/tiktok-timestamp): точный Python integer, перевод ID в binary, первые 31 значимых бита. Принимается полный `https://www.tiktok.com/@user/video/ID` или десятичный videoID. Shortlinks не раскрываются, login/запрос кTikTok не выполняются. Поддерживается наблюдаемый формат с 63 значимыми битами до 2038 года; неожиданный формат отвергается.

[Первичное исследование Ryan Benson](https://hindsig.ht/blog/tinkering-with-tiktok-timestamps/) приводит URL `https://www.tiktok.com/@billnye/video/6854717870488702213`. Локальный расчёт даёт 1595988373 / **2020-07-29T02:06:13Z**; указанное в исследовании createTime1595988377 на 4 секунды позднее. Значение изID — производный временной сигнал, не независимо проверенная публикация, существование или авторство видео.

### shadow_regions

Локальная вычислительная часть [ShadowFinder0.7.1](https://github.com/bellingcat/ShadowFinder) адаптирована под bounded scalar execution без plotting/timezone stack. Солнечные координаты воспроизводят формулы используемого upstream `suncalc-py`; соответствующие MIT и BSD-2-Clause notices сохранены. Это не вызов всего CLI или Colab, не нейросеть и не определение места по одному фото.

Обязателен `datetime_utc` вISO8601 сZ/смещением. Дополнительно **либо** `object_height` и `shadow_length` в одинаковых единицах, **либо** `sun_altitude_deg`. Неизвестное местное время не угадывается. Используется исходная формула `predicted_shadow=height/tan(sun_altitude)` и относительный остаток `(predicted-observed)/observed`, либо относительный остаток угла.

Выход: возможная полоса географических ячеек вGeoJSON, шаг сетки, tolerance, число оценённых/подходящих ячеек, явный truncation, рассчитанные солнечные параметры и оценки заданных кандидатов. `compatibility_score` от 0 до 1 — нормализованный геометрический остаток, **не вероятность местоположения**. Точки ниже горизонта не совпадают. Область может включать множество стран.

Ограничения: UTC и измерения должны быть известны; вертикальный объект, ровная поверхность, без наклона/рельефа/атмосферной рефракции. Grid считает центр ячейки, не точный контур. Максимум 210000 оценённых центров,2000 возвращённых ячеек,100 явных кандидатов. Проверки отмены/deadline выполняются внутри циклов. Не скачиваются timezonegrid, карты, модели, датасеты. Root может сопоставлять `candidate_scores` с отдельно полученными GeoCLIP/Waypoint-кандидатами; без собственных входных данных такой результат не выдумывается.

Тесты: точный опубликованный upstream SunCalc vector `2013-03-05T00:00:00Z,lat50.5,lon30.5` даёт altitude=-0.7000406838781611rad и соответствующий azimuth. Документированный ShadowFinder CLIпример `10 5 2024-02-29 13:59:59 --time_format=utc` вычисляет настоящую неоднозначную полосу. Также проверены angle mode, ночная сторона, явная timezone, лимиты и неверные параметры.

### role_classify

Из [LinkedIn OSINT Toolkit](https://github.com/michaelelizarov/linkedin-osint-toolkit) адаптированы только MIT-файлы `osint_classify_rules.py` и `classification_rules.json`. Правила читаются через package resource, без fallback кпроизвольному cwd. Вход 1–100 уже известных текстов должностей, максимум 256 символов. Выход — hierarchy level/weight и division, исходный текст и индекс сохранены. Groq/браузер/скрейпингLinkedIn не используются.

Это эвристика английских keywords, не доказательство трудоустройства, реальных обязанностей или оргструктуры. Неизвестные/неанглийские названия могут получить Staff/General. Алгоритм проверен на upstream-примерах CEO, Director ofFinance, SeniorSoftwareEngineer, JuniorDeveloper и Intern. Сетевой сбор LinkedIn исключён из-за обязательного логина и stealth.

## Все 11 проектов

| № | Проект / commit | Лицензия | Допуск | Причина и независимая часть |
| --- | --- | --- | --- | --- |
| 4 | [LinkedIn OSINT Toolkit](https://github.com/michaelelizarov/linkedin-osint-toolkit) · `c2b38ae785ee` | MIT | PARTIAL_LOCAL_ONLY | Сетевой сбор требуетLinkedIn login/stealth; только локальная классификация уже полученных titles. |
| 5 | [Steam Monitor](https://github.com/misiektoja/steam_monitor) · `16a603517b02` | GPL-3.0-or-later | EXCLUDED | Мониторинг требуетSteam Web API key. Независимый проверенный режим мониторинга без ключа не найден. |
| 6 | [x-scraper](https://github.com/proxidize/x-scraper) · `90423e9b6931` | MIT | EXCLUDED | ТребуютсяX credentials/session; anti-detection/proxy-режимы не подключаются. ActualLICENSE=MIT, несмотря на README badgeEducational. |
| 8 | [insto](https://github.com/subzeroid/insto) · `124f8c681495` | MIT | EXCLUDED | HikerAPI token либо aiograpi сInstagram login. Бесплатный trial не устраняет ключ. |
| 9 | [Osintgraph](https://github.com/XD-MHLOO/Osintgraph) · `c9bbcabb2060` | GPL-3.0-or-later | EXCLUDED | Instagram login, Neo4j и Gemini stack. Не копируетсяGPL-код сборщика/агента. Root graph — независимая обработка собственного evidence. |
| 10 | [TokIntel](https://github.com/HackUnderway/TokIntel) · `0b6cb36bcc0b` | MIT | EXCLUDED | Сбор через обязательныйApify token. DTO/formatting не выдаются за новый источник. |
| 12 | [Bellingcat TikTok Date Extract](https://github.com/bellingcat/tiktok-timestamp) · `aa9831e7dfd1` | MIT | LOCAL_EXECUTION_SUCCESS | Локальный ID timestamp без сети; время изID не равно независимой верификации публикации. |
| 13 | [Telegram Phone Number Checker](https://github.com/bellingcat/telegram-phone-number-checker) · `0241df1953cd` | MIT | EXCLUDED | Telegram API_ID/API_HASH и авторизованный аккаунт; contact operations не выполняются. |
| 14 | [Instagram Location Search](https://github.com/bellingcat/instagram-location-search) · `e4045cc5b194` | MIT | EXCLUDED | README прямо требуетInstagram cookies; undocumented API. Анонимный допустимый запрос не подтверждён. |
| 15 | [ShadowFinder](https://github.com/bellingcat/ShadowFinder) · `215485abd5a4` | MIT | LOCAL_EXECUTION_SUCCESS | Локальные солнечные вычисления адаптированы без тяжёлого plotting/timezone stack; не photo-only inference. |
| 17 | [VKAnalysis](https://github.com/migalin/VKAnalysis) · `23bfedc490c9` | Apache-2.0 | EXCLUDED | VK login/password, старыеPyQt/vk-api/Caffe зависимости; сбор исключён. Root может считать пересечения только уже полученного evidence. |

## Установка, лицензии и проверка

Для исключённых обязательных auth/key-режимов installation/execution намеренно не выполнялись: не вводились фиктивные ключи, аккаунты не создавались, несовместимые стеки не ставились в основное окружение. Это указано как **Не проверено**, а не INSTALLATION_SUCCESS. Для принятых частей выполнена реальная локальная адаптация с чистым импортом в существующем Python и без внешних зависимостей.

**44 passed** в 0.17 с: `python -m pytest -q tests/test_integrations19_local.py`. Математические функции реально вычисляются, не подменяются MockTransport. Ошибки, пустые/неподдержанные параметры, неизвестные операции, отмена и deadline проверены. Сетевой live-статус неприменим клокальному вычислению и не присваивается. Agent/evidence иpackagedEXE статусы root подтверждает отдельно.

Лицензии сохранены в `resources/third-party/integrations19/`: ShadowFinder MIT, TikTok timestamp MIT, LinkedIn classifier MIT, suncalc-py MIT и исходный SunCalc BSD-2-Clause. Лицензии всего Osintgraph/VKAnalysis рассмотрены, но их программный код не включён. Не установлены и не распространяются модели или чужие датасеты.

VKAnalysis clone завис при получении; остановлены только идентифицированные процессы этой нашей clone-команды. Исходники и точный commit затем получены штатным публичнымGitHub API и raw URLs,43 файла проверены, pinned23bfedc490c99d488078039b9aab1c7cd3defce9. Это не обход защиты и не установка старого инструмента.

Фактический локальный smoke (`output/integrations19/local-execution.json`): timestamp0.219 мс, первичный импорт классификатора+5 должностей 85.926 мс, ShadowFinder UTC-сетка 13140 центров, grid_step2°,197 подходящих ячеек, wall51.788 мс. Из 100 разрешённых output ячеек остальные явно обрезаны сtruncated=true. Это измерения одного локального запуска, не общая гарантия времени.
