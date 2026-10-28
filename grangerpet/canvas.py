"""Local editable report workspace, separate from immutable source evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from PySide6.QtCore import QIODevice, QSaveFile, Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSizePolicy,
    QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from .config import data_directory
from .markdown_view import MarkdownView, headings
from .typography import ui_font


def write_utf8(path, text):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = str(text).encode('utf-8')
    file = QSaveFile(str(destination))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly) or file.write(data) != len(data) or not file.commit():
        file.cancelWriting()
        raise OSError('Не удалось сохранить документ.')
    return destination


class CanvasWorkspace(QWidget):
    close_requested = Signal()
    document_saved = Signal(str)
    user_activity = Signal()

    def __init__(self, parent=None, *, directory=None):
        super().__init__(parent)
        self.setObjectName('CanvasWorkspace')
        self.directory = Path(directory) if directory is not None else data_directory()/'canvas'
        self.document_id = ''
        self._original_source = ''
        self._loading, self._dirty = False, False
        self._documents = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setObjectName('CanvasHeader')
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(8)
        self.back = QPushButton('К чату')
        self.back.setAccessibleName('Вернуться к переписке')
        self.back.setFixedWidth(72)
        self.back.setObjectName('QuietButton')
        self.back.clicked.connect(self._back)
        row.addWidget(self.back)
        self.title = QLabel('Canvas · Отчёт')
        self.title.setObjectName('SectionTitle')
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(self.title, 1)
        self.edit_button = QPushButton('Править')
        self.edit_button.setCheckable(True)
        self.edit_button.setFixedWidth(80)
        self.edit_button.setObjectName('QuietButton')
        self.edit_button.toggled.connect(self._switch_mode)
        row.addWidget(self.edit_button)
        self.save_button = QPushButton('Сохранить')
        self.save_button.setObjectName('QuietButton')
        self.save_button.setFixedWidth(88)
        self.save_button.clicked.connect(self.save_document)
        row.addWidget(self.save_button)
        self.export_button = QPushButton('Экспорт .md')
        self.export_button.setObjectName('QuietButton')
        self.export_button.setFixedWidth(96)
        self.export_button.clicked.connect(self._export_clicked)
        row.addWidget(self.export_button)
        layout.addWidget(header)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.heading_list = QListWidget()
        self.heading_list.setObjectName('CanvasOutline')
        self.heading_list.setWordWrap(True)
        self.heading_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.heading_list.setMinimumWidth(120)
        self.heading_list.setMaximumWidth(240)
        self.heading_list.itemActivated.connect(self._go_heading)
        self.heading_list.itemClicked.connect(self._go_heading)
        self.heading_list.setAccessibleName('Разделы документа')
        self.splitter.addWidget(self.heading_list)
        self.pages = QStackedWidget()
        self.preview = MarkdownView()
        self.preview.setAccessibleName('Документ Canvas')
        self.preview.selectionChanged.connect(self.user_activity)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName('CanvasEditor')
        self.editor.setFont(ui_font(14))
        self.editor.setAccessibleName('Редактор Markdown документа')
        self.editor.setPlaceholderText('Текст отчёта в Markdown')
        self.editor.textChanged.connect(self._edited)
        self.pages.addWidget(self.preview)
        self.pages.addWidget(self.editor)
        self.splitter.addWidget(self.pages)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([170, 650])
        layout.addWidget(self.splitter, 1)
        footer = QWidget()
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(16, 7, 16, 7)
        self.status = QLabel('Документ сохраняется отдельно от исходных свидетельств.')
        self.status.setObjectName('SmallMuted')
        self.status.setWordWrap(True)
        footer_row.addWidget(self.status, 1)
        self.copy_button = QPushButton('Копировать')
        self.copy_button.setToolTip('Копировать документ в формате Markdown')
        self.copy_button.setFixedWidth(110)
        self.copy_button.setObjectName('QuietButton')
        self.copy_button.clicked.connect(self._copy_document)
        footer_row.addWidget(self.copy_button)
        layout.addWidget(footer)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)
        self._save_timer.timeout.connect(self.save_document)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(180)
        self._preview_timer.timeout.connect(self._refresh_preview)

    def open_document(self, text, document_id=None):
        if self.document_id and self._dirty:
            self.save_document()
        source = str(text)
        identifier = str(document_id) if document_id is not None else hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', identifier):
            raise ValueError('Некорректный идентификатор документа.')
        self.document_id, self._original_source = identifier, source
        current = self._documents.get(identifier)
        path = self.directory/(identifier+'.md')
        if current is None and path.is_file():
            if path.stat().st_size > 2_000_000:
                raise ValueError('Документ превышает допустимый размер.')
            current = path.read_text(encoding='utf-8')
        self._loading = True
        self.editor.setPlainText(source if current is None else current)
        self._loading = False
        self._dirty = False
        self.edit_button.setChecked(False)
        self._refresh_preview()
        self.status.setText('Документ Canvas · изменения не затрагивают исходные свидетельства.')

    set_document = open_document

    def _refresh_preview(self):
        text = self.editor.toPlainText()
        self.preview.set_source(text)
        self.heading_list.clear()
        outline = headings(text)
        for index, value in enumerate(outline):
            item = QListWidgetItem('  '*(value['level']-1)+value['title'])
            item.setToolTip(value['title'])
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.heading_list.addItem(item)
        self.heading_list.setVisible(bool(outline) and self.width() >= 560)
        title = outline[0]['title'] if outline else 'Отчёт'
        self.title.setText('Canvas · '+title[:100])
        self.title.setToolTip(title)

    def _edited(self):
        if self._loading:
            return
        self._dirty = True
        self.user_activity.emit()
        self.status.setText('Изменения сохраняются в локальном документе Canvas…')
        self._save_timer.start()
        self._preview_timer.start()

    def _switch_mode(self, editing):
        if not editing:
            self._refresh_preview()
        self.pages.setCurrentWidget(self.editor if editing else self.preview)
        self.edit_button.setText('Просмотр' if editing else 'Править')
        if editing:
            self.editor.setFocus()

    def _go_heading(self, item):
        self.edit_button.setChecked(False)
        target = item.data(Qt.ItemDataRole.UserRole)
        current = -1
        block = self.preview.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel():
                current += 1
                if current == target:
                    self.preview.setTextCursor(QTextCursor(block))
                    self.preview.ensureCursorVisible()
                    return
            block = block.next()

    def save_document(self):
        self._save_timer.stop()
        if not self.document_id:
            return None
        text = self.editor.toPlainText()
        if len(text.encode('utf-8')) > 2_000_000:
            self.status.setText('Документ слишком большой для локального сохранения.')
            return None
        try:
            destination = write_utf8(self.directory/(self.document_id+'.md'), text)
            # Metadata describes only the local editable copy, never evidence.
            write_utf8(self.directory/(self.document_id+'.json'), json.dumps({
                'id':self.document_id, 'updated_at':datetime.now(timezone.utc).isoformat(),
                'original_sha256':hashlib.sha256(self._original_source.encode('utf-8')).hexdigest(),
                'title':self.title.text()}, ensure_ascii=False, indent=2))
        except OSError:
            self.status.setText('Не удалось сохранить документ. Текст остаётся в Canvas.')
            return None
        self._documents[self.document_id] = text
        self._dirty = False
        self.status.setText('Сохранено локально · исходные свидетельства не изменены.')
        self.document_saved.emit(str(destination))
        return destination

    def export_document(self, path=None):
        if path is None:
            value, _ = QFileDialog.getSaveFileName(self, 'Сохранить отчёт Markdown', 'GrangerPet-report.md', 'Markdown (*.md)')
            if not value:
                return None
            path = value
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix('.md')
        try:
            result = write_utf8(destination, self.editor.toPlainText())
        except OSError:
            self.status.setText('Не удалось экспортировать документ.')
            return None
        self.status.setText('Документ экспортирован в Markdown.')
        return result

    def _export_clicked(self):
        self.export_document()

    def _copy_document(self):
        QApplication.clipboard().setText(self.editor.toPlainText())

    def _back(self):
        if self._dirty:
            self.save_document()
        self.close_requested.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.heading_list.setVisible(self.heading_list.count()>0 and self.width()>=560)

    def shutdown(self):
        self._preview_timer.stop()
        if self._dirty:
            self.save_document()
        self._save_timer.stop()
