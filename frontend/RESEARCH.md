# Granger-OSINT: interface sources and implementation decisions

Research date: 2026-10-28. This is a replacement of the presentation layer of an existing Windows/Python application, not a new web service. Production resources are bundled locally; there is no network frontend API, remote asset, analytics script, font service, or API key in JavaScript.

## Architecture compared

| Option | Fit for this project | Decision |
| --- | --- | --- |
| React + TypeScript + Vite in a desktop container | Rich layout, semantic Markdown, accessible primitives and maintainable component boundaries | Use as the presentation layer |
| Tauri with a Python sidecar | Requires a new Rust host, child-process lifecycle, IPC and packaging while the existing native character already depends on Qt | Not selected for this migration |
| Qt WebEngine + React + QWebChannel | Reuses the Python event loop, native character, cancellation and controller ownership; Qt ships Chromium | Selected; renderer restricted to a bundled custom origin, finite bridge actions, no remote navigation |
| Continue Qt Widgets only | Small runtime cost and existing code, but recreating web component behavior and complex Markdown consumes substantial maintenance effort | Existing controllers and secure credential forms retained; main presentation replaced |

The existing character is a native transparent QWidget. The main window reserves a separate 240 logical-pixel right column for it at every supported width; source text never occupies that column. The launcher shows an unchanged copy of `grangerpet/assets/character.png`. No new character art is generated.

## Primary design research

