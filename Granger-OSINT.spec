# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys
import sysconfig
from PyInstaller.utils.hooks import copy_metadata, collect_submodules

root = Path(SPECPATH)
assets = root / "grangerpet" / "assets"
frontend = root / "frontend" / "dist"
resources = root / "resources"
if not (frontend / "index.html").is_file():
    raise SystemExit("Build frontend first: npm ci --ignore-scripts and npm run build in frontend/")
icon = resources / "Granger-OSINT.ico"
version = resources / "Granger-OSINT.version.txt"
if not icon.is_file() or not version.is_file():
    raise SystemExit("Missing Granger-OSINT icon/version resource; run scripts/generate_app_icon.py")

# Do not collect unrelated developer-PATH copies of Windows ICU/UCRT libraries.
windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
purelib = Path(sysconfig.get_paths()["purelib"])
native_paths = [Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
                purelib / "PySide6", purelib / "shiboken6", windows / "System32", windows]
os.environ["PATH"] = os.pathsep.join(str(path) for path in native_paths if path.is_dir())

# The installed PyInstaller QtWebEngineCore hook collects QtWebEngineProcess,
# resource .pak/ICU data, locales and its qt.conf; Qt dependency hooks collect
# the real imported DLLs. Excluding Qml/Quick would break those dependencies.
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(assets), "grangerpet/assets"), (str(frontend), "frontend"),
           (str(icon), "resources"), (str(resources / "Granger-OSINT.svg"), "resources"),
           (str(version), "resources"), (str(resources / "third-party"), "resources/third-party"),
           (str(root / "THIRD_PARTY_NOTICES.md"), "resources"),
           (str(root / "grangerpet/visual_models/manifest.json"), "grangerpet/visual_models"),
           (str(root / "grangerpet/visual_models/scene_manifest.json"), "grangerpet/visual_models"),
           (str(root / "grangerpet/integrations19/classification_rules.json"), "grangerpet/integrations19"),
           (str(resources / "ocr"), "resources/ocr")] + [
        (str(path), "grangerpet/engine") for path in (root / "grangerpet" / "engine").glob("*.py")
    ] + copy_metadata("httpx") + copy_metadata("Pillow") + copy_metadata("cryptography"),
    hiddenimports=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
                   "pdb", "pydoc", "doctest", "symtable", "fileinput", "pickletools", "codeop", "unittest.mock"] +
                  [name for package in ("unittest", "asyncio", "multiprocessing", "xml", "importlib.resources", "zoneinfo")
                   for name in collect_submodules(package)] +
                  sorted(name for name in sys.stdlib_module_names
                         if name not in {"_tkinter", "tkinter", "turtle", "turtledemo", "idlelib", "ensurepip", "venv", "antigravity", "this", "test"}
                         and not name.startswith("_test")),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["google.genai", "google.generativeai", "dotenv"],
    noarchive=False,
    optimize=1,
)
system_dlls = {"ucrtbase.dll", "icu.dll", "icuuc.dll", "icuin.dll"}
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in system_dlls
              and not Path(entry[0]).name.lower().startswith(("api-ms-win-", "ext-ms-win-"))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Granger-OSINT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon),
    version=str(version),
)
