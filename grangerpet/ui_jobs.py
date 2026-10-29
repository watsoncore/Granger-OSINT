"""Cancellable daemon work with queued Qt delivery; never holds process exit open."""
import sys
import threading
from PySide6.QtCore import QObject, Signal


class UiJob(QObject):
    done = Signal(object, str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        from .gui_lifecycle import ensure_gui_collection
        ensure_gui_collection()
        self.function = function
        self.cancelled = threading.Event()

    def start(self):
        threading.Thread(target=self._run, name="GrangerPetConnection", daemon=True).start()

    def _run(self):
        try:
            result, error = self.function(), ""
        except Exception as exc:
            result, error = None, str(exc) if exc.__class__.__module__.startswith("grangerpet") else "Не удалось выполнить запрос к сервису."
        finally:
            # Release captured files/passwords/large payloads even when a
            # cancelled job suppresses its queued GUI result.
            self.function = lambda: None
        if not self.cancelled.is_set() and not sys.is_finalizing():
            try:
                self.done.emit(result, error)
            except RuntimeError:
                pass

    def cancel(self):
        self.cancelled.set()
