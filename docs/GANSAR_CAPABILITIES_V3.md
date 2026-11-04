# Gansar: фактические возможности установленного движка (V3)

Дата аудита: 2026-11-04. Проверен существующий `Gansar-main`, не новый коллектор.
Исходники Gansar не изменены. Таблица описывает реализованный код, а не успешный
сетевой ответ провайдера. Результаты live-проверок приводятся отдельно в отчёте
выпуска: импорт, проверка формата и fixture не считаются live-проверкой.

## Матрица сетей

Источник истины — `app/aggregator/analyzer.py` (выбор коллекторов около строк
3185–3250, UTXO fallback около 3635), `app/attribution/normalize.py`,
`app/utils/detect.py`, конкретные `app/sources/*` и
`grangerpet/engine/blockchain_runner.py`. В установленном наборе **11 сетей**.
Одинаковый EVM-адрес в разных сетях — разные сущности.

| Сеть / ID | Действительные источники | Фактические данные | Зависимости и ограничения |
|---|---|---|---|
| Bitcoin (`btc`) | Blockstream, mempool.space; BlockCypher при отсутствии истории | Native BTC, UTXO/история адреса, наблюдаемые контрагенты | Публичные quotas/429; ограниченная выборка. Нет token/NFT inventory |
| Dogecoin (`doge`) | Blockchair; BlockCypher fallback; опционально SoChain/OKLink | Native DOGE, UTXO/история адреса | SoChain/OKLink требуют ключи. Dogechain — HTML/ссылка без structured parser. Core RPC проверяет узел, не обещает address index. Bitquery/GetBlock — явно недоступные skeletons, даже при наличии ключа |
| Ethereum (`eth`, 1) | RPC, Etherscan V2, Blockscout, Blockchair, Ethplorer, labels/HTML | Баланс/nonce/code; индексированная история, token/NFT transfer observations, ENS/public context | Etherscan требует ключ. История/токены зависят от ответившего источника. Transfer observations не являются полной NFT-инвентаризацией |
| BNB Smart Chain (`bsc`, 56) | BSC RPC, BscScan, BscIntel, BscScan HTML | Native state, ограниченные BEP20/NFT события, approvals/contract observations | BscScan требует ключ, публичный enrichment/log scan ограничен. Полной NFT-инвентаризации нет |
| Polygon (`polygon`, 137) | RPC, PolygonScan HTML, Etherscan V2 | Баланс/nonce/code; доступные explorer/API observations | RPC state не перечисляет историю. API требует ключ; HTML может блокироваться. Полной NFT-инвентаризации нет |
| Arbitrum One (`arbitrum`, 42161) | RPC, Arbiscan HTML, Etherscan V2 | Баланс/nonce/code; доступные explorer/API observations | Аналогичные границы RPC/ключа/HTML. Полной NFT-инвентаризации нет |
| Optimism (`optimism`, 10) | RPC, Blockscout, explorer HTML, Etherscan V2 | Native state и индексированные history/transfer observations | Доступность и quotas индексера; Etherscan требует ключ. Полной NFT-инвентаризации нет |
| Avalanche C-Chain (`avalanche`, 43114) | Avalanche RPC, Etherscan V2 | Native balance/nonce/code, публичные contract observations; индексированные API observations при ответе | Один RPC не даёт полную историю, API требует ключ. Полной NFT-инвентаризации нет |
| Tron (`tron`) | TronScan, TronGrid, TronContractEvidenceSource | TRX, TRC20, resources, transfer/event semantics, contract metadata | Public quotas, optional provider keys, несколько форматов событий. Полной NFT-инвентаризации нет |
| TON (`ton`) | TonAPI, Tonviewer; Toncenter/V3 и public fallback; отдельный оригинальный TON NFT service | TON/Jetton, history, NFT wallet/item/collection, точные DNS/collectible identifiers, owners/get methods, transfer/sale/listing | Mainnet; public gates/429; metadata не доказывает подлинность, индексер не заменяет свежую on-chain ownership-проверку |
| Solana (`solana`) | Solana RPC; Solscan explorer context | SOL/account state, signatures/decoded transactions, SPL accounts, отдельные NFT observations | RPC quotas/pruning. Solscan, вернувший ошибку, не считается успешной заменой. Отдельной полной NFT-инвентаризации нет |

