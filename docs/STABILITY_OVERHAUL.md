# Stability and investigation overhaul — verification record

Work starts from `7a0bb9b` on the existing `main` branch. This report is updated
after measured stages; earlier delivery reports are baseline claims, not new QA.

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
