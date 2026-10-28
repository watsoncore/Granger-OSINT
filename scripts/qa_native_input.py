"""Native SendInput engineering test restricted to this run's GrangerPet process.

The user explicitly requested real Windows mouse events against the EXE. This
is not a general desktop automation helper: it refuses a pre-existing pet,
verifies its exact spawned process image and HWND before each gesture, uses a
fresh profile, never targets another app, releases the button and restores the
cursor in finally. Source mode is a preliminary calibration, not an EXE claim.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]


class Native:
    MOVE, DOWN, UP, ABSOLUTE, VIRTUALDESK = 0x0001, 0x0002, 0x0004, 0x8000, 0x4000

    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        self.user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        # The test client is a QCoreApplication, so it does not configure GUI
        # DPI awareness. Read HWND/cursor rectangles in physical pixel units,
        # exactly the coordinate system required by absolute SendInput.
        self.user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user.SendInput.restype = wintypes.UINT
        self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.WindowFromPoint.argtypes = [wintypes.POINT]
        self.user.WindowFromPoint.restype = wintypes.HWND
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wintypes.LPARAM]

    def cursor(self):
        point = wintypes.POINT()
        if not self.user.GetCursorPos(ctypes.byref(point)):
            raise RuntimeError("Cannot read cursor position")
        return point.x, point.y

    def inject(self, flags, x=0, y=0):
        event = INPUT()
        event.type = 0
        event.mi = MOUSEINPUT(x, y, 0, flags, 0, 0)
        if self.user.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise RuntimeError("Windows rejected the scoped test input")

    def move(self, x, y):
        left, top = self.user.GetSystemMetrics(76), self.user.GetSystemMetrics(77)
        width, height = self.user.GetSystemMetrics(78), self.user.GetSystemMetrics(79)
        if not (left <= x < left + width and top <= y < top + height):
            raise RuntimeError("The test gesture would leave the virtual desktop")
        ax = round((x - left) * 65535 / max(1, width - 1))
        ay = round((y - top) * 65535 / max(1, height - 1))
        self.inject(self.MOVE | self.ABSOLUTE | self.VIRTUALDESK, ax, ay)

    def image(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(32768)
            value = ctypes.create_unicode_buffer(size.value)
            if self.kernel.QueryFullProcessImageNameW(handle, 0, value, ctypes.byref(size)):
                return str(Path(value.value).resolve())
            return ""
        finally:
            self.kernel.CloseHandle(handle)

    def window(self, pid):
        windows = []
        def accept(hwnd, unused):
            current = wintypes.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(current))
            if current.value == pid and self.user.IsWindowVisible(hwnd):
                length = self.user.GetWindowTextLengthW(hwnd)
                title = ctypes.create_unicode_buffer(length + 1)
                self.user.GetWindowTextW(hwnd, title, length + 1)
                if title.value == "GrangerPet · Гермиона":
                    windows.append(int(hwnd))
            return True
        callback = self.callback_type(accept)
        self.user.EnumWindows(callback, 0)
        if len(windows) != 1:
            raise RuntimeError(f"Expected one owned pet HWND, got {windows}")
        return windows[0]

    def anchor(self, hwnd, status):
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("Cannot inspect the owned pet geometry")
        left, top, width, height = status["collar_rect"]
        size, ratio = status["size"], status["dpr"]
        point = wintypes.POINT(rect.left + round((12 + size * (left + width / 2)) * ratio),
                               rect.top + round((12 + size * (top + height / 2)) * ratio))
        found = self.user.WindowFromPoint(point)
        if int(self.user.GetAncestor(found, 2) or 0) != hwnd:
            raise RuntimeError("The owned pet's collar is occluded; no other window will be clicked")
        return point.x, point.y


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--qa-window", action="store_true", help="Optional enumerable Qt.Window; default exercises production Qt.Tool")
    parser.add_argument("--exe", type=Path, default=ROOT / "dist/GrangerPet.exe")
    parser.add_argument("--size", type=int, choices=(100, 195), default=195)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Native Windows test only")
    from PySide6.QtCore import QCoreApplication
    from grangerpet.ipc import send_command
    from grangerpet.config import Settings
    app = QCoreApplication.instance() or QCoreApplication([])
    if send_command("pet", "status", timeout=200) or send_command("launcher", "status", timeout=200):
        raise SystemExit("Close GrangerPet before this isolated input test; no existing process is touched")
    mode = "source" if args.source else "exe"
    output = args.output or ROOT / f"output/search-overhaul-qa/{mode}-sendinput-{args.size}"
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    trace = output / "interaction.jsonl"
    # Keep previous attempts, so failed runs are not silently rewritten as a pass.
    if trace.exists():
        raise SystemExit(f"Trace already exists: {trace}; use a new output folder")
    profile = output / "appdata/GrangerPet"
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "settings.json").write_text(json.dumps(Settings(size=args.size, x=600, y=320).to_dict()), encoding="utf-8")
    executable = Path(sys.executable).resolve() if args.source else args.exe.resolve()
    arguments = [str(executable)] + ([str(ROOT / "main.py")] if args.source else []) + ["--pet"]
    if args.qa_window:
        arguments.append("--interaction-qa")
    environment = os.environ.copy()
    environment["APPDATA"] = str(output / "appdata")
    environment["GRANGERPET_INTERACTION_TRACE"] = str(trace)
    environment.pop("QT_QPA_PLATFORM", None)
    native = Native()
    original_cursor = native.cursor()
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(), "mode": mode,
              "input": "Native Windows SendInput: synthetic OS mouse events with real timing; not human hand movement or QTest",
              "size": args.size, "scope": "Only exact spawned GrangerPet process and verified HWND",
              "window_mode": "QA Qt.Window" if args.qa_window else "Production Qt.Tool",
              "checks": [], "gestures": []}
    if not args.source:
        report["exe_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    process = subprocess.Popen(arguments, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    owned_pid = None

    def status():
        value = send_command("pet", "status", timeout=500)
        if not value or not value.get("running"):
            raise RuntimeError("Owned pet process did not answer")
        if owned_pid is not None and value["pid"] != owned_pid:
            raise RuntimeError("Pet ownership changed; refusing input")
        return value

    def check(name, condition, details=""):
        report["checks"].append({"name": name, "passed": bool(condition), "details": details})
        if not condition:
            raise AssertionError(name + ": " + details)

    def events():
        if not trace.is_file():
            return []
        return [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]

    def gesture(name, direction, step, interval, count, expected):
        current = status()
        hwnd = native.window(owned_pid)
        origin = native.anchor(hwnd, current)
        before = len(events())
        native.move(*origin)
        time.sleep(.08)
        started = time.monotonic()
        native.inject(native.DOWN)
        time.sleep(.08)
        try:
            for index in range(1, count + 1):
                point = (origin[0], origin[1] + round(direction * step * index * current["dpr"]))
                native.move(*point)
                time.sleep(interval)
            # A real short hold lets Qt paint the selected reaction, and supplies
            # normal stationary polling messages while the button is still down.
            time.sleep(.20)
        finally:
            native.inject(native.UP)
        time.sleep(.30)
        captured = events()[before:]
        reactions = [item.get("reaction") or item.get("to") for item in captured if item.get("event") in ("trigger", "reaction")]
        samples = [item for item in captured if item.get("event") == "sample"]
        details = {"name": name, "origin_physical_px": list(origin), "step_logical_px": step,
                   "interval_s": interval, "count": count, "direction": direction,
                   "elapsed_s": round(time.monotonic() - started, 4), "reactions": reactions,
                   "sample_count": len(samples), "max_abs_vy": max((abs(item.get("velocity_y_px_s", 0)) for item in samples), default=0),
                   "mouse_event_count": sum(item.get("source") == "mouse_event" for item in samples)}
        report["gestures"].append(details)
        check(name + "_actual_samples", len(samples) >= 4 and details["mouse_event_count"] >= 2, str(details))
        if expected:
            check(name + "_reaction", expected in reactions, str(reactions))
        else:
            check(name + "_no_false_anger", not any(value in ("jerk_up", "jerk_down", "angry") for value in reactions), str(reactions))
        # No gesture starts while the prior reaction is still deliberately held.
        time.sleep(3.8)
        check(name + "_recovers", status()["drag_reaction"] == "calm")

    try:
        deadline = time.monotonic() + 20
        initial = None
        while time.monotonic() < deadline:
            initial = send_command("pet", "status", timeout=150)
            if initial and initial.get("running"):
                break
            time.sleep(.05)
        check("fresh_pet_running", bool(initial and initial.get("running")))
        owned_pid = int(initial["pid"])
        actual_image = Path(native.image(owned_pid)).resolve()
        expected_image = Path(sys.base_prefix) / "python.exe" if args.source else executable
        # A Windows venv wrapper launches its base interpreter. Compare the known
        # exact base executable rather than assuming Popen.pid is the real pet.
        check("exact_owned_process_image", os.path.normcase(str(actual_image)) == os.path.normcase(str(expected_image.resolve())), str(actual_image))
        report["pid"], report["dpr"] = owned_pid, initial["dpr"]
        check("expected_size", initial["size"] == args.size)
        gesture("slow_up", -1, 1, .020, 30, None)
        gesture("jerk_up", -1, 8, .008, 12, "jerk_up")
        gesture("jerk_down", 1, 8, .008, 12, "jerk_down")
        current = status()
        origin = native.anchor(native.window(owned_pid), current)
        before = len(events())
        native.move(*origin)
        time.sleep(.08)
        native.inject(native.DOWN)
        time.sleep(.075)
        native.inject(native.UP)
        time.sleep(.35)
        click_events = events()[before:]
        check("gentle_click_embarrassed", any(item.get("reaction") == "embarrassed" for item in click_events if item.get("event") == "trigger"))
        time.sleep(2)
        check("embarrassed_recovers", status()["drag_reaction"] == "calm")
        # Hover intentionally selects a stationary gaze frame. Move the cursor
        # away without clicking anything before requiring the Idle animation to
        # advance; a constant directed-gaze frame is not an animation failure.
        native.move(*original_cursor)
        time.sleep(.9)
        idle_status = status()
        if idle_status.get("near"):
            rect = wintypes.RECT()
            native.user.GetWindowRect(native.window(owned_pid), ctypes.byref(rect))
            away_x = min(native.user.GetSystemMetrics(76) + native.user.GetSystemMetrics(78) - 8,
                         rect.right + round(320 * current["dpr"]))
            native.move(away_x, max(8, rect.top))
            time.sleep(.9)
        check("idle_restored_after_cursor_leave", status()["state"] == "idle")
        frame_a = status()["frame"]
        time.sleep(.25)
        check("animation_continues_after_input", status()["frame"] != frame_a)
        # Runtime captures are emitted by the actual renderer after the trigger.
        captures = [path.name for path in output.glob("reaction-*.png")]
        for kind in ("jerk_up", "jerk_down", "embarrassed"):
            check("visible_capture_" + kind, any(kind in name for name in captures), str(captures))
        report["captures"] = captures
        capture_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in output.glob("reaction-*.png")}
        check("directional_and_embarrassed_images_distinct", len(set(capture_hashes.values())) >= 3)
        report["capture_sha256"] = capture_hashes
        report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        native.inject(native.UP)
        native.move(*original_cursor)
        if owned_pid is not None:
            try:
                if send_command("pet", "status", timeout=200).get("pid") == owned_pid:
                    send_command("pet", "stop", timeout=500)
            except (AttributeError, TypeError):
                pass
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            # Only the process we started. No arbitrary process enumeration kill.
            process.terminate()
        report["trace_exists"] = trace.is_file()
        timeline = [item for item in events() if item.get("event") in ("trigger", "reaction", "release", "mouse_release")]
        report["reaction_timeline"] = timeline
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
