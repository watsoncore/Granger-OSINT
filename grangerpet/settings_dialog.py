"""Settings live in their own window; opening them never displaces evidence."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTableWidget, QMessageBox,
                               QTableWidgetItem, QHeaderView, QVBoxLayout, QWidget)

from .connections import ConnectionsPane
from .ui_jobs import UiJob
from .window_chrome import FramelessWindow, WindowHeader
from .motion import fade_in


class SettingsDialog(FramelessWindow):
    settings_saved = Signal(object)
    readiness_progress = Signal(object)
    ai_connection_changed = Signal(bool)

    def __init__(self, settings, store=None, parent=None, *, ai_state=None):
        super().__init__(parent)
        self.setWindowTitle("GrangerPet · Настройки")
        self.setObjectName("SettingsDialog")
        self.resize(570, 470)
        self._auto_size = QSize(570, 470)
        self._ending = False
        self.setMinimumSize(460, 420)
        self._jobs = []
        self._readiness_rows = {}
        self.readiness_progress.connect(self._update_readiness_row)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = WindowHeader(self, "Настройки", "Источники и помощь Гермионы")
        outer.addWidget(self.header)
        body = QWidget()
        outer.addWidget(body, 1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        self.connections = ConnectionsPane(settings, store, ai_state=ai_state)
        self.ai_state = self.connections.ai_state
        self.connections.settings_saved.connect(self.settings_saved)
        self.connections.ai_connection_changed.connect(self.ai_connection_changed)
        layout.addWidget(self.connections, 1)
        self.readiness = QTableWidget(0, 2)
        self.readiness.setHorizontalHeaderLabels(["Источник", "Готовность"])
        self.readiness.verticalHeader().hide()
        self.readiness.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.readiness.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.readiness.setWordWrap(True)
        self.readiness.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.readiness.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.readiness.setMinimumHeight(160)
        self.readiness.setMaximumHeight(260)
        self.readiness.setVisible(False)
        source_layout = self.connections.pages["Источники"]
        info = QLabel("Проверьте локальные инструменты перед поиском. Проверка импортирует настоящие зависимости и не выполняет поисковые запросы.")
        info.setWordWrap(True)
        info.setObjectName("Muted")
        source_layout.insertWidget(0, info)
        source_layout.insertWidget(1, self.readiness)
        self.check_sources = QPushButton("Проверить готовность источников")
        self.check_sources.clicked.connect(self.refresh_readiness)
        source_layout.insertWidget(2, self.check_sources)
        footer = QHBoxLayout()
        self.connections.layout.removeWidget(self.connections.save_button)
        footer.addWidget(self.connections.save_button)
        self.done_button = QPushButton("Готово")
        self.done_button.clicked.connect(self.close)
        footer.addWidget(self.done_button)
        footer.addStretch()
        layout.addLayout(footer)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(0)
        self._fit_timer.timeout.connect(self._fit_section)
        self.connections.tabs.currentChanged.connect(self._section_changed)
        self.connections.provider.currentIndexChanged.connect(self._request_fit)
        self.ai_state.changed.connect(self._request_fit)

    def _request_fit(self, *_):
        # Once the user explicitly resizes the settings window, scroll its
        # contents at that size instead of immediately undoing their choice.
        if not self._ending and self.isVisible() and self.size() == self._auto_size:
            self._fit_timer.start()

    def _section_changed(self, *_):
        self._request_fit()
        page = self.connections.tabs.currentWidget()
        if page is not None:
            fade_in(page.viewport(), 180)

    def _fit_section(self):
        if self._ending or not self.isVisible() or self.size() != self._auto_size:
            return
        scroll = self.connections.tabs.currentWidget()
        if scroll is None:
            return
        content = scroll.widget()
        content_layout = content.layout()
        content_height = content_layout.heightForWidth(scroll.viewport().width())
        if content_height < 0:
            content_height = content.sizeHint().height()
        shell_height = self.height() - scroll.height()
        available = self.screen().availableGeometry().height() - 40
        height = max(self.minimumHeight(), min(620, available, content_height + shell_height + 8))
        if self.height() != height:
            self.resize(self.width(), height)
            self._auto_size = self.size()

    def set_settings(self, settings):
        self.connections.set_settings(settings)

    @property
    def deepseek_verified(self):
        return self.connections.deepseek_verified

    def options(self):
        pane = self.connections
        settings = pane.settings
        value = {"source_root": pane.source_root.text().strip(), "tools_root": pane.source_root.text().strip(),
                 "runtime_python": pane.runtime_python.text().strip(),
                 "telegram_api_id": pane.telegram_api_id.text().strip(),
                 "google_cx": pane.google_cx.text().strip(), "enable_snoop": pane.enable_snoop.isChecked()}
        from .credentials import get_secret
        for name, field in pane.secret_fields.items():
            if name == "deepseek_api_key":
                continue
            try:
                value[name] = field.text().strip() or get_secret(name)
            except Exception:
                value[name] = ""
        return value

    def refresh_readiness(self):
        if self._jobs:
            return
        self.check_sources.setEnabled(False)
        self.check_sources.setText("Проверяю окружения…")
        self.readiness.setVisible(True)
        options = self.options()
        # Show an honest pending state rather than an empty panel while the
        # isolated interpreters import their actual vendor entry points.
        from .engine.readiness import LABELS
        self.readiness.setRowCount(len(LABELS))
        self._readiness_rows = {}
        for row, (source_id, label) in enumerate(LABELS.items()):
            self._readiness_rows[source_id] = row
            self.readiness.setItem(row, 0, QTableWidgetItem(label))
            self.readiness.setItem(row, 1, QTableWidgetItem("Проверяется…"))
        self.readiness.resizeRowsToContents()
        def probe():
            from .engine.readiness import source_readiness
            return source_readiness(options, refresh=True, cancelled=job.cancelled,
                                    on_result=self.readiness_progress.emit)
        job = UiJob(probe, self)
        self._jobs.append(job)
        def finished(rows, error):
            if job not in self._jobs:
                return
            self._jobs.remove(job)
            job.deleteLater()
            self.check_sources.setEnabled(True)
            self.check_sources.setText("Проверить готовность источников")
            rows = rows or [{"label": "Подключения", "state": "unavailable", "message": error}]
            self.readiness.setRowCount(len(rows))
            self._readiness_rows = {source.get("id", str(row)): row for row, source in enumerate(rows)}
            for row, source in enumerate(rows):
                self._update_readiness_row(source, row)
            self.readiness.resizeRowsToContents()
        job.done.connect(finished)
        job.start()

    def _update_readiness_row(self, source, row=None):
        source_id = source.get("id", "")
        if row is None:
            row = self._readiness_rows.get(source_id)
        if row is None:
            return
        titles = {"ready": "Готов", "available": "Готов", "auth_required": "Нужна авторизация",
                  "unavailable": "Недоступен", "disabled": "Выключен", "error": "Ошибка", "partial": "Нужна настройка"}
        title = source.get("label") or source_id or "Источник"
        state = titles.get(source.get("state"), source.get("state", "Не проверен"))
        detail = source.get("message", "")
        self.readiness.setItem(row, 0, QTableWidgetItem(str(title)))
        item = QTableWidgetItem(state)
        item.setToolTip(detail)
        title_item = self.readiness.item(row, 0)
        if title_item is not None:
            title_item.setToolTip(detail)
        self.readiness.setItem(row, 1, item)
        self.readiness.resizeRowToContents(row)

    def shutdown(self):
        self._ending = True
        self._fit_timer.stop()
        for job in self._jobs:
            job.cancel()
        self._jobs.clear()
        self.connections.shutdown()
        self.hide()

    def closeEvent(self, event):
        if self.connections.is_dirty():
            answer = self.ask_unsaved_changes()
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Save:
                if not self.connections.save():
                    event.ignore()
                    return
            else:
                self.connections.discard_changes()
        self.connections.reset_secret_visibility()
        event.ignore()
        self.hide()

    def ask_unsaved_changes(self):
        return QMessageBox.question(self, "Несохранённые настройки", "Сохранить изменения подключения и настроек?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)

    def showEvent(self, event):
        self.connections.reset_secret_visibility()
        super().showEvent(event)
        self._request_fit()
