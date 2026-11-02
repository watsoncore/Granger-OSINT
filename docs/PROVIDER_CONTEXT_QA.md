# Provider and conversation scope — Master Fix V2

Work in progress; these checks concern source, not the final V2 EXE.

## Routing and conversation boundary

The short literal `а этот IP 87.199.131.94?` previously selected plain streaming
chat despite a correctly recognized IP target. Chat now uses the shared entity
router and a conversation-scoped active target. A short location follow-up can
select network tools; the original user question remains the investigation goal.
The runner rejects a target from a different conversation.

`Герми, ты здесь?` is ordinary conversation. `Отложим` clears the working target
and creates a context barrier, without deleting messages, evidence or checkpoints.
New conversations clear the target. Image selections replace an old IP target;
working image scope no longer falls back to every previously authorized image.
Saved investigations still require explicit continuation.

Source fixtures: 106 passed in 38.27 s, including real Qt/UiJob routing, social
turns after investigation, checkpoint attachment scope and conversation mismatch.
Fixtures are not network or model verification.

## Controlled live gateway checks

2026-11-02 UTC. The saved gateway credential was resolved internally and never
written to source, configuration, reports or logs. No user conversation history
was used. Source keys were disabled. Raw controlled evidence stays in ignored
`output/master-fix-v2/` with isolated APPDATA.

| Scenario | Actual requests | HTTP | Outcome |
| --- | ---: | --- | --- |
| Ordinary greeting | 1 | 200 | 37 characters, 3.184 s |
| Short IP 87.199.131.94 | 3 | 200 × 3 | 7 evidence records; 6 tools; 38.727 s |
| Passive voin-cs.kz | 3 | 200 × 3 | 21 evidence records; bounded tool limit; 45.991 s |
| Broad multi-category request, before binding fix | 0 | No HTTP request | Local invalid_request after web_read; 1 evidence retained |

The short-IP run actually executed RDAP, PTR, routing, reputation and Feodo.
`ip_lookup` timed out: this is not a verified geographic location. The site run
retained evidence despite domain RDAP failure and certificate timeout.

The observed broad failure is local: the registry can select more than 40
definitions while DeepSeekClient rejects more than 40. It does not establish
the cause of the user's historical HTTP 400. The controlled site request did
not reproduce that HTTP error. Runtime negotiation and safe provider error
diagnostics are the next stage; no guessed provider limitation is asserted.
