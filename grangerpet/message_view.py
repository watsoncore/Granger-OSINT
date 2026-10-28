"""Selectable native text bubbles, with predictable scrolling and no HTML input."""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from .motion import fade_in, reduced_motion
from .typography import ui_font
from .markdown_view import MarkdownView, code_blocks


class BubbleText(MarkdownView):
    def __init__(self, text, parent=None, *, markdown=True):
        self._as_markdown = markdown
        super().__init__(text, parent, auto_height=True)

    def set_source(self, text, *, preserve_selection=True):
        if self._as_markdown:
            return super().set_source(text, preserve_selection=preserve_selection)
        self._plain = str(text)
        self.setPlainText(self._plain)


class MessageBubble(QFrame):
    report_requested = Signal(str)

    def __init__(self, role, text, retry=None, parent=None):
        super().__init__(parent)
        self.role, self.message_text = role, str(text)
        self.setObjectName('OutgoingBubble' if role == 'user' else 'IncomingBubble' if role == 'model' else 'StatusBubble')
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(7)
        self.text_view = BubbleText(text, self, markdown=role == 'model')
        layout.addWidget(self.text_view)
        actions = QWidget()
        actions.setObjectName('BubbleActions')
        action_row = QHBoxLayout(actions)
        action_row.setContentsMargins(0, 2, 0, 0)
        action_row.setSpacing(10)
        self.canvas_button = QToolButton()
        self.canvas_button.setText('Открыть в Canvas')
        self.canvas_button.setObjectName('InlineAction')
        self.canvas_button.clicked.connect(self._request_report)
        action_row.addWidget(self.canvas_button)
        self.copy_code_button = QToolButton()
        self.copy_code_button.setText('Копировать код')
        self.copy_code_button.setObjectName('InlineAction')
        self.copy_code_button.clicked.connect(self._copy_code)
        action_row.addWidget(self.copy_code_button)
        action_row.addStretch(1)
        self._actions = actions
        layout.addWidget(actions)
        if retry:
            self.retry = QToolButton()
            self.retry.setText('Повторить')
            self.retry.setObjectName('InlineAction')
            self.retry.setAccessibleName('Повторить запрос вручную')
            self.retry.clicked.connect(retry)
            layout.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignLeft)
        self._refresh_actions()

    def _copy_code(self):
        blocks = code_blocks(self.message_text)
        QApplication.clipboard().setText('\n\n'.join(value for _, value in blocks))

    def _request_report(self):
        self.report_requested.emit(self.message_text)

    def _refresh_actions(self):
        report = self.role == 'model' and (len(self.message_text)>300 or self.message_text.count('\n')>=3 or self.message_text.startswith('#'))
        code = self.role == 'model' and bool(code_blocks(self.message_text))
        self.canvas_button.setVisible(report)
        self.copy_code_button.setVisible(code)
        self._actions.setVisible(report or code)

    def update_text(self, text):
        self.message_text = str(text)
        self.text_view.set_source(self.message_text)
        self._refresh_actions()

    def reflow(self, available_width):
        cap = 900 if self.role == 'model' else 680
        max_width = max(110, min(cap, round(available_width * .84)))
        metrics = QFontMetrics(ui_font(14))
        longest = max((metrics.horizontalAdvance(line) for line in self.message_text.splitlines()), default=0)
        width = min(max_width, max(76, longest + 32))
        if self._actions.isVisible():
            width = max(min(280, max_width), width)
        if self.role == 'status':
            width = min(max_width, max(160, width))
        self.setFixedWidth(width)
        self.text_view.setFixedWidth(max(1, width - 28))
        self.text_view.fit_height()
        self.layout().activate()
        self.setFixedHeight(self.layout().sizeHint().height())


class MessageHistory(QScrollArea):
    report_requested = Signal(str)
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
        self._pending_updates = {}
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(50)
        self._update_timer.timeout.connect(self.flush_updates)
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
            bubble.reflow(self._available_width())
        self.rows.activate()
        if following:
            QTimer.singleShot(0, lambda: self._scroll_to_end(False))

    def _available_width(self):
        gutter = max(14, (self.viewport().width()-1120)//2)
        self.rows.setContentsMargins(gutter, 18, gutter, 16)
        return max(100, self.viewport().width()-2*gutter)

    def append_message(self, role, text, retry=None):
        following = self._follow_bottom
        self._records.append({'role': role, 'text': str(text)})
        self.empty.hide()
        bubble = MessageBubble(role, text, retry, self.body)
        bubble.report_requested.connect(self.report_requested)
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
        bubble.reflow(self._available_width())
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
        """Coalesce streaming Markdown updates while retaining a stable bubble."""
        if bubble not in self.bubbles:
            return
        index = self.bubbles.index(bubble)
        value = str(text)
        self._records[index]['text'] = value
        self._pending_updates[bubble] = value
        if not self._update_timer.isActive():
            self._update_timer.start()

    def flush_updates(self):
        self._update_timer.stop()
        if not self._pending_updates:
            return
        following = self._follow_bottom
        old_scroll = self.verticalScrollBar().value()
        anchor, offset = None, 0
        if not following:
            for number in range(self.rows.count()-1):
                row = self.rows.itemAt(number).widget()
                if row and row.geometry().bottom() >= old_scroll:
                    anchor, offset = row, old_scroll-row.y()
                    break
        pending, self._pending_updates = self._pending_updates, {}
        self._programmatic_scroll = True
        for bubble, text in pending.items():
            if bubble in self.bubbles:
                bubble.update_text(text)
                bubble.reflow(self._available_width())
        self.rows.activate()
        if following and not self._follow_scheduled:
            self._follow_scheduled = True
            QTimer.singleShot(0, self._follow_if_needed)
        elif not following:
            def restore():
                try:
                    self.verticalScrollBar().setValue(max(0, anchor.y()+offset) if anchor else old_scroll)
                except RuntimeError:
                    return
                self._programmatic_scroll = False
                self._follow_bottom = False
            QTimer.singleShot(0, restore)
        else:
            self._programmatic_scroll = False

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
        self._update_timer.stop()
        self._pending_updates.clear()
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
