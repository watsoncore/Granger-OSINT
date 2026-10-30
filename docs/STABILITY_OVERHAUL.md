# Stability and investigation overhaul — verification record

Work starts from `7a0bb9b` on the existing `main` branch. This report is updated
after measured stages; earlier delivery reports are baseline claims, not new QA.

**Итоговая поставка30 октября2026:** `dist/Granger-OSINT.exe`,276823658 байт,
SHA-256 `3957a014519c6176577a432ccefd971cf2a4483348762ec7bbcc4fae41df9047`.
1316 Python-тестов и118 frontend-тестов прошли. Проверки именно этого EXE:
24 графа,16 восстановления,17 живого pipeline,6 сохранённых реальных
представлений; Launcher/Pet запущены с минимальным PATH.
Частичные результаты и пределы проверок перечислены в заключительном этапе.

## Stage 1 — data contract and restart safety

**Root cause reproduced.** The former `agent_evidence.redact` used one 6,000-node
budget across a whole record. Large `details` exhausted it; a later `provenance`
dictionary became the string `[ограничено]`. `desktop_bridge.source_view` then
called `origin.get('acquisition')` (baseline line 53), raising the reported
`AttributeError: 'str' object has no attribute 'get'`. This happens with a valid
synthetic adapter result, without malformed external JSON. The old public
journal writer applied the same shared budget to a complete snapshot and could
also damage later scalar metadata. Reapplying whole-record redaction during UI
publication repeated the defect. Restoring the persisted report repeated it
after restart.

The latest real report was inspected structurally without exporting its content.
It contained 74 evidence records and 485 executions; one provenance object and
five optional metadata fields were truncated. Its encrypted checkpoint was
intact. Read-only recovery restored the one matching evidence ID from that
validated checkpoint: all 74 records and 485 execution entries are readable.
Original file hashes remained unchanged. No profile, secret or history migration
was performed. The production log directory only contained old logs, so the
traceback above is an exact reproduction against baseline code, not an invented
recent log entry.

**Fix.** Redaction preserves dictionary/list types; evidence identity, metadata,
details and provenance have independent bounds. Explicit evidence, execution,
public journal and private checkpoint contracts run before dereferencing or
replaying saved state. Public recovery isolates invalid rows/optional fields in
memory, preserves good neighbors, and can recover an exact evidence ID from a
fully validated checkpoint. Unknown counters remain unknown, never fabricated
zeros. Invalid private protocol state is rejected before replay. Public saved
`running` state becomes `interrupted` in memory; startup does not resume work.

**Modal spam.** The old global `sys.excepthook` called `QMessageBox.critical` for
every unhandled Qt callback. Publication could repeatedly enter the same broken
snapshot. `errors.ErrorCenter` now fingerprints exception type and stack,
aggregates repeats in one existing non-blocking toast, logs a sanitized stack
once, and cancels affected work. A broken publisher retains the last good view
and does not re-enter until another conversation/investigation is selected.
The file log is explicitly attached even if another dependency configured the
root logger first. Error callbacks do not own or invoke deleted widgets.

**Validation so far.** The focused stage suite passed 114 tests; 33 additional
checkpoint/IPC tests passed. Ten frontend boot/contract tests passed and the
production TypeScript/Vite build passed (existing bundle-size warning remains).
A regression raises the same exception 100 times and checks one notification,
one sanitized log entry, no modal call and a count of 100. The production recovery
check used only structural counts, not a live investigation. Actual EXE/restart
results: **16/16 checks passed** in a real staged Windows EXE, including two
starts with damaged synthetic public/private state, responsive Qt/WebEngine,
one aggregated recovery notice, no automatic resume, rejected invalid checkpoint,
opening another conversation, clean exit and unchanged original fixture hashes.
Staged SHA-256: `6f2326476ee2f61b7b0b9d7e08a622070c91a59a549bfef5fdb9b5d766310492`.
This is a stability-stage build, not the final investigation/graph release.

Release QA now has an explicitly isolated same-user IPC namespace as well as an
isolated encrypted profile. It cannot command or replace an already-running user
instance. No network listener, service, system PATH/Python or external application
is changed.

## Stage 2 — progress, repeat prevention and useful stops

