"""Actual Qt maximized/fullscreen state transitions; no desktop input injection."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from grangerpet.window_chrome import FramelessWindow, WindowHeader


def test_web_desktop_escape_reaches_focused_control_before_window_command():
    from PySide6.QtWidgets import QLineEdit
    app=QApplication.instance() or QApplication([])
    previous=app.property('web_desktop')
    class Editor(QLineEdit):
        escapes=0
        def keyPressEvent(self,event):
            if event.key()==Qt.Key.Key_Escape:
                self.escapes+=1;event.accept();return
            super().keyPressEvent(event)
    window=None
    try:
        app.setProperty('web_desktop',True)
        window=FramelessWindow();window.enable_window_modes();window.resize(620,610)
        editor=Editor(window);editor.resize(300,40)
        window.show();window.activateWindow();editor.setFocus();QTest.qWait(80)
        QTest.keyClick(editor,Qt.Key.Key_Escape);app.processEvents()
        assert editor.escapes==1
        window.toggle_fullscreen();QTest.qWait(80);editor.setFocus()
        QTest.keyClick(editor,Qt.Key.Key_Escape);app.processEvents()
        assert editor.escapes==2 and window.isFullScreen()
    finally:
        if window is not None:window.close()
        app.setProperty('web_desktop',previous)


def test_maximize_restore_fullscreen_and_visible_pet():
    app=QApplication.instance() or QApplication([])
    pet=QWidget(None,Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint);pet.resize(100,100);pet.show()
    window=FramelessWindow();window.setMinimumSize(460,420);window.setGeometry(50,50,620,610)
    header=WindowHeader(window,'GrangerPet',enable_window_modes=True)
    layout=QVBoxLayout(window);layout.addWidget(header);window.show();app.processEvents()
    normal=window.geometry()
    header.maximize_button.click();app.processEvents();assert window.isMaximized() and pet.isVisible()
    header.maximize_button.click();app.processEvents();assert not window.isMaximized() and window.geometry()==normal
    window.toggle_fullscreen();app.processEvents();assert window.isFullScreen() and pet.isVisible()
    window.toggle_fullscreen();app.processEvents();assert not window.isFullScreen() and window.geometry()==normal
    window.toggle_maximized();window.toggle_fullscreen();app.processEvents();assert window.isFullScreen()
    window.toggle_fullscreen();app.processEvents();assert window.isMaximized()
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    window.close();pet.close();app.processEvents()


def test_header_double_click_restores_window():
    app=QApplication.instance() or QApplication([])
    window=FramelessWindow();window.resize(620,610);header=WindowHeader(window,'GrangerPet',enable_window_modes=True)
    window.show();header.show();app.processEvents()
    QTest.mouseDClick(header,Qt.MouseButton.LeftButton);app.processEvents();assert window.isMaximized()
    QTest.mouseDClick(header,Qt.MouseButton.LeftButton);app.processEvents();assert not window.isMaximized()
    window.close()


def test_native_windows_fullscreen_restore_survives_delayed_size_messages():
    """A native child event loop catches the Windows-only delayed state reset."""
    if sys.platform != 'win32':
        import pytest
        pytest.skip('Native Windows state transitions require Windows')
    code = r'''
import json
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QVBoxLayout
from grangerpet.window_chrome import FramelessWindow, WindowHeader
app=QApplication([])
window=FramelessWindow();window.resize(620,610)
layout=QVBoxLayout(window);layout.addWidget(WindowHeader(window,'GrangerPet window-mode test',enable_window_modes=True))
window.show()
checks=[]
def restored():
    checks.append(window.isMaximized() and not window.isFullScreen())
    window.showNormal()
def normal_full():
    checks.append(not window.isMaximized() and not window.isFullScreen())
    checks.append(window.width()==620 and window.height()==610)
    window.setGeometry(80,70,620,610)
    window.toggle_fullscreen()
def final():
    checks.append(not window.isFullScreen() and not window.isMaximized())
    checks.append(window.width()==620 and window.height()==610)
    print(json.dumps({'native_windows_checks':checks}),flush=True)
    app.exit(0 if all(checks) else 2)
QTimer.singleShot(150,window.showMaximized)
QTimer.singleShot(450,window.toggle_fullscreen)
QTimer.singleShot(850,window.toggle_fullscreen)
QTimer.singleShot(1500,restored)
QTimer.singleShot(1850,normal_full)
QTimer.singleShot(2200,window.toggle_fullscreen)
QTimer.singleShot(2850,final)
QTimer.singleShot(7000,lambda:app.exit(3))
app.exec()
'''
    environment=os.environ.copy()
    environment.pop('QT_QPA_PLATFORM',None)
    result=subprocess.run([sys.executable,'-u','-c',code],cwd=Path(__file__).resolve().parents[1],
        env=environment,capture_output=True,text=True,encoding='utf-8',timeout=12)
    assert result.returncode==0, result.stdout+'\n'+result.stderr
    assert '"native_windows_checks": [true, true, true, true, true]' in result.stdout
