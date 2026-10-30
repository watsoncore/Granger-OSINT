# Master Fix — поиск, Gansar и расширение расследований

Это сохранённый исходный baseline и этап I. Итог текущей поставки:
[MASTER_FIX_RELEASE.md](MASTER_FIX_RELEASE.md).

Исходная точка: `002fc9180f8f8990a2e351f7267e153921000bc2`.
Предыдущий отчёт сохранён в `STABILITY_OVERHAUL.md`; его проверки не заменяют
проверки этого задания. Этапы ниже заполняются по фактическому выполнению.

## I. Воспроизведение и первичный ремонт маршрута

В настоящем EXE SHA256
`3957a014519c6176577a432ccefd971cf2a4483348762ec7bbcc4fae41df9047`
в изолированном профиле нативными вводом/кликом выполнен запрос пользователя
`UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd`.
`output/masterfix/baseline-auto-ton-02/report.json`:25.31с,20 сохранённых в
GUI записей, `completed_with_errors`, «Проверено: 1», пустой investigation ID.
Это успешное воспроизведение проблемы, не успешное глубокое расследование.
Ранний harness ошибочно ожидал `search.kind=blockchain` вместо фактического
значения выбранного UI-режима `auto`; исходный неуспешный отчёт не удалён.

Фактический путь: `Search.tsx` → `desktop_bridge.search_run` →
`OsintPanel.start_search` → `SearchController` → единственный внешний адаптер
`blockchain` → subprocess `engine/worker.py` → `engine/blockchain.py` →
`app.aggregator.analyzer.analyze_address`. `SearchSummary.checked_sources`
и `panel._engine_finished` считали **адаптеры Granger**, не провайдеров,
endpoint-запросы, активы или независимые подтверждения. Поэтому1 не доказывает
ни единственный HTTP-запрос, ни единственный blockchain-источник.

Этот автоматический путь в отличие от существующего `tool_run` не вызывал
`InvestigationWorkspace.manual_result`; данные оставались в Qt result model
без общего checkpoint/graph ID. Literal blockchain-поиск переведён в существующий
инструментальный путь с evidence/journal/graph. Второй агент или второй чат
не создаются. Счётчик адаптеров переименован в однозначную метрику.

Другие подтверждённые ограничения тонкого bridge, ещё требующие следующих этапов:
общий timeout25с, `max_txs` связан с UI-лимитом результатов20, request budget
5–50, фиксированный provider timeout5с, `include_experimental=False`, выдача
обрезается20 строками, теряются многие поля `AddressReport`, отдельный
`ton_nft` engine не вызывается, provider health не доходит при прерывании worker.
Слабость связующего слоя не означает отсутствия этих функций в самом Gansar.

## II. Исходный Gansar: начало read-only аудита

Найден `C:/Users/Admin/Desktop/crypto_osint`, origin
`https://github.com/watsoncore/Gansar.git`, HEAD
`2caceea93bed4fffcfcca9a7e353007197e5f1f6`, рабочая директория чистая.
Инвентаризация AST/хешей:121 Python-модуль. Все121 совпадают с `Gansar-main`
в существующем Granger checkout. Нельзя объяснять проблему выдуманной старой
версией движка. Первичный снимок — `output/masterfix/baseline.json`.
Базы, captures, пользовательские отчёты и credentials исходного Gansar не читались
и не переносились. Исходный репозиторий не изменяется и не публикуется.

`app.models.report.Chain` подтверждает11 сетей:
BTC, DOGE, ETH, BSC, Polygon, Tron, TON, Solana, Arbitrum, Optimism, Avalanche.
Это список форматов/реализаций, ещё **не11 живых успешных сетевых проверок**.
В source registry есть отдельные provider-capabilities, NFT engine,
ENS forward/reverse, Lens/Basenames/EAS и contract observations. Наличие записи
registry не заменяет аудит реализации и реальную проверку каждого направления.

Read-only baseline дополнительно фиксирует SHA-25627 файлов исходного профиля,
receipt уже установленного CPU-runtime и исходный EXE. Секреты в отчёт не попадают.

Следующие обязательные этапы: полная таблица функций Gansar и исключений,
нормализованная интеграция возможностей/диагностики, направления и глубина агента,
читаемость графа, реальные медиа, полный EXE и живые сценарии. Первичный ремонт
маршрута не объявляется выполнением всего задания.
