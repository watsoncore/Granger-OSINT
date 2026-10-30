# Granger-OSINT: итог Master Fix

Готовая сборка: `dist/Granger-OSINT.exe`. Существующие настройки источников и
изолированные runtimes используются на прежнем месте. Это не пакет с моделями
и всеми vendor-репозиториями внутри EXE.

- Размер: **276882699 байт**.
- SHA-256: `f6849c5b1e4a8d3e4d93e616680223cd171e9b3ef3b50fb563521baa68be5be9`.
- Исходники реализации: commit `2282f1f142f1724ff692c2dc0d3fdc91efb7bf57`; последующая публикация
  отчёта и упаковочных файлов не меняет исполняемый код.
- [Функциональный аудит Gansar](GANSAR_MASTER_AUDIT.md).
- [Причины, архитектура, live-матрица и ограничения](MASTER_FIX_VERIFICATION.md).
- [Агрегированный протокол проверки](../output/masterfix/release-public/release-summary.json).

## Поиск до и после

Для указанного в задании TON-адреса исходный EXE показывал20 строк, один адаптер
и не создавал расследование. Исправленный автоматический поиск создаёт общий
checkpoint/граф, возвращает200 строк текущей выдачи и показывает отдельные метрики:
**10 запущенных коллекторов Gansar,54 HTTP-запроса**,48,37 секунды в контрольном
прогоне. Это не10 независимых подтверждений. Нормализованные доказательства
сохраняются отдельно от лимита видимых карточек.

Баланс, токены, NFT/домены, события, контрагенты, Web3 records, контрактные
наблюдения и source diagnostics доступны через один `blockchain_gansar`.
Полный Gansar DTO хранится зашифрованно. NFT pagination/cursors возобновляются
через готовую реализацию Gansar, без чтения оригинальных пользовательских SQLite.

Публичные источники по-прежнему дают403/429/402/500/404 и тайм-ауты. Частичный
результат не переименован в полную проверку. Сводка содержит причины по источникам.

## Гермиона: реально проверенные сценарии

| Сценарий | Проверенный результат |
|---|---|
| TON: активы/tx/NFT/граф | реальные profile/nft/evidence_graph, активы видны в графе |
| ENS/Web3 | реальные identity calls; в финальном адресном тесте нет стартового финансового profile и повторного запуска той же identity-операции |
| Выделенный контрагент | реальный trace по выбранному адресу, прежний investigation_id сохранён |
| Объяснение связи | реальные локальные evidence_get; внешние инструменты не запускаются |
| Сохранённые активы | реальный cached вызов,0 новых HTTP-запросов |
| Продолжение после перезапуска | восстановлен тот же журнал и идентификатор; запросы не стартуют сами |

Полный шестисценарный EXE-прогон:14 проверок. После него внесено адресное
исправление identity-дедупликации и выбора начальной операции; оно отдельно
проверено на конечном EXE —6 проверок. Остальной UI/engine при этой правке не менялся.

**Ограничение модели:** TON и ENS этапы шестисценарного прогона завершились
защитной приостановкой `no_progress`, а не уверенным LLM-заявлением о полном поиске.
Данные, содержательный фактический отчёт и продолжение сохранились. Пустые
результаты одной ветви не исключают ещё не проверенные запросившиеся направления;
повторение исчерпанных операций не означает новые доказательства.

## Отмена, сохранность, запуск

Отмена после реально полученных blockchain-транзакций вернула UI за
**0.437 сек.** Доказательства остались в checkpoint, пережили
фактическое закрытие/повторный запуск EXE и не вызвали автоматический повтор поиска.

Неизменность подтверждена SHA-256: **27 файлов исходного профиля,121 модуль
оригинального Gansar, receipt установленного visual CPU-runtime**. Исходный Gansar
остаётся с чистым git status. Питомец и спрайты не редактировались. Пользовательская
рабочая копия приложения не закрывалась ради smoke-теста.

Конечный EXE прошёл оба настоящих запуска с минимальным PATH: launcher и pet,
реальный React/WebEngine ready, нормальное завершение.105 упакованных Python-
модулей совпадают с выдаваемым исходным кодом;138 проверок упакованных ресурсов
прошли. Временные QA-копии DeepSeek-ключа удалены из Credential Manager.

## Граф и изображения

На конечном EXE:24 нативные проверки graph/tree/evidence, pan/zoom/drag, выбора
узла/связи, фильтров, четырёх тем и восстановления сохранённого вида.
Стресс-набор явно синтетический:1000 основных узлов и5000 отношений; в обзоре
рисуется связный остов999 отношений, остальные раскрываются по выбранному узлу.
Данные не удаляются ради скорости.

В контрольном измерении: раскладка **17.1 мс**, отрисовка
**36.3 мс**. Медианная CPU в короткой выборке1,8 сек. —
**0.82% мощности машины**; пик суммы RSS
наблюдаемых собственных процессов **586.5 МиБ**.
Общие страницы учитываются повторно; это не измерение private working set или
всей Windows. Геомодели при этих blockchain/graph проверках не запускались.

