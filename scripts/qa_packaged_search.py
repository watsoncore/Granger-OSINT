"""Bounded live search verification through the packaged application's own IPC.

This does not inject UI input or substitute results. The EXE runs its real panel,
router, controller and existing source workers; its own QA-only snapshot command
captures the actual rendered widgets. No pre-existing GrangerPet is touched.
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
TON = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"


def process_image(pid: int) -> Path:
    """Read only the exact process identified by our own application's IPC."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise RuntimeError("Cannot verify the spawned pet's executable")
    try:
        size = wintypes.DWORD(32768)
        value = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, value, ctypes.byref(size)):
            raise RuntimeError("Cannot read the spawned pet's executable")
        return Path(value.value).resolve()
    finally:
        kernel.CloseHandle(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=ROOT / "dist/GrangerPet.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "output/search-overhaul-qa/exe-search-final")
    parser.add_argument("--keep-open", action="store_true", help="Leave only this owned pet open for a follow-up visual inspection")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This packaged verification requires Windows")
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    app = QCoreApplication.instance() or QCoreApplication([])
    if send_command("pet", "status", timeout=200) or send_command("launcher", "status", timeout=200):
        raise SystemExit("Close GrangerPet before this isolated test; existing instances are never touched")
    exe, output = args.exe.resolve(), args.output.resolve()
    if not exe.is_file():
        raise SystemExit(f"EXE not found: {exe}")
    if (output / "report.json").exists() or (output / "interaction.jsonl").exists():
        raise SystemExit("Use a fresh output folder to preserve earlier attempts")
    output.mkdir(parents=True, exist_ok=True)
    profile = output / "appdata/GrangerPet"
    profile.mkdir(parents=True, exist_ok=True)
    settings = Settings(size=195, x=600, y=320, source_root=str(ROOT), request_limit=20,
                        search_timeout=35, telegram_api_id="", api_cx="", ai_provider="none")
    (profile / "settings.json").write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    environment = os.environ.copy()
    environment["APPDATA"] = str(output / "appdata")
    environment["GRANGERPET_INTERACTION_TRACE"] = str(output / "interaction.jsonl")
    environment.pop("QT_QPA_PLATFORM", None)
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(),
              "method": "Real packaged EXE panel/controller/worker path through same-user application IPC; actual widget grabs, no mock results",
              "exe": str(exe), "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
              "window_mode": "QA enumerable pet Qt.Window; search UI and source handlers unchanged",
              "limits": {"request_limit": 20, "search_timeout_s": 35, "total_deadline_s": 195},
              "credential_scope": "No credentials created, modified or exported. Telegram API ID deliberately empty, so no authorized Telegram request is possible. The harness does not inspect Windows secret storage.",
              "checks": [], "searches": [], "screenshots": []}
    process = subprocess.Popen([str(exe), "--pet", "--interaction-qa"], cwd=ROOT, env=environment,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    owned_pid = None
    leave_open = False
    started = time.monotonic()

    def check(name, condition, detail=None):
        report["checks"].append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(f"{name}: {detail}")

    def status():
        if time.monotonic() - started > 195:
            raise TimeoutError("Packaged QA exceeded its bounded total deadline")
        value = send_command("pet", "status", timeout=600)
        if not value or not value.get("running") or (owned_pid is not None and value.get("pid") != owned_pid):
            raise RuntimeError("The owned pet no longer answers; no other process will be touched")
        return value

    def command(name, payload=None):
        status()  # Verify identity before every mutating application command.
        value = send_command("pet", name, payload, timeout=600)
        if not value or not value.get("ok"):
            raise RuntimeError(f"Application command rejected: {name}: {value}")

    def snapshot(name):
        command("qa_snapshot", {"name": name})
        path = output / f"{name}-search.png"
        deadline = time.monotonic() + 5
        while not path.is_file() and time.monotonic() < deadline:
            time.sleep(.05)
        check(f"screenshot_{name}", path.is_file())
        report["screenshots"].append(path.name)

    def sample(value, origin):
        return {"elapsed_s": round(time.monotonic() - origin, 3), **{key: value.get(key) for key in
                ("searching", "search_phase", "search_status", "result_count", "result_confirmed", "state", "frame")}}

    def search(name, text, kind, deadline_seconds=65):
        before = status()
        origin = time.monotonic()
        entry = {"name": name, "input": text, "chosen_kind": kind, "samples": []}
        report["searches"].append(entry)
        command("search", {"text": text, "kind": kind})
        observed_start = False
        prior_signature = None
        while time.monotonic() - origin < deadline_seconds:
            time.sleep(.15)
            current = status()
            observed_start |= bool(current.get("searching"))
            signature = tuple(current.get(key) for key in ("searching", "search_phase", "search_status", "result_count", "result_confirmed"))
            if signature != prior_signature:
                entry["samples"].append(sample(current, origin))
                prior_signature = signature
            # A fast auth-required response may complete between two samples.
            changed = current.get("search_phase") != before.get("search_phase") or current.get("search_status") != before.get("search_status")
            if not current.get("searching") and (observed_start or changed):
                entry["final"] = sample(current, origin)
                entry["live_findings_observed"] = bool(current.get("result_count", 0))
                check(name + "_finished", current.get("search_phase") not in ("failed", "needs_clarification", "cancelled"), entry["final"])
                check(name + "_counter_range", 0 <= current.get("result_confirmed", 0) <= current.get("result_count", 0), entry["final"])
                snapshot(name)
                print(json.dumps({"search": name, "final": entry["final"]}, ensure_ascii=False), flush=True)
                return current
        raise TimeoutError(f"Live EXE search did not finish in {deadline_seconds} seconds: {name}")

    def observe_idle_animation():
        manifest = json.loads((ROOT / "grangerpet/assets/animations.json").read_text(encoding="utf-8"))
        blink_frames = set(manifest.get("features", {}).get("blink_frames", {}).get("idle", []))
        observation = {"method": "Observe actual packaged Idle frame status and immediately request actual renderer PNGs; no input or forced state",
                       "blink_frames_from_manifest": sorted(blink_frames), "captures": [], "idle_frames_seen": [],
                       "capture_timing_limit": "Status and renderer grab are separate local IPC commands; before/after frame values are recorded for visual verification."}
        report["idle_animation"] = observation
        deadline = time.monotonic() + 8
        seen_frames, captures, first_open = set(), set(), None
        states = set()
        while time.monotonic() < deadline:
            current = status()
            states.add(current.get("state"))
            frame = current.get("frame")
            if current.get("state") != "idle":
                time.sleep(.025)
                continue
            seen_frames.add(frame)
            name = None
            if frame not in blink_frames and "idle-open" not in captures:
                name, first_open = "idle-open", frame
            elif frame == min(blink_frames, default=-1) and "idle-blink" not in captures:
                # First closed frame leaves the entire closed-eye interval for
                # the queued renderer grab, rather than targeting its last tick.
                name = "idle-blink"
            elif frame not in blink_frames and first_open is not None and abs(frame - first_open) >= 12 and "idle-breath" not in captures:
                name = "idle-breath"
            if name:
                snapshot(name)
                after = status()
                path = output / f"{name}-pet.png"
                observation["captures"].append({"name": path.name, "frame_before": frame,
                    "frame_after": after.get("frame"), "state_after": after.get("state"),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
                captures.add(name)
            if {"idle-open", "idle-blink", "idle-breath"}.issubset(captures):
                break
            time.sleep(.012)
        observation["idle_frames_seen"] = sorted(seen_frames)
        observation["states_seen"] = sorted(value for value in states if value)
        observation["blink_observed_in_exe"] = bool(seen_frames.intersection(blink_frames))
        observation["verified"] = len(captures) == 3
        if observation["verified"]:
            check("exe_idle_frames_advance", len(seen_frames) > 1)
            hashes = {item["sha256"] for item in observation["captures"]}
            check("exe_idle_open_blink_breath_images_distinct", len(hashes) == 3)
        else:
            observation["unverified_reason"] = "No complete Idle/open/blink/breath capture set within 8 seconds; cursor hover or another real activity may have priority. No animation success is inferred."

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
        report["pid"] = owned_pid
        check("exact_owned_process_image", os.path.normcase(str(process_image(owned_pid))) == os.path.normcase(str(exe)))
        command("panel")
        time.sleep(.35)
        check("new_panel_visible", status().get("panel_visible"))
        snapshot("initial-empty")
        search("profiles-solvnox", "solvnox", "username")
        search("ton-auto-gansar", TON, "auto")

        origin = time.monotonic()
        command("search", {"text": TON, "kind": "auto"})
        deadline = time.monotonic() + 4
        current = status()
        while not current.get("searching") and time.monotonic() < deadline:
            time.sleep(.05)
            current = status()
        check("cancellation_started_actual_search", current.get("searching"), sample(current, origin))
        time.sleep(.6)
        command("cancel_search")
        time.sleep(.25)
        cancelled = status()
        check("cancellation_stops_search", not cancelled.get("searching") and cancelled.get("search_phase") == "cancelled", sample(cancelled, origin))
        cancelled_count = cancelled.get("result_count")
        time.sleep(1.5)
        after = status()
        check("cancelled_generation_no_late_results", after.get("result_count") == cancelled_count and after.get("search_phase") == "cancelled", sample(after, origin))
        report["cancellation"] = {"before": sample(cancelled, origin), "after": sample(after, origin)}
        snapshot("cancelled")
        telegram = search("telegram-auth-required", "https://t.me/telegram", "auto", deadline_seconds=20)
        check("following_query_has_no_stale_ton_findings", telegram.get("result_count") == 0, sample(telegram, origin))
        time.sleep(2)
        check("following_query_remains_stable", status().get("result_count") == 0)
        observe_idle_animation()
        report["passed"] = True
        leave_open = args.keep_open
    except Exception as error:
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if not leave_open:
            if owned_pid is not None:
                current = send_command("pet", "status", timeout=250)
                if current and current.get("pid") == owned_pid:
                    send_command("pet", "stop", timeout=600)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Popen is the exact wrapper we spawned, never an enumerated app.
                process.terminate()
                process.wait(timeout=5)
            report["process_closed"] = process.poll() is not None
        else:
            report["left_open_for_visual_review"] = {"pid": owned_pid, "wrapper_pid": process.pid}
        report["elapsed_s"] = round(time.monotonic() - started, 3)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report.get("passed", False), "error": report.get("error"),
                          "checks": len(report["checks"]), "report": str(output / "report.json")}, ensure_ascii=False), flush=True)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
