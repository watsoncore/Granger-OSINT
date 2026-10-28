# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys
import sysconfig
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH)
assets = root / "grangerpet" / "assets"
icon = assets / "GrangerPet.ico"

# Qt uses Windows' unsuffixed ICU API. Developer PATH entries (for example
# Poppler's ICU78 or libheif's old UCRT forwarders) must never enter the EXE.
windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
purelib = Path(sysconfig.get_paths()["purelib"])
native_paths = [
    Path(sys.executable).parent,
    Path(sys.base_prefix),
    Path(sys.base_prefix) / "DLLs",
    purelib / "PySide6",
    purelib / "shiboken6",
    windows / "System32",
    windows,
]
os.environ["PATH"] = os.pathsep.join(str(path) for path in native_paths if path.is_dir())

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(assets), "grangerpet/assets"),
           (str(root / "Gansar-main" / "app" / "utils" / "ton_normalize.py"), "grangerpet/validators")] + [
        (str(path), "grangerpet/engine") for path in (root / "grangerpet" / "engine").glob("*.py")
    ] + copy_metadata("httpx"),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["google.genai", "google.generativeai", "dotenv", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
    optimize=1,
)
# These are OS components on every supported Windows 10/11 installation.
# App-local copies can shadow the OS API and produce missing-procedure errors.
system_dlls = {"ucrtbase.dll", "icu.dll", "icuuc.dll", "icuin.dll"}
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in system_dlls
              and not Path(entry[0]).name.lower().startswith(("api-ms-win-", "ext-ms-win-"))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GrangerPet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon) if icon.exists() else None,
)
