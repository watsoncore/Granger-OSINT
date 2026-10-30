# Локальный анализ видимой сцены

Модель: Florence-2-base-ft (0,23B), исходный издатель Microsoft. Используется
совместимый с установленным Transformers нативный checkpoint
`florence-community/Florence-2-base-ft`, revision
`0b03b6f15a4a211370fb204aee4e7dd48887ea37`.

Источники:
- [Microsoft model card](https://huggingface.co/microsoft/Florence-2-base-ft).
- [Совместимый checkpoint](https://huggingface.co/florence-community/Florence-2-base-ft).
- [Оригинальная MIT-лицензия](https://huggingface.co/microsoft/Florence-2-base-ft/blob/f6c1a25888ffc1d945ee8a1a77ac833c7303d46e/LICENSE).

MIT разрешает использование, в том числе коммерческое, с сохранением copyright и
license notice. Копия лицензии включена в resources/third-party. Не загружается и
не исполняется Python-код из model repository: `trust_remote_code=False`, только
закреплённые JSON/tokenizer/Safetensors-файлы с проверкой SHA-256 и размера.

## Ресурсы и установка

468 555 285 байт загрузки; сами веса — 463 178 864 байта. Отдельный каталог
`.toolenvs/scene-vision`. Повторно используется уже установленный optional visual
CPU runtime, его файлы и receipt не меняются. Основной Python не изменяется.
Проверены 14 ГиБ физической RAM, около 6 ГиБ свободной RAM, 126 ГБ свободного диска.
Большая GPU-модель не выбрана: цель — реальное CPU-описание на существующем ПК.

Установщик проекта: `python scripts/setup_scene_vision.py --install`.
Без `--install` он только показывает проверяемые параметры. Приложение не
скачивает эти веса автоматически. На копии без optional runtime инструмент
остаётся недоступным с понятной причиной; облачная модель не подменяет локальную.

## Исполнение

`image_understand` — операция в существующем ToolRegistry. Включена по умолчанию
в `visual_geoint` между OCR и генераторами координат. Отдельный disposable worker,
2 CPU threads, Job Object с пределом 5 ГБ памяти на Windows, дедлайн до 180 с,
отмена с закрытием процесса. Импорт ML в Qt не производится. Сетевые сокеты
worker запрещены; метаданные EXIF удалены перед inference.

Реальные задачи: detailed caption, dense region caption, caption phrase grounding.
Нормализованные области привязаны к ориентированному исходному кадру. Описание,
границы и особенности — оценки модели; не проверенная истина. OCR выполняется
отдельно; язык вывески и место по архитектуре не придумываются.

## Проверка 30.10.2026

- Реальный исходный кадр 547 × 365: описание ночного города, освещённых зданий,
  большой центральной постройки и башни с часами. Отдельная модельная область часов
  соответствует видимому объекту. Первый CPU inference: 21,543 с, peak RSS
  1 834 278 912 байт; передача фотографии внешнему сервису отсутствует.
- После добавления phrase grounding штатный ToolRegistry → visual_geoint:
  62,404 с на всю цепочку, scene + GeoCLIP + Waypoint возвращены. Общий partial
  обусловлен слабым OCR; описание сцены и координаты сохранены.
- 96 targeted tests passed, включая строгий attachment scope, отсутствие
  encoded pixels в контексте DeepSeek, pinned manifest и отмену реального child
  process по дедлайну. Accuracy не подтверждается fixtures.

Это ещё не доказательство готового GEOINT: поиск эталонов, сравнение, карта и
визуальная проверка конечного EXE выполняются следующими этапами.