The existing runner treated fresh `empty`/`complete` responses as progress even
without a new fact, and automatically retried failed cached calls after resume.
It now compares semantic resource/content/status/property digests, excluding
timestamps, request wording and derived graph observations. Empty HTTP200 and
the same document fetched through another query do not reset the guard. A real
property change or contradiction does. The threshold is configurable (2–10) in
the existing investigation technical settings. Existing explicit token, step,
tool, time, page, concurrency, context and per-request limits remain effective;
zero retains its documented meaning of no user-selected overall budget.

All cached outcomes survive resume, including 403/timeouts/empty responses.
Conservative argument normalization preserves case-sensitive paths/addresses;
old signatures are re-keyed in memory, without migrating files. Public fallback
no longer invents cross-platform nickname pivots for explicit Telegram, crypto,
photo or URL goals. The useful generic public-mentions fallback is retained.

Every partial/limited/cancelled/error stop creates a bounded report with the
original goal, actual attributed findings, uncertainty, failed directions and
separate counts of executed calls/documents/evidence. It makes no extra provider
request after stop. The report is retained in the protected checkpoint and chat
archive; private goals/protocol are not added to the plaintext public journal.
Provider errors keep their error/retry status, alongside the saved-data report.

The first focused regression suite passed 86 tests. Tests cover distinct empty
queries, identical observations through different acquisitions, new properties,
contradictions, failure-cache resume, scoped fallback, budgets and API failure.
Final integration/EXE checks are performed again after the graph work.

## Stage 3 — tool execution boundary

The real registry previously accepted `results='HTML ERROR'`, `null`, or a list
of strings with `status=complete`, dropped the payload and marked execution
verified. Adapter root/status/results/limitations and each finding are now
validated before acceptance. Invalid data produces `invalid_tool_output` with a
safe field/type diagnostic; valid neighboring records survive as an explicitly
partial outcome. A real complete response with no findings becomes `empty`.
The runner independently validates registry outcomes too, and publishes counts
from the accepted records, not an invalid raw payload.

The existing invocation contract is preserved and enriched with `execution_id`,
`execution_status`, `contract_version` and measured `duration_ms`. Standard status
categories coexist with existing UI-compatible statuses. Failed output cannot
set `execution_verified=true`. No adapters have been removed.

An investigation-scoped decoded-response budget covers repository-owned HTTP
transports (public reader/APIs, passive DNS/network requests, public integrations
and maps). It is shared across parallel public-search tasks, restored with the
checkpoint and configurable in the existing technical settings (default20MiB;
zero disables the chosen byte limit). Cancellation and per-response limits still
apply. A final already-received chunk can cross the budget; further reads/requests
stop. Third-party CLI network traffic is **not** falsely reported as metered;
its existing request/concurrency/time limits remain in effect.

285 focused tests passed, including all48 registered adapters' common status
contract, malformed outputs, partial neighbors, real streamed-byte transport
fixtures, cancellation and browser parsing. TypeScript checks passed. A fresh
read-only local readiness audit found48 registered and44 available with this
profile's settings; this is not48 live successes or a GUI verification claim.

## Stage 4 — deterministic target routing and public Telegram

`entity_router` recognizes literal Telegram/social/GitHub targets, validated TON,
other blockchain candidates, email/phone/domain/IP, coordinates and scoped image
IDs. It keeps platform identities separate and labels unknown Telegram object
type honestly. Invalid TON/testnet/private targets do not fall through into an
unrelated username search. The existing runner performs a bounded primary route
through its normal tool protocol, then offers tools for actually observed linked
objects. The original user URL is now seeded into the existing reader authority
before execution: the missing seed previously blocked legitimate direct reads.

`telegram_public` now defaults to restricted public page/preview HTTP without a
session. A channel type requires an observed preview containing publication URLs.
It uses the same pinned DNS/robots/size/cancel policy. The existing authorized
adapter remains available through explicit `access_mode=authorized` and separate
confirmation; no credentials enter public requests. No new registered adapter or
new session requirement was added. Search routes Telegram/GitHub/IP/coordinates
to the appropriate existing operation, and chat availability questions receive
the actual backend readiness snapshot. Images retain internal capability IDs;
location requests use the available model pipeline, not shell instructions.

