# Third-party components and local source integrations

## Granger-OSINT 3.0 interface and desktop runtime

The React interface uses React/React DOM, Radix primitives, Motion, class-variance-authority, clsx, react-markdown and remark-gfm under MIT-compatible package licenses; Lucide icons use ISC with included Feather MIT notices. The Button/Slot composition is adapted from shadcn/ui (MIT, copyright2023 shadcn). Full locked production dependency notices are generated into `frontend/THIRD_PARTY_NOTICES.txt` and bundled with the frontend. `frontend/RESEARCH.md` records the primary sources and the components actually used. No paid21st.dev or Motion+ templates, Telegram GPL code or proprietary Magic UI blocks were copied.

Qt WebEngine is now an active bundled dependency. Qt/PySide/Shiboken are not MIT components: their applicable commercial/LGPL/GPL alternatives and Chromium's additional licenses must be considered separately. Official references: [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html), [Qt WebEngine licensing and third-party list](https://doc.qt.io/qt-6/qtwebengine-licensing.html). The installed Qt runtime remains dynamically linked. License texts from the installed distributions and Qt6.11.1's LGPLv3/GPLv3 texts are preserved in `resources/third-party/Qt-PySide6/`; `provenance.json` records the official source URLs and hashes. Corresponding Qt sources: [qtbase v6.11.1](https://github.com/qt/qtbase/tree/v6.11.1), [qtwebengine v6.11.1](https://github.com/qt/qtwebengine/tree/v6.11.1), [pyside-setup v6.11.1](https://github.com/qtproject/pyside-pyside-setup/tree/v6.11.1).

These notices do not grant new commercial rights to the existing fan artwork or character. Those assets retain their original provenance and rights; introducing an MIT frontend library does not change them.

Granger-OSINT invokes locally supplied tools through isolated processes. Vendor source trees, datasets, user investigation databases and optional tool runtimes are not embedded into Granger-OSINT.exe. Original license files remain in their respective folders. This document records the audited local copies; it does not supply a missing upstream license.

| Component / local folder | Version in local source | License found | Use |
|---|---|---|---|
| Instaloader / `instaloader-master` | 4.16 | MIT; `LICENSE`, Alexander Graf, André Koch-Kramer and contributors, 2016–2026 | Public profile metadata adapter |
| Telethon / `Telethon-1` | 1.42.0 | MIT; `LICENSE`, LonamiWebs, 2016–present | Authorized public Telegram lookup; generated TL schema built from local source |
| vk_api / `vk_api-master` | 11.10.1 | Apache-2.0; `LICENSE`, python273 | Official VK API adapter |
| vkbottle / `vkbottle-master` | 4.11.0 | MIT; `LICENSE`, timoniq, axd1x8a, luwqz1 | Audited; intentionally inactive because vk_api supplies the selected VK integration |
| WaybackPy / `waybackpy-master` | 3.0.6 | MIT; `LICENSE`, waybackpy contributors | Existing archive lookup through CDX |
| Gansar / `Gansar-main` | crypto-osint 0.3.1 | No root source LICENSE found in this local checkout | Existing user-local analyzer is invoked; source/data are not redistributed in the EXE |

Gansar includes separate notices for attribution resources under `app/attribution/assets/licenses/`, including GraphSense (MIT), Safe (MIT) and Serum (Apache-2.0). Those notices remain alongside the user's data. Its own project-level licensing must be clarified before independently redistributing its source.

The bundled TON representation validator in `grangerpet/validators/ton_address.py` is an independent implementation using Python's standard library, based on the public [TON format documentation](https://docs.ton.org/foundations/addresses/formats) and [TEP-2](https://github.com/ton-blockchain/TEPs/blob/master/text/0002-address.md). It contains no Gansar source. Since 2.6 the build no longer embeds the unlicensed optional vendor validator.

Telegram Desktop was studied as a UI reference. Granger-OSINT's Python/Qt message and document widgets are independently implemented; Telegram's C++ code, logos and branding are not included. Telegram Desktop's GPLv3 and its exceptions remain relevant to its original source, available in the [official repository](https://github.com/telegramdesktop/tdesktop).

The username, email and phone tools have additional terms, including copyleft and personal-use limitations. The complete audited list is in [docs/INTEGRATIONS_CORE.md](docs/INTEGRATIONS_CORE.md); Snoop is disabled by default and remains an explicit user-local source. Existing source copyright and license texts are preserved.

The desktop application uses Python, PySide6/Qt and Shiboken. PySide6/Qt provide their own LGPL/GPL/commercial licensing options and Qt third-party notices; consult the installed distribution's license files before redistribution. PyInstaller is the build packager and supplies its bootloader under its own license exception. Optional Python dependencies retain their upstream licenses and are recorded per environment in `.toolenvs/<group>/installed-requirements.txt`.

Hermione Granger / Harry Potter character references and the fan artwork are independent of the source-tool licenses. Granger-OSINT is an unofficial fan project and is not endorsed by the named platforms or their rights holders.

## Local GEOINT and portable security

Pillow13.0.0 supplies local image decoding, EXIF and bounded pixel processing. Cryptography50.0.2 supplies Argon2id and AES-GCM; no custom cipher is used. Installed distribution license texts and hashes are preserved in `resources/third-party/Python-geoint-security/` and included in the EXE.

The portable Tesseract5.5.3 runtime and its dynamically linked dependencies are reproduced from checksum-verified official MSYS2 packages. The Russian and English `tessdata_fast` models are pinned to the upstream commit recorded in `resources/ocr/provenance.json`. This runtime contains components with different licences, including copyleft alternatives; their full original notices are included under `resources/ocr/licenses/`. The manifest records original package/source URLs, versions, checksums and every delivered binary/model. `scripts/setup_geoint_ocr.py` reproduces the runtime without executing an installer or changing Windows. Tesseract is invoked as a separate local process; image pixels and TSV travel through anonymous pipes.

## Optional scene understanding

Florence-2-base-ft: Microsoft, MIT; compatible native checkpoint maintained by
florence-community. Pinned model files are downloaded separately, not bundled in
the executable. License: `resources/third-party/Florence-2-LICENSE.txt`.
See `docs/SCENE_VISION_RUNTIME.md` for exact revision, hashes and runtime limits.
