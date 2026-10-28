"""Selectable native text bubbles, with predictable scrolling and no HTML input."""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from .motion import fade_in, reduced_motion
from .typography import ui_font


class BubbleText(QTextBrowser):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setObjectName('BubbleText')
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFont(ui_font(14))
        option = self.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(option)
        self.document().setDocumentMargin(0)
        self._plain = str(text)
        self._render_plain(self._plain)

    def _render_plain(self, text):
        # Preserve source text, including literal HTML. Only fenced code gets
        # a local character style; no model output becomes executable markup.
        cursor = QTextCursor(self.document())
        normal = QTextCharFormat()
        normal.setFont(ui_font(14))
        normal.setForeground(QColor('#F1F3F5'))
        code = QTextCharFormat(normal)
        code_font = QFont('Consolas')
        code_font.setPixelSize(13)
        code.setFont(code_font)
        code.setBackground(QColor('#101D2B'))
        fenced = False
        lines = text.splitlines(keepends=True)
        for line in lines:
            if line.lstrip().startswith('```'):
                fenced = not fenced
                continue
            cursor.insertText(line, code if fenced else normal)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        action = menu.addAction('Копировать сообщение целиком')
        action.triggered.connect(lambda: QApplication.clipboard().setText(self._plain))
        menu.exec(event.globalPos())

    def fit_height(self):
        width = max(1, self.viewport().width())
        self.document().setTextWidth(width)
        height = math.ceil(self.document().size().height()) + 2
        self.setFixedHeight(max(self.fontMetrics().height() + 2, height))

    def wheelEvent(self, event):
        # The outer conversation owns wheel/touchpad scrolling, while this
        # read-only editor owns only text selection and copying.
        event.ignore()


class MessageBubble(QFrame):
    def __init__(self, role, text, retry=None, parent=None):
        super().__init__(parent)
        self.role, self.message_text = role, str(text)
        self.setObjectName('OutgoingBubble' if role == 'user' else 'IncomingBubble' if role == 'model' else 'StatusBubble')
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(5)
        self.text_view = BubbleText(text, self)
        layout.addWidget(self.text_view)
        if retry:
            self.retry = QToolButton()
            self.retry.setText('Повторить')
            self.retry.setObjectName('InlineAction')
            self.retry.setAccessibleName('Повторить запрос вручную')
            self.retry.clicked.connect(retry)
            layout.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignLeft)
        self._max_width = 0

    def reflow(self, available_width):
        max_width = max(90, round(available_width * .80))
        metrics = QFontMetrics(ui_font(14))
        longest = max((metrics.horizontalAdvance(line) for line in self.message_text.splitlines()), default=0)
        width = min(max_width, max(64, longest + 28))
        if self.role == 'status':
            width = min(max_width, max(160, width))
        self.setFixedWidth(width)
        self.text_view.setFixedWidth(max(1, width - 24))
        self.text_view.fit_height()
        self.layout().activate()
        self.setFixedHeight(self.layout().sizeHint().height())


