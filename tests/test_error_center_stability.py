import json
import logging
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QMessageBox
from grangerpet.errors import ErrorCenter


def test_one_hundred_identical_exceptions_have_one_notification_and_one_log(caplog, monkeypatch):
    app = QApplication.instance() or QApplication([])
    center = ErrorCenter()
    center.register_secrets(('PRIVATE-FIXTURE-KEY',))
    notifications, stopped = [], []
    center.changed.connect(lambda: notifications.append(True))
    center.taskFailed.connect(stopped.append)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: (_ for _ in ()).throw(AssertionError('modal error')))
    for _ in range(100):
        try:
            raise AttributeError('PRIVATE-FIXTURE-KEY malformed mapping')
        except AttributeError as error:
            center.report(type(error), error, error.__traceback__, operation='fixture', stop_task=True)
    assert len(notifications) == len(stopped) == 1
    assert center.snapshot()[0]['count'] == 100
    assert 'PRIVATE-FIXTURE-KEY' not in caplog.text
    assert sum('operation=fixture' in record.message for record in caplog.records) == 1
    center.dismiss(stopped[0])
    assert center.snapshot() == []


def test_logging_attaches_actual_file_even_if_dependency_configured_root(tmp_path, monkeypatch):
    import grangerpet.app as module
    root = logging.getLogger()
    old_hook = sys.excepthook
    monkeypatch.setattr(module, 'data_directory', lambda: tmp_path)
    marker = logging.StreamHandler()
    root.addHandler(marker)
    try:
        module._setup_logging()
        logging.getLogger('grangerpet.test').warning('safe diagnostic fixture')
        for handler in root.handlers:
            handler.flush()
        assert 'safe diagnostic fixture' in (tmp_path / 'logs' / 'launcher.log').read_text(encoding='utf-8')
    finally:
        sys.excepthook = old_hook
        root.removeHandler(marker)
        for handler in list(root.handlers):
            if getattr(handler, '_granger_log', False):
                root.removeHandler(handler)
                handler.close()


def test_failed_snapshot_is_not_retried_on_every_signal_and_other_conversation_can_open(tmp_path, monkeypatch):
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.panel import OsintPanel
    from grangerpet.desktop_bridge import DesktopBridge
    app = QApplication.instance() or QApplication([])
    for module in ('grangerpet.panel', 'grangerpet.connections', 'grangerpet.ai_keys'):
        monkeypatch.setattr(module + '.get_secret', lambda name: '')
    monkeypatch.setattr('grangerpet.desktop_bridge.resolve_deepseek_key', lambda: '')
    monkeypatch.setattr('grangerpet.desktop_bridge.credential_presence', lambda **_: {})
    host = OsintPanel(Settings(), SettingsStore(tmp_path / 'settings.json'))
    bridge = DesktopBridge(host)
    packets, calls = [], []
    bridge.stateChanged.connect(lambda raw: packets.append(json.loads(raw)))
    original = bridge.snapshot
    def broken():
        calls.append(True)
        return 'bad'.get('field')
    monkeypatch.setattr(bridge, 'snapshot', broken)
    try:
        for _ in range(50):
            bridge.publish(force=True)
        assert len(calls) == 1
        assert packets[-1]['busy'] is False and packets[-1]['errors']
        host.chat_widget.new_conversation()
        monkeypatch.setattr(bridge, 'snapshot', original)
        bridge.publish(force=True)
        assert packets[-1]['conversation_id'] == host.chat_widget.conversation_id
        assert not host.chat_widget.busy
    finally:
        bridge.shutdown()
        host.shutdown()
        host.deleteLater()
        app.processEvents()
