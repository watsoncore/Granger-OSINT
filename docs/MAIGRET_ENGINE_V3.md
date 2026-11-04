# Maigret V3: original engine, measured coverage

## Installed facts (2026-11-04)

The worker imports the supplied `maigret-main/maigret` 0.6.6 engine in the existing `.toolenvs/maigret` Python 3.12 runtime. Its original database and installed package database are identical: 3,221,408 bytes, SHA-256 `25b734d93fb338c75b24f0149ae0251f6fca88d8fce2f9968a0875884421b343`. The database contains **8,232 entries**, not an assumed 8,600. The original `MaigretDatabase` parser exposes **7,508 enabled username entries**. Other identifier types and disabled entries are not silently counted as checked usernames.

The previous adapter selected only `query.limit` sites (normally 10, at most 50), searched only a ranked prefix, disabled metadata extraction and emitted findings only after the entire original API call returned. It also incorrectly rejected URL templates beginning with `{urlMain}` before formatting them. A further, distinct registry result-retention limit required removal in the shared tool registry.

## Modes and policies

| Mode | Selection in the original database | Measured selection / eligible / explicit policy skips |
|---|---|---|
| Quick | Original ranker top 10 by default, including its source mirrors; bounded fast sample | 16 / 12 / 4 |
| Standard | Original packaged `top_sites_count=500`, including mirrors | 509 / 365 / 144 |
| Full | Every enabled username entry; no top-N result or site ceiling | 7,508 / 6,434 / 1,074 |
| Custom | Count (0 means all matching), actual site names/tags/excluded tags; optional exact names without source mirrors | Determined from the actual database and identifier |

Counts above use `solvnox` and this database. Original ranker mirrors explain why top 10/500 can select 16/509 entries. Site-specific username format rejections are subsequently reported separately by the engine; a selected site is not necessarily an HTTP request. Quick alone supports a deliberate 1–50 ranked-site sample. Standard and Full reject a positive `site_count`, so an old limit cannot silently shorten Full.

Full disjoint policy exclusions are: protected/CAPTCHA/WAF/TLS impersonation **223**; activation **3**; non-public or non-HTTPS display/probe URL **798**; non-read request method/payload **5**; similar-name search **11**; credential-bearing headers **4**; existing excluded categories **19**; unsupported DNS **7**, Tor **3**, I2P **1**. Every skipped site and reason is retained. The exclusions do not claim a negative username result. Normal certificate or DNS failures encountered during checking are unknown/unavailable, not predeclared site absence.

The original checkout's HTTP checker disables TLS certificate verification and trusts environment proxies. Granger substitutes only its worker-local transport constructor: verified system CA context and hostname validation, `trust_env=False`, HTTPS-only public destination/probe/redirect checks, public-only DNS resolution, maximum four redirects, maximum 4 MB decoded response body. Oversized pages become unavailable, never a negative based on truncated HTML. The original request and site detection functions remain in use; vendor files are untouched. No cookies, login, activation, CAPTCHA/WAF bypass, TLS impersonation, automatic DB update, recursive username expansion or extra enrichment requests are enabled.

Standard preserves the original packaged site rank/count. Its execution settings intentionally differ from unrestricted original CLI defaults: desktop concurrency defaults to 12 rather than 100; a visible total budget applies; no recursive expansion or enrichment. Per-site timeout defaults to the original 30 seconds; parsing already-fetched public metadata is enabled. These are reported configuration differences, not a claim of identical unmodified CLI execution.

## Streaming, status and cancellation contract

`grangerpet.engine.maigret_contracts.INPUT_SCHEMA` is the registry/manifest schema. `normalize_options()` validates it again inside the isolated worker. Options travel in `options['maigret']` or `query.options['maigret']`. Public arguments: `username`, `mode`, `site_count`, `sites`, `tags`, `exclude_tags`, `include_mirrors`, `per_site_timeout`, `concurrency`, `parse_metadata`, `time_budget`. Exact names without mirrors are Custom-only. Input list bounds constrain one filter request, not Full database coverage.

The existing original `maigret(..., output_container=...)` API exposes completed checks before the coroutine finishes. The adapter drains that container every 100 ms, emits each genuine finding using the existing `result` event, and throttles compact `maigret_progress` events to about three per second. No negative, unavailable or progress row becomes a profile finding. A matching nickname is explicitly not identity confirmation.

`maigret_progress` has `{event, source:'maigret', progress:{...}}`. Coverage fields include mode/version/database SHA/size/count, selected, scheduled, processed, checked, found, not_found, unknown, blocked, unavailable, errors, skipped/reasons, pending, elapsed_seconds, phase, complete, cancelled. `processed` includes engine format rejections; `checked` excludes those skipped engine outcomes. `complete` describes coverage of the selected eligible work, while terminal source status can remain `partial` because of uncertain checks. Initial policy skips are outside `scheduled`.