Для EVM дополнительно подключаются реальные `VerifiedContractSource` и
`WormholeExecutionEvidenceSource`. Wormhole сохраняет exact protocol evidence,
не синтезирует финансовый перевод. Lens/Basenames — target-only public context;
EAS — Ethereum attestations. **Basenames/Base 8453 context не означает поддержку
двенадцатой финансовой сети Base**. Sourcify/code verification не устанавливает
человека, оператора или владельца адреса.

## Операции и типы цели

`grangerpet/crypto_targets.py` выдаёт сериализуемую матрицу и формальную
совместимость до запуска worker. Общие операции: `profile`, `balances`, `assets`,
`transactions`, `labels`, `attribution`, `trace`, `cached`. Общая операция
`assets` может вернуть только native balance; она не обещает токены для UTXO.
`trace` ограничен бюджетом и реально полученными history rows, не полная история.

| Дополнительная операция | Реальная граница |
|---|---|
| `nft` | Полная специализированная инвентаризация только TON; на других сетях не предлагается |
| `contracts` | Шесть EVM-сетей и Tron; фактические публичные contract observations |
| `identity` | EVM/ENS public Ethereum identity context; не подтверждение личности и не перенос владельца между сетями |
| `.eth` | Отложенное ENS resolution; financial address используется только после подтверждённого forward resolution |
| `.ton`, exact collectible/NFT reference | TON service. Имя, подарок, публичная страница и NFT contract — различные сущности; reference не становится подтверждённым wallet address |

Wallet/contract/NFT-узел передаёт только `address`, `contract` или `asset_id`.
Коллекция использует свой `collection` contract. `target_address` владельца и
отображаемый `label` не подставляются вместо контракта. IP, обычный username,
person и transaction hash несовместимы с address API. История конкретного hash
не симулируется вызовом wallet endpoint.

Формат `0x` даёт шесть возможных сетей: явный выбор обязателен. Bitcoin проверяет
Base58Check и BIP-173/350, Dogecoin/Tron — Base58Check с правильной версией и
длиной, TON — raw/CRC16 с сохранением test-only, Solana — Base58 public key
длиной 32 байта. EVM проверяет 20-байтовый hex-формат; наличие аккаунта и EIP-55
checksum не утверждаются. TON test-only не выполняется через mainnet providers.

`identity_key = chain + '|' + canonical_address` совпадает с действующей моделью
wallet-узлов. Разные EVM chain IDs не сливаются. TON raw/bounceable/non-bounceable
совпадают в mainnet-домене; test-only отдельно. Bitcoin Bech32 upper/lower
совпадают, case-sensitive Base58 сохраняется. Для deferred name/reference
используется отдельное пространство ключа, без утверждения resolved ownership.

## Существующая агрегация и граф

Новая evidence-система не создаётся. `blockchain_rows.normalize_dossier` сохраняет
типизированные наблюдения и provenance, полный DTO — существующий dossier store.
`blockchain_analytics.analyze_transactions` считает полученную выборку через
Decimal; `evidence_graph.build(full=True)` уже создаёт wallet-to-wallet
`transfers` с отдельными network+asset/contract, count, amount coverage,
first/last time, transaction IDs, evidence IDs и source URLs.

Нативная монета, одинаковые ticker разных контрактов и разные сети не суммируются
в одну величину. Неизвестная сумма не превращается в ноль. Failed/reverted/aborted
events не входят в объём. Повторные observations одного события не становятся
повторными платежами. USD-оценка не выдумывается.

Wallet-centric вид — проекция этих же сущностей и агрегатных рёбер. Источники,
транзакции и NFT/details остаются в общей evidence/inspector-модели, а отображение
всех промежуточных узлов на полотне включается отдельно. Скрытие узла из текущей
проекции не удаляет доказательство.

## Проверки

