# Granger-OSINT — очистка и единственная сборка

Дата: 4 ноября 2026. Проект: `C:\Users\Admin\Desktop\Hermi_osint`.

Это исторический результат отдельной очистки до Master Fix V4. Текущие размер,
SHA-256 и функциональная проверка EXE приведены в [отчёте V4](docs/MASTER_FIX_V4.md).

## Фактический результат

| Показатель | До | После |
|---|---:|---:|
| Размер, байт | 50,108,143,867 | 7,122,907,901 |
| GB (10^9 байт) | 50.108143867 | 7.122907901 |
| GiB (2^30 байт) | 46.666845555 | 6.633724925 |
| Файлы | 219,453 | 78,388 |
| Каталоги | 17,008 | 8,786 |
| Granger EXE, включая варианты имён | 64 | 1 |
| Все EXE, включая служебные runtime | 256 | 175 |

**Освобождено в дереве проекта: 42,985,235,966 байт = 42.985235966 GB = 40.033120630 GiB.**
Размеры получены обходом всех обычных файлов, включая скрытые. Ссылки/junction не
обходились; ошибок чтения и reparse entries нет. Это логические размеры файлов,
не оценка по именам каталогов. Итог включает размер этого отчёта.

В `dist` программно подтверждён ровно один файл:
`C:\Users\Admin\Desktop\Hermi_osint\dist\Granger-OSINT.exe`.
Размер EXE: **279,380,121 байт**.
SHA-256: `464ab580095bc1fc7a98f88ab7b198a4475f1f69e55a485500a51eb710263677`.
Отдельных GrangerPet.exe, архивных Granger EXE, release ZIP, sidecar-отчётов и
`_internal` в `dist` нет. Остальные 174 EXE принадлежат необходимым Python,
Go, Qt/PyInstaller, Nuclei, browser/tool runtimes и Tesseract; это не версии Granger.

## Что удалено

- Все 63 прежних Granger EXE/варианта, кроме заменённого канонического пути;
  размеры, SHA-256, даты и происхождение сверены; для 50 EXE в dist дополнительно проверены PE timestamps. Перед
  удалением кандидат сверялся с текущим source, а не только с датами файлов.
- Все 25 старых ZIP релизов в `dist` и остальные старые каталоги/копии выпуска.
  Их ZIP directories проверены: профилей, sessions и secret.env внутри не найдено.
- `build` (5,064,180,394 B): PyInstaller PKG/PYZ/TOC, xref, warnings и bytecode.
- Старые `output` QA-профили, 95 тысяч производных PNG, рендеры, logs, dumps,
  распакованные source/release-копии и `test-output`; оставлены только исключения ниже.
- 220 исторических производных media-файлов `docs/validation`; текущие два media
  `master-fix-v3` и техническая документация сохранены. История доступна в `.git`.
- Go build/module cache (675,104,745 B), Python/pytest/TypeScript caches.
- Go SDK installer ZIP (79,010,309 B): **все 15,657 его файлов побайтно совпали
  с установленным SDK**. Сам Go SDK сохранён; setup использует установленный go.exe.

Мусор удалён по спискам файлов с проверкой containment/reparse и состояния перед
удалением. Новых папок old/backup/архивных копий не создавалось. Временные сборки и
QA были уничтожены после проверки, включая неуспешную первую проверку.

## Сохранность и исключения

SHA-256 до/после: **252/252 файла настоящего профиля**, 268/268 файлов приложения,
202/202 ресурсов и 6/6 исходных config/lock-файлов совпали. Все 55,421 рабочих файла
внешних runtime/model деревьев совпали; из первоначально проверенного набора
дополнительно удалён только доказанно дублирующий Go installer. Веса моделей,
оригинальные artwork, код/ресурсы GrangerPet и vendor sources сохранены.
Расшифрованные профили/секреты не экспортировались; рабочий профиль в `%APPDATA%/GrangerPet` не изменён.

Следующие существующие небольшие материалы оставлены по причине уникальности:

- `output/character-review/`: 5 файлов, 4,504,444 B — исходные reference contact
  sheets, уникальный кандидат и prompt/заметки. Они не являются текущими спрайтами.
- `output/emergency-identity/wip-backup/`: 8 файлов, 101,154 B; и
  `output/emergency-identity/deferred-animation-work/`: 4 файла, 82,946 B —
  незакоммиченные source snapshots, отсутствующие среди достижимых Git blobs.
