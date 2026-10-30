"""Exercise the actual standalone Windows binary without a Python/Qt PATH."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def _pe_info(executable: Path) -> dict:
    data = executable.read_bytes()
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("The executable has no DOS/PE header")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if offset + 96 > len(data) or data[offset:offset + 4] != b"PE\0\0":
        raise ValueError("The executable has an invalid PE header")
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    optional = offset + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    subsystem = struct.unpack_from("<H", data, optional + 68)[0]
    if (machine, magic, subsystem) != (0x8664, 0x20B, 2):
        raise ValueError(f"Expected AMD64 PE32+ Windows GUI; got machine={machine:#x}, magic={magic:#x}, subsystem={subsystem}")
    return {"machine": "AMD64", "format": "PE32+", "subsystem": "Windows GUI", "subsystem_id": subsystem}


def _ensure_no_running_instance() -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel.WaitNamedPipeW.restype = wintypes.BOOL
    identity = hashlib.sha256(str(Path.home()).casefold().encode("utf-8")).hexdigest()[:12]
    namespace=os.environ.get('GRANGERPET_QA_NAMESPACE','')
    if namespace and os.environ.get('GRANGERPET_INTERACTION_TRACE'):
        identity=hashlib.sha256((str(Path.home()).casefold()+'|qa|'+namespace).encode('utf-8')).hexdigest()[:12]
    for role in ("launcher", "pet"):
        name = rf"\\.\pipe\GrangerPet-{identity}-{role}"
        ctypes.set_last_error(0)
        available = kernel.WaitNamedPipeW(name, 1)
        error = ctypes.get_last_error()
        # A busy pipe still means an instance exists. Missing path/name is safe.
        if available or error not in (2, 3):
            raise RuntimeError("Close the running GrangerPet Launcher and Hermione before testing the binary; an existing instance would invalidate the smoke test.")


def _terminate_spawned_binary_tree(executable: Path, root_pid: int) -> list[int]:
    """Terminate only descendants of our Popen PID whose image is this EXE."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return []
    parents = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        exists = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while exists:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            exists = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    ordered = [root_pid]
    for parent in ordered:
        ordered.extend(pid for pid, ancestor in parents.items() if ancestor == parent and pid not in ordered)
    killed = []
    expected = os.path.normcase(str(executable.resolve()))
    for pid in reversed(ordered):
        handle = kernel.OpenProcess(0x1000 | 0x0001, False, pid)
        if not handle:
            continue
        try:
            size = wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(size.value)
            if kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
                if os.path.normcase(os.path.abspath(image.value)) == expected:
                    if kernel.TerminateProcess(handle, 1):
                        killed.append(pid)
        finally:
            kernel.CloseHandle(handle)
    return killed


def _run_surface(executable: Path, pet: bool, directory: Path) -> dict:
    role = "pet" if pet else "launcher"
    marker = "Desktop pet started" if pet else "Launcher started"
    appdata = directory / role / "appdata"
    working = directory / role / "empty-working-directory"
    temporary = directory / role / "tmp"
    working.mkdir(parents=True)
    temporary.mkdir(parents=True)
    environment = os.environ.copy()
    for key in list(environment):
        if key.upper() in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM", "QT_QPA_PLATFORM_PLUGIN_PATH") or key.startswith(("_PYI_", "PYINSTALLER_")):
            environment.pop(key)
    environment.update(APPDATA=str(appdata), TEMP=str(temporary), TMP=str(temporary),
                       PATH=str(Path(environment.get("SystemRoot", r"C:\Windows")) / "System32"))
    arguments = [str(executable)] + (["--pet"] if pet else []) + ["--smoke-test", "--interaction-qa"]
    process = subprocess.Popen(arguments, env=environment, cwd=working,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    check = {"name": role, "spawned_pid": process.pid, "timeout_seconds": 30,
             "restricted_path": environment["PATH"], "fresh_profile": True, "passed": False}
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        check["terminated_own_binary_pids"] = _terminate_spawned_binary_tree(executable, process.pid)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        check["error"] = "The EXE did not exit within 30 seconds; only this test's matching binary processes were terminated."
        return check
    check["exit_code"] = process.returncode
    log = appdata / "GrangerPet" / "logs" / f"{role}.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    check["fresh_start_log"] = marker in text
    check["react_ready"] = ("Desktop surface ready: " + ("main" if pet else "launcher")) in text
    check["passed"] = process.returncode == 0 and check["fresh_start_log"] and check["react_ready"]
    if not check["passed"]:
        check["error"] = "The EXE failed to start a fresh surface. Close existing GrangerPet instances and inspect the build if this repeats."
        check["log_tail"] = text[-6000:]
        check["stderr_tail"] = stderr.decode("utf-8", errors="replace")[-2000:]
    return check


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=ROOT / "dist" / "Granger-OSINT.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "binarysmoke.json")
    args = parser.parse_args()
    executable = args.exe.resolve()
    report = {"schema_version": 1, "tested_at_utc": datetime.now(timezone.utc).isoformat(),
              "executable": str(executable), "status": "failed", "checks": []}
    try:
        if sys.platform != "win32":
            raise RuntimeError("This smoke test requires native Windows")
        report["sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
        report["size_bytes"] = executable.stat().st_size
        report["pe"] = _pe_info(executable)
        with tempfile.TemporaryDirectory(prefix="GrangerPet-binary-smoke-") as temporary:
            namespace=uuid.uuid4().hex
            os.environ.update(GRANGERPET_QA_NAMESPACE=namespace,GRANGERPET_QA_VAULT='GrangerPet/QA/smoke_'+namespace,
                GRANGERPET_INTERACTION_TRACE=str(Path(temporary)/'interaction.jsonl'))
            report['isolated_ipc']=True
            for pet in (False, True):
                _ensure_no_running_instance()
                check = _run_surface(executable, pet, Path(temporary))
                report["checks"].append(check)
                if not check["passed"]:
                    break
        if len(report["checks"]) == 2 and all(check["passed"] for check in report["checks"]):
            report["status"] = "passed"
    except (OSError, ValueError, RuntimeError) as error:
        report["error"] = str(error)
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.resolve().write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
