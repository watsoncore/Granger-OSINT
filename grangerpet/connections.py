"""Compact provider settings. User secrets remain in the Windows vault."""
from __future__ import annotations

import hashlib
import math
import time
from copy import deepcopy

from PySide6.QtCore import Qt, Signal, QTimer, QSize, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QToolButton, QVBoxLayout, QWidget,
                               QTabWidget, QScrollArea, QFrame)
from PySide6.QtWidgets import QSizePolicy

from .ai import AIError, DeepSeekClient, OllamaClient
from .ai_keys import DEFAULT_DEEPSEEK_MODEL, DEEPSEEK_BASE_URL, deepseek_key_source, resolve_deepseek_key, resolve_deepseek_model
from .credentials import delete_secret, get_secret, set_secret
from .ui_jobs import UiJob
from .ai_state import AIState


def _label(text, name="Muted"):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setObjectName(name)
    return label


def _eye_icon():
    image = QPixmap(40, 40)
    image.setDevicePixelRatio(2)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#9a9da3"), 1.4))
    path = QPainterPath(QPointF(2, 10))
    path.cubicTo(6, 4, 14, 4, 18, 10)
    path.cubicTo(14, 16, 6, 16, 2, 10)
    painter.drawPath(path)
    painter.drawEllipse(QPointF(10, 10), 2.4, 2.4)
    painter.end()
    return QIcon(image)


