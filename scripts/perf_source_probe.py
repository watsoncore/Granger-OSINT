"""Opt-in numeric instrumentation of the ordinary source application.

Set GRANGERPET_PERF_OUTPUT to an isolated QA JSON path, then launch this
wrapper with the same flags as main.py, for example --pet --interaction-qa.
Production modules are monkeypatched only in this process; no provider,
messages, credentials, filesystem paths or other applications are sampled.

Counters describe Python calls and QWidget paint events, not GPU/compositor
FPS. Timing includes this wrapper's small perf_counter/lock overhead. The
latest cumulative sample is atomically replaced once per second and at exit.
Use the matching uninstrumented EXE for process-resource measurements.
"""
from __future__ import annotations

import argparse
import functools
import gc
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class NumericProbe:
    """Record fixed operation names and numeric totals only."""

    def __init__(self, output):
        self.output = Path(output).resolve()
        self.started = time.perf_counter_ns()
        self.lock = threading.RLock()
        self.operations = {}
        self.active_jobs = 0
        self.peak_jobs = 0
        self.gc_started = {}
        self.samples = 0

    def record(self, name, duration=0, count=1):
        with self.lock:
            row = self.operations.setdefault(name, {'calls': 0, 'total_ns': 0, 'max_ns': 0})
            row['calls'] += count
            row['total_ns'] += duration
            row['max_ns'] = max(row['max_ns'], duration)

    def gc_callback(self, phase, info):
        generation = int(info.get('generation', 0))
        now = time.perf_counter_ns()
        if phase == 'start':
            self.gc_started[generation] = now
        elif phase == 'stop':
            start = self.gc_started.pop(generation, now)
            self.record('gc_generation_' + str(generation), now-start)
            self.record('gc_collected_objects', count=int(info.get('collected', 0)))
            self.record('gc_uncollectable_objects', count=int(info.get('uncollectable', 0)))

    def flush(self):
        with self.lock:
            self.samples += 1
            value = {
                'schema_version': 1,
                'pid': os.getpid(),
                'elapsed_ns': time.perf_counter_ns()-self.started,
                'samples': self.samples,
                'active_ui_jobs': self.active_jobs,
                'peak_ui_jobs': self.peak_jobs,
                'gc_enabled': int(gc.isenabled()),
                'operations': {key: dict(row) for key, row in self.operations.items()},
            }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output.with_suffix(self.output.suffix + '.pending')
        temporary.write_text(json.dumps(value, separators=(',', ':')), encoding='utf-8')
        temporary.replace(self.output)

    def wrap(self, cls, method, label, *, rendered=False, job=False):
        original = getattr(cls, method)

        @functools.wraps(original)
        def measured(instance, *args, **kwargs):
            before = instance._rendered.cacheKey() if rendered else None
            if job:
                with self.lock:
                    self.active_jobs += 1
                    self.peak_jobs = max(self.peak_jobs, self.active_jobs)
            started = time.perf_counter_ns()
            try:
                return original(instance, *args, **kwargs)
            finally:
                self.record(label, time.perf_counter_ns()-started)
                if rendered and instance._rendered.cacheKey() != before:
                    self.record('pet_rendered_image_changes')
                if job:
                    with self.lock:
                        self.active_jobs -= 1

        setattr(cls, method, measured)


def install(probe):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from grangerpet import app as application
    from grangerpet.desktop_bridge import DesktopBridge
    from grangerpet.pet import PetWindow
    from grangerpet.ui_jobs import UiJob

    for method, label in (
        ('_tick', 'pet_tick'), ('paintEvent', 'pet_paint_event'),
        ('setMask', 'pet_set_mask'), ('_poll_cursor', 'pet_cursor_poll'),
        ('_sync_overlay_placement', 'pet_overlay_sync'),
    ):
        probe.wrap(PetWindow, method, label)
    probe.wrap(PetWindow, '_draw_frame', 'pet_draw_frame', rendered=True)
    for method, label in (
        ('snapshot', 'bridge_snapshot'), ('publish', 'bridge_publish'),
        ('_history', 'bridge_history'),
    ):
        probe.wrap(DesktopBridge, method, label)
    probe.wrap(UiJob, '__init__', 'ui_jobs_created')
    probe.wrap(UiJob, '_run', 'ui_jobs_run', job=True)
    original_bridge_init = DesktopBridge.__init__

    @functools.wraps(original_bridge_init)
    def bridge_init(bridge, *args, **kwargs):
        original_bridge_init(bridge, *args, **kwargs)
        def state_emitted(raw):
            probe.record('bridge_state_emissions')
            probe.record('bridge_state_characters', count=len(raw))
        bridge.stateChanged.connect(state_emitted)
        probe.record('bridges_created')
    DesktopBridge.__init__ = bridge_init

    class ProbeApplication(QApplication):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._numeric_probe_timer = QTimer(self)
            self._numeric_probe_timer.setInterval(1000)
            self._numeric_probe_timer.timeout.connect(probe.flush)
            self._numeric_probe_timer.start()
            self.aboutToQuit.connect(probe.flush)

        def notify(self, watched, event):
            if os.environ.get('GRANGERPET_PERF_NOTIFY') != '1':
                return super().notify(watched, event)
            # Fixed class/type labels only: no objectName, user text, URLs,
            # widget contents or event payloads. Durations include nested Qt
            # delivery and must not be summed as independent CPU accounting.
            label = 'qt_notify_' + watched.metaObject().className() + '_' + str(int(event.type()))
            started = time.perf_counter_ns()
            try:
                return super().notify(watched, event)
            finally:
                probe.record(label, time.perf_counter_ns()-started)
    application.QApplication = ProbeApplication


def main():
    output = os.environ.get('GRANGERPET_PERF_OUTPUT')
    if not output:
        raise SystemExit('Set GRANGERPET_PERF_OUTPUT to enable the numeric QA probe')
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--project-root', type=Path, default=ROOT)
    options, app_arguments = parser.parse_known_args()
    project_root = options.project_root.resolve()
    if not (project_root/'grangerpet/app.py').is_file():
        raise SystemExit('The source project must contain grangerpet/app.py')
    sys.path.insert(0, str(project_root))
    probe = NumericProbe(output)
    install(probe)
    gc.callbacks.append(probe.gc_callback)
    from grangerpet.app import main as application_main
    try:
        return application_main(app_arguments)
    finally:
        if probe.gc_callback in gc.callbacks:
            gc.callbacks.remove(probe.gc_callback)
        probe.flush()


if __name__ == '__main__':
    raise SystemExit(main())