Live test of the requested Telegram URL retrieved two public pages and actually
discovered links to `watsoncore/GrangerBrowser` and `watsoncore/Gansar`. Both
repositories returned metadata through the GitHub API. These are **published-link
relationships**, not evidence of a common real-world owner. Names were extracted
from live content, not installed as a fixture or discovery shortcut.

The first bounded real-agent run exposed semantically duplicate calls (name vs
full Telegram URL and ignored singleton limits) and truncated navigation links.
It reached its12-call test budget, so it is not claimed as a completed research
success. Canonical effective arguments and prioritized actual external links
fixed this. A second normal-registry/DeepSeek run **completed in23.4s with5 tool
executions**, checking both discovered repositories. No fake transport or reduced
tool registry was used. A separate real readiness response completed in10.2s
with0 tool executions, correctly distinguishing local readiness from network or
inference verification. Focused routing/controller suites passed277 tests and a
final119-test subset after the canonicalization change.

## Stage 5 — shared results, provenance, graph state and bridge

`investigation_results.project` supplies one dataset for overview, tree, graph
and evidence. It ranks exact targets and actually observed link chains, separates
potential/context-only observations and unrelated background, groups duplicate
resources while retaining every original evidence ID, and exposes separate
call/document/raw-record/evidence/error counters. Source streaming events no
longer become extra execution attempts. Background search hits do not reset the
runner's semantic progress detector and are marked as background in model context.

The existing `evidence_graph` is extended rather than replaced: stable relation
IDs, five verification statuses, original claim kind, literal-link provenance,
Telegram/GitHub display types, root scope, sources and typed geographic hypotheses.
Same-name profiles remain platform-scoped. Blockchain aggregates are directed
and asset-specific, deduplicate transaction events, use Decimal sums and retain
the individual transaction IDs and evidence. Unknown amounts stay unknown.
Full UI snapshots are bounded at5000 nodes/20000 relations and cancellable;
the model-facing operation retains small pages/subgraphs.

The bridge prepares graphs on its existing background job infrastructure and
provides a compact evidence projection, source lookup, selection and encrypted
view persistence. Manual search results use the **same** checkpoint/evidence/cache
format as AgentRunner and can later continue in that runner. No second agent,
chat, graph database or plaintext private-goal store was created. Position/zoom/
filter/selection state is a new encrypted v1 sidecar. Unknown/corrupt view state
is preserved as identical protected bytes before any replacement; rollback bytes
were decrypted/verified in a test. Existing user files are not migrated.

Structured graph followups retain investigation ID, original goal, evidence and
cache. Only12 nodes/24 relations enter the relevant model context. Explain mode
cannot start external network tools, even if the model proposes one; explicit
investigate mode uses the existing registry and approvals. Vault lock clears graph
projections and selection state; jobs follow the existing cancellation lifecycle.

151 core projection/contract/runner tests,106 bridge/regression tests and13
graph bridge/followup tests passed in the focused runs (overlapping suites, not a
sum of unique tests). The live Telegram capture projects to40 entities/41
relations with4 source URLs and5 actual tool calls. **This backend stage alone
is not claimed as completion of the required interactive UI.**

## Stage 6 — interactive Search workspace in the actual executable

Search now contains Overview / Tree / Graph / Evidence over that same projection.
The bundled Canvas2D renderer supports node/edge selection, a provenance inspector,
dragging/pinning, background pan, anchored wheel zoom, fit, filters, node search,
branch expansion/collapse, separate tree coordinates and saved investigation
selection. Evidence uses a virtual list. Layout runs in a bundled module worker;
explicit cancellation terminates that worker and stale replies are ignored.
Small graphs show readable labels; large graphs default to a bounded visible
subset with an explicit expansion control. No animation loop runs while idle.
The four existing palettes and the existing pet/dock remain in use.

Structured graph followups now also bound individual strings/evidence arrays,
omit aggregate transaction-ID collections and enforce an18,000-character
structured envelope. The selected endpoints are preserved. Large selected
wallets cannot silently serialize the whole investigation into model context.
Activity rows carry real call IDs/arguments and result counts, including parallel
calls of the same tool. Search can stop the current existing agent task.

