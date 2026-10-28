"""Readable source details; each displayed value can be copied without truncation."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QTextOption
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from .engine.models import is_confirmed
from .result_view import service_name, source_url
from .typography import ui_font
from .motion import fade_in


def label(text, name=""):
    value = QLabel(str(text))
    value.setTextFormat(Qt.TextFormat.PlainText)
    value.setWordWrap(True)
    value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name:
        value.setObjectName(name)
    return value


class ValueField(QPlainTextEdit):
    """Wrap opaque hashes/URLs too; long fields remain selectable and scrollable."""
    def __init__(self, text, name):
        super().__init__(text)
        self.setReadOnly(True)
        self.setFont(ui_font(14))
        self.setAccessibleName(name)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.setStyleSheet('QPlainTextEdit { background: transparent; border: none; padding: 0; }')
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lines = min(5, max(1, (len(text) + 46) // 47))
        self.setFixedHeight(self.fontMetrics().lineSpacing() * lines + 5)

    def text(self):
        return self.toPlainText()


class ResultDetails(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record, self.fields = dict(record), {}
        self.setWindowTitle("GrangerPet · Сведения источника")
        self.setObjectName("ResultDetails")
        self.resize(520, 440)
        self.setMinimumSize(400, 300)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(label(service_name(record.get("platform")), "Heading"))
        area = QScrollArea()
        area.setWidgetResizable(True)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 4, 0)
        content.setSpacing(10)
        details = record.get("details") or {}
        if record.get("type") == "email_check":
            self._field(content, "Проверяемый email", details.get("email"))
            self._field(content, "Статус", "Сервис сообщил о регистрации" if record.get("status") == "registration_detected" else str(record.get("status") or "Не указан"))
            self._field(content, "Достоверность", "Согласно ответу источника" if is_confirmed(record) else "Требуется проверка")
        else:
            self._field(content, "Название", record.get("title"))
            self._field(content, "Идентификатор", record.get("id"))
            self._field(content, "Статус", record.get("status"))
            if not is_confirmed(record):
                content.addWidget(label("Наблюдение требует проверки и не считается подтверждённым фактом.", "Caution"))
        self._field(content, "Источник", ", ".join(str(item) for item in record.get("sources", [])))
        self._field(content, "Дата", record.get("date"))
        self._field(content, "Описание", record.get("description"))
        for key, value in details.items():
            if key in ("email", "service_url") or value is None:
                continue
            if not isinstance(value, (dict, list)):
                self._field(content, str(key), value)
        address = source_url(record)
        self._field(content, "URL источника", address)
        if record.get("type") == "email_check" and address:
            content.addWidget(label("Страница сервиса. Ссылка на личный профиль этим источником не предоставлена.", "SmallMuted"))
        raw_toggle = QToolButton()
        raw_toggle.setText("Исходные поля источника")
        raw_toggle.setObjectName("Disclosure")
        raw_toggle.setCheckable(True)
        raw = QPlainTextEdit(json.dumps(record, ensure_ascii=False, indent=2, default=str))
        raw.setReadOnly(True)
        raw.setMinimumHeight(180)
        raw.hide()
        raw_toggle.toggled.connect(raw.setVisible)
        content.addWidget(raw_toggle)
        content.addWidget(raw)
        content.addStretch()
        area.setWidget(body)
        layout.addWidget(area, 1)
        actions = QHBoxLayout()
        self.open_button = QPushButton("Открыть источник ↗")
        self.open_button.setObjectName("QuietButton")
        self.open_button.setEnabled(bool(address))
        self.open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(address)))
        actions.addWidget(self.open_button)
        copy = QPushButton("Копировать всё")
        copy.setObjectName("QuietButton")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(json.dumps(record, ensure_ascii=False, indent=2, default=str)))
        actions.addWidget(copy)
        actions.addStretch()
        done = QPushButton("Готово")
        done.clicked.connect(self.accept)
        actions.addWidget(done)
        layout.addLayout(actions)

    def showEvent(self, event):
        super().showEvent(event)
        fade_in(self, 170)

    def _field(self, layout, name, value):
        if value is None or value == "":
            return
        text = str(value)
        block = QVBoxLayout()
        block.setSpacing(3)
        caption = QHBoxLayout()
        caption.addWidget(label(name, "SmallMuted"), 1)
        copy = QToolButton()
        copy.setText("Копировать")
        copy.setObjectName("InlineAction")
        copy.setAccessibleName("Копировать " + name)
        copy.clicked.connect(lambda checked=False, content=text: QApplication.clipboard().setText(content))
        caption.addWidget(copy)
        block.addLayout(caption)
        field = ValueField(text, name)
        block.addWidget(field)
        self.fields[name] = field
        layout.addLayout(block)