Реальный NFT WebP загружен из наблюдённого metadata URL, проверен backend,
зашифрован и декодирован настоящим frontend как локальное preview. Проверены
инспектор, дерево и evidence; нет внешних HTTP-запросов из renderer и AI-картинок.
Неудачные ранние QA-прогоны сохранены: они выявляли обрывы больших снимков,
лишние UI-перепроверки, aliasing media-state и ошибки координат самого теста.
Их не засчитывали как успех.

Скриншоты конечной/проверяемой сборки:

- [NFT и настоящий инспектор](../output/masterfix/release-public/nft-inspector.png).
- [Дерево по настоящим NFT-наблюдениям](../output/masterfix/release-public/nft-tree.png).
- [Доказательства NFT](../output/masterfix/release-public/nft-evidence.png).
- [Нагрузочный обзор: синтетический набор](../output/masterfix/release-public/graph-stress-synthetic.png).
- [Автоматический TON-поиск](../output/masterfix/release-public/automatic-ton.png).

## Регрессия и поставка

**1336 Python tests passed,2 skipped,32 subtests passed;118 frontend tests passed.**
Live-сеть проверялась отдельно от fixtures. Ни успешный импорт, ни запись в
каталоге инструментов не считаются доказательством работы внешнего провайдера.

В `dist/Granger-OSINT-source.zip` включаются исходники приложения и только
проверенный агрегированный протокол/скриншоты. Checkpoints, история диалогов,
original Gansar datasets, credentials, cookies и тяжёлые модели не публикуются.
Новая сборка использует сохранённый `source_root` и прежние optional runtimes.
После замены EXE уже запущенный старый процесс необходимо перезапустить.

## Изменённые файлы

- `docs/GANSAR_MASTER_AUDIT.md`
- `docs/MASTER_FIX.md`
- `docs/MASTER_FIX_RELEASE.md`
- `docs/MASTER_FIX_VERIFICATION.md`
- `frontend/src/components/InvestigationCanvas.tsx`
- `frontend/src/components/InvestigationWorkspace.tsx`
- `frontend/src/components/Settings.tsx`
- `frontend/src/graph-model.test.ts`
- `frontend/src/graph-model.ts`
- `frontend/src/investigation-graph.css`
- `grangerpet/agent.py`
- `grangerpet/agent_evidence.py`
- `grangerpet/agent_tools.py`
- `grangerpet/app.py`
- `grangerpet/blockchain_store.py`
- `grangerpet/chat.py`
- `grangerpet/config.py`
- `grangerpet/desktop_bridge.py`
- `grangerpet/engine/blockchain.py`
- `grangerpet/engine/blockchain_contracts.py`
- `grangerpet/engine/blockchain_rows.py`
- `grangerpet/engine/blockchain_runner.py`
- `grangerpet/engine/router.py`
- `grangerpet/engine/runtime.py`
- `grangerpet/engine/worker.py`
- `grangerpet/entity_router.py`
- `grangerpet/evidence_graph.py`
- `grangerpet/graph_context.py`
- `grangerpet/investigation.py`
- `grangerpet/investigation_contracts.py`
- `grangerpet/investigation_progress.py`
- `grangerpet/investigation_results.py`
- `grangerpet/ipc.py`
- `grangerpet/link_relevance.py`
- `grangerpet/panel.py`
- `grangerpet/public_media.py`
- `grangerpet/public_sources.py`
- `grangerpet/ui_jobs.py`
- `scripts/audit_masterfix_baseline.py`
- `scripts/audit_masterfix_preservation.py`
- `scripts/package_masterfix_validation.py`
- `scripts/qa_investigation_graph_exe.py`
- `scripts/qa_masterfix_agent_exe.py`
- `scripts/qa_masterfix_blockchain_live.py`
- `scripts/qa_masterfix_matrix.py`
- `scripts/qa_masterfix_media_exe.py`
- `scripts/qa_masterfix_media_live.py`
- `scripts/qa_masterfix_search_exe.py`
- `tests/test_blockchain_dossier.py`
- `tests/test_chat.py`
- `tests/test_desktop_bridge.py`
- `tests/test_investigation_graph_bridge.py`
- `tests/test_ipc.py`
- `tests/test_public_media.py`
- `tests/test_query_router.py`

## Git

- `9b16804`: восстановлен общий путь автоматического поиска и понятная метрика адаптеров.
- `19713e0`: read-only аудит настоящего Gansar.
- `5ce2cef`: структурированные Gansar dossiers, направления, граф и media pipeline.
- `2282f1f`: identity-дедупликация и нативные проверки отмены/медиа.

Для каждого завершённого этапа выполнен обычный push в существующий origin/main,
без force. Финальный commit отчёта и чистота рабочего дерева фиксируются в
публикационном manifest после упаковки.
