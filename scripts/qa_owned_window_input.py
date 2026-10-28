"""Timed native engineering gestures only for this run's verified GrangerPet panel.

Extends the existing explicitly requested Windows EXE input verification. This
is not a generic desktop controller: exact known test PID, EXE and title are
required; a point belonging to another window is never pressed.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import ctypes
from ctypes import wintypes
import json
import os
import time

from PySide6.QtCore import QCoreApplication

from qa_native_input import Native
from grangerpet.ipc import send_command

ROOT = Path(__file__).resolve().parents[1]


def main():
    app = QCoreApplication([])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'output/ui-gemini-qa/window-final/report.json')
    path = parser.parse_args().report.resolve()
    report = json.loads(path.read_text())
    pid = report['pid']
    native = Native()
    previous_cursor = native.cursor()
    assert os.path.normcase(native.image(pid)) == os.path.normcase(str(ROOT / 'dist/GrangerPet.exe'))
    assert send_command('pet', 'status')['pid'] == pid
    windows = []
    @native.callback_type
    def select(hwnd, unused):
        actual = wintypes.DWORD()
        native.user.GetWindowThreadProcessId(hwnd, ctypes.byref(actual))
        if actual.value == pid:
            title = ctypes.create_unicode_buffer(256)
            native.user.GetWindowTextW(hwnd, title, 256)
            if title.value == 'GrangerPet · Поиск':
                windows.append(int(hwnd))
        return True
    native.user.EnumWindows(select, 0)
    assert len(windows) == 1
    hwnd = windows[0]
    def rect():
        value = wintypes.RECT()
        assert native.user.GetWindowRect(hwnd, ctypes.byref(value))
        return [value.left, value.top, value.right, value.bottom]
    def drag(point, delta):
        found = native.user.WindowFromPoint(wintypes.POINT(*point))
        assert int(native.user.GetAncestor(found, 2) or 0) == hwnd
        assert send_command('pet', 'status')['pid'] == pid
        native.move(*point)
        time.sleep(.10)
        native.inject(native.DOWN)
        time.sleep(.16)
        try:
            for step in range(1, 9):
                native.move(point[0] + round(delta[0] * step / 8), point[1] + round(delta[1] * step / 8))
                time.sleep(.025)
        finally:
            native.inject(native.UP)
        time.sleep(.15)
    report['preliminary_observations'] = report.pop('checks', [])
    report['checks'] = []
    report['method'] = 'Timed Windows SendInput engineering test, only exact owned GrangerPet PID/HWND'
    report['tested_at_utc'] = datetime.now(timezone.utc).isoformat()
    try:
        before = rect()
        drag((before[0] + 270, before[1] + 28), (100, 50))
        after = rect()
        report['timed_move_rectangles'] = [before, after]
        report['checks'].append({'name':'timed_native_header_move','passed':before[:2] != after[:2]})
        before = rect()
        drag((before[2] - 2, before[3] - 2), (75, 55))
        after = rect()
        report['timed_resize_rectangles'] = [before, after]
        report['checks'].append({'name':'timed_native_corner_resize','passed':(before[2]-before[0],before[3]-before[1]) != (after[2]-after[0],after[3]-after[1])})
        send_command('pet', 'qa_snapshot', {'name':'moved-resized'}, timeout=600)
        time.sleep(.15)
        report['passed'] = all(item['passed'] for item in report['checks'])
    finally:
        native.inject(native.UP)
        native.move(*previous_cursor)
        current = send_command('pet', 'status', timeout=300)
        if current and current.get('pid') == pid:
            send_command('pet', 'stop', timeout=600)
        path.write_text(json.dumps(report, indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