class SettingsTabs(QTabWidget):
    """Scroll pages own wrapping; hidden forms must not set the window height."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)

    def hasHeightForWidth(self):
        return False

    def heightForWidth(self, width):
        return -1


class ConnectionsPane(QWidget):
    settings_saved = Signal(object)
    ai_connection_changed = Signal(bool)
    dirty_changed = Signal(bool)

    def __init__(self, settings, store=None, parent=None, *, ai_state=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.settings, self.store, self._jobs = deepcopy(settings), store, []
        self.ai_state = ai_state or AIState(settings, self)
        self._pending_deletions = set()
        self._baseline = None
        self.secret_fields = {}
        self._updating = True
        self._verified_identity = None
        self.connection_details = {}
        self._connection_details_identity = None
        self._provider_kind = None
        self._draft_models = {}
        self._test_generation = 0
        self._retry_until = 0.0
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(250)
        self._retry_timer.timeout.connect(self._update_check_button)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.tabs = SettingsTabs()
        self.tabs.setObjectName("SettingsTabs")
        self.pages = {}
        for title in ("Источники", "Авторизация", "ИИ", "Поиск"):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(2, 12, 10, 8)
            layout.setSpacing(10)
            layout.addStretch()
            self.pages[title] = layout
            scroll.setWidget(page)
            self.tabs.addTab(scroll, title)
        self.layout.addWidget(self.tabs, 1)

        runtime = self._section("Локальные источники")
        self.source_root = self._path_row(runtime, "Папка инструментов", True)
        self.runtime_python = self._path_row(runtime, "Python источников", False)
        runtime.addRow(_label("Пустой путь — поиск рядом с приложением. Зависимости подготавливаются отдельно."))
        self.enable_snoop = QCheckBox("Дополнительная проверка профилей")
        self.enable_snoop.setToolTip("Snoop: локальная установка, только при включении и в пределах лицензии источника.")
        runtime.addRow(self.enable_snoop)

        searching = self._section("Поведение поиска", expanded=True)
        self.request_limit = QSpinBox()
        self.request_limit.setRange(5, 50)
        searching.addRow("Лимит результатов", self.request_limit)
        self.search_timeout = QSpinBox()
        self.search_timeout.setRange(5, 60)
        self.search_timeout.setSuffix(" с")
        searching.addRow("Таймаут источника", self.search_timeout)
        searching.addRow(_label("Поиск работает без ИИ. Недоступные источники не создают находок; неполная проверка отмечается в выдаче."))
        budget = self._section("Бюджет расследования")
        self.agent_budget_fields = {}
        for name, title, low, high, step in (
            ("agent_steps", "Ходы анализа", 2, 20, 1), ("agent_calls", "Вызовы инструментов", 1, 30, 1),
            ("agent_timeout", "Длительность, с", 30, 600, 30), ("agent_tokens", "Бюджет токенов", 4000, 100000, 4000),
            ("agent_page_limit", "Прочитанные страницы", 1, 12, 1), ("agent_page_depth", "Глубина переходов", 0, 3, 1)):
            field = QSpinBox()
            field.setRange(low, high)
            field.setSingleStep(step)
            budget.addRow(title, field)
            self.agent_budget_fields[name] = field
        budget.addRow(_label("Больше шагов и страниц может расходовать больше времени и баланса шлюза. Лимиты применяются к новому расследованию."))

        google = self._section("Google Search API")
        self.google_key = self._secret_row(google, "google_api_key", "API-ключ")
        self.google_cx = QLineEdit()
        google.addRow("Search engine ID", self.google_cx)
        google.addRow(_label("Необязательно. Без API запрос откроется в браузере. Доступ DeepSeek подключается отдельно."))
        telegram = self._section("Telegram")
        self.telegram_api_id = QLineEdit()
        telegram.addRow("API ID", self.telegram_api_id)
        self._secret_row(telegram, "telegram_api_hash", "API hash")
        self._secret_row(telegram, "telegram_session", "StringSession")
        telegram.addRow(_label("Требуется уже авторизованная Telethon-сессия. Вход по коду выполняется отдельно."))
        vk = self._section("ВКонтакте")
        self._secret_row(vk, "vk_token", "Access token")
        vk.addRow(_label("Официальный API; доступ определяется правами токена."))
        instagram = self._section("Instagram")
        self.instagram_username = QLineEdit()
        instagram.addRow("Логин сессии", self.instagram_username)
        self._secret_row(instagram, "instagram_session", "Cookies JSON")
        instagram.addRow(_label("Необязательно: cookies существующей сессии. Приватные данные не обходятся."))

        ai_form = self._flat_section("ИИ", "Помощь Гермионы")
        self.provider = QComboBox()
        for title, value in (("Без ИИ", "none"), ("DeepSeek V4 Flash", "deepseek"), ("Ollama · локально", "ollama")):
            self.provider.addItem(title, value)
        ai_form.addRow("Провайдер", self.provider)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumContentsLength(12)
        self.model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model.setToolTip("Модель deepseek-v4-flash · " + DEEPSEEK_BASE_URL)
        ai_form.addRow("Модель", self.model)
        self.model_label = ai_form.labelForField(self.model)

        self.deepseek_panel = QWidget()
        deepseek_form = self._form(self.deepseek_panel)
        self.deepseek_key = self._secret_row(deepseek_form, "deepseek_api_key", "API-ключ", reveal=True)
        self.key_source = _label("")
        deepseek_form.addRow(self.key_source)
        self.deepseek_notice = _label("Проверка отправит шлюзу до трёх коротких запросов и расходует API-квоту. Результаты поиска автоматически не передаются.")
        self.deepseek_notice.setToolTip(DEEPSEEK_BASE_URL + " · проверка ответа и безопасный тест формата tool_calls, без запуска OSINT.")
        deepseek_form.addRow(self.deepseek_notice)
        ai_form.addRow(self.deepseek_panel)
        self.ollama_panel = QWidget()
        ollama_form = self._form(self.ollama_panel)
        self.ollama_url = QLineEdit()
        self.ollama_url.setPlaceholderText("http://localhost:11434")
        ollama_form.addRow("Сервер", self.ollama_url)
        ollama_form.addRow(_label("Только локальный loopback-сервер. Модели не скачиваются автоматически."))
        ai_form.addRow(self.ollama_panel)
        self.ai_actions = QWidget()
        actions = QHBoxLayout(self.ai_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.check = QPushButton("Проверить подключение")
        self.check.clicked.connect(self.check_connection)
        actions.addWidget(self.check)
        self.cancel_check = QPushButton("Отменить")
        self.cancel_check.clicked.connect(self.cancel_connection_test)
        self.cancel_check.hide()
        actions.addWidget(self.cancel_check)
        actions.addStretch()
        ai_form.addRow(self.ai_actions)
        self.ai_status = _label("Не проверено")
        self.ai_status.setObjectName("ConnectionStatus")
        ai_form.addRow(self.ai_status)
        self.ai_disabled = _label("Базовый поиск доступен без ИИ. Подключите провайдера для диалога и объяснения найденных сведений.")
        ai_form.addRow(self.ai_disabled)
        self.status = _label("")
        self.layout.addWidget(self.status)
        self.save_button = QPushButton("Сохранить")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save)
        self.dirty_changed.connect(self.save_button.setEnabled)
        self.layout.addWidget(self.save_button)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.model.currentTextChanged.connect(self._invalidate_connection)
        self.deepseek_key.textChanged.connect(self._invalidate_connection)
        self.ollama_url.textChanged.connect(self._invalidate_connection)
        self.ai_state.changed.connect(self._shared_state_changed)
        self.set_settings(settings, force=True)
        for field in (self.source_root, self.runtime_python, self.telegram_api_id, self.instagram_username, self.google_cx):
            field.textChanged.connect(self._notify_dirty)
        for field in self.secret_fields.values():
            field.textChanged.connect(self._notify_dirty)
        self.request_limit.valueChanged.connect(self._notify_dirty)
        self.search_timeout.valueChanged.connect(self._notify_dirty)
        for field in self.agent_budget_fields.values():
            field.valueChanged.connect(self._notify_dirty)
        self.enable_snoop.toggled.connect(self._notify_dirty)
        self._updating = False

    @staticmethod
    def _form(body):
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        return form

    def _flat_section(self, category, title):
        target = self.pages[category]
        heading = _label(title, "SectionTitle")
        target.insertWidget(target.count() - 1, heading)
        body = QWidget()
        form = self._form(body)
        target.insertWidget(target.count() - 1, body)
        return form

    def _section(self, title, expanded=False):
        category = "Источники" if title == "Локальные источники" else "Поиск" if title in ("Поведение поиска", "Бюджет расследования") else "Авторизация"
        target = self.pages[category]
        button = QToolButton()
        button.setObjectName("Disclosure")
        button.setText(title)
        button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        button.setCheckable(True)
        button.setChecked(expanded)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        target.insertWidget(target.count() - 1, button)
        body = QWidget()
        body.setVisible(expanded)
        form = self._form(body)
        target.insertWidget(target.count() - 1, body)
        button.toggled.connect(body.setVisible)
        button.toggled.connect(lambda checked: button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow))
        return form

    def _path_row(self, form, label, directory):
        row, edit = QHBoxLayout(), QLineEdit()
        edit.setPlaceholderText("Автоматически")
        button = QToolButton()
        button.setText("…")
        button.setToolTip("Выбрать папку" if directory else "Выбрать Python")
        def browse():
            path = QFileDialog.getExistingDirectory(self, label) if directory else QFileDialog.getOpenFileName(self, label, "", "Python (python.exe pythonw.exe);;Все файлы (*)")[0]
            if path:
                edit.setText(path)
        button.clicked.connect(browse)
        row.addWidget(edit, 1)
        row.addWidget(button)
        form.addRow(label, row)
        return edit

    def _secret_row(self, form, name, title, reveal=False):
        row, edit = QHBoxLayout(), QLineEdit()
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setMaxLength(500000 if name in ("telegram_session", "instagram_session") else 4096)
        edit.setPlaceholderText("Не настроено")
        self.secret_fields[name] = edit
        row.addWidget(edit, 1)
        if reveal:
            show = QToolButton()
            show.setIcon(_eye_icon())
            show.setIconSize(QSize(20, 20))
            show.setFixedWidth(32)
            show.setCheckable(True)
            show.setAccessibleName("Показать введённый API-ключ")
            show.setToolTip("Показать введённый ключ")
            show.toggled.connect(lambda checked: edit.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
            row.addWidget(show)
            self.deepseek_reveal = show
        erase = QToolButton()
        erase.setText("Удалить")
        erase.setAccessibleName("Удалить сохранённый " + title)
        erase.setToolTip("Удалить сохранённый ключ или сессию при сохранении настроек")
        def clear():
            self._pending_deletions.add(name)
            edit.clear()
            edit.setPlaceholderText("Будет удалено при сохранении")
            if name == "deepseek_api_key":
                self._invalidate_connection()
                self.deepseek_reveal.setChecked(False)
            self.status.setText("Удаление отмечено. Нажмите «Сохранить», чтобы применить.")
            self._notify_dirty()
        erase.clicked.connect(clear)
        row.addWidget(erase)
        form.addRow(title, row)
        return edit

    def selected_model(self):
        index = self.model.currentIndex()
        text = self.model.currentText().strip()
        data = self.model.itemData(index) if index >= 0 and self.model.itemText(index) == text else None
        return str(data or text).removeprefix("models/")

    def _set_model(self, model):
        self.model.clear()
        if self.provider.currentData() == "deepseek":
            self.model.addItem("DeepSeek V4 Flash", DEFAULT_DEEPSEEK_MODEL)
            if model and model != DEFAULT_DEEPSEEK_MODEL:
                self.model.addItem(model, model)
                self.model.setCurrentIndex(self.model.count() - 1)
        elif model:
            self.model.addItem(model, model)
        else:
            self.model.setEditText("")

    def _refresh_key_source(self):
        if "deepseek_api_key" in self._pending_deletions and not self.deepseek_key.text().strip():
            self.key_source.setText("Ключ будет удалён из Windows только после сохранения.")
            self.deepseek_key.setPlaceholderText("Будет удалено при сохранении")
            return
        try:
            source = "input" if self.deepseek_key.text().strip() else deepseek_key_source()
        except Exception:
            source = "missing"
        titles = {"windows": "Ключ сохранён в Windows Credential Manager.",
                  "input": "Введённый ключ будет сохранён только по кнопке «Сохранить».",
                  "missing": "Введите свой ключ шлюза aikeysforyou.com."}
        self.key_source.setText(titles.get(source, titles["missing"]))
        if not self.deepseek_key.text():
            self.deepseek_key.setPlaceholderText("Сохранён в Windows" if source == "windows" else "API-ключ шлюза")

    def _preferences_signature(self):
        return (self.provider.currentData(), self.selected_model(), self.source_root.text(), self.runtime_python.text(),
                self.telegram_api_id.text(), self.instagram_username.text(), self.ollama_url.text(), self.google_cx.text(),
                self.request_limit.value(), self.search_timeout.value(), self.enable_snoop.isChecked(),
                tuple(field.value() for field in self.agent_budget_fields.values()))

    def is_dirty(self):
        return bool(self._baseline is not None and (self._preferences_signature() != self._baseline or
                    self._pending_deletions or any(field.text().strip() for field in self.secret_fields.values())))

    def _notify_dirty(self, *_):
        if not self._updating:
            self.dirty_changed.emit(self.is_dirty())

    def _effective_override(self):
        entered = self.deepseek_key.text().strip()
        if entered:
            self._pending_deletions.discard("deepseek_api_key")
            return entered
        return "" if "deepseek_api_key" in self._pending_deletions else None

    def _sync_draft(self):
        self.ai_state.update_draft(self.provider.currentData(), self.selected_model(), self._effective_override(), self.ollama_url.text())

    def _shared_state_changed(self, snapshot):
        self._show_connection_state()
        self.ai_connection_changed.emit(self.deepseek_verified)

    def reset_secret_visibility(self):
        self.deepseek_reveal.setChecked(False)
        for field in self.secret_fields.values():
            field.setEchoMode(QLineEdit.EchoMode.Password)

    def discard_changes(self):
        self.cancel_connection_test(reset_status=False)
        self._updating = True
        for field in self.secret_fields.values():
            field.clear()
        self._pending_deletions.clear()
        self.reset_secret_visibility()
        self._updating = False
        self.ai_state.discard_draft()
        self.set_settings(self.ai_state.settings, force=True)
        self.status.clear()

    def set_settings(self, settings, *, force=False):
        if not force and self.is_dirty():
            self.settings = deepcopy(settings)
            self.ai_state.set_settings(settings)
            return
        old_updating = self._updating
        self._updating = True
        self.settings = deepcopy(settings)
        self.ai_state.set_settings(settings)
        for name in ("source_root", "runtime_python", "telegram_api_id", "instagram_username", "ollama_url"):
            getattr(self, name).setText(str(getattr(settings, name, "http://localhost:11434" if name == "ollama_url" else "")))
        self.google_cx.setText(getattr(settings, "api_cx", ""))
        self.request_limit.setValue(getattr(settings, "request_limit", 20))
        self.search_timeout.setValue(getattr(settings, "search_timeout", 25))
        for name, field in self.agent_budget_fields.items():
            field.setValue(getattr(settings, name))
        self.enable_snoop.setChecked(getattr(settings, "enable_snoop", False))
        self._provider_kind = None
        self._draft_models = {"deepseek": resolve_deepseek_model(getattr(settings, "deepseek_model", "")),
                              "ollama": getattr(settings, "ollama_model", "")}
        self.provider.setCurrentIndex(max(0, self.provider.findData(getattr(settings, "ai_provider", "none"))))
        self._provider_changed()
        for name, field in self.secret_fields.items():
            if name == "deepseek_api_key":
                continue
            try:
                saved = bool(get_secret(name))
            except Exception:
                saved = False
            field.setPlaceholderText("Сохранено в Windows" if saved else "Не настроено")
        self._refresh_key_source()
        self.reset_secret_visibility()
        self._baseline = self._preferences_signature()
        self._updating = old_updating
        self._show_connection_state()
        self._update_check_button()
        self.dirty_changed.emit(self.is_dirty())

    def _provider_changed(self, *_):
        old_updating = self._updating
        self._updating = True
        if self._provider_kind in ("deepseek", "ollama"):
            self._draft_models[self._provider_kind] = self.selected_model()
        provider = self.provider.currentData()
        self._provider_kind = provider
        self._set_model(self._draft_models.get(provider, ""))
        enabled = provider in ("deepseek", "ollama")
        self.model.setVisible(enabled)
        self.model_label.setVisible(enabled)
        self.deepseek_panel.setVisible(provider == "deepseek")
        self.ollama_panel.setVisible(provider == "ollama")
        self.ai_actions.setVisible(enabled)
        self.ai_status.setVisible(enabled)
        self.ai_disabled.setVisible(not enabled)
        self.check.setEnabled(enabled)
        self._updating = old_updating
        if not self._updating:
            self._invalidate_connection()

    def _identity(self):
        try:
            override = self._effective_override()
            key = resolve_deepseek_key() if override is None else override
            return (self.selected_model(), hashlib.sha256(key.encode()).digest()) if key else None
        except Exception:
            return None

    @property
    def deepseek_verified(self):
        return (self.provider.currentData() == "deepseek" and
                self.ai_state.snapshot()["connection_status"] in ("connected", "verified_unsaved") and
                self.ai_state.is_verified("deepseek", self.selected_model(), self._effective_override()))

    def _show_connection_state(self):
        snapshot = self.ai_state.snapshot()
        state = snapshot["connection_status"]
        if self.provider.currentData() != "deepseek" or self._identity() != self._connection_details_identity:
            self.connection_details = {}
        self.ai_status.setProperty("state", "ready" if state == "connected" else "error" if snapshot["last_error"] else "unknown")
        self.ai_status.setText(self.ai_state.status_text(snapshot))
        capability = self.connection_details.get("tool_calls", {})
        if capability.get("status") == "supported":
            detail = "Формат tool_calls подтверждён безопасным тестом. Ручной запуск OSINT сохранён."
        else:
            detail = "Поддержка tool_calls не подтверждена. Ручной поиск и анализ выбранных находок доступны."
        self.ai_status.setToolTip(DEEPSEEK_BASE_URL + "\n" + detail if snapshot["provider"] == "deepseek" else "")

    def _invalidate_connection(self, *_):
        if self._updating:
            return
        self.cancel_connection_test(reset_status=False)
        self._verified_identity = None
        self.connection_details = {}
        self._connection_details_identity = None
        self._retry_until = 0.0
        self._sync_draft()
        self._refresh_key_source()
        self.ai_connection_changed.emit(self.deepseek_verified)
        self._notify_dirty()

    def cancel_connection_test(self, *, reset_status=True):
        self._test_generation += 1
        had_jobs = bool(self._jobs)
        for job in self._jobs:
            job.cancel()
            job.deleteLater()
        self._jobs.clear()
        self.ai_state.cancel_check()
        self._update_check_button()
        self.cancel_check.hide()
        if had_jobs and reset_status:
            self.ai_status.setText("Проверка отменена")
            self.ai_connection_changed.emit(False)

    def check_connection(self):
        provider = self.provider.currentData()
        if provider not in ("deepseek", "ollama") or self._jobs or time.monotonic() < self._retry_until:
            return
        if provider == "deepseek" and "deepseek_api_key" in self._pending_deletions and not self.deepseek_key.text().strip():
            self.status.setText("Ключ отмечен для удаления. Сохраните изменения или отмените их.")
            return
        model = self.selected_model() or (DEFAULT_DEEPSEEK_MODEL if provider == "deepseek" else "")
        identity = self._identity() if provider == "deepseek" else None
        entered_key = self.deepseek_key.text().strip()
        address = self.ollama_url.text()
        self._verified_identity = None
        self.connection_details = {}
        self._connection_details_identity = None
        self.ai_connection_changed.emit(False)
        self.check.setEnabled(False)
        self.cancel_check.show()
        self.ai_status.setText("Проверяю подключение…")
        generation = self._test_generation
        state_generation = self.ai_state.begin_check(provider, model, self._effective_override(), address)
        def request():
            try:
                if provider == "deepseek":
                    result = DeepSeekClient(entered_key or None).test_connection(model=model, cancel_event=job.cancelled)
                    capability = result.get("tool_calls", {})
                    capability = capability if isinstance(capability, dict) else {}
                    round_trip = capability.get("round_trip") is True
                    capability_status = capability.get("status")
                    if capability_status not in ("supported", "unverified", "unsupported") or capability_status == "supported" and not round_trip:
                        capability_status = "unverified"
                    safe_capability = {"status": capability_status, "round_trip": round_trip}
                    return {"connected": bool(result.get("connected")), "model": result.get("model", model), "tool_calls": safe_capability}
                models = OllamaClient(address).list_models()
                return {"models": models, "connected": bool(models)}
            except AIError as exc:
                return {"error": str(exc), "code": getattr(exc, "code", "error"), "http_status": getattr(exc, "http_status", None), "retry_after": getattr(exc, "retry_after", None)}
        job = UiJob(request, self)
        self._jobs.append(job)
        def done(result, error):
            if job not in self._jobs or generation != self._test_generation:
                return
            self._jobs.remove(job)
            job.deleteLater()
            self._update_check_button()
            self.cancel_check.hide()
            if self.provider.currentData() != provider:
                return
            result = result or {}
            if error or result.get("error"):
                retry = result.get("retry_after")
                if isinstance(retry, (int, float)) and retry > 0:
                    self._retry_until = time.monotonic() + retry
                    self._retry_timer.start()
                    self._update_check_button()
                self.ai_state.finish_check(state_generation, success=False, error=result if result.get("error") else {"code":"provider_error"})
                self.ai_status.style().unpolish(self.ai_status)
                self.ai_status.style().polish(self.ai_status)
                self.ai_connection_changed.emit(self.deepseek_verified)
                return
            self.ai_status.setProperty("state", "ready" if result.get("connected") else "unknown")
            self.ai_status.style().unpolish(self.ai_status)
            self.ai_status.style().polish(self.ai_status)
            if provider == "deepseek":
                if not result.get("connected") or result.get("model") != model:
                    self.ai_state.finish_check(state_generation, success=False, error={"code":"model_not_found"})
                    return
                if self._identity() != identity:
                    self.ai_status.setText("Ключ изменён · требуется новая проверка")
                    return
                self.connection_details = {"model": model, "tool_calls": result.get("tool_calls", {"status": "unverified", "round_trip": False})}
                self._connection_details_identity = identity
                self._verified_identity = identity
                self.ai_state.finish_check(state_generation, success=True)
                self.ai_connection_changed.emit(self.deepseek_verified)
            else:
                models = result.get("models", [])
                old = self.selected_model()
                self._updating = True
                self.model.clear()
                for item in models:
                    self.model.addItem(item, item)
                if old in models:
                    self.model.setCurrentText(old)
                self._updating = False
                self._sync_draft()
                state_generation_ollama = self.ai_state.begin_check(provider, self.selected_model(), endpoint=address)
                self.ai_state.finish_check(state_generation_ollama, success=bool(models), error=None if models else {"code":"model_not_found"})
                self._notify_dirty()
                self.ai_status.setText("Ollama доступна · локальных моделей: " + str(len(models)) if models else "Сервер доступен; локальные модели не найдены")
        job.done.connect(done)
        job.start()

    def check_models(self):
        """Compatibility entry point; DeepSeek validates a generation, not a list."""
        self.check_connection()

    def _update_check_button(self):
        remaining = max(0, math.ceil(self._retry_until - time.monotonic()))
        if remaining:
            self.check.setText(f"Повторить через {remaining} с")
        else:
            self.check.setText("Проверить подключение")
            self._retry_timer.stop()
        self.check.setEnabled(not self._jobs and not remaining and self.provider.currentData() != "none")

    def save(self):
        changed_secrets = {name: field.text().strip() for name, field in self.secret_fields.items() if field.text().strip()}
        changed_secrets.update({name: "" for name in self._pending_deletions if name not in changed_secrets})
        previous_secrets, applied = {}, []
        previous_settings = None
        configuration_written = False
        try:
            self._updating = True
            previous_settings = self.store.load() if self.store else deepcopy(self.settings)
            settings = deepcopy(previous_settings)
            for name in ("source_root", "runtime_python", "telegram_api_id", "instagram_username", "ollama_url"):
                setattr(settings, name, getattr(self, name).text().strip())
            settings.api_cx = self.google_cx.text().strip()
            settings.request_limit = self.request_limit.value()
            settings.search_timeout = self.search_timeout.value()
            for name, field in self.agent_budget_fields.items():
                setattr(settings, name, field.value())
            settings.enable_snoop = self.enable_snoop.isChecked()
            settings.ai_provider = self.provider.currentData()
            if settings.ai_provider in ("deepseek", "ollama"):
                setattr(settings, settings.ai_provider + "_model", self.selected_model())
            for name in changed_secrets:
                previous_secrets[name] = get_secret(name)
            for name, value in changed_secrets.items():
                if previous_secrets[name] != value:
                    applied.append(name)
                    set_secret(name, value) if value else delete_secret(name)
                if get_secret(name) != value:
                    raise OSError("Credential verification failed")
                if name == "google_api_key":
                    settings.api_key = value
            if self.store:
                self.store.save(settings)
                configuration_written = True
                persisted = self.store.load()
                if persisted.to_dict() != settings.to_dict():
                    raise OSError("Configuration verification failed")
            self.settings = deepcopy(settings)
            for name, field in self.secret_fields.items():
                field.clear()
                field.setPlaceholderText("Сохранено в Windows" if (changed_secrets.get(name) or name not in changed_secrets and get_secret(name)) else "Не настроено")
            self._pending_deletions.clear()
            self.reset_secret_visibility()
            self._baseline = self._preferences_signature()
            self.ai_state.commit(settings)
            self._refresh_key_source()
            self._show_connection_state()
            self.status.setText("Настройки сохранены")
            self._updating = False
            self.settings_saved.emit(settings)
            self.ai_connection_changed.emit(self.deepseek_verified)
            self.dirty_changed.emit(False)
            return True
        except Exception:
            # A vault write and preferences write are separate OS operations.
            # Restore any changed credential if the atomic preferences commit
            # fails; keep the user's draft visible so it can be saved again.
            for name in reversed(applied):
                try:
                    value = previous_secrets[name]
                    set_secret(name, value) if value else delete_secret(name)
                except Exception:
                    pass
            if configuration_written and self.store and previous_settings is not None:
                try:
                    self.store.save(previous_settings)
                except Exception:
                    pass
            self._updating = False
            self.reset_secret_visibility()
            self.ai_state.save_failed()
            self.status.setText("Не удалось сохранить. Проверьте доступ к хранилищу Windows и файлу настроек.")
            self.dirty_changed.emit(True)
            return False

    def shutdown(self):
        self.cancel_connection_test(reset_status=False)
        self._retry_timer.stop()
