# Visual GEOINT: конкретный план optional CPU-runtime

Только изолированный каталог Granger, без изменения основного venv, системного
Python, PATH, Windows services, других приложений. Основной EXE не получает
гигабайты весов. Установка требует отдельного явного согласия пользователя.

## Зафиксированные источники

- GeoCLIP1.3.0, официальный upstream commit
  `5ef9c350fff3be42efbbb6b54537288aeab062c7`, MIT.
  Wheel PyPI SHA-256 `08a93791166a279d52b95c466a952c75f17f654cc61bdf6ab20355325b564dec`,
  40292198 байт; включает официальные headweights/GPS gallery.
- OpenAI CLIP ViT-L/14, HF revision
  `32bd64288804d66eefd0ccbe215aa642df71cc41`, safetensors1710540580 байт,
  SHA-256 `a2bf730a0c7debf160f7a6b50b3aaf3703e7e88ac73de7a314903141db026dcb`.
  Код/веса CLIP опубликованы upstream OpenAI под MIT; модель HF — conversion.
- Waypoint exact upstream commit
  `502318a7da42bdc38af2ad2f87152492dbf9d671`, уже Rust+ONNX/Tauri.
  Старое предположение Electron/PyTorch не переносится в отчёт.
- ONNX models HF revision `af84a8fbf2e7f7fea9beeddb0bf230ba33fca4e2`:
  DINOv2+PLONK_YFCC для coarse samples, DISK+LightGlue для локального matching.
  DINOv2/DISK/LightGlue Apache2.0, PLONK MIT. StreetCLIP/OSV5M(CC BY-NC4)
  исключён из выбранного набора. Mapillary/token и недокументированный GSV
  excluded. Список каждого файла, точный URL/размер/SHA — в manifest.json.

