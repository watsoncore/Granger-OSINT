"""Actual sprite raster fit and DOM/native geometry, without WebEngine or networking."""
import os
from types import SimpleNamespace
import uuid
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QBitmap, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from grangerpet.config import Settings, SettingsStore
from grangerpet.pet import PetWindow
import grangerpet.credentials as credentials


@pytest.fixture
def pet(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setProperty('web_desktop', False)
    monkeypatch.setenv('APPDATA', str(tmp_path))
    store = credentials.CredentialsStore(prefix='GrangerPet/UI-Fit-Test/' + uuid.uuid4().hex, directory=tmp_path / 'vault', data_root=tmp_path)
    store.portable.create('synthetic UI fixture passphrase', secrets={})
    monkeypatch.setattr(credentials, '_STORE', store)
    current = PetWindow(Settings(size=195, cursor_reaction=False), SettingsStore(tmp_path / 'settings.json'))
    current.show()
    current.frame_timer.stop()
    current.cursor_timer.stop()
    app.processEvents()
    yield current, app
    current.shutdown()
    current.panel.close()
    current.panel.deleteLater()
    current.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('size', [32, 96, 140, 195])
def test_fitted_raster_keeps_all_opaque_pixels_inside_padding_without_saving_size(pet, size):
    current, app = pet
    current._set_display_size(size)
    current._draw_frame(force=True)
    bounds = QRegion(QBitmap.fromImage(current._rendered.createAlphaMask())).boundingRect()
    assert current._display_size == size
    assert current.width() == current.height() == size + 24
    assert not bounds.isEmpty()
    assert bounds.left() > 0 and bounds.top() > 0
    assert bounds.right() < current.width() - 1 and bounds.bottom() < current.height() - 1
    assert current.settings.size == 195
    current._set_display_size(195)
    assert current.width() == 219
    assert current.settings.size == 195


def test_temporary_workspace_fit_restores_desktop_size_when_host_is_inactive(pet, monkeypatch):
    current, app = pet
    available = app.primaryScreen().availableGeometry()
    dock = QRect(available.left() + 50, available.top() + 50, 180, 160)
    state = {'active': True, 'geometry': available, 'dock': dock, 'obstructions': []}
    monkeypatch.setattr(current.panel, 'desktop_window_state', lambda: state)
    current._sync_overlay_placement()
    assert current.isVisible()
    assert dock.contains(current.frameGeometry())
    assert current._display_size == 136
    assert current.settings.size == 195
    state['active'] = False
    current._sync_overlay_placement()
    assert current._display_size == 195
    assert current.size().width() == 219


def test_native_dock_uses_exact_dom_stage_and_zoom_without_fabricated_fallback(pet):
    current, app = pet
    panel = current.panel
    class Surface(QWidget):
        def zoomFactor(self): return 1.5
    surface = Surface(panel)
    surface.setGeometry(0, 0, 760, 560)
    surface.bridge = SimpleNamespace(_dock_rect=QRect(300, 70, 200, 150))
    panel.desktop_surface = surface
    panel.show()
    app.processEvents()
    try:
        dock = panel.hermione_dock_geometry()
        assert dock.topLeft() == surface.mapToGlobal(QPoint(450, 105))
        assert dock.size().width() == 300
        assert dock.size().height() == 225
        surface.bridge._dock_rect = QRect()
        assert panel.hermione_dock_geometry().isEmpty()
    finally:
        panel.desktop_surface = None
        surface.deleteLater()
