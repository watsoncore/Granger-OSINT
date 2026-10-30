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