class MessageHistory(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('MessageHistory')
        self.viewport().setObjectName('MessageViewport')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName('История диалога с Гермионой')
        self.body = QWidget()
        self.body.setObjectName('MessageBody')
        self.rows = QVBoxLayout(self.body)
        self.rows.setContentsMargins(14, 18, 14, 16)
        self.rows.setSpacing(9)
        self.rows.addStretch(1)
        self.setWidget(self.body)
        self.bubbles = []
        self._records = []
        self._follow_bottom = True
        self._follow_scheduled = False
        self._appearing_bubble = None
        self._programmatic_scroll = False
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b'value', self)
        self._scroll_animation.setDuration(140)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_animation.finished.connect(self._scroll_finished)
        self.verticalScrollBar().valueChanged.connect(self._scroll_changed)
        self.verticalScrollBar().sliderPressed.connect(self._user_scroll_started)
        self.empty = QLabel('Спросите Гермиону\nоб открытых источниках или найденных сведениях', self.viewport())
        self.empty.setObjectName('ChatEmptyState')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._position_empty()

    def _scroll_changed(self, value):
        if not self._programmatic_scroll:
            bar = self.verticalScrollBar()
            self._follow_bottom = bar.maximum() - value <= 24

    def _scroll_finished(self):
        self._programmatic_scroll = False

    def _user_scroll_started(self):
        self._scroll_animation.stop()
        self._programmatic_scroll = False

    def _position_empty(self):
        size = self.viewport().size()
        self.empty.setGeometry(20, max(15, (size.height()-80)//2), max(10,size.width()-40), 80)

    def resizeEvent(self, event):
        following = self._follow_bottom
        super().resizeEvent(event)
        self._position_empty()
        for bubble in self.bubbles:
            bubble.reflow(max(100, self.viewport().width() - 28))
        self.rows.activate()
        if following:
            QTimer.singleShot(0, lambda: self._scroll_to_end(False))

    def append_message(self, role, text, retry=None):
        following = self._follow_bottom
        self._records.append({'role': role, 'text': str(text)})
        self.empty.hide()
        bubble = MessageBubble(role, text, retry, self.body)
        row = QWidget()
        row.setObjectName('MessageRow')
        horizontal = QHBoxLayout(row)
        horizontal.setContentsMargins(0, 0, 0, 0)
        if role == 'user':
            horizontal.addStretch(1)
            horizontal.addWidget(bubble)
        else:
            horizontal.addWidget(bubble)
            horizontal.addStretch(1)
        self.rows.insertWidget(self.rows.count()-1, row)
        self.bubbles.append(bubble)
        bubble.reflow(max(100, self.viewport().width() - 28))
        self.rows.activate()
        bubble.show()
        previous = self._appearing_bubble
        if previous is not None:
            animation = getattr(previous, '_appearance_animation', None)
            if animation is not None:
                animation.stop()
                previous.setGraphicsEffect(None)
                previous._appearance_animation = None
                animation.deleteLater()
        fade_in(bubble, 150)
        self._appearing_bubble = bubble
        if following and not self._follow_scheduled:
            self._follow_scheduled = True
            QTimer.singleShot(0, self._follow_if_needed)
        return bubble

    def _follow_if_needed(self):
        self._follow_scheduled = False
        if self._follow_bottom:
            self._scroll_to_end(True)

    def update_message(self, bubble, text):
        """Replace one streaming bubble without rebuilding the conversation."""
        if bubble not in self.bubbles:
            return
        index = self.bubbles.index(bubble)
        value = str(text)
        self._records[index]['text'] = value
        bubble.message_text = value
        bubble.text_view._plain = value
        bubble.text_view.document().clear()
        bubble.text_view._render_plain(value)
        following = self._follow_bottom
        bubble.reflow(max(100, self.viewport().width() - 28))
        self.rows.activate()
        if following and not self._follow_scheduled:
            self._follow_scheduled = True
            QTimer.singleShot(0, self._follow_if_needed)

    def _scroll_to_end(self, animate=True):
        bar = self.verticalScrollBar()
        self._scroll_animation.stop()
        self._programmatic_scroll = True
        if animate and not reduced_motion() and self.isVisible() and bar.maximum() > bar.value():
            self._scroll_animation.setStartValue(bar.value())
            self._scroll_animation.setEndValue(bar.maximum())
            self._scroll_animation.start()
        else:
            bar.setValue(bar.maximum())
            self._programmatic_scroll = False
        self._follow_bottom = True

    def wheelEvent(self, event):
        # Wheel and touchpad input retain Qt's normal pixel/angle behavior.
        self._scroll_animation.stop()
        self._programmatic_scroll = False
        super().wheelEvent(event)
        self._scroll_changed(self.verticalScrollBar().value())

    def toPlainText(self):
        return '\n\n'.join(item['text'] for item in self._records)

    def copy_all(self):
        QApplication.clipboard().setText(self.toPlainText())

    def clear(self):
        self._scroll_animation.stop()
        self._records.clear()
        self.bubbles.clear()
        self._appearing_bubble = None
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._follow_bottom = True
        self.empty.show()