- 13 прежних файлов профиля, 1,548,580 B, отличаются от текущих и потому сохранены
  на прежних местах: `output/master-fix-v3/baseline/private-profile-copy/attempt-1/`,
  `output/investigation-workspace-v1/baseline/private-profile-copy/`,
  `output/investigation-workspace-v1/preservation-nov04-current/conversations/`,
  `output/master-fix-v2/private-current-preservation/`,
  `output/chibi-reconstruction/private-encrypted-preservation/`.
  Содержимое и имена частных диалогов здесь не публикуются. 262 точных дубликата
  действующего профиля удалены; перечисленные 13 не признаны мусором.
- 12 корневых ZIP (13,242,191 B) — разные предоставленные исходные архивы сторонних
  проектов, а не Granger releases. Их не заменяли предположением о восстановимости.

В `output` осталось ровно 30 файлов / 6,237,124 B из этих исключений.
Обнаруженные 22 иных content ID тестовых GPI сопоставлены с синтетическими,
Commons/Panoramax и публичными browser fixtures; пользовательской работы в них нет.

## Оставшиеся крупные каталоги

| Каталог | Байт |
|---|---:|
| `.toolenvs` | 5,442,567,440 |
| `.venv` | 738,607,393 |
| `.git` | 292,143,001 |
| `dist` | 279,380,121 |
| `frontend` | 167,442,405 |
| `resources` | 58,313,915 |
| `snoop-master` | 38,544,617 |
| `Gansar-main` | 24,791,961 |
| `social-analyzer-main` | 15,625,062 |

Основной объём `.toolenvs` — GeoCLIP/Waypoint/scene-vision weights и изолированные
рабочие инструменты. Крупнейшие веса: CLIP 1,710,540,580 B, DINOv2 1,214,511,816 B,
scene model 463,178,864 B, PLONK 144,272,160 B. torch_cpu.dll (309,509,120 B) — CPU
inference. Wheel-архивы visual-cpu/downloads сохранены: действующий безопасный
uninstall проверяет их и выводит из них список файлов. `.venv` и frontend/node_modules —
единственные необходимые build environments; QtWebEngineCore.dll нужен Qt UI.
Git pack 276,271,183 B хранит историю, Nuclei 144,920,576 B — действующий инструмент.
Дубликат Nuclei из dist/tools удалён после сравнения с `.toolenvs/nuclei/3.11.1/nuclei.exe`.

## Проверки и процесс следующей сборки

- Ветка `granger/chibi-reconstruction`, HEAD `3576fa192ddb51dead7fd0a275bbf43780e182c2`
  сохранены; reset/force push/prune не выполнялись. `git fsck --connectivity-only`
  завершился с кодом 0; существующие dangling objects оставлены. Изменения очистки
  и build tooling находятся в рабочем дереве для просмотра.
- Новый EXE реально собран PyInstaller во временном каталоге, проверен и установлен
  атомарно. **163 встроенных Python-модуля и 239 resource/data checks совпали**
  с текущим source/frontend. Повторная сверка выполнена после очистки.
- **22/22 native checks PASS** на staged EXE и **22/22 PASS по каноническому пути**:
  launcher/Pet с restricted PATH; PID+полный image path; frontend; пять разделов;
  сохранённое синтетическое расследование, UTF-8 Canvas и граф; медиа/original viewer;
  настоящий локальный image_metadata и полный source SHA; Gansar/Maigret availability;
  обычное закрытие и restart/persistence. Рабочий пользовательский профиль не открывался.
- **37 focused lifecycle/policy/secret-pattern tests PASS**. Полный старый backend
  suite в этой очистке не выдаётся за повторённый. Новые сетевые OSINT запросы и
  model inference не запускались. Первый тестовый сценарий требовал исправления
  порядка overlay/DOM ожиданий и чтения full source; неуспешный кандидат не устанавливался.
- `build.ps1` / `scripts/build_release.py` оставляют только `dist/Granger-OSINT.exe`.
  Stage/work/cache и isolated QA имеют finally/TemporaryDirectory cleanup, включая
  ошибки и KeyboardInterrupt. Запущенный canonical EXE не перезаписывается и не убивается.
  Оба spec запрещают прямой непроверенный выпуск в dist.
- Старый package_release ведёт в этот же процесс; прежние one-off baseline/export
  entrypoints остановлены до побочных записей. pytest не хранит cache/старые tmp_path;
  настройки/lock-файлы проекта сохранены. GitHub CI имеет явно ограниченную проверку
  registry при отсутствии внешних runtimes; обычная локальная сборка остаётся строгой.
  Сам GitHub CI в этой задаче не запускался.

Финально: один канонический EXE; build/stage/QA/cache directories и старых Granger
release archives нет. Файлов с отказом удаления нет. Препятствий нет; перечисленные
небольшие исключения сохранены намеренно. Приложение после проверок штатно закрыто.