`tests/test_crypto_targets.py` проверяет все 11 форматов/chain IDs, EVM ambiguity,
ошибочные checksum/сети/test-only, неизменяемость входных arguments, машинные
атрибуты вместо label, TON aliases, разделение EVM networks, совпадение ID с
импортированными wallet-узлами, а также существующий Decimal graph aggregate на
Bitcoin uppercase/lowercase Bech32. Эти проверки offline и не подтверждают
доступность конкретного upstream. Vendor и пользовательские данные не меняются.

### Реальные source-проверки 2026-11-04

Через существующий production registry → isolated worker, отдельные QA APPDATA,
без ключей и mock, режим quick. Все три результата **partial**, не полная история.
Локальные receipts: `output/master-fix-v3/gansar-live/{btc,tron,solana}/report.json`.

| Сеть / публичная контрольная цель | Время | Наблюдения | Реальные HTTP / ограничение |
|---|---|---|---|
| BTC / genesis address `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` | 14.900 s | 135 findings; 50 transaction rows, balance, 74 vendor counterparties | 16 запросов, 2 провайдера; HTTP 200 ×12, 400 ×1, остальные без HTTP response |
| Tron / USDT contract `TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj` | 14.046 s | 168 findings; 82 transaction observations, 5 token assets, balance, 69 counterparties | 11 HTTP 200, 3 провайдера; contract metadata collector сообщил error, retained как error |
| Solana / system program `11111111111111111111111111111111` | 14.366 s | 1105 findings; balance, 1102 token observations, analytics; transaction rows не получены | 15 запросов, HTTP 200 ×14, 429 ×1; Retry-After 10; Solscan skipped |

Загрузка существующего защищённого dossier новым registry сработала для всех
трёх целей без сети (185 / 216 / 1104 rows, `from_saved_data=true`, 0 providers,
0 HTTP). Это проверка cache round-trip, не свежести данных.

BTC source DTO сохраняет UTXO `inputs[]`/`outputs[]`, направление относительно
target и Decimal amount; попарные `from_address`/`to_address` в контрольной
выборке отсутствуют. Поэтому текущий shared graph не создаёт для неё финансовые
wallet-to-wallet aggregates и analytics не приписывает peer volume. Это явное
ограничение проекции UTXO, а не отсутствие транзакций. Полная исходная структура
сохранена; many-input/many-output суммы не распределяются по выдуманным парам.

Явные native `blockchain_counterparty` observations теперь связывают root с peer
отдельным **ненаправленным** `source_reports_counterparty`: count, first/last,
исходные evidence/provenance. Это сообщение источника о контрагенте,
`financial_transfer=false`, `owner_verified=false`, без amount/aggregate и без
утверждения отправителя/получателя. Повторные source claims не суммируются:
показан maximum reported count с сохранением отдельных claims. Одинаковые
адреса/отношения в разных сетях имеют разные ID. Финансовые `transfers` и их
Decimal-агрегация остаются отдельным прежним видом связи.

Нормализованная projection ограничена 2000 observations на ответ и выбранным
`max_transactions` режима. Внутри этого бюджета summary/analytics сохраняются
первыми, остальные категории выбираются по кругу: большой список токенов больше
не вытесняет весь раздел переводов/балансов/контрагентов. Summary содержит
`projection.available_counts`, `emitted_counts`, `omitted_counts`, `truncated`,
наблюдаемое и выбранное количество транзакций и доступные сохранённые разделы.
Полный DTO остаётся в защищённом dossier; cached section выбирает отдельный
раздел без сетевого запроса. Это явное ограничение проекции, не обещание показать
все данные в одном полотне; предел полотна 5000 узлов также остаётся явным.

`scripts/qa_canvas_stress.py --observed-result <result.json>` отдельно от
synthetic fixtures строит wallet projection реальных сохранённых records,
фиксирует SHA исходного receipt и evidence и не делает сетевых запросов.
Aggregate edge раскрывается там, где есть pairwise observations; иначе
проверяется реальный режим транзакций. Native paint/latency/resource measurements
записываются только после фактического запуска GUI; unit-тесты подготовки seed
не считаются native acceptance.