| Source, documentation and actual source | License verified | Applied decision |
| --- | --- | --- |
| [shadcn/ui components](https://ui.shadcn.com/docs/components), [Button](https://ui.shadcn.com/docs/components/radix/button), [Sidebar](https://ui.shadcn.com/docs/components/sidebar), [Button source](https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/button.tsx), [Sidebar source](https://github.com/shadcn-ui/ui/blob/main/apps/v4/registry/new-york-v4/ui/sidebar.tsx) | [MIT](https://github.com/shadcn-ui/ui/blob/main/LICENSE.md) | Button variant/size composition is adapted in `components/ui.tsx`, with attribution. Compact sidebar, consistent focus, input, dialog, menu, tabs, tooltip, collapsible and slider behavior informed the component system. Command palettes and resizable panels were considered, but unused controls were not added. |
| [assistant-ui Thread demo](https://www.assistant-ui.com/elements/thread), [composer](https://www.assistant-ui.com/elements/composer), [scroll anchor](https://www.assistant-ui.com/elements/scroll-anchor), [actual Thread source](https://github.com/assistant-ui/assistant-ui/blob/main/apps/docs/components/pages/docs/assistant/thread.tsx), [scroll-anchor source](https://github.com/assistant-ui/assistant-ui/blob/main/packages/ui/src/components/react/assistant-ui/elements/scroll-anchor.tsx) | [MIT](https://github.com/assistant-ui/assistant-ui/blob/main/LICENSE) | Studied separate composer, stable streaming rows, grouped tools, copy/regenerate/stop, and an explicit jump-to-latest action. A second runtime/client was unnecessary: the existing Python chat owns history and requests. No assistant-ui source is copied. |
| [Motion AnimatePresence](https://motion.dev/docs/react-animate-presence), [layout animation](https://motion.dev/docs/react-layout-animations), [source](https://github.com/motiondivision/motion) | [MIT](https://github.com/motiondivision/motion/blob/main/LICENSE.md) | Actual Motion components animate section changes, message insertion, source disclosure, navigation indicator and notices. No token-by-token animation. System and app reduced-motion settings are respected. |
| [Radix Dialog live example](https://www.radix-ui.com/primitives/docs/components/dialog), [Slider implementation](https://github.com/radix-ui/primitives/blob/main/packages/react/slider/src/slider.tsx), [primitives source](https://github.com/radix-ui/primitives) | [MIT](https://github.com/radix-ui/primitives/blob/main/LICENSE) | Installed actual Dialog, DropdownMenu, Tooltip, Slider, Switch, Collapsible and Slot packages. They provide keyboard controls, focus trapping/restoration and state attributes. |
| [Lucide React](https://lucide.dev/guide/react), [icons and source](https://github.com/lucide-icons/lucide) | [ISC, with Feather attribution](https://lucide.dev/license) | Installed tree-shaken `lucide-react`. The same SVG icon family covers navigation, controls, sources and system buttons. |
| [21st.dev live community gallery](https://21st.dev/community/components), [AI chat category](https://21st.dev/community/components/s/ai-chat), navigation/buttons/forms/dashboard examples | Per-component rights vary; a gallery is not a blanket license | Compared dense navigation, composer composition and interactive states from publicly readable demos. No paid or uncertain-license component is copied or installed. Decorative marketing effects were rejected as a poor desktop fit. |
| [Magic UI Animated List live documentation](https://magicui.design/docs/components/animated-list), [actual implementation](https://github.com/magicuidesign/magicui/blob/main/apps/www/registry/magicui/animated-list.tsx) | [MIT for open source repository](https://github.com/magicuidesign/magicui/blob/main/LICENSE.md); commercial Pro templates separate | Studied keyed transitions and controlled insertion. Used Motion directly, not timed demonstration data, perpetual effects or Pro blocks. No Magic UI code copied. |
| [Telegram Desktop message implementation](https://github.com/telegramdesktop/tdesktop/blob/dev/Telegram/SourceFiles/history/view/history_view_message.cpp), [history controller](https://github.com/telegramdesktop/tdesktop/blob/dev/Telegram/SourceFiles/history/history_widget.cpp), [compose controls](https://github.com/telegramdesktop/tdesktop/blob/dev/Telegram/SourceFiles/history/view/controls/history_view_compose_controls.cpp) | [GPLv3](https://github.com/telegramdesktop/tdesktop/blob/dev/LICENSE) | Readable message widths, compact contextual controls and scroll anchoring informed independent behavior. No Telegram code, assets or branding copied. |

The research tools retrieved actual documentation/demo DOM and source text. Root additionally opened the live shadcn Button page in the in-app browser, inspected its visual demo, opened assistant-ui Thread and its actual message-actions menu, and inspected the live 21st.dev AI-chat category. No third-party login or paid component was used. Runtime visual QA is performed separately against the real bundled Granger-OSINT UI.

React Flow was reviewed as an optional direction in the request. No investigation graph is introduced in this frontend because no compatible existing graph contract was provided; this avoids a second disconnected evidence model.

## Actually installed runtime libraries

- React and React DOM: MIT; component rendering only.
- Radix primitives, `class-variance-authority`, `clsx`: MIT; behavior and style composition.
- Motion: MIT; finite transitions and reduced-motion support.
- Lucide React: ISC, with its included Feather MIT notices.
- `react-markdown`, `remark-gfm` and their parser dependencies: MIT; semantic Markdown and tables. HTML is skipped, remote images are not rendered, public links must pass an HTTP(S) allowlist and go through Python. Local evidence anchors are explicit.
- Vite, TypeScript and Vitest are build/test dependencies, not desktop services.

Exact versions and integrity hashes are in `package-lock.json`. `npm run build` generates `THIRD_PARTY_NOTICES.txt` from the locked **production** dependency tree, including each package's installed license/notice text. The same file is copied into `dist/` for distribution.

## Data flow and behavior

`bridge.ts` connects only to `QWebChannel(qt.webChannelTransport).objects.desktop`. Requests have an ID, allowlisted action and JSON payload; native responses return explicit success/error. The initial snapshot contains real state, not example messages or fabricated progress. Subsequent patches preserve unchanged message references; snapshots are coalesced at 50ms and backend updates are throttled separately.

`Chat.tsx` retains draft text in App across routes, grows the composer, handles Enter/Shift+Enter/IME, shows native streaming/cancellation and stops automatic scrolling while reading earlier messages. It offers an explicit jump-to-latest action. Markdown, copy, code copy, regenerate, stop and Canvas actions use the native bridge. Source cards distinguish snippets, directly read pages, adapters and errors; details retain evidence IDs away from the main prose.

`Search.tsx` displays the real registry, readiness reasons, supported inputs, calls and cancellation. Results are real backend rows, with copying/source inspection/analyze actions. Activity rows are exclusively derived from backend events. `History.tsx` uses the existing encrypted conversation library. `Canvas.tsx` edits/saves/exports through the Python document controller; source evidence remains separate.

`Settings.tsx` groups providers, investigations, tools, interface, Hermione, notifications and data. Credentials are entered only in native secure settings. Token figures come from provider usage. Unknown context/balance stay unknown. An explicit zero budget means no user cap; tool/API timeouts and repeated-call protection remain active. Settings save only edited values.

`Launcher.tsx` renders a single real lifecycle state; launch/stop, size, FPS and cursor preferences go to Python. The existing native Hermione remains responsible for animation, interaction, dragging and notifications.

## Local development and checks

```powershell
cd frontend
npm ci --ignore-scripts
npm test
npm run build
```

The generated `dist/` must be included in the desktop build. A standalone browser can display the UI but explicitly reports that Python is disconnected; it does not simulate working chat/tools. UI fixtures in tests are isolated and are never shipped as live state. Native host/EXE, DPI, live API, tool execution and notification QA are recorded in the main project report.


## 3.1 performance follow-up — long transcripts

An isolated 1000-message fixture exposed excessive mounted Markdown/Motion/Radix rows and high resource use in the real pre-optimization EXE. Added pinned `@tanstack/react-virtual` 3.14.23 (MIT) only for conversations above 100 messages. Its headless viewport keeps existing styles and all records; dynamic heights, overscan, scroll-to-index and source/notification IDs remain under application control. No global GPU switch, runtime CDN or remote UI dependency. Native before/after results and limitations are in `docs/PERFORMANCE_3.1.md`. Native browser find can inspect only mounted rows; the complete transcript remains available by scrolling and in DPAPI/export.

Primary sources inspected on 29 October 2026: [React adapter](https://tanstack.com/virtual/latest/docs/framework/react/react-virtual), [virtualizer API](https://tanstack.com/virtual/latest/docs/api/virtualizer), [upstream MIT license](https://github.com/TanStack/virtual/blob/main/LICENSE). Locked transitive license text is generated into the bundled third-party notices.
