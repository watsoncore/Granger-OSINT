"""Prepare optional isolated source runtimes from existing user checkouts.

No vendor repository or model is cloned. Legacy dependencies stay out of the
desktop .venv and EXE. Telegram's omitted generated schema is built in a temp
copy, leaving the user's original checkout untouched. No credentials needed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name("source_requirements.json")


def _run(arguments, cwd, timeout=600, env=None):
    result = subprocess.run([str(value) for value in arguments], cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            timeout=timeout, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {result.stdout[-5000:]}")
    return result.stdout


def _python(env):
    return env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _create(env, root, python):
    executable = _python(env)
    if executable.is_file():
        return executable
    uv = shutil.which("uv")
    if uv:
        _run([uv, "venv", "--python", python, str(env)], root)
    elif python not in ("3.12", "3.12.14") and Path(python).is_file():
        _run([python, "-m", "venv", str(env)], root)
    elif os.name == "nt" and shutil.which("py"):
        _run(["py", "-3.12", "-m", "venv", str(env)], root)
    elif sys.version_info[:2] == (3, 12):
        _run([sys.executable, "-m", "venv", str(env)], root)
    else:
        raise RuntimeError("Python 3.12 is required for isolated tools. Install it or pass --python /path/to/python; uv can provision it automatically when available.")
    return executable


def _install(executable, arguments, root):
    uv = shutil.which("uv")
    if uv:
        return _run([uv, "pip", "install", "--python", executable] + arguments, root)
    _run([executable, "-m", "ensurepip", "--upgrade"], root)
    return _run([executable, "-m", "pip", "install"] + arguments, root)


def _telethon(executable, root):
    source = root / "Telethon-1"
    # Upstream setup.py generates TL types/errors from its included schemas.
    # A build copy avoids creating or replacing any file in the original source.
    with tempfile.TemporaryDirectory(prefix="GrangerPet-Telethon-build-") as temporary:
        copied = Path(temporary) / "Telethon"
        shutil.copytree(source, copied, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "build", "dist"))
        _install(executable, ["--no-deps", str(copied)], root)


def _install_local(executable, source, root):
    with tempfile.TemporaryDirectory(prefix="GrangerPet-local-build-") as temporary:
        copied = Path(temporary) / source
        shutil.copytree(root / source, copied, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", "build", "dist", "*.egg-info", ".github"))
        _install(executable, [str(copied)], root)


def _blackbird_data(env):
    output = env / "wmn-data.json"
    if output.is_file():
        data = json.loads(output.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sites"), list):
            return "existing valid app-owned WhatsMyName cache"
    request = urllib.request.Request("https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json",
                                     headers={"User-Agent": "GrangerPet/2.0 dependency setup"})
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = response.read(12_000_001)
    if len(payload) > 12_000_000:
        raise RuntimeError("WhatsMyName data exceeded its setup size limit")
    data = json.loads(payload)
    if not isinstance(data, dict) or not isinstance(data.get("sites"), list):
        raise RuntimeError("WhatsMyName source did not return the expected site database")
    output.write_bytes(payload)
    return "official WhatsMyName database cached once; SHA256=" + hashlib.sha256(payload).hexdigest()


def _check(executable, spec, root):
    source_paths = [str(root / source) for source in spec.get("sources", []) if source != "Telethon-1"]
    code = "import importlib,json,sys;sys.path[:0]=" + repr(source_paths) + ";mods=" + repr(spec.get("imports", [])) + ";[importlib.import_module(x)for x in mods];print(json.dumps({'python':sys.version.split()[0],'imports':mods}))"
    return json.loads(_run([executable, "-I", "-c", code], root).splitlines()[-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT, help="Folder containing the existing source directories")
    parser.add_argument("--groups", default="all", help="Comma-separated groups, or all")
    parser.add_argument("--python", default="3.12", help="Compatible tool interpreter; uv accepts a version or absolute path")
    parser.add_argument("--audit", action="store_true", help="List existing sources and runtimes without installing anything")
    parser.add_argument("--go", type=Path, help="Optional existing Go compiler for the PhoneInfoga bridge")
    parser.add_argument("--output", type=Path, default=PROJECT / "output" / "integration_setup.json")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    groups = manifest["groups"]
    selected = list(groups) if args.groups == "all" else [name.strip() for name in args.groups.split(",") if name.strip()]
    unknown = set(selected) - set(groups)
    if unknown:
        parser.error("Unknown groups: " + ", ".join(sorted(unknown)))
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(), "source_root": str(root), "groups": {}}
    for name in selected:
        spec = groups[name]
        env = root / ".toolenvs" / name
        item = {"sources": {source: (root / source).is_dir() for source in spec.get("sources", [])}, "runtime": str(_python(env))}
        report["groups"][name] = item
        if args.audit:
            item["status"] = "present" if _python(env).is_file() else "not_installed"
            continue
        print(f"Preparing isolated source group: {name}", flush=True)
        try:
            missing = [source for source, exists in item["sources"].items() if not exists]
            if missing:
                raise RuntimeError("Missing existing sources: " + ", ".join(missing))
            executable = _create(env, root, args.python)
            if spec.get("dependencies"):
                _install(executable, spec["dependencies"], root)
            for requirement in spec.get("requirements", []):
                _install(executable, ["-r", str(root / requirement)], root)
            for source in spec.get("local_packages", []):
                _install_local(executable, source, root)
            if name == "platforms":
                _telethon(executable, root)
            if name == "blackbird":
                item["database"] = _blackbird_data(env)
            item.update(_check(executable, spec, root))
            item["status"] = "ready"
            installed = _run([executable, "-I", "-c", "from importlib.metadata import distributions;print('\\n'.join(sorted(d.metadata['Name']+'=='+d.version for d in distributions())))"], root)
            (env / "installed-requirements.txt").write_text(installed, encoding="utf-8")
            (env / "grangerpet-runtime.json").write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            item.update(status="error", error=str(error)[:5500])
        print(f"{name}: {item['status']}", flush=True)
    local_go = root / ".toolenvs" / "go" / "bin" / "go.exe"
    compiler = str(args.go) if args.go else str(local_go) if local_go.is_file() else shutil.which("go")
    if compiler:
        bridge = PROJECT / "scripts" / "phoneinfoga_bridge.go"
        if bridge.is_file():
            try:
                destination = root / ".toolenvs" / "phoneinfoga"
                destination.mkdir(parents=True, exist_ok=True)
                binary = destination / ("phoneinfoga-bridge.exe" if os.name == "nt" else "phoneinfoga-bridge")
                build_env = os.environ.copy()
                build_env.update(GOPATH=str(root / ".toolenvs" / "go-cache" / "path"), GOCACHE=str(root / ".toolenvs" / "go-cache" / "build"))
                _run([compiler, "build", "-mod=readonly", "-o", binary, bridge], root / "phoneinfoga-master", env=build_env)
                report["phoneinfoga"] = {"status": "ready", "binary": str(binary)}
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                report["phoneinfoga"] = {"status": "error", "error": str(error)[:2000]}
    else:
        report["phoneinfoga"] = {"status": "not_installed", "message": "No existing Go compiler or PhoneInfoga binary found; source files alone are not an executable."}
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if any(item.get("status") == "error" for item in report["groups"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
