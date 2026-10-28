import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from grangerpet.config import Settings, SettingsStore
from grangerpet.pet import PetWindow
from grangerpet.theme import STYLE


def test_compact_context_menu_toggles_attention_and_opens_search(tmp_path):
    app = QApplication.instance() or QApplication([])
    # Source-widget tests queue deleteLater without running QApplication.exec.
    # Dispose previous fixtures before repolishing, and mirror production's
    # one-time application style instead of repolishing the same style twice.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    if app.styleSheet() != STYLE:
        app.setStyleSheet(STYLE)
    pet = PetWindow(Settings(), SettingsStore(tmp_path / "settings.json"))
    pet.show()
    app.processEvents()
    try:
        for title in ("Реагировать на курсор", "Открыть поиск"):
            clicked = []
            def choose(title=title):
                menu = app.activePopupWidget()
                assert isinstance(menu, QMenu)
                action = next(action for action in menu.actions() if action.text() == title)
                rect = menu.actionGeometry(action)
                assert rect.height() <= 32
                clicked.append(title)
                QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=rect.center())
            QTimer.singleShot(40, choose)
            QTimer.singleShot(1000, lambda: app.activePopupWidget().close() if app.activePopupWidget() else None)
            point = QPoint(pet.width() // 2, pet.height() // 2)
            pet.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, pet.mapToGlobal(point)))
            assert clicked == [title]
        assert not pet.settings.cursor_reaction
        assert pet.panel.isVisible()
    finally:
        pet.shutdown()
        pet.panel.deleteLater()
        pet.deleteLater()
        app.processEvents()