Native own-window mouse/wheel/key events were delivered to the real WebEngine
widget in an isolated QA profile. The final candidate passed20 graph checks,
including **1000 simultaneously rendered nodes /5000 relations**, the actual
bundled worker, drag/pin, wheel, background pan, search, collapse/expand,
virtualized evidence, all four themes and state recovery after a second EXE
launch. Measured initial stress layout22.1ms and paint68.4ms on this machine;
these are observations, not guaranteed frame times. Stress evidence is explicitly
synthetic and is never reported as a real investigation. The full graph includes
additional hidden provenance/domain nodes. The same candidate separately passed
16 corrupt-state/restart checks without rewriting the damaged originals.

118 frontend tests and the production frontend build passed. A full Python run
found four assertions using the former contracts: account-required Telegram,
mandatory arguments for the local graph view, the old hypothesis status, and an
LLM fixture assuming metadata had not already been routed. They were updated to
verify the current contracts; all48 tests in those affected suites passed. Full
suite confirmation and new live EXE scenarios are recorded below when complete.

Candidate: `output/stability/candidate/Granger-OSINT.exe`, SHA-256
`692d9d36ed9de78606d8b737ce1e3ac1a1dbab99f340a81bafe79eff766a1de2`.

## Stage 7 — actual selected-graph analysis, including exhausted research

Live EXE checks exposed an important distinction: a graph action could append a
new local stop report while an exhausted cumulative budget prevented any new
model request. The original permissive check was strengthened to require an
increased successful-provider-request count and a completed new answer. The
earlier incomplete GUI runs are retained as failures, not counted as successes.

An explicit Explain/Compare request now has a small local-analysis phase, at
most3 model turns,6 local operations,24,000 reserved tokens and90 seconds, also
respecting smaller nonzero configured limits. Baselines are validated and
persisted; ordinary resume cannot reset them. Cumulative calls, time, provider
usage and the full protected protocol archive remain intact. This does **not**
renew the budget for external investigation. Investigate continues to use the
original cumulative research budget and existing approvals.

Explain receives selected entities/relations plus up to6 bounded excerpts from
their actual saved evidence, with source URL, tool and acquisition time. The
whole structured envelope remains under18,000 characters. Explain requests have
no tool definitions, so the real provider produces an answer rather than using
the short phase to reread the same records. Compare retains bounded local tools
and a final response opportunity. The live gateway check now proves a **new
model answer**, unchanged investigation ID/goal/cumulative tool count, and no new
external source calls.42 focused runner/context/bridge tests passed after this
last change; the complete suite then passed1315 tests, with1 skip and32 subtests.

The release candidate's100 embedded Python modules and138 resources match the
delivered source/assets. Its actual EXE passed24 native graph checks and16
corrupt-state/restart checks. The24-check graph run adds source-detail opening,
type filters, edge selection, switching saved investigations and orphan-process
checks. Edge hit testing uses a separate small graph in the same renderer; the
1000-node stress overview deliberately has overlapping targets. Its measured
layout was14.9ms and paint65.8ms. A1.8-second warm static sample measured0.83%
median machine CPU,625,242,112 bytes summed RSS and551,026,688 bytes private
commit over2 observed owned processes. Shared RSS is double-counted; private
commit is not private working set. These short samples are not a long benchmark.

The temporary candidate is placed beside the existing dist build during live
model QA so the existing adjacent `.toolenvs/visual-cpu` runtime is reused.
Staging an EXE several directories deeper correctly reports no adjacent runtime;
that is not a failed inference or a reason to reinstall the models.

Release-candidate SHA-256:
`8515cb4971176fe020a509fc25c482cbac0266c409e0ec359ce6ecc6fce33030`,
276,822,249 bytes. Final live model/TON results and deployment are recorded next.

## Stage 8 — итоговый EXE, фактические сценарии и ограничения

Поставлен `dist/Granger-OSINT.exe`,276823658 байт; SHA-256
`3957a014519c6176577a432ccefd971cf2a4483348762ec7bbcc4fae41df9047`.
Предыдущие EXE сохранены в `dist/archive`; исходная поставка доступна в
`before-stability-3a3fabd4db0d/Granger-OSINT.exe`. Замена выполнялась через
проверенный временный файл. В момент замены основной EXE не был запущен.
Данные, секреты, настройки и runtime не мигрировались.21 файл основного профиля
сравнён по SHA-256; receipt установленного CPU-runtime также не изменился.
Все12 защищённых ресурсов персонажа совпадают с исходной контрольной точкой.