The private `maigret_plan` event carries configuration and scheduled names; private `maigret_checks` batches carry actual per-site statuses. The subprocess transport retains both on timeout/cancellation, together with all already-received profile findings. Terminal `source_diagnostics` contains `coverage`, full `site_checks`, `configuration`, `original_defaults`, `policy`, `resumption`. Compact coverage is suitable for UI progress; detailed checks belong in the private research journal.

The worker streams findings rather than duplicating the entire result set inside one final JSONL line. `streamed_result_count` is checked by the parent transport before reconstructing final results. A transport byte budget (16 MB per JSONL frame, 128 MB total) is an explicit memory safeguard, not a number-of-sites/result limit; overflow produces a partial/error outcome and retains accepted observations.

Persistence has a source-specific complete-coverage contract too. `safe_maigret_diagnostics()` validates and redacts each site-check row and remaining site name independently instead of applying the generic 150-item excerpt policy to the entire list. Its explicit 10,000-row structural guard exceeds this installed database and rejects excess data rather than slicing it. `InvestigationEvidence` accepts a Maigret result set in validated batches instead of inheriting the generic 2,000-row per-envelope sample. The ordinary redaction and other-source budgets remain unchanged. Outcome sanitization, private checkpoint cache, public journal execution metadata and evidence restoration all preserve the full Maigret records and coverage.

Cancellation closes the existing owned process job, never a global process-name kill. Original Maigret supports an in-memory partial output container, **not native durable resume**. Retained `remaining_sites` can be explicitly rerun with Custom exact site filters, in filter batches of at most 100 names. This is a new run of the remaining checks, not an invented persistent Maigret session. Resumption should verify the database SHA, username and configuration before comparing runs.

## Verification and honest comparison

`scripts/verify_maigret_v3.py` is offline unless `--live` is explicitly given. It verifies original parser counts and strict transport construction using actual installed aiohttp without making network requests. `--live --username solvnox` performs two sequential, fixed six-site checks: original core API under the same verified transport, then the Granger adapter; GitHub, YouTube, TikTok, Wikipedia, WordPressOrg and GooglePlayStore only, exact names without mirrors, timeout 3 s, concurrency 3, total budget 25 s each, metadata enabled.

The comparison reports per-site native/mapped statuses, HTTP/error classes, timings, database hash, actual findings, progress events and any status differences. It does **not** claim parity with unsafe unmodified CLI defaults, nor a live Full/Standard scan. Remote responses can change between the sequential runs. The raw local comparison artifact belongs in ignored `test-output/v3/maigret_live_comparison.json`, not the public repository.

Meaningful offline tests cover >9,000-entry Full selection, explicit policy skips, original output-container streaming of 55 findings despite legacy limit=1, actual UTF-8 metadata, distinct not-found/unknown/blocked/unavailable/error classifications, deadline partials, strict TLS/redirect/private DNS behavior and real owned subprocess complete/cancel/timeout retention. A 2,201-finding end-to-end fixture passes through the real registry, outcome sanitizer, manual workspace, encrypted temporary checkpoint, public journal, reopen and `InvestigationEvidence.restore`; all 2,201 facts/check rows and 201 remaining site names survive, while injected secret fields/values are removed. This catches both former 150-row diagnostics and 2,000-finding persistence truncations. Existing worker/process-tree regression tests remain applicable.

## Other adapter limit audit (unchanged by this scoped integration)

| Adapter | Actual local input | Current restriction and interpretation |
|---|---|---|
| Blackbird | 692 entries, 691 valid, 646 HTTPS/non-NSFW candidates | Prefix `query.limit` (1–50, often 10), concurrency 3, request timeout ≤7 s. Sample, not complete original coverage. |
| Snoop | 328 Demo entries | Prefix limit; original Demo license/expiry honored. No full-version/license bypass. |
| SocialAnalyzer | 999 database website entries | Original `top` plus separate request-count limit, concurrency 3; metadata/extract off, detected-only. Sample/heuristic, not complete original output. |
| Holehe | 123 module files; 24 pass existing static non-recovery/read-only selection | At most min(limit,8), concurrency 3. Recovery, POST/password reset and notification-capable modules remain excluded. |
| PhoneInfoga | Original local numbering scanner | One real offline number-plan metadata row. Remote/key-based scanner coverage is not connected and must not be advertised as full PhoneInfoga. |
| Steam public | Reviewed SteamRecon subset/public pages | Groups/games 20, aliases 100 parsed→20 retained, friends 20 retained with observed count/sample flag. These samples are not complete histories. |
| Steam inventory | Public paginated API | Explicit max_pages 1–10, page_size 10–200; real cursor/stop reason and partial status support continuation. This is a bounded call with observable pagination. |

This audit exposes remaining restrictions; it does not assert that those adapters were rewritten or that all their returned metadata is now retained without limits.
