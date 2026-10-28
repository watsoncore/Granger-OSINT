"""Compact launcher. Closing this window leaves the independent pet running."""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBitmap, QCloseEvent, QPixmap, QRegion
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from . import __version__
from .config import SettingsStore, resource_path
from .ipc import launch_process, send_command


class Launcher(QWidget):
    exit_requested = Signal()

    def __init__(self, store: SettingsStore):
        super().__init__()
        self.store = store
        self.settings = store.load()
        self.running = False
        self.start_deadline = 0.0
        self.stopping = False
        self.setWindowTitle("GrangerPet")
        self.setObjectName("launcher")
        self.setFixedWidth(360)
        self.setMinimumHeight(350)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self._build()
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1100)
        self.poll_timer.timeout.connect(self.refresh_status)
        self.poll_timer.start()
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(180)
        self.save_timer.timeout.connect(self.save_preferences)
        QTimer.singleShot(0, self.refresh_status)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(12)
        hero = QHBoxLayout()
        hero.setSpacing(12)
        self.preview = QLabel()
        self.preview.setObjectName("CharacterPreview")
        self.preview.setFixedSize(114, 152)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for candidate in ("assets/character.png", "assets/idle.png"):
            pixmap = QPixmap(str(resource_path(candidate)))
            if not pixmap.isNull():
                if pixmap.width() > pixmap.height() * 2:
                    pixmap = pixmap.copy(0, 0, 256, 256)
                bounds = QRegion(QBitmap.fromImage(pixmap.toImage().createAlphaMask())).boundingRect()
                if not bounds.isEmpty():
                    pixmap = pixmap.copy(bounds)
                self.preview.setPixmap(pixmap.scaled(108, 148, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                break
        hero.addWidget(self.preview)
        words = QVBoxLayout()
        words.setSpacing(6)
        words.addStretch()
        title = QLabel("GrangerPet")
        title.setObjectName("LauncherTitle")
        words.addWidget(title)
        caption = QLabel("Гермиона на рабочем столе")
        caption.setWordWrap(True)
        caption.setObjectName("Muted")
        words.addWidget(caption)
        self.status = QLabel("Проверяю состояние…")
        self.status.setWordWrap(True)
        self.status.setObjectName("ProcessStatus")
        words.addWidget(self.status)
        words.addStretch()
        hero.addLayout(words, 1)
        layout.addLayout(hero)
        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.start_button = QPushButton("Запустить Гермиону")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setMinimumHeight(36)
        self.start_button.clicked.connect(self.start_pet)
        self.stop_button = QPushButton("Остановить")
        self.stop_button.setMinimumHeight(36)
        self.stop_button.clicked.connect(self.stop_pet)
        actions.addWidget(self.start_button, 1)
        actions.addWidget(self.stop_button)
        layout.addLayout(actions)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Размер"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setObjectName("sizeSlider")
        self.size_slider.setRange(100, 195)
        self.size_slider.setSingleStep(1)
        self.size_slider.setValue(self.settings.size)
        self.size_slider.valueChanged.connect(self._size_changed)
        size_row.addWidget(self.size_slider, 1)
        self.size_label = QLabel(f"{self.size_slider.value()} px")
        self.size_label.setObjectName("Muted")
        self.size_label.setMinimumWidth(44)
        size_row.addWidget(self.size_label)
        layout.addLayout(size_row)
        self.preferences_toggle = QToolButton()
        self.preferences_toggle.setObjectName("Disclosure")
        self.preferences_toggle.setText("Поведение и анимация")
        self.preferences_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.preferences_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.preferences_toggle.setCheckable(True)
        layout.addWidget(self.preferences_toggle)
        preferences = QWidget()
        preferences.hide()
        options = QHBoxLayout(preferences)
        options.setContentsMargins(0, 0, 0, 0)
        self.reaction_box = QCheckBox("Реакция на курсор")
        self.reaction_box.setChecked(self.settings.cursor_reaction)
        self.reaction_box.toggled.connect(self._preferences_changed)
        options.addWidget(self.reaction_box, 1)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(8, 30)
        self.fps_spin.setSuffix(" к/с")
        self.fps_spin.setValue(self.settings.fps)
        self.fps_spin.setFixedWidth(79)
        self.fps_spin.valueChanged.connect(self._preferences_changed)
        options.addWidget(self.fps_spin)
        layout.addWidget(preferences)
        self.preferences_toggle.toggled.connect(preferences.setVisible)
        self.preferences_toggle.toggled.connect(lambda checked: self.preferences_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow))
        self.preferences_toggle.toggled.connect(lambda: QTimer.singleShot(0, self.adjustSize))
        tip = QLabel("Клик — поиск. Потяните за воротник, чтобы перенести.")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        footer = QHBoxLayout()
        version = QLabel(f"v{__version__}")
        version.setObjectName("SmallMuted")
        footer.addWidget(version, 1)
        self.exit_button = QPushButton("Выйти")
        self.exit_button.setObjectName("QuietButton")
        self.exit_button.setToolTip("Закрыть Launcher и Гермиону")
        self.exit_button.clicked.connect(self.exit_all)
        footer.addWidget(self.exit_button)
        layout.addLayout(footer)

    def _size_changed(self, value):
        self.size_label.setText(f"{value} px")
        self._preferences_changed()

    def _preferences_changed(self, *_):
        self.save_timer.start()

    def save_preferences(self):
        # Read the most recent position/API fields written by the independent pet.
        settings = self.store.load()
        settings.size = self.size_slider.value()
        settings.fps = self.fps_spin.value()
        settings.cursor_reaction = self.reaction_box.isChecked()
        try:
            self.store.save(settings)
        except OSError:
            logging.getLogger(__name__).exception("Could not save launcher preferences")
            self.status.setText("Не удалось сохранить настройки")
            return
        self.settings = settings
        if self.running:
            send_command("pet", "settings", {name: getattr(settings, name) for name in ('size', 'fps', 'cursor_reaction')})

    def refresh_status(self):
        response = send_command("pet", "status", timeout=80)
        self.running = bool(response and response.get("ok") and response.get("running"))
        starting = bool(self.start_deadline and time.monotonic() < self.start_deadline)
        if self.running:
            self.start_deadline = 0.0
            self.status.setText("●  Гермиона на рабочем столе")
        elif starting:
            self.status.setText("Запускаю Гермиону…")
        elif self.start_deadline:
            self.status.setText("Запуск не подтверждён. Подробности — в logs.")
            self.start_deadline = 0.0
        elif self.stopping:
            self.status.setText("Гермиона остановлена")
            self.stopping = False
        else:
            self.status.setText("Гермиона ещё не запущена")
        self.start_button.setEnabled(not self.running and not starting)
        self.stop_button.setEnabled(self.running)

    def start_pet(self):
        self.save_preferences()
        if send_command("pet", "status", timeout=100):
            self.refresh_status()
            return
        self.start_button.setEnabled(False)
        self.start_deadline = time.monotonic() + 35.0
        self.status.setText("Запускаю Гермиону…")
        if not launch_process(pet=True):
            self.start_deadline = 0.0
            self.start_button.setEnabled(True)
            self.status.setText("Не удалось создать процесс Гермионы")
        else:
            QTimer.singleShot(500, self.refresh_status)

    def stop_pet(self):
        response = send_command("pet", "stop", timeout=250)
        self.stopping = bool(response and response.get("ok"))
        self.status.setText("Останавливаю Гермиону…" if self.stopping else "Гермиона уже остановлена")
        self.stop_button.setEnabled(False)
        QTimer.singleShot(300, self.refresh_status)

    def exit_all(self):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self.save_preferences()
        send_command("pet", "stop", timeout=350)
        self.exit_requested.emit()

    def focus_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self.save_preferences()
        event.accept()
        self.exit_requested.emit()