На последнем живом прогоне (`output/stability/live-exe-06/report.json`):

| Сценарий | Фактический результат | Ограничение |
|---|---|---|
| DeepSeek | Проверка API успешна; настоящие tool_calls и usage | Только собственный сохранённый ключ, скопированный непосредственно в отдельный Credential Manager namespace; затем удалён |
| Telegram → GitHub | Публичная страница и preview без сессии; оба обнаруженных репозитория проверены;17 операций,42.53с | Остановка `paused` при отсутствии новых фактов, сохранённый содержательный итог; это не полный сбор всех сведений о проекте |
| Объяснить узел | Новый успешный ответ модели, `completed`; тот же ID/цель; число tool calls17→17 | Только выбранный структурированный подграф и сохранённые выдержки; никаких новых сетевых инструментов |
| Cancel/restart/resume | Stop сохраняет checkpoint; после запуска нет автовозобновления; явное продолжение сохраняет ID | Неизвестный результат прерванного вызова не превращается в успех и не повторяется автоматически |
| Visual GEOINT | Реальный `visual_geoint` из существующего чата; GeoCLIP и Waypoint;9 географических кандидатов;150.24с | `paused` после повторных локальных чтений без новых фактов; координаты — гипотезы, raw score не вероятность; фото в LLM не передаётся |
| TON |10 сохранённых наблюдений, из них8 транзакций; направленные агрегаты с Decimal-суммами и evidence | Само выполнение `timeout`; интерфейс показывает `completed_with_errors`, не полный сбой и не полный успех; владельцы не установлены |

Этот живой прогон прошёл17/17 проверок, включая отсутствие оставшихся дочерних
процессов и удаление временного API-ключа. Один идемпотентный snapshot-read IPC
потребовал повторения; команды чата/инструментов после неоднозначного ответа
не повторялись. Ранние прогоны `live-exe-01..04` сохранены с их проваленными
проверками; они не входят в итоговые17. `live-exe-05` подтвердил pipeline до
последней правки отображения частичного ручного результата.

Дополнительный запуск `saved-live-views-05` без ключа/сетевых вызовов открыл
настоящие сохранённые результаты: карта гипотез и таблица широты/долготы/raw
score, географический граф, направленный агрегат TON и его раскрытие в отдельные
транзакции.6/6 проверок прошли. Скриншоты координатной схемы и таблицы просмотрены
визуально: это **координатная сетка без картографической подложки**, явно
подписанная как гипотезы. Не заявляется проверка онлайн-карт или истинности места.
Снимки сделаны `QWidget.grab()` настоящего окна EXE, не из макета.

Финальный графовый прогон `delivery-graph/report.json`:24/24,1000 узлов/5000
связей одновременно в Canvas2D; layout24.8мс, paint92.4мс во время параллельных
проверок. Короткая1.8с статическая выборка: median CPU0.79% всей машины,
599695360 байт суммарного RSS,524578816 байт private commit,2 наблюдаемых процесса.
Суммарный RSS повторно учитывает разделяемые страницы; private commit не является
private working set. Предыдущий15-секундный замер во время CPU-inference:
около3.07GB RSS и19.5% CPU всей12-поточной машины, отдельно от графового теста
(`visual-live04-perf.json`, предыдущая сборка с тем же runtime). Это ограниченные
измерения на данной машине, не гарантия частоты кадров или длительный soak-test.

Проверка повреждённых сохранений `delivery-restart`:16/16, два настоящих запуска.
`delivery-smoke`: настоящие Renderer-ready Launcher/Pet и коды выхода0 с
PATH=System32.100 встроенных Python-модулей соответствуют исходникам,138 ресурсов
соответствуют файлам поставки. Персонаж, спрайты и анимации не редактировались.

Полный завершающий Python-прогон без тяжёлого inference: **1316 passed,1 skipped,
32 subtests**,244.48с. Skip — optional live Ollama. Предшествующий параллельный
прогон имел1315 pass и один3-секундный Qt timeout в тесте сохранения draft;
ожидание не увеличивалось, этот провал не скрыт. Повторный полный прогон прошёл.
Frontend:118 tests pass; TypeScript/Vite production build прошёл. Сохраняется
предупреждение Vite о размере основного bundle; оно не ошибка сборки.

