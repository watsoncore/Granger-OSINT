# GEOINT Research — backend и границы проверки

Операция `geoint_research` работает в существующем ToolRegistry/AgentRunner.
Вход — выбранное attachment ID и уже сохранённые координатные гипотезы. Она не
угадывает координаты при отсутствии результатов моделей. Близкие точки
группируются; raw scores и модельный разброс не превращаются в вероятности.

## Исполняемые этапы

1. Сохранённые EXIF/OCR/Florence/GeoCLIP/Waypoint observations.
2. Nominatim reverse lookup с общим rate gate и cache.
3. Ограниченный OSM/Overpass-запрос 500 м: исторические/туристические объекты,
   остановки и именованные мосты. Пользовательский endpoint сохраняется. Для
   временной недоступности default разрешён один публичный fallback
   [Private.coffee](https://overpass.kumi.systems/), с теми же ограничениями.
   401/403 не обходятся; глобальных запросов и сетки координат нет.
4. Запросы на английском и русском зависят от описанной сцены и названий места;
   используются действительные `name:en`/`name:ru`, если они предоставлены OSM.
5. Wikimedia geosearch + imageinfo: координаты, source page, изображение, автор,
   лицензия. Небольшие оригиналы допускаются напрямую из фактического API-ответа.
6. Panoramax STAC: ограниченный bbox, до 10 metadata records, ранжирование по
   расстоянию; для загрузки выбираются доступные эталоны. Источник, дата,
   координаты и лицензия сохраняются.
7. Фотографии скачиваются через `public_media.py`: DNS pinning, robots,
   MIME/decoder/size validation, encrypted cache. Неуспех одного архива не
   отбрасывает фотографии другого. Сохранённые references доступны после restart.
8. До двух локальных сравнений: Florence-описание эталона и DISK/LightGlue с
   геометрической диагностикой. Сохраняются точки и размеры входов. Маленькая
   область совпадений или повторяющиеся фасады не подтверждают локацию.

Состояния `model_candidate` и `geographically_plausible` не означают exact match.
Снимок из близкой точки не объявляется снимком исходного ракурса. На данном
этапе automatic exact-match verification не заявляется.

## Официальные дополнительные API

Ключи добавляются существующим нативным редактором и хранятся прежним защищённым
механизмом (в том числе portable vault). Ключи не попадают в renderer, URL или логи.

- [Google Cloud Vision Web Detection](https://docs.cloud.google.com/vision/docs/detecting-web):
  официальный image annotation endpoint, web entities, matching images/pages,
  similar images. Это отдельный API с billing/auth; не Google Lens.
- [Yandex SearchByImage](https://aistudio.yandex.ru/ru/docs/search-api/api-ref/ImageSearch/searchByImage):
  отдельная разрешаемая передача выбранного файла, API key + Folder ID.
- [Yandex ImageSearch.Search](https://aistudio.yandex.ru/ru/docs/search-api/api-ref/ImageSearch/search):
  текстовый поиск без загрузки фото. Ответ — base64 UTF-8 XML. Поля провайдер
  [не гарантирует](https://aistudio.yandex.ru/ru/docs/search-api/concepts/image-search);
  парсер принимает только однозначно обозначенные image URL, запрещает DTD/entities
  и не выдаёт неизвестный формат за успешную находку.
- [Mapillary API](https://mapillary.github.io/mapillary-python-sdk/docs/mapillary.models/mapillary.models.client/):
  optional token в `Authorization: OAuth`, ограниченный bbox и metadata/thumbnail
  из настоящего ответа. Токен не передаётся в query string.

Google/Yandex reverse image search всегда требуют отдельного разрешения на upload;
сохранённый ключ не является разрешением. Исходный снимок не отправляется ни одному
платному провайдеру в базовом открытом pipeline. Обычные Google Search, Images,
Cloud Vision, Lens, Maps и Street View не смешиваются.
[Custom Search JSON API](https://developers.google.com/custom-search/v1/overview)
закрыт для новых клиентов и прекращается для прежних с 01.01.2027; существующий
optional adapter не объявляется универсальным бесплатным глобальным поиском.

## Реальная проверка

Локальные приватные QA артефакты — `output/reconstruction`, в Git не включаются.
Production registry запускал реальные Nominatim, Commons, Panoramax и локальные
модели. В одном полном запуске: 146,559 с, два настоящих загруженных снимка
Panoramax с CC-BY-SA-4.0 и автором, два реальных reference captions и сравнения.
Статус partial: Overpass default/fallback timeout, Commons invalid response.
Это не было выдано за отсутствие объектов или полное покрытие.

В другом запуске Commons metadata успешно получены, но thumbnail host перенаправил
robots.txt на HTML главной страницы. Такой robots-ответ не используется как
разрешение: загрузка отклонена, затем использован другой архив. Лимиты robots и
политика доступа не ослаблены. Соседние изображения и совпадения повторяющихся
деталей фасада не были выданы за подтверждение точки исходного снимка.

Actual credential-presence check: Google Vision, Yandex и Mapillary unconfigured.
Live paid API requests — 0, private image uploads — 0. Payload/consent/HTTP errors
проверены transport fixtures; эти тесты не доказывают доступ к платным API.

Проверены 88 backend targeted tests, 13 frontend settings tests и TypeScript.
Карта, встроенная галерея и итоговая EXE-приёмка выполняются следующими этапами.
