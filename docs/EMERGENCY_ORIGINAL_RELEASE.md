# Исходная Гермиона — восстановление и предметные анимации

Историческая сборка `ba6de760`. Восстановление идентичности остаётся основой
текущего renderer; телефонная постановка и её старые клипы заменены отдельной
[исправленной сценой](PHONE_SOLVNOX_FIX.md). Показатели ниже относятся к прежнему EXE.

1 ноября 2026. Исходная Гермиона восстановлена; проверенный EXE установлен в
`dist/Granger-OSINT.exe`, существующий desktop shortcut сохранён.
История этапов и отклонённых кандидатов — [EMERGENCY_CHARACTER_RESTORATION.md](EMERGENCY_CHARACTER_RESTORATION.md).

## A. Восстановление

Исторический источник — `1b75ee99ef5329880048287f962e7b00684346b2`.
Он выбран по совпадению пользовательского reference, master, семи atlas и
provenance, а не по дате. Эти 12 файлов уже сохраняли исходные bytes; регрессия
была в активном renderer. Исходный head layer подтверждён отдельно по `a3d0ccb`.
Весь проект не откатывался, `git reset --hard` не применялся.

| Эталон | Совпавший SHA-256 |
|---|---|
| `character.png` и `base-512.png` | `78da6453cb337f3e780523c5aa7c74c50156808173f3ca45bb0292fd3dd5d74b` |
| Пользовательский `reference.png` | `6cdebad01e0e85c0381efcbf931b1908eb054fcd9eed9dbd5a6303a9a8d19520` |
| Исторический `hermione-head.png` | `aefca77b6dad974687280d6e49969e6a1fd19380c63140ef3d85381945d2ed4b` |

Все 13 checksums перечислены в
[`identity.json`](../grangerpet/assets/original-hermione/identity.json).
Сохранены master, 249 кадров семи atlas, исходные neutral face/чёлка/волосы,
нейтральный рот, палитра, одежда и размеры. 512px neutral воспроизводит исторический
`Rig.posed('idle',0)`; 256px neutral совпадает с оригинальным atlas frame0.
Сравнение production renderer: **0 изменённых pixel/alpha values**.

`original_identity.py` проверяет пакетные оригиналы. Генераторы atlas/scene
layers теперь по умолчанию пишут отдельно в `output/derived-character` и
отказываются перезаписывать исходные каталоги. При запуске ничего не генерируется.
Исторический generator сохранён как текст для воспроизведения и аудита.
ImageGen для этой работы не использовался.

## B. Глаза и лицо

Прежний `articulated.py` перекрывал исходные глаза и нейтральный рот, а также
собирал локоны из несовместимых слоёв. Отклонённый незакоммиченный `face_rig.py`
во время предшествующей попытки добавил собственные открытые глаза; он не
попадал в опубликованный EXE. Эксперименты сохранены локально и убраны из runtime.

Теперь `original_face.py` возвращает исходную голову для neutral без наложений.
Двигаются только небольшие участки зрачков внутри фиксированной геометрии глаз.
Белки, ресницы, размеры и расстояние между глазами не перемещаются.
Закрытые веки получены из исторического helper, после blink возвращаются точные
исходные pixels. Лицо и голова имеют один transform parent.

У исходного PNG даже внутри лица alpha равен 253–254. Повторный SourceOver
увеличивал его плотность. Теперь небольшой facial patch вставляется один раз,
с буквальным сохранением исходного alpha; вторая голова поверх первой не рисуется.
Каждый facial component хранит не более 16 маленьких patches и одного последнего
512px head frame. Mouth/brow variants используют прежние совместимые paths.

Отдельный `original-motion-v1/head.png` разделяет полный исходный hair silhouette
для движения, исключая выступающий фрагмент палочки из старого mask. Лицо и
чёлка вставлены буквальными bytes исходного head. На месте закрытой палочкой
малой области используется прежняя локальная repair; новая причёска не рисовалась.

## C. Руки и контакты

В `original-motion-v1` отдельно выделены исходные sleeve/hand layers.
Плечо → локоть → кисть исходной позы:

- слева `(171,293) → (157,335) → (132,294)`;
- справа `(281,294) → (327,338) → (365,364)`.

