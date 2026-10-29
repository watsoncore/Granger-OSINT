"""Bounded, non-modal error reporting shared by Qt controllers.

Only exception type, stack locations and sanitized text enter the log. Repeated
failures update one notification; reporting never calls a dialog or a worker.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import traceback as traceback_module

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from .agent_evidence import redact


class ErrorCenter(QObject):
    changed = Signal()
    taskFailed = Signal(str)

    def __init__(self, parent=None, *, clock=time.monotonic):
        super().__init__(parent)
        self._clock = clock
        self._lock = threading.RLock()
        self._rows = {}
        self._secrets = set()
        self._reporting = False

    def register_secrets(self, values):
        with self._lock:
            self._secrets.update(value for value in values if isinstance(value, str) and value)

    def report(self, kind, value, tb=None, *, operation='application', stop_task=False):
        frames = traceback_module.extract_tb(tb) if tb is not None else []
        signature = (kind.__module__, kind.__name__, operation,
                     tuple((frame.filename, frame.name, frame.lineno) for frame in frames))
        fingerprint = hashlib.sha256(repr(signature).encode('utf-8')).hexdigest()[:20]
        now = self._clock()
        with self._lock:
            # A logging handler failure cannot recurse through the exception hook.
            if self._reporting:
                return fingerprint
            self._reporting = True
            try:
                existing = self._rows.get(fingerprint)
                if existing:
                    existing['count'] += 1
                    existing['last_seen'] = now
                    first = False
                else:
                    if len(self._rows) >= 32:
                        self._rows.pop(next(iter(self._rows)))
                    self._rows[fingerprint] = {
                        'id': fingerprint, 'operation': operation, 'count': 1,
                        'first_seen': now, 'last_seen': now, 'dismissed': False,
                        'message': 'Операция остановлена из-за ошибки. Полученные данные сохранены. Можно открыть другое расследование.',
                        'code': kind.__name__,
                    }
                    first = True
                if first:
                    message = redact(str(value), tuple(self._secrets))
                    stack = ''.join(traceback_module.format_list(frames))
                    for secret in self._secrets:
                        stack = stack.replace(secret, '[скрыто]')
                    logging.getLogger('grangerpet.errors').error(
                        'Error %s operation=%s type=%s\n%s%s: %s',
                        fingerprint, operation, kind.__name__, stack, kind.__name__, message)
            finally:
                self._reporting = False
        # Signal delivery is queued to the owning QObject, including reports
        # originating in a worker. No timer captures a QWidget here.
        if first:
            if stop_task:
                self.taskFailed.emit(fingerprint)
            self.changed.emit()
        return fingerprint

    def dismiss(self, identifier):
        with self._lock:
            row = self._rows.get(identifier)
            if row:
                row['dismissed'] = True
        self.changed.emit()

    def snapshot(self):
        with self._lock:
            return [dict(row) for row in self._rows.values() if not row['dismissed']][-4:]


def error_center():
    app = QApplication.instance()
    if app is None:
        return None
    center = getattr(app, '_granger_errors', None)
    if center is None:
        center = ErrorCenter(app)
        app._granger_errors = center
    return center


def report_exception(error, *, operation='application', stop_task=False):
    center = error_center()
    if center is not None:
        return center.report(type(error), error, error.__traceback__, operation=operation, stop_task=stop_task)
    logging.getLogger('grangerpet.errors').error('Operation %s failed: %s', operation, type(error).__name__)
    return ''
