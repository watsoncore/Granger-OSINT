# Reconstruction audit — 2026-10-29

Starting commit: `034e2895264f0bc438d469c5793040d6c2f4c337`; branch `main`, clean tree.
Existing project remains the application; no alternate launcher/chat is introduced.

| Area | Existing implementation |
| --- | --- |
| Backend / entry | `main.py`, `grangerpet/app.py`, `panel.py`, `chat.py` |
| Qt / React bridge | `desktop_surface.py`, `desktop_bridge.py`; private in-process QWebChannel, bundled asset-only origin |
| Frontend / build | `frontend/src`, `frontend/vite.config.ts`, `frontend/package.json`; React19, TypeScript5.9, Vite8 |
| Launcher / companion | `launcher.py`, `pet.py`, independent IPC lifecycle |
| Character | `animation.py`, `pet_life.py`, `pet_actions.py`, `reactions.py`; seven existing sprite sheets, native Qt dock above WebEngine |
| Tool execution | `agent_tools.py`, `engine/adapters.py`, `engine/runtime.py`, `engine/readiness.py`; strict allowlist, cancellable owned workers |
| Agent / evidence | `agent.py`, `agent_evidence.py`, `investigation.py`; typed tool calls, normalized provenance, bounded model context |
| History / checkpoints | `chat_archive.py`, `agent_journal.py`, `conversations.py`; Windows DPAPI before portable migration |
| AI / connections | `ai.py`, `ai_keys.py`, `ai_state.py`, `connections.py`; existing DeepSeek gateway retained |
| Settings / themes | `config.py`, `theme.py`, `frontend/src/styles.css`, `typography.css`; one original palette |
| Sources / zoom | `frontend/src/components/Sources.tsx`, `App.tsx`; native dock geometry reported by renderer; Qt WebEngine zoom |
| Windows release | `build.ps1`, `Granger-OSINT.spec`, existing PyInstaller pipeline |
| Tests | `pytest`, `frontend` npm test (Vitest), packaged QA scripts |

Assets found: local Manrope variable TTF with OFL, existing Hermione PNG/ICO/SVG brand resources. No additional navigation icon pack or new font family was supplied. The request refers to screenshots but attaches only text in this turn; visual verification uses the actual application. The font reference is not identified as an exact font family.

Baseline commands: `.venv/Scripts/python.exe -m pytest -q`; `npm.cmd test -- --reporter=dot` in `frontend`. Output is local under `output/reconstruction-qa/`.

Baseline result: **661 passed, 1 skipped, 32 subtests**, 104.45s (the existing Ollama live check skipped because no local model server is running); frontend **62 tests / 9 files passed**, 6.64s.

Preserve: chat virtualization (>100 messages), incremental streaming/seen observers, hidden-renderer publication suspension, native page visibility, owned worker cancellation, no forced WebEngine Frozen lifecycle, unchanged character assets. No other applications, OS settings, services, or registry are part of this work.

The requested Start.me collection was attempted directly at `https://start.me/p/L1rEYQ/osint4all`. The HTTP client received 403 with a Cloudflare challenge; the web reader returned no page lines. No challenge bypass and no fabricated extracted entries. Other official sources must be attributed separately.