`solo_sequence.py` начинает и заканчивает сцены этой позой. Перед книгой,
телефоном и жестами палочка опускается в карман; в конце восстанавливается
исходный idle, в котором она уже в руке. Это явное движение, без исчезновения
в воздухе и без crossfade двух фигурок. Производные sleeves для чтения,
страницы, щеки, подбородка, скрещённых рук и бедра используют отдельные конечности;
исходные руки под ними не остаются.

`painted_arms.py` связывает манжету, кисть и prop anchors. Указательный/щипковый
контакт рассчитывается аналитически: прежняя fixed-point итерация ошибалась
у короткого предплечья рядом с уменьшенным телефоном. Page corner и painter
используют одну book projection. У телефона палец со стороны скрытого экрана
не перерисовывается поверх задней крышки. Диагностика без реквизита сохраняет
те же hand modes, скрывая только предмет.

## D. Анимации

- **Чтение:** доставание закрытой книги, подхват, открытие, наклонённые к Гермионе
  страницы, опущенные голова/взгляд, scans, освобождение правой руки, pinch-page
  turn, возврат хвата, закрытие, карман. Три варианта реакции. Mouth — прежний
  thinking path. Встроенное чтение гостевых сцен сохраняет прежний rest contract.
- **Телефон:** небольшая задняя крышка и край к зрителю, экран к Гермионе;
  чтение, несколько касаний, пауза, отдельное backspace-нажатие, частичное удаление
  `3→1`, повторный набор `1→3`, мягкая улыбка/румянец, приближение к груди и карман.
  Это локальные движения, без Telegram, API и отправки сообщений.
- **Палочка:** четыре варианта, связанный хват, участие локтя, эффект на настоящем
  кончике, убирание и возврат к исходному владению палочкой.
- **Смущение/недовольство:** по три варианта, source-compatible лицо и отдельные
  poses рук; сохранены поворот головы, мягкий румянец, жест объяснения и притоп.
- **Задумчивость/мечтательность:** кисть у подбородка, небольшие движения головы,
  возврат к idle. **Idle:** дыхание по исторической механике, неподвижные ступни,
  исходные лицо и одежда. Hover использует ограниченный pupil gaze.

`pet.py` интерполирует единственную articulated pose до точного original idle,
вместо прежнего пропуска перехода из-за палочки. Открытое меню блокирует scheduler
до закрытия. Drag/hover/figure input сохраняют приоритет; `_busy`, набор текста,
работа в приложении и глобальная активность Windows не стали блокировкой жизни.
Новых runtime timers нет. Гостевые рисунки не перерабатывались.

## E. QA

- Финальный backend: **1533 passed, 1 skipped, 32 subtests**, 289.58 s.
  Skip — optional Ollama. Последние 100 связанных проверок пересекаются с этим
  прогоном и не суммируются с ним.
- Identity gate: 13 исходных SHA, точные 256/512 neutral, возврат после blink,
  неизменность alpha/eye contours, неизменность лица/чёлки motion derivative.
- Source diagnostics: 3833 facial cels /17 последовательностей, 512 pose renders
  с предметами и без. Это production components, отдельно от native записи.
- Frozen: **130 модулей, 209 ресурсов**, frontend сохранён побайтно.
- Окончательный EXE: **21 полный native-клип /4754 кадра** — 19 QWidget-записей
  и две guarded compositor-записи поверх настоящего окна с текстом. Фактическая
  частота **23.805–23.817 fps**, исходный порядок/время сохранены.
- Native acceptance: **58/58**, soak **600.01 s**, первые **300 s** — реальный
  набор draft при неизменённых natural deadlines. Естественно появились reading,
  annoyed, shy и Ron note. Все **351/351** соседних видимых наблюдений менялись;
  таймеров всегда **3**. Max status IPC **0.1917 s**, retries **0**.
  Проверены drag up/down, hover interrupt, три native размера, guest input
  transparency, minimize/maximize/close, restart, exit0 и отсутствие orphan процессов.
- Cold smoke с ограниченным `PATH`, пустым отдельным профилем: launcher
  **11.054 s**, pet **12.155 s**, обе поверхности готовы и завершились с exit0.
