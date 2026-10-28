"""Native, inert GitHub-flavoured Markdown for chat and local documents.

Qt renders text and tables. External images/resources and active HTML never
load; clicking a supported link is an explicit user action.
"""
from __future__ import annotations

import ipaddress
import math
import re
from urllib.parse import urlsplit

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPalette, QTextCursor, QTextDocument, QTextFormat, QTextLength, QTextOption
from PySide6.QtWidgets import QApplication, QFrame, QSizePolicy, QTextBrowser

from .typography import ui_font


FEATURES = QTextDocument.MarkdownFeature.MarkdownDialectGitHub | QTextDocument.MarkdownFeature.MarkdownNoHTML


def public_link(address):
    try:
        value = urlsplit(str(address))
        host = value.hostname or ''
        if value.scheme.lower() not in ('http', 'https') or not host or value.username or value.password:
            return False
        if host.casefold() == 'localhost' or host.casefold().endswith(('.localhost', '.local', '.internal')):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            # Unqualified intranet names and alternate numeric-IP spellings
            # are unsuitable destinations for untrusted report hyperlinks.
            if '.' not in host or re.fullmatch(r'[0-9.]+', host):
                return False
        return value.port in (None, 80, 443)
    except (ValueError, UnicodeError):
        return False


def code_blocks(text):
    blocks, current, fence, language = [], [], None, ''
    for line in str(text).splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)
        if match:
            marker = match[1]
            if fence is None:
                fence, language, current = marker, match[2].strip(), []
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                blocks.append((language[:40], '\n'.join(current)))
                fence, current = None, []
            else:
                current.append(line)
        elif fence is not None:
            current.append(line)
    if fence is not None:
        blocks.append((language[:40], '\n'.join(current)))
    return blocks


def headings(text):
    """Readable navigation labels; code fences cannot create fake headings."""
    result, fence = [], None
    for line_number, line in enumerate(str(text).splitlines()):
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            fence = None if fence and marker[1][0] == fence[0] else marker[1]
            continue
        match = re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$', line)
        if match and fence is None:
            result.append({'level':len(match[1]), 'title':re.sub(r'[*_`]', '', match[2])[:180], 'line':line_number})
    return result


class MarkdownView(QTextBrowser):
    link_rejected = Signal(str)
    evidence_requested = Signal(str)

    def __init__(self, text='', parent=None, *, auto_height=False):
        super().__init__(parent)
        self._plain = ''
        self._auto_height = auto_height
        self.setObjectName('BubbleText' if auto_height else 'MarkdownDocument')
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFont(ui_font(14))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard | Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if auto_height else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed if auto_height else QSizePolicy.Policy.Expanding)
        option = self.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(option)
        self.document().setDocumentMargin(0 if auto_height else 18)
        self.document().setDefaultFont(ui_font(14))
        self.document().setDefaultStyleSheet('a { color: #8ec7f5; text-decoration: none; } blockquote { color: #b8c7d7; } th { background: #243442; }')
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Link, QColor('#8ec7f5'))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor('#b7b1ec'))
        self.setPalette(palette)
        self.anchorClicked.connect(self._open_anchor)
        self.set_source(text)

    def loadResource(self, resource_type, name):
        # QTextBrowser would otherwise read local files or fetch image resources.
        return None

    def _open_anchor(self, url):
        address = url.toString()
        if re.fullmatch(r'(?:evidence:|#)?ev_[a-f0-9]{20}', address):
            self.evidence_requested.emit(address.split(':')[-1].lstrip('#'))
        elif address.startswith('#'):
            self.scrollToAnchor(address[1:])
        elif public_link(address):
            QDesktopServices.openUrl(QUrl(address))
        else:
            self.link_rejected.emit(address)

    def set_source(self, text, *, preserve_selection=True):
        value = str(text)
        cursor = self.textCursor()
        anchor, position = cursor.anchor(), cursor.position()
        scroll, horizontal = self.verticalScrollBar().value(), self.horizontalScrollBar().value()
        self._plain = value
        # Preserve an image's alt label as inert text/link, without loading it.
        rendered = re.sub(r'!\[([^\]\n]*)\]\(([^\n)]*)\)', lambda m:'[' + (m[1] or 'Изображение') + '](' + m[2] + ')', value)
        self.document().setMarkdown(rendered, FEATURES)
        self._format_document()
        if preserve_selection:
            maximum = max(0, self.document().characterCount()-1)
            cursor = QTextCursor(self.document())
            cursor.setPosition(min(anchor, maximum))
            cursor.setPosition(min(position, maximum), QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)
        self.verticalScrollBar().setValue(scroll)
        self.horizontalScrollBar().setValue(horizontal)

    def _render_plain(self, text):
        # Compatibility with the previous bubble renderer's public surface.
        self.set_source(text)

    def _format_document(self):
        editor = QTextCursor(self.document())
        editor.beginEditBlock()
        block = self.document().begin()
        while block.isValid():
            form = block.blockFormat()
            form.setLineHeight(125, 1)
            form.setTopMargin(7 if form.headingLevel() else 2)
            form.setBottomMargin(6 if form.headingLevel() else 5)
            cursor = QTextCursor(block)
            cursor.setBlockFormat(form)
            if form.headingLevel():
                char = cursor.blockCharFormat()
                char.setFontWeight(QFont.Weight.DemiBold)
                font = ui_font(max(15, 22-form.headingLevel()))
                font.setWeight(QFont.Weight.DemiBold)
                char.setFont(font)
                cursor.setBlockCharFormat(char)
            block = block.next()
        editor.endEditBlock()

    def _tables(self):
        frames = list(self.document().rootFrame().childFrames())
        while frames:
            frame = frames.pop(0)
            if hasattr(frame, 'columns'):
                yield frame
            frames.extend(frame.childFrames())

    def fit_height(self):
        width = max(20, self.viewport().width())
        self.document().setTextWidth(width)
        for table in self._tables():
            form = table.format()
            # Long reports keep normal paragraph wrapping while genuinely wide
            # tables retain columns and use the native horizontal scrollbar.
            table_width = max(width, min(2400, table.columns()*128))
            if form.width().type() == QTextLength.Type.FixedLength and abs(form.width().rawValue()-table_width)<1 and form.cellPadding()==7:
                continue
            form.setWidth(QTextLength(QTextLength.Type.FixedLength, table_width))
            form.setCellPadding(7)
            form.setCellSpacing(0)
            form.setBorder(1)
            form.setBorderBrush(QColor('#405263'))
            table.setFormat(form)
        height = math.ceil(self.document().size().height()) + 3
        if self.horizontalScrollBar().maximum() > 0:
            height += self.horizontalScrollBar().sizeHint().height()
        if self._auto_height:
            self.setFixedHeight(max(self.fontMetrics().height()+4, height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._auto_height:
            self.fit_height()

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction('Копировать Markdown целиком')
        action.triggered.connect(lambda:QApplication.clipboard().setText(self._plain))
        blocks = code_blocks(self._plain)
        if blocks:
            code_menu = menu.addMenu('Копировать блок кода')
            for index, (language, code) in enumerate(blocks):
                code_action = code_menu.addAction(f'{index+1}. {language or "Код"}')
                code_action.triggered.connect(lambda _checked=False,value=code:QApplication.clipboard().setText(value))
        menu.exec(event.globalPos())

    def wheelEvent(self, event):
        if self._auto_height and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            event.ignore()
        else:
            super().wheelEvent(event)
