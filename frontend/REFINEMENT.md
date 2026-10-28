# Interface refinement2026-10-28

The existing React/TypeScript/Vite/QtWebEngine architecture is retained. No sprite, face, animation or native character asset was changed.

## Font and type system

Primary font candidates were checked against their actual project documentation and license:

- [Inter](https://rsms.me/inter/), [OFL1.1](https://github.com/rsms/inter/blob/master/LICENSE.txt): strong small-text design, broad glyph coverage, variable optical sizing.
- [Geist](https://vercel.com/font), [OFL1.1](https://github.com/vercel/geist-font/blob/main/OFL.txt): inspected as a candidate; the published specimen did not provide adequate evidence of full Russian coverage for this selection.
- [Manrope project](https://github.com/googlefonts/manrope), [Google Fonts metadata](https://github.com/google/fonts/blob/main/ofl/manrope/METADATA.pb), [OFL1.1](https://github.com/google/fonts/blob/main/ofl/manrope/OFL.txt): explicit Cyrillic support and variable200–800weights. Selected for its substantial, compact Cyrillic forms.

The unmodified164700byte font is bundled in `public/fonts/Manrope-Variable.ttf`. SHA256 and provenance are in `public/fonts/SOURCE.md`; all Russian letters and Ё/ё were independently checked in the actual TrueType cmap. The font license is included both alongside the binary and in generated distribution notices. No runtime font download occurs. Windows WebEngine visual/DPI review remains part of native QA, rather than being inferred from a successful web build.

`typography.css` defines body15px (16px on wide displays), navigation14px, ordinary labels13–14px, metadata12px, section headings19–22px and primary headings25–28px. Weight, contrast, line height, buttons, settings, tables, chat, source metadata and launcher are coordinated without changing the existing dark palette. The separate native Hermione column retains240px width and a280px figure region for the existing character and local notification.

## Functional refinements

- Catalog: real readiness states, readable tool names, input types, search/filter, inspectable failed tools, concrete diagnostic reason and remedy. No readiness or execution result is fabricated.
- Settings: ordinary provider, model, Ollama, source paths, result/time budgets, Google cx, Telegram API ID, Instagram login and Snoop preferences are in React. Native forms are reserved for secure secret entry and file selection. A VK token action and explicit token-rotation advice are included.
- Balance: separate refresh, successful-update timestamp and honest unknown-unit label. An undocumented `token_balance` value is shown as gateway units, never converted to model tokens or money. Usage remains distinct.
- Sources/activity: readable names, source kind, acquisition time, retrieval status, excerpt and details. Raw evidence IDs remain in the technical disclosure and data model. API sources are distinct from snippets, pages and adapter observations.
- Avito: explicit manual browser action with current query. The UI states that no machine results were retrieved; this is not an agent API.
- Unread: completed model messages are acknowledged only after visibility intersection inside an active native chat, scoped to conversation and message IDs. Backend remains authoritative.

Regression tests cover secure-dialog dispatch, ordinary settings, unknown balance units, balance failure isolation, readiness reasons/filtering, explicit Avito launch and visible-message acknowledgements. Native screenshots/actual backend and external endpoint outcomes are recorded by the main project's QA report.