- Сохранность: **54/54** файла профиля, **4/4** гостевых, **23/23** исходных
  character assets и дополнительный снимок **70/70** art files совпали.
  Более ранняя аномалия одного encrypted dialog остаётся без установленной
  причины; в этой работе он сохранён, откат/расшифровка/публикация не выполнялись.

Standalone195 /native DPR1.25, 20 samples по каждому состоянию, без capture,
сборок и других GUI QA во время измерения:

| Состояние | Render fps | Tick p50/p95, ms | CPU машины | Private commit дерева, MB |
|---|---:|---:|---:|---:|
| idle | 12.014 | 2.230/5.804 | 1.027% | 240.37 |
| reading | 23.831 | 8.184/9.707 | 2.182% | 241.43 |
| phone | 23.842 | 8.295/9.237 | 2.311% | 243.28 |

CPU, где 100% — одно логическое ядро: **12.326/26.184/27.735%**.
В историческом замере `da5c8693…` CPU машины был **0.515/2.700/2.571%**:
idle стал дороже, reading/phone дешевле. Это не заявление об улучшении всех
нагрузок. GPU counters не собирались. После 25 быстрых смен сцен таймеров
осталось 3; private commit **243281920→244342784 bytes** (+1060864).
Метод/полные metrics — [performance.json](validation/emergency-original/performance.json).

[21 полная запись и все native face/frame sheets](validation/emergency-original/EXE_PREVIEWS.md) ·
[точное сравнение](validation/emergency-original/identity-comparison.png) ·
[руки без реквизита/с ним](validation/emergency-original/hands-with-and-without-props.png) ·
[58 native checks](validation/emergency-original/native-acceptance.json).

Ранние неудачные прогоны не скрыты: facial alpha, contact iteration, joint return,
yawn→sleep ожидание, единичный IPC timeout и влияние параллельного GUI QA описаны
в журнале этапов. Финальный soak выполняется одним тестовым приложением.
Все APPDATA/IPC/vault namespaces тестов изолированы от профиля пользователя.

## F. Поставка

Поставлен `dist/Granger-OSINT.exe`:
**278980266 bytes**, SHA-256
`ba6de760a9fffc412cc51913c6e2ed258adb29c737aea9e1d6216392d402deaa`.
Существующий desktop shortcut указывает на этот путь. Предыдущие EXE и source
ZIP сохранены в `dist/archive`. Исходники — `dist/Granger-OSINT-source.zip`;
контрольные суммы и финальный audit receipt находятся рядом с артефактами.

Проверенные этапы опубликованы обычным push в `granger/chibi-reconstruction`:
`7a36ba0`, `5dddc40`, `39ffce2`, `27def32`, `b567ad6`.
Публикация — обычные commits/push, без force. Source/Git/QA/EXE и распакованный
source ZIP проверяются на saved secret values и credential patterns;
результат — `secret-scan.json`/`git-publication.json` в public evidence и dist receipt.

Основные изменённые файлы:

- `grangerpet/original_identity.py`, `scene_art.py`, immutable manifest и
  `scripts/create_wand_animations.py`, `build_pet_scene_assets.py` — identity gate.
- `grangerpet/original_face.py`, `original_idle.py`, `articulated.py` — лицо,
  blink/gaze, исходный idle и общий painter.
- `grangerpet/scene_pose.py`, `solo_sequence.py`, `hermione_actions.py`,
  `painted_arms.py`, отдельные `original-motion-v1` assets — руки/предметные циклы.
- `grangerpet/pet.py` — единичная pose interpolation и menu lifetime guard.
- `tests/test_character_identity.py`, `test_hermione_prop_choreography.py`,
  `test_pet_life.py`, `test_cameo_placement.py`; QA scripts, документы и evidence.

Frontend, OSINT/GEOINT, DeepSeek, Gansar, пользовательские расследования/vault,
гостевые source artwork и настройки Windows не изменялись.

Ограничения: исходный raster master — 512px; другой мониторный DPR не
переключался. DPR 1/1.25/1.5/2 и размеры 100/160/195/256 проверяются direct
renderer plates, native Windows monitor — 1.25. Blink использует две совместимые
cels, чтобы сохранить исходный рисунок. Пиксели волос, закрытые предметом на
исходнике, нельзя получить из невидимого участка: сохранена историческая repair.
Короткие soak/cycle tests не являются многодневной гарантией.