Лицензии кода и весов проверены раздельно. У host-моделей выбранного revision
[явно указаны лицензии каждого ONNX-файла](https://huggingface.co/killameep/waypoint-models/blob/af84a8fbf2e7f7fea9beeddb0bf230ba33fca4e2/README.md).
[DINOv2 original code и weights Apache2](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/README.md#license);
[LightGlue code и pretrained weights Apache2](https://github.com/cvg/LightGlue/blob/5a650c444718caffc2669dc0094cde908f42dd73/README.md#license),
включая выбранный DISK вариант. [PLONK_YFCC model card MIT](https://huggingface.co/nicolas-dufour/PLONK_YFCC/blob/4f358d09938a89ed239a847777729e95c5d187bc/README.md).
Это не распространяется на отдельные Cell-DINO/Xray-DINO, SuperPoint или
StreetCLIP: эти модели отсутствуют в наборе. GeoCLIP heads/gallery входят в
официальный MIT wheel; отдельной ограничительной лицензии весов upstream не
публикует. Данные обучения не копируются в приложение.

Полные исходные тексты лицензий и model cards находятся в
`resources/third-party/visual-models/`; `provenance.json` содержит exact source
commit/revision и SHA каждого текста. Полный аудит двух проектов, dependencies,
inputs/outputs, выбранных/исключённых стадий — `INTEGRATIONS19_VISUAL_AUDIT.json`.
Лицензии всех47 зависимостей также записаны в manifest; оригинальные
`dist-info/licenses` сохраняются при распаковке wheel.

## Объём и ресурсы

- Модели/малые configs: **3125492684 байт** (~3.13GB decimal).
- 47 wheel artifacts Windows CPython3.14 с зафиксированными metadata/SHA:
  **249883088 байт**. Реальную совместимость подтверждает отдельный probe.
- Итого загрузка **3375375772 байт** (~3.38GB decimal /3.14GiB).
- Рекомендуется **8GB свободного диска** для download cache, установки и
  atomic staging. Фактический installedsize измеряется после установки.
- План CPU-only, CUDA не требуется. Предварительная рекомендация RAM6GB;
  реальные peakRAM/loadtime/inference будут измерены. Это ещё не benchmark.
- Главные версии: torch2.15.0, torchvision0.29.2, onnxruntime1.31.1,
  numpy2.5.4, transformers5.22.0, Pillow13.0.0, safetensors0.8.0.
  Metadata resolution47wheels не заменяет installation/clean-start test.

## После согласия

1. Скачать только pinnedwheels/artifacts по whitelist иSHA-256 с boundedresume.
2. Распаковать проверенные wheel-файлы в отдельный `site-packages`, без pip,
   setup scripts, `.pth` и изменения основного окружения. Дочерний процесс
   запускается тем же EXE/CPython3.14 с `--visual-model-worker`; глобальный Python
   для собранного EXE не требуется. В исходном проекте используется текущий
   интерпретатор и тот же worker.
3. Проверить фактические imports/versions/CPUproviders. Отметить installation
   success только после clean start.
4. Запустить штатный GeoCLIP по PILpixels существующего protected attachment.
5. Запустить выбранные ONNXstages Waypoint, без отдельного desktopUI.
6. Проверить 3 разные фотографии (известная Москва/иная страна/недостаточноclues),
   GPScontradiction, cancellation, повторный запуск localcache.
7. Зафиксировать latency/RAM/size и настоящие candidates/scores, не калибровать
   rawscore в проценты достоверности и не обещать конкретный дом/улицу.

Пользователь отдельно подтвердил загрузку и CPU-проверку выбранного набора.
Загрузка выполняется с проверкой размеров и SHA, сетевые обрывы возобновляются.
Пока реальный inference не выполнен, ни установка, ни готовность модели не
объявляются успешными. Итоговые измерения записываются отдельно после запуска.

## Протокол и реализованные стадии

`VisualModelManager` передаёт уже разрешённые приложением bytes изображения
через stdin дочернего процесса. Пути/URL из ответа модели не принимаются.
JSON-операции: `probe`, `geoclip`, `waypoint`, `waypoint_match`. Один запрос
выполняется одновременно; смена компонента перезапускает дочерний процесс,
чтобы полностью освободить native allocator предыдущей тяжёлой модели.
Менеджер завершает весь собственный Windows Job при отмене/тайм-ауте
и выгружает процесс через 20 секунд простоя. В worker CPU ограничен двумя
потоками; для ONNX указан только `CPUExecutionProvider`, исходящие socket
операции дополнительно запрещены Python audit hook.

- `probe` импортирует реальные numpy/torch/torchvision/transformers/GeoCLIP/ORT,
  сверяет версии manifest и исполняет крошечный Identity ONNX на CPU. Это
  проверка runtime, а не успешный inference опубликованной модели.
- `geoclip`: официальный GeoCLIP1.3.0, локальный safetensors CLIP backbone,
  оригинальные headweights и 100K gallery. На вход идут PIL RGB pixels;
  location embeddings вычисляются блоками по1024 и сохраняются в памяти
  worker. Возвращаются top-k координаты gallery, исходные logits и отдельно
  softmax по gallery; оба score некалиброванные.
- `waypoint`: DINOv2 square center crop→336 RGB/ImageNet normalization,
  PLONK_YFCC, исходные 250 шагов float32 sigmoid schedule и
  SplitMix64/Box-Muller seed. DBSCAN/haversine100км повторяет upstream
  min_samples/mean/std/noise. `raw_score` — доля samples в кластере, не
  вероятность правильной геолокации. Если кластеров нет, список predictions
  пуст; исходные samples и noise остаются доступны. Среднее longitude у
  пересечения линии смены дат помечается `dateline_warning`.
- `waypoint_match`: опубликованные DISK-depth и модульные LightGlue ONNX,
  bilinear/16px preprocessing, strict5×5 NMS и исходный adaptive loop.
  CPU-лимит1024 keypoints вместо upstream2048 указан в результате.
  Дополнительная геометрическая проверка — собственный normalized eight-point
  RANSAC/Sampson3px. Это явно отличается от upstream seven-point RANSAC;
  вырожденные/малые наборы не объявляются геометрически подтверждёнными.

Каждый результат содержит `device=cpu`, `duration_ms`, `cached`, версии,
зафиксированные SHA моделей, RSS/peak working set/private memory процесса.
Отдельно измеряются загрузка модели и inference; для Waypoint — загрузка
DINOv2/PLONK, embedding и sampling. Cached load time отмечается нулём.
EXIF/GPS не участвуют в model inference; приложение может анализировать их
отдельно как независимое evidence. Локальное совпадение изображений само по
себе не доказывает место съёмки.

Реализованы именно свободные offline coarse/matching стадии Waypoint.
Автоматический Panoramax/OSM retrieval, оценка солнца и финальное слияние
источников не симулируются worker; их наличие проверяется на уровне текущих
отдельных инструментов Granger. Никакие изображения не загружаются наружу.

## Независимые проверки протокола и математики

`tests/test_visual_worker.py`: **31 passed**, без skipped после появления
optional NumPy/Pillow. Проверяются bounded JSON/base64, запрет сети, отсутствие ML/Qt
при import worker, upstream schedule/confidence constants, статистика RNG,
порядок lat/lon, DBSCAN noise/count/dateline и реальное измерение памяти.
Пять optional проверок покрывают upstream NMS, top-n, preprocessing, удаление
EXIF и синтетическую геометрию. Они не заменяют реальные model fixtures.
Model accuracy, cold/warm latency и RAM остаются pending до benchmark-run.

## Безопасное удаление optional runtime

`remove_runtime(root)` вызывается после native confirmation и закрытия worker.
Допускается только абсолютный exact `default_runtime_root()`, совпадающий
receipt/manifest/packages/artifacts и проверенный wheel cache. Инвентарь
установленных файлов восстанавливается из SHA-проверенных wheel-файлов;
посторонние файлы даже внутри `site-packages`, symlink/junction/reparse
останавливают удаление до первой мутации. Удаляются только собственные файлы
и затем пустые директории; общий recursive delete не применяется.

CLI: `python scripts/setup_visual_runtime.py --remove --confirm-remove`.
Пользовательские данные приложения и основное окружение не входят в runtime.
Если wheel cache изменён/удалён или receipt неизвестен, безопасное удаление
отказывается продолжать. Настоящий установленный runtime при проверках удаления
не трогался: тесты используют только временные каталоги.

`tests/test_visual_installation.py`: **43 passed**, mock HTTP вместо реальных
загрузок. Проверены resume/Range, полная и повреждённая `.part`, retries,
size/hash, redirect whitelist, отмена, ZIP traversal/symlink, purelib/platlib,
пропуск entry scripts, отсутствие выполнения `.pth`, atomic staging/rollback,
строгая принадлежность файлов при удалении и реальные Windows junction fixtures.
