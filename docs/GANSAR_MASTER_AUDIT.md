# Gansar: фактические функции и граница интеграции

Аудит исходников на HEAD `2caceea93bed4fffcfcca9a7e353007197e5f1f6`.

Измеренные сетевые результаты и ограничения: [MASTER_FIX_VERIFICATION.md](MASTER_FIX_VERIFICATION.md).

## Матрица интеграции и доказательств

«Гермиона: доступно» означает зарегистрированную строго типизированную операцию,
а не live-проверку каждой возможной сети/провайдера через LLM. GUI-проверки ниже
отдельно ограничены фактически показанными сущностями. Все операции используют
один существующий инструмент и изолированный runtime, без нового Gansar UI.

| Function | Original Gansar module | Supported networks | Integration method | Dependencies | Live tested | Hermione accessible | GUI verified | Limitations |
|---|---|---|---|---|---|---|---|---|
| Account/profile | aggregator.analyzer |11 | profile → protected AddressReport | existing pydantic/httpx runtime |11, partial | да, profile | TON | разные глубина/источники |
| Native balance | sources/*, models.report.Balance |11 | exact decimal findings | existing runtime |11 | да, balances/cached | TON | неизвестное не0 |
| Tokens | ton_tonapi, eth*, bsc, tron*, solana | покрытие источников | TokenHolding → token_asset | existing runtime | TON/ETH/Tron/Solana | да, assets | TON | current/historical/metadata различаются |
| Financial history | financial_operations, event_identity, sources/* |11 с разным покрытием | transactions → qualified events | existing runtime | BTC/DOGE/ETH/Optimism/Tron/TON/Solana | да | TON transfers/inspector | полная история не гарантируется |
| Counterparties | aggregator.analyzer, counterparty_ranking | по наблюдаемым tx | scoped address nodes | existing runtime | UTXO/EVM/TON/Tron | да, trace/profile | TON | нет утверждения общего владельца |
| NFT inventory | ton_nft.service | TON | nft wallet/item/collection/auto | sqlite in temporary cwd | wallet6 items, domain item | да, nft | NFT node/image | другой сети full NFT engine нет |
| NFT owners/collection | ton_nft.protocol/providers | TON | actual projected observations | existing runtime | wallet/item/domain | да, nft | source-scoped asset/collection | сбор не доказывает полноту владельцев |
| NFT events/market | ton_nft.analytics/service | TON | event semantics + complete protected DTO | existing runtime | wallet/domain events | да, nft/transactions | evidence | sale price ≠ NFT quantity |
| NFT cursors/resume | ton_nft.service._resume_report | TON | saved typed report → resumed engine | protected Granger store | реальное восстановление/повтор | да при продолжении | protected checkpoint path | private vendor DB не используется |
| ENS | sources.ethereum_ens | ETH | identity; resolver/block provenance | ens-normalize in runtime | vitalik.eth,48 HTTP200 | да, identity | typed graph contract; chat QA отдельно | reverse требует forward check |
| TON DNS | ton_nft.discovery | TON | exact domain → NFT | existing runtime | foundation.ton | да | asset/evidence projection | NFT owner ≠ доказанный человек |
| Lens/Basenames/EAS | web3_identity, basenames, eas_public | ETH/Base context | identity/source-scoped claims | existing runtime | profile probes; отдельные claims не гарантированы | да | typed Web3 graph, unit contract | Base не финансовая12-я сеть |
| Contract metadata/code | attribution.network, evm_rpc |6 EVM/Tron context | contracts → contract_observation | RPC/Sourcify/provider availability | ETH USDT,1 observation | да | graph contract | verification ≠ ownership |
| Labels/public datasets | attribution.datasets, engine | поддержанные сети | labels/attribution, bundled snapshot | bundled licensed public data | labels in TON/ETH/BSC/Tron | да | labels/evidence | private datasets не читаются |
| Behavioral/timeline/migration | fingerprints, wallet_timeline, inference | по исходному коду | bounded analysis findings + full DTO | existing runtime | analyzer reports | да, attribution | hypotheses/evidence | объяснимые гипотезы, не личность |
| Multi-hop frontier | attribution.investigation_planner | compatible history collectors | trace with time/request/depth budgets | existing runtime | selected TON operation | да, selected focus | same investigation graph | key-only providers недоступны без ключей |
| Media URLs | ton_nft models/providers, metadata | TON и фактические public records | evidence-bound Granger MediaStore | existing Pillow/httpx | actual Fragment WebP | URL metadata, без отправки пикселей LLM | decoded local preview/inspector | robots/SSRF/MIME/размер;404 сохранён |
| Exported raw dossier | models.report |11 | encrypted local storage | existing DPAPI/portable vault | save/load/cache restore | cached sections | source inspector/provenance |16 МБ budget, не vendor DB export |

Готовый GUI/exporter самого Gansar намеренно не запускается: пользователь просил
сохранить существующий интерфейс Granger. Private datasets, original searches,
cookies и keyed provider sessions исключены. Они не считаются интегрированными
или протестированными за счёт наличия файлов в другом проекте.
Оригинал: `C:/Users/Admin/Desktop/crypto_osint`, чистый git status.
121 Python-модуль побайтово совпадает с локальным `Gansar-main` Granger.
Исходники Gansar не изменяются и не публикуются этим заданием. Базы SQLite,
captures, `.search_sessions`, production output и приватные snapshots в Granger
не копируются. Ниже состояние **по коду**; колонки live/GUI заполняются отдельными
фактическими прогонами, не выводятся из наличия класса.

## Сети

`app/models/report.py:Chain` содержит ровно11 сетей. Base используется для
Basenames как контекст8453, а не как двенадцатая сеть финансового анализа.
Одинаковый0x-формат означает неоднозначность EVM, не существование баланса везде.

| Сеть | Модули источников | Реализованные операции | Ограничения |
|---|---|---|---|
| BTC | bitcoin_mempool, bitcoin_blockstream, blockcypher | balance, UTXO/history, точные детали | pagination/общие квоты; суммы UTXO не переносятся в EVM |
| DOGE | dogecoin, blockcypher | balance, history, UTXO, stats | Blockchair/SoChain/OKLink/Bitquery/GetBlock имеют разные условия; некоторые требуют ключ/узел |
| ETH | eth, ethereum_*, evm_rpc, evm_blockscout | RPC state, history, tokens/NFT transfers, ENS | Etherscan может требовать ключ; Ethplorer freekey/Blockscout зависят от публичного доступа |
| BSC | bsc, evm_rpc, evm_scans_html | native state, BEP20/NFT, approvals, metadata | Bscscan V2 требует ключ; публичный enrichment имеет отдельные ограничения |
| Polygon | evm_rpc, evm_scans_html | balance/nonce/code, доступные explorer/API observations | история не выводится из наличия RPC state; explorer может блокировать |
| Arbitrum | evm_rpc, evm_scans_html | balance/nonce/code, explorer/API observations | история/токены зависят от конкретного источника/ключа |
| Optimism | evm_rpc, evm_blockscout, evm_scans_html | RPC state, indexed history/transfer context | legacy Blockscout migration/quotas могут ограничивать доступ |
| Avalanche | evm_rpc | native state, code, contract observations | нет автоматической гарантии полной истории/NFT inventory |
| Tron | tron_tronscan, tron_trongrid, tron | balance, TRC20, resources, tx, metadata/contracts | разные семантики событий; rate limits; optional keys |
| TON | ton_tonapi, ton_toncenter*, ton_public_pages, ton_nft | native/Jetton/NFT, history, DNS/collectibles, owners/get methods | публичные TonAPI/Toncenter gates,429, explorer restrictions; Tonconsole opt-in key |
| Solana | solana | balance/account info, signatures/decoded tx, token accounts | public RPC limits; недоступный Solscan API не считается успешной заменой |

## Функции и метод подключения

Общий способ — существующий изолированный headless worker, без Gansar GUI,
браузера, сервиса или изменения основного Python. Прямые vendor imports остаются
в дочернем процессе с временным cwd. В Granger переносятся typed observations,
не HTML-отчёты и не сырая консоль. pydantic/httpx и существующие зависимости
из `.toolenvs/blockchain` используются повторно; новые модельные файлы не нужны.

| Функция | Оригинальный модуль | Сети | Граница/зависимости | Состояние исходного кода |
|---|---|---|---|---|
| Форматы/сеть | utils.detect, utils.ton_normalize |11 | локальная проверка checksum/формата | реализовано; EVM неоднозначен |
| Account/profile | aggregator.analyzer, models.report |11 | bounded analyze_address | реализовано; прежний bridge обрезал поля |
| Native balance | sources/*, Balance |11 | Decimal/base units, timestamp/source | реализовано по источникам; unknown не0 |
| Tokens/Jettons | sources/ton_tonapi, tron*, bsc, solana, ethereum_ethplorer | часть сетей | TokenHolding/provenance | реализовано, current/historical/metadata различаются |
| Native/transfers | sources/*, financial_operations, utils.event_identity |11 с разным покрытием | Transaction/event ID, asset-qualified Decimal | реализовано; один hash может содержать несколько разных действий |
| Контрагенты/ранги | aggregator.analyzer._build_counterparties/_build_counterparty_ranking |11 | только реально наблюдаемые участники | реализовано, личность не утверждается |
| NFT wallet/item/collection | ton_nft.service.investigate_ton_nft | TON | отдельные бюджеты/пагинация; собственный временный store | реализовано; отсутствовало в старом Granger bridge |
| NFT owners/collection/get methods | ton_nft.protocol/providers/service | TON | on-chain getter vs indexer assertion, freshness | реализовано; неподтверждённый индексер не подтверждает owner |
| NFT transfer/sale/listing | ton_nft.analytics, models, service | TON | evidence/coverage/asset-qualified events | реализовано; история может быть частичной |
| NFT/collection media URLs | ton_nft.models, utils.ton_assets | TON; token metadata elsewhere | URL + evidence; загрузка отдельно через политику Granger | реальные metadata, не гарантированная подлинность |
| ENS forward/reverse | sources.ethereum_ens | ETH | snapshot block, resolver, forward check, ens-normalize | реализовано; reverse не принят без forward check |
| TON DNS/collectible names | ton_nft.discovery/protocol/providers | TON | exact domain→NFT; NFT owner/record отдельно | реализовано; `.ton` ошибочно отвергался Granger router |
| Lens | sources.web3_identity | EVM target context | публичные exact roles/records | реализовано; self-published claim не личность |
| Basenames | sources.basenames | EVM target, Base8453 context | primary/forward checks, профили | реализовано; не добавляет Base financial rows |
| EAS | sources.eas_public | ETH | author/recipient/schema, revoked/expiry | реализовано; attestation не подтверждает личность |
| Verified contracts | attribution.network, sources.evm_rpc |6 EVM + Tron context | Sourcify compilation/deployer/proxy observations | реализовано; code verification не ownership/service identity |
| Labels/offline public datasets | attribution.datasets, ton_attribution |11 | bundled public snapshots; без автоматического refresh | реализовано; локальные production datasets не переносятся |
| Service/attribution relations | attribution.engine/models, ton_attribution.relationships |11 | source scoped evidence, contradicting claims | реализовано; не следует распространять labels по соседям |
| Behavioral/application heuristics | attribution.wallet_application, *_fingerprints, inference | UTXO/EVM/TON/Tron/Solana по коду | объяснимые гипотезы и ограничения | реализовано; не вероятности и не идентификация приложения/человека |
| Bounded multi-hop frontier | attribution.investigation_planner | поддержанные history sources | max neighbors/HTTP/time/cursors | реализовано; нужно связать с общим бюджетом Granger |
| Asset paths/timeline/activity | aggregator.analyzer, financial_operations |11 | evidence-preserving projections | реализовано; путь не выделение конкретных взаимозаменяемых средств |
| Price fields | ton_nft.analytics.money_from_price, token/NFT provider metadata | источники, которые дают котировку | source currency/time отдельны от количества | нет универсального достоверного USD pricing engine; цену не придумывать |
| Checkpoints/caches | ton_nft.storage, utils.public_history_cache, utils.http | соответствующие pipelines | приватные состояния через защиту Granger | реализовано; текущие balances/ownership не выдаются из historical cache за свежие |
| Graph payload | graph.builder/nft_builder |11 | преобразование отношений, не замена Canvas2D | реализовано; адаптировать типы/evidence к существующей модели Granger |

Проверка зависимостей импорта прежнего worker уже проходит; это **readiness**,
не реальные запросы к каждому провайдеру. Названия sources/capabilities в registry
сопоставлены с конкретными классами/методами и полями AddressReport. Полная
AST-инвентаризация функций/классов/полей и SHA-256 находится в приватном локальном
`output/masterfix/baseline.json`; исходные файлы и datasets там не дублируются.

## Явные исключения

- HTML/PDF exporters, CLI/GUI Gansar не подменяют Qt/React Granger и не запускаются
  как отдельное обязательное приложение.
- Private production databases/captures/history не импортируются в Granger и Git.
- Опциональные local-node/key-only skeletons не объявляются keyless-источниками.
- Не добавляются вымышленные12-я сеть Base financial, глобальный NFT name search,
  универсальная цена/USD, подтверждение человека по nickname или reverse name.
- Модули с отсутствующей реализацией/неточным покрытием остаются отмеченными
  unavailable/unsupported, а не фиктивно успешными. Итоговые live/Hermione/GUI
  статусы будут дописаны по фактическим проверкам текущей интеграции.