### Проверки A–J и пределы доказательства

| Требование | Доказательство |
|---|---|
| A: AttributeError | Воспроизведение baseline, строгие evidence-контракты; актуальный EXE восстанавливает сохранённые данные |
| B: повреждённый checkpoint |16 EXE-проверок, сохранены исходные байты, нет автовозобновления |
| C: повторные ошибки |100 одинаковых исключений в детерминированном ErrorCenter-тесте → одно уведомление/лог; реальные empty/blocked/timeout в живых сценариях. Не заявляется создание100 настоящих403/429 запросов |
| D: Telegram | Реальный публичный pipeline и опубликованная цепочка ссылок; имена репозиториев извлечены из ответов, не зашиты в адаптер |
| E: TON | Реальные транзакции/суммы/направления;6 saved-view GUI-проверок включают раскрытие агрегата; метки не владельцы |
| F: GEOINT | Реальные две CPU-модели через чат, фото без GPS,9 кандидатов, визуально проверенные сетка/таблица |
| G: граф |24 native input-проверки: выбор узла/связи, drag/pin, pan, wheel, поиск, фильтр, evidence, collapse/expand, темы, restart |
| H: продолжение | Реальный Stop/restart/resume и новое объяснение с тем же ID/целью; кэш/протокол дополнительно проверены unit-тестами |
| I: длительность | Ограниченные многоминутные реальные сценарии и холодный CPU-inference, отмена/cleanup; многочасовая нагрузка не тестировалась |
| J: большой граф | Синтетические1000 узлов/5000 связей в настоящем EXE; данные помечены синтетическими, не выдаются за OSINT |

### Инструменты, файлы и Git

[Отдельная таблица48 адаптеров](STABILITY_TOOLS48.md):45 локально готовы,
8 получили фактическую проверку данных/агентного вызова/GUI на данном этапе.
Snoop и Nuclei выключены; VirusTotal требует ключ.45 не означает45 подтверждённых
внешних сервисов. Не проверялись чужие/закрытые аккаунты и инструменты, требующие
отдельного согласия. Возможность отмены/контрактов48 операций покрывается кодом
и тестами, не48 внешними успешными расследованиями.

Изменённые основные компоненты: `agent.py`, `agent_evidence.py`, `agent_journal.py`,
`investigation_contracts.py`, `investigation_progress.py`, `investigation_results.py`,
`investigation_workspace.py`, `evidence_graph.py`, `graph_context.py`,
`graph_store.py`, `tool_contracts.py`, `download_budget.py`, `entity_router.py`,
`telegram_public.py`, `errors.py`, `chat.py`, `desktop_bridge.py`, `app.py`, `ipc.py`;
frontend `Search.tsx`, `InvestigationWorkspace.tsx`, `InvestigationCanvas.tsx`,
`graph-model.ts`, `graph-layout.worker.ts`, `types.ts`, `investigation-graph.css`,
CSP и связанное поле существующих технических настроек. Проверочные scripts/tests
и документация включены в архив исходников. Полный список — diff от `7a0bb9b`.

Поэтапно отправлены обычным push в `origin/main`:
`ce56275` — crash/recovery; `da7ef1b` — прогресс/итоги; `6221002` — контракты/бюджеты;
`662e664` — маршрутизация/Telegram; `7ce0e26` — evidence/граф/persistence;
`2860715` — настоящий frontend; `21dde06` — объяснение/EXE-проверки.
Последняя небольшая правка статуса частичного результата и итоговые материалы
публикуются финальным commit; конкретный SHA и состояние remote проверяются
в отчёте поставки `output/stability/release-public/git-publication.json`.

Оставшиеся ограничения: внешний доступ и полнота зависят от источников; HTTP
download-бюджет не измеряет трафик сторонних CLI; локальные модели не устанавливают
место или личность; координатная схема не содержит online basemap; полноэкранный
граф ограничен5000 узлами/20000 связями, обычное отображение —220 с явным
расширением до1200; неизвестные/повреждённые private checkpoints не проигрываются.
Поддержка OAuth/сессий и новые дополнительные источники не добавлялись ради QA.
