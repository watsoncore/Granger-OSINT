# Third-party components and local source integrations

GrangerPet invokes locally supplied tools through isolated processes. Vendor source trees, datasets, user investigation databases and optional tool runtimes are not embedded into GrangerPet.exe. Original license files remain in their respective folders. This document records the audited local copies; it does not supply a missing upstream license.

| Component / local folder | Version in local source | License found | Use |
|---|---|---|---|
| Instaloader / `instaloader-master` | 4.16 | MIT; `LICENSE`, Alexander Graf, André Koch-Kramer and contributors, 2016–2026 | Public profile metadata adapter |
| Telethon / `Telethon-1` | 1.42.0 | MIT; `LICENSE`, LonamiWebs, 2016–present | Authorized public Telegram lookup; generated TL schema built from local source |
| vk_api / `vk_api-master` | 11.10.1 | Apache-2.0; `LICENSE`, python273 | Official VK API adapter |
| vkbottle / `vkbottle-master` | 4.11.0 | MIT; `LICENSE`, timoniq, axd1x8a, luwqz1 | Audited; intentionally inactive because vk_api supplies the selected VK integration |
| WaybackPy / `waybackpy-master` | 3.0.6 | MIT; `LICENSE`, waybackpy contributors | Existing archive lookup through CDX |
| Gansar / `Gansar-main` | crypto-osint 0.3.1 | No root source LICENSE found in this local checkout | Existing user-local analyzer is invoked; source/data are not redistributed in the EXE |

Gansar includes separate notices for attribution resources under `app/attribution/assets/licenses/`, including GraphSense (MIT), Safe (MIT) and Serum (Apache-2.0). Those notices remain alongside the user's data. Its own project-level licensing must be clarified before independently redistributing its source.

The username, email and phone tools have additional terms, including copyleft and personal-use limitations. The complete audited list is in [docs/INTEGRATIONS_CORE.md](docs/INTEGRATIONS_CORE.md); Snoop is disabled by default and remains an explicit user-local source. Existing source copyright and license texts are preserved.

The desktop application uses Python, PySide6/Qt and Shiboken. PySide6/Qt provide their own LGPL/GPL/commercial licensing options and Qt third-party notices; consult the installed distribution's license files before redistribution. PyInstaller is the build packager and supplies its bootloader under its own license exception. Optional Python dependencies retain their upstream licenses and are recorded per environment in `.toolenvs/<group>/installed-requirements.txt`.

Hermione Granger / Harry Potter character references and the fan artwork are independent of the source-tool licenses. GrangerPet is an unofficial fan project and is not endorsed by the named platforms or their rights holders.
