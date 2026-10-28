"""Collect Python/Qt cycles on the GUI thread, never inside an HTTP worker.

CPython can run cyclic collection in whichever thread crosses its allocation
threshold. A cycle owning a QWidget must instead be finalized in Qt's thread.
"""
import gc

from PySide6.QtCore import QCoreApplication, QThread, QTimer


def ensure_gui_collection():
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() != app.thread() or hasattr(app, '_python_cycle_timer'):
        return
    previously_enabled = gc.isenabled()
    if not previously_enabled:
        return
    gc.disable()
    timer = QTimer(app)
    timer.setInterval(1500)
    app._python_cycle_timer = timer
    ticks = [0]
    def collect():
        ticks[0] += 1
        gc.collect(2 if ticks[0] % 20 == 0 else 0)
    timer.timeout.connect(collect)
    def finish():
        timer.stop()
        gc.collect()
        if previously_enabled:
            gc.enable()
    app.aboutToQuit.connect(finish)
    timer.start()
