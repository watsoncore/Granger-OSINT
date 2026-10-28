"""The optional Google operator builder is a separate compact tool window."""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QScrollArea, QWidget)

from .dorks import DorkError, DorkSpec, build_query
from .window_chrome import FramelessWindow, WindowHeader
from .typography import ui_font
from .motion import fade_in


class DorkDialog(FramelessWindow):
    query_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GrangerPet · Операторы Google")
        self.resize(520, 550)
        self.setMinimumSize(440, 380)
        self.setFont(ui_font(14))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(WindowHeader(self, 'Операторы Google'))
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 12, 18, 14)
        layout.setSpacing(10)
        area.setWidget(body)
        outer.addWidget(area, 1)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Слова запроса")
        layout.addWidget(self.text)
        form = QFormLayout()
        self.mode = QComboBox()
        for label, value in (("Обычный поиск", "web"), ("По домену", "domain"), ("Документы", "documents"),
                             ("Упоминания", "mentions"), ("Свободный Dork", "custom")):
            self.mode.addItem(label, value)
        form.addRow("Сценарий", self.mode)
        self.domain = QLineEdit()
        self.domain.setPlaceholderText("example.org")
        form.addRow("Домен", self.domain)
        self.filetype = QComboBox()
        self.filetype.addItems(["PDF", "DOCX", "XLSX"])
        form.addRow("Тип документа", self.filetype)
        self.exact = QCheckBox("Точная фраза")
        form.addRow(self.exact)
        self.title_input, self.url_input, self.intext_input, self.exclude = (QLineEdit() for _ in range(4))
        for label, widget, hint in (("Заголовок", self.title_input, "intitle:"), ("Часть URL", self.url_input, "inurl:"),
                                    ("Текст страницы", self.intext_input, "intext:"), ("Исключить", self.exclude, 'слово "фраза"')):
            widget.setPlaceholderText(hint)
            form.addRow(label, widget)
        layout.addLayout(form)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview.setObjectName("QueryPreview")
        layout.addWidget(self.preview)
        use = QPushButton("Использовать запрос")
        use.setObjectName("PrimaryButton")
        use.clicked.connect(self.use_query)
        footer = QHBoxLayout()
        footer.setContentsMargins(18, 12, 18, 14)
        footer.addStretch()
        footer.addWidget(use)
        outer.addLayout(footer)
        for edit in (self.text, self.domain, self.title_input, self.url_input, self.intext_input, self.exclude):
            edit.textChanged.connect(self.update_preview)
        self.mode.currentIndexChanged.connect(self.update_preview)
        self.filetype.currentIndexChanged.connect(self.update_preview)
        self.exact.toggled.connect(self.update_preview)
        self.update_preview()

    def showEvent(self, event):
        super().showEvent(event)
        fade_in(self, 170)

    def spec(self):
        return DorkSpec(self.mode.currentData(), self.text.text(), self.domain.text(), self.filetype.currentText(),
                        self.title_input.text(), self.url_input.text(), self.intext_input.text(), self.exact.isChecked(), self.exclude.text())

    def update_preview(self):
        self.filetype.setEnabled(self.mode.currentData() == "documents")
        try:
            self.preview.setText(build_query(self.spec()))
        except DorkError as exc:
            self.preview.setText(str(exc))

    def use_query(self):
        try:
            value = build_query(self.spec())
        except DorkError as exc:
            self.preview.setText(str(exc))
            return
        self.query_selected.emit(value)
        self.hide()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
