"""A search-first native panel. Settings, executions and evidence are separate."""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, Qt, QUrl, Signal, QVariantAnimation, QEasingCurve, QRectF, QRect, QPoint
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QPainter, QColor
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout,
    QLabel, QLineEdit, QListView, QMenu, QPlainTextEdit, QProgressBar, QPushButton,
    QSizePolicy, QStackedWidget, QTabWidget, QTabBar, QToolButton, QVBoxLayout, QWidget, QSizeGrip)

from .credentials import CredentialError, get_secret
from .dork_dialog import DorkDialog
from .dorks import google_url
from .engine import SearchController, SearchQuery, is_confirmed
from .engine.router import detect_query
from .result_view import BLOCKCHAIN_TYPES, ResultDelegate, ResultListModel, source_url
from .result_details import ResultDetails
from .search import SearchResult as GoogleResult
from .settings_dialog import SettingsDialog
from .theme import STYLE, style_for_theme, apply_theme
from .window_chrome import FramelessWindow, WindowHeader
from .chat import ChatWidget
from .ai_state import AIState
from .typography import ui_font
from .motion import reduced_motion, fade_in


def plain(text='', name=''):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


class NavigationTabBar(QTabBar):
    """Animate only a two-pixel indicator, retaining normal Qt tab semantics."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('ModeTabs')
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setFont(ui_font(14))
        self._indicator = QRectF()
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._advance)
        self.currentChanged.connect(self._selection_changed)

    def _target(self):
        if self.currentIndex() < 0:
            return QRectF()
        rect = self.tabRect(self.currentIndex())
        return QRectF(rect.left()+14, self.height()-3, max(1, rect.width()-28), 2)

    def _advance(self, rect):
        self._indicator = QRectF(rect)
        self.update()

    def _selection_changed(self, *_):
        self._animation.stop()
        target = self._target()
        if self._indicator.isEmpty() or not self.isVisible() or reduced_motion():
            self._advance(target)
            return
        self._animation.setStartValue(self._indicator)
        self._animation.setEndValue(target)
        self._animation.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._animation.stop()
        self._indicator = self._target()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#6C9ED2'))
        painter.drawRoundedRect(self._indicator if not self._indicator.isEmpty() else self._target(), 1, 1)


class PanelModes(QTabWidget):
    """Pages lay out wrapping text internally, without fixing window height.

    QTabWidget's default heightForWidth includes preferred heights of hidden
    pages and scroll views. Windows uses that as a native resize constraint,
    so a chat transcript could otherwise prevent shrinking the search window.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(NavigationTabBar(self))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)

    def hasHeightForWidth(self):
        return False

    def heightForWidth(self, width):
        return -1


class OsintPanel(FramelessWindow):
    user_activity = Signal()
    messages_seen = Signal(str, object)
    messages_removed = Signal(str, object)
    search_state = Signal(str)
    closed = Signal()

    def __init__(self, settings, store=None, parent=None):
        super().__init__(parent)
        self.settings, self.store = settings, store
        self._busy, self._ending = False, False
        self._query, self._chosen_text, self._chosen_kind = '', '', None
        self._executions = {}
        self._accept_results = False
        self._generation = 0
        self._pending_search = None
        self._ai_busy, self._ai_activity = False, 'idle'
        self._last_activity = None
        from .character import CharacterController
        self.character=CharacterController(self)
        self._result_types = set()
        self.chat_widget = None
        self.phase = 'idle'
        self.setWindowTitle('Granger-OSINT')
        self.setObjectName('OsintPanel')
        self.resize(760, 690)
        self.setMinimumSize(460, 420)
        self.setStyleSheet(style_for_theme(settings.ui_theme))
        self.ai_state = AIState(settings, parent=self)
        self.controller = SearchController(self)
        if hasattr(getattr(self.controller, 'search_event', None), 'connect'):
            self.controller.search_event.connect(self._controller_event)
        else:
            self.controller.result.connect(self._engine_result)
            self.controller.source_status.connect(self._source_status)
            self.controller.progress.connect(self._progress)
            self.controller.finished.connect(self._engine_finished)
            self.controller.error.connect(self._engine_error)
            self.controller.state.connect(self._engine_state)
        self.settings_dialog = SettingsDialog(settings, store, self, ai_state=self.ai_state)
        self.settings_dialog.settings_saved.connect(self.set_settings)
        self.connections = self.settings_dialog.connections
        self.dork_dialog = DorkDialog(self)
        self.dork_dialog.query_selected.connect(self._use_dork)
        # Legacy IPC may select a route explicitly, but the main interface has
        # no technical type selector. Clarification belongs to the current text.
        self.direction = QComboBox(self)
        for name in ('auto', 'username', 'email', 'phone', 'telegram', 'vk', 'instagram', 'web', 'blockchain', 'dork'):
            self.direction.addItem(name, name)
        self.direction.hide()
        self.direction.currentIndexChanged.connect(self._compat_kind_changed)
        self.chain = QComboBox(self)
        for title, value in (('Автоматически', ''), ('Ethereum', 'eth'), ('Polygon', 'polygon'), ('TON', 'ton'), ('Bitcoin', 'btc')):
            self.chain.addItem(title, value)
        self.chain.hide()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self.header = WindowHeader(self, 'Granger-OSINT', settings_action=self.open_settings, enable_window_modes=True)
        self.settings_button = self.header.settings_button
        self.close_button = self.header.close_button
        outer.addWidget(self.header)
        self.mode_tabs = PanelModes()
        self.mode_tabs.setObjectName('PanelModes')
        self.search_page = QWidget()
        self.search_page.setObjectName('SearchPage')
        layout = QVBoxLayout(self.search_page)
        layout.setContentsMargins(18, 14, 18, 12)
        layout.setSpacing(10)
        self.mode_tabs.addTab(self.search_page, 'Поиск')
        self.workspace = QStackedWidget()
        self.workspace.addWidget(self.mode_tabs)
        self.canvas = None
        outer.addWidget(self.workspace, 1)
        self.text = QLineEdit()
        self.text.setObjectName('MainQuery')
        self.text.setMinimumHeight(44)
        self.text.setPlaceholderText('Никнейм, email, TON-адрес, URL...')
        self.text.setClearButtonEnabled(True)
        self.text.returnPressed.connect(self.start_search)
        self.text.textChanged.connect(self._query_changed)
        query_row = QHBoxLayout()
        query_row.setSpacing(10)
        query_row.addWidget(self.text, 1)
        self.detection = plain('Введите данные для поиска', 'Detection')
        detection_row = QHBoxLayout()
        detection_row.setSpacing(8)
        detection_row.addWidget(self.detection, 1)
        self.change_kind = QToolButton()
        self.change_kind.setText('Изменить')
        self.change_kind.setObjectName('Disclosure')
        self.change_kind.setToolTip('Уточнить направление текущего запроса')
        self.change_kind.clicked.connect(lambda: self.choose_kind('auto'))
        self.change_kind.hide()
        detection_row.addWidget(self.change_kind)
        self.find = QPushButton('Найти')
        self.find.setObjectName('PrimaryButton')
        self.find.setFixedHeight(44)
        self.find.setMinimumWidth(88)
        self.find.clicked.connect(self._main_action)
        query_row.addWidget(self.find)
        layout.addLayout(query_row)
        layout.addLayout(detection_row)
        self.clarification = QWidget()
        clarification = QHBoxLayout(self.clarification)
        clarification.setContentsMargins(0, 0, 0, 0)
        clarification.setSpacing(6)
        clarification.addWidget(plain('Что искать?', 'Muted'))
        self.profiles_choice = QPushButton('Публичные профили')
        self.mentions_choice = QPushButton('Упоминания')
        for button, kind in ((self.profiles_choice, 'username'), (self.mentions_choice, 'dork')):
            button.setCheckable(True)
            button.setObjectName('ChoiceButton')
            button.clicked.connect(lambda checked=False, value=kind: self.choose_kind(value))
            clarification.addWidget(button)
        clarification.addStretch()
        self.clarification.hide()
        layout.addWidget(self.clarification)
        summary = QHBoxLayout()
        self.count_label = plain('Найдено: 0', 'ResultCount')
        self.count_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        summary.addWidget(self.count_label, 1)
        self.checked_label = plain('', 'SmallMuted')
        self.checked_label.setWordWrap(False)
        self.checked_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.checked_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        summary.addWidget(self.checked_label)
        layout.addLayout(summary)
        self.status = plain('', 'SearchStatus')
        self.status.hide()
        layout.addWidget(self.status)
        self.activity = QProgressBar()
        self.activity.setRange(0, 0)
        self.activity.setFixedHeight(2)
        self.activity.setTextVisible(False)
        self.activity.hide()
        layout.addWidget(self.activity)
        self.email_notice = plain('Регистрация не подтверждает личность владельца email.', 'SmallMuted')
        self.email_notice.hide()
        layout.addWidget(self.email_notice)
        self.blockchain_overview = QWidget()
        overview = QVBoxLayout(self.blockchain_overview)
        overview.setContentsMargins(0, 2, 0, 4)
        overview.setSpacing(4)
        overview_row = QHBoxLayout()
        self.blockchain_summary = plain('', 'ResultCount')
        overview_row.addWidget(self.blockchain_summary, 1)
        self.fact_group = QComboBox()
        self.fact_group.setMinimumWidth(184)
        self.fact_group.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.fact_group.setAccessibleName('Группа блокчейн-наблюдений')
        self.fact_group.currentIndexChanged.connect(self._filter_fact_group)
        self.fact_group.activated.connect(lambda *_: fade_in(self.results_stack, 160))
        overview_row.addWidget(self.fact_group)
        overview.addLayout(overview_row)
        self.blockchain_address = QLineEdit()
        self.blockchain_address.setObjectName('AddressSummary')
        self.blockchain_address.setReadOnly(True)
        self.blockchain_address.setAccessibleName('Исследуемый блокчейн-адрес')
        overview.addWidget(self.blockchain_address)
        self.attribution_summary = plain('', 'SmallMuted')
        overview.addWidget(self.attribution_summary)
        self.blockchain_overview.hide()
        layout.addWidget(self.blockchain_overview)
        self.result_model = ResultListModel(self)
        self._records = self.result_model.records
        self.result_model.count_changed.connect(self._update_count)
        self.results_view = QListView()
        self.results_view.setObjectName('EvidenceList')
        self.results_view.setAccessibleName('Результаты поиска')
        self.results_view.setModel(self.result_model)
        delegate = ResultDelegate(self.results_view)
        delegate.open_requested.connect(self._open_inline_result)
        delegate.details_requested.connect(self._show_index_details)
        self.results_view.setItemDelegate(delegate)
        self.results_view.setMouseTracking(True)
        self.results_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.results_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results_view.setLayoutMode(QListView.LayoutMode.Batched)
        self.results_view.setBatchSize(100)
        self.results_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.results_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_view.customContextMenuRequested.connect(self._result_menu)
        self.results_view.clicked.connect(self._show_index_details)
        self.results_view.selectionModel().selectionChanged.connect(self._selection_changed)
        self.results_stack = QStackedWidget()
        self.empty = plain('Начните с запроса\nНикнейм, email, адрес кошелька или публичная ссылка', 'EmptyState')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_stack.addWidget(self.empty)
        self.results_stack.addWidget(self.results_view)
        layout.addWidget(self.results_stack, 1)
        # Public actions remain available to keyboard/context-menu callers. Their
        # visible counterparts now belong directly to the corresponding row.
        self.open_button = QPushButton(self)
        self.copy_button = QPushButton(self)
        self.details_button = QPushButton(self)
        for button in (self.open_button, self.copy_button, self.details_button):
            button.hide()
            button.setEnabled(False)
        footer = QHBoxLayout()
        footer.setSpacing(4)
        self.analyze = QPushButton('Объяснить с помощью Гермионы')
        self.analyze.setObjectName('QuietButton')
        self.analyze.clicked.connect(self.analyze_current_results)
        footer.addWidget(self.analyze)
        footer.addStretch()
        self.dorks_button = QToolButton()
        self.dorks_button.setText('Операторы Google')
        self.dorks_button.setObjectName('Disclosure')
        self.dorks_button.clicked.connect(self.open_dorks)
        footer.addWidget(self.dorks_button)
        layout.addLayout(footer)
        self.errors_button = QToolButton()
        self.errors_button.setObjectName('Disclosure')
        self.errors_button.setText('Подробности источников')
        self.errors_button.setCheckable(True)
        self.errors_button.toggled.connect(self._toggle_diagnostics)
        self.errors_button.hide()
        error_actions = QHBoxLayout()
        error_actions.addWidget(self.errors_button)
        error_actions.addStretch()
        self.configure_access = QPushButton('Настроить доступ')
        self.configure_access.setObjectName('QuietButton')
        self.configure_access.clicked.connect(lambda: self.open_settings('Авторизация'))
        self.configure_access.hide()
        error_actions.addWidget(self.configure_access)
        layout.addLayout(error_actions)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumHeight(90)
        self.diagnostics.hide()
        layout.addWidget(self.diagnostics)
        self.attach_chat_widget(ChatWidget(settings, store, self, ai_state=self.ai_state))
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 2, 1)
        grip_row.addStretch()
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(12, 10)
        grip_row.addWidget(self.size_grip)
        outer.addLayout(grip_row)
        self._pending_timer = QTimer(self)
        self._pending_timer.setInterval(50)
        self._pending_timer.timeout.connect(self._start_pending)
        copy_action = QAction(self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self.copy_selected)
        self.results_view.addAction(copy_action)
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self._update_analysis_button()
        self.desktop_surface = None
        self.independent_main_window = False
        if QApplication.instance().property('web_desktop'):
            from .desktop_surface import DesktopSurface
            self.desktop_surface = DesktopSurface(self)
            self.independent_main_window = True
            while outer.count():
                item = outer.takeAt(0)
                if item.widget(): item.widget().hide()
            self.size_grip.hide()
            outer.setContentsMargins(0,0,0,0)
            outer.addWidget(self.desktop_surface)
            self.setMinimumSize(760,560)
            area=QApplication.primaryScreen().availableGeometry()
            self.resize(max(760,min(1120,area.width()-40)),max(560,min(760,area.height()-40)))

    def sizeHint(self):
        return QSize(760, 690)

    def attach_chat_widget(self, widget):
        if self.chat_widget is not None:
            self.mode_tabs.removeTab(self.mode_tabs.indexOf(self.chat_widget))
        self.chat_widget = widget
        self.mode_tabs.addTab(widget, 'Гермиона')
        widget.settings_requested.connect(lambda: self.open_settings('ИИ'))
        widget.activity_changed.connect(lambda state: self._emit_activity(state, origin='ai'))
        widget.character_event.connect(self.character.handle_event)
        widget.busy_changed.connect(self._on_ai_busy)
        widget.connection_changed.connect(lambda *_: self._update_analysis_button())
        if hasattr(widget, 'evidence_received'):
            widget.evidence_received.connect(self._agent_evidence)
        if hasattr(widget, 'report_requested'):
            widget.report_requested.connect(self.open_canvas)
        if hasattr(widget, 'user_activity'):
            widget.user_activity.connect(self.user_activity)

    def open_canvas(self, text):
        from .canvas import CanvasWorkspace
        if self.canvas is None:
            directory = Path(self.store.path).parent / 'canvas' if self.store is not None else None
            self.canvas = CanvasWorkspace(self, directory=directory)
            self.canvas.close_requested.connect(self.show_chat)
            if hasattr(self.canvas, 'user_activity'):
                self.canvas.user_activity.connect(self.user_activity)
            self.workspace.addWidget(self.canvas)
        self.canvas.open_document(text)
        self.workspace.setCurrentWidget(self.canvas)
        if self.desktop_surface:
            self.desktop_surface.bridge.route = 'canvas'
            self.desktop_surface.bridge.mark_dirty()
        self.user_activity.emit()

    def _agent_evidence(self, records):
        """Reuse the existing source list/details; keep manual query and results."""
        if self._ending or not isinstance(records, list):
            return
        for raw in records[:200]:
            if not isinstance(raw, dict):
                continue
            value = dict(raw)
            details = dict(value.get('details') or {})
            origin = value.get('provenance') or {}
            details.update(evidence_id=value.get('evidence_id', ''),
                           agent_tool=origin.get('tool', ''), original_query=origin.get('query', ''),
                           obtained_at=origin.get('obtained_at', ''),
                           evidence_verification=value.get('verification', 'unconfirmed'))
            value['details'] = details
            self._engine_result(value)

    def _on_ai_busy(self, busy):
        self._ai_busy = bool(busy)
        self._update_analysis_button()

    def show_chat(self):
        self.workspace.setCurrentWidget(self.mode_tabs)
        self.mode_tabs.setCurrentWidget(self.chat_widget)
        if self.desktop_surface:
            self.desktop_surface.bridge.route = 'chat'
            self.desktop_surface.bridge.mark_dirty()

    def show_search(self):
        self.workspace.setCurrentWidget(self.mode_tabs)
        self.mode_tabs.setCurrentWidget(self.search_page)
        if self.desktop_surface:
            self.desktop_surface.bridge.route = 'search'
            self.desktop_surface.bridge.mark_dirty()

    def open_message(self, message_id, index=None, conversation_id=None):
        if conversation_id and conversation_id != self.chat_widget.conversation_id:
            self.chat_widget.load_conversation(conversation_id)
        if self.isMinimized(): self.showNormal()
        self.show(); self.raise_(); self.activateWindow(); self.show_chat()
        if self.desktop_surface:
            self.desktop_surface.bridge.message_focus = message_id
            self.desktop_surface.bridge.mark_dirty()
        elif isinstance(index,int):
            self.chat_widget.history.verticalScrollBar().setValue(self.chat_widget.history.verticalScrollBar().maximum())

    def notification_context(self):
        """Only this application's current foreground conversation, no app scan."""
        route = self.desktop_surface.bridge.route if self.desktop_surface else ('chat' if self.mode_tabs.currentWidget() is self.chat_widget else '')
        return {'active': bool(self.isVisible() and not self.isMinimized() and self.isActiveWindow() and route == 'chat'),
                'conversation_id': self.chat_widget.conversation_id}

    def report_messages_seen(self, conversation_id, message_ids):
        """Accept frontend viewport ACKs only for the real active current chat."""
        context = self.notification_context()
        if not context['active'] or conversation_id != context['conversation_id'] or not isinstance(message_ids,list):
            return False
        available = {row['id'] for index,row in enumerate(self.chat_widget.messages)
            if row.get('role') in ('model','status') and row.get('id')
            and not (self.chat_widget.busy and index == self.chat_widget._stream_index)}
        visible = list(dict.fromkeys(identifier for identifier in message_ids[:500] if isinstance(identifier,str) and identifier in available))
        if visible:
            self.messages_seen.emit(conversation_id, visible)
        return bool(visible)

    def report_messages_removed(self, conversation_id, message_ids):
        """Local controller acknowledgement after an explicit successful clear."""
        if isinstance(conversation_id,str) and isinstance(message_ids,list):
            identifiers = [value for value in message_ids if isinstance(value,str) and len(value)<=160]
            self.messages_removed.emit(conversation_id,identifiers)

    def hermione_dock_geometry(self):
        if not self.desktop_surface or not self.isVisible() or self.isMinimized(): return QRect()
        value = self.desktop_surface.bridge._dock_rect
        if not value.isValid(): return QRect()
        zoom=self.desktop_surface.zoomFactor()
        box=QRect(round(value.x()*zoom),round(value.y()*zoom),round(value.width()*zoom),round(value.height()*zoom))
        box=box.intersected(self.desktop_surface.rect())
        if box.width()<56 or box.height()<56: return QRect()
        return QRect(self.desktop_surface.mapToGlobal(box.topLeft()),box.size())

    def desktop_window_state(self):
        def owned_window(widget):
            # Qt top-level owned dialogs have a QObject parent but are not
            # QWidget.isAncestorOf descendants on Windows.
            while widget is not None:
                if widget is self:return True
                widget=widget.parent()
            return False
        active = QApplication.activeWindow()
        owned = owned_window(active)
        modal = QApplication.activeModalWidget()
        owned_modal = owned_window(modal)
        return {'active':bool(self.desktop_surface and self.isVisible() and not self.isMinimized() and
            (self.isActiveWindow() or owned or owned_modal)),
            'geometry':self.frameGeometry(),'dock':self.hermione_dock_geometry(),
            'obstructions':[modal.frameGeometry()] if owned_modal else []}

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'blockchain_address'):
            expanded = self.height() >= 500
            self.blockchain_address.setVisible(expanded and bool(self.blockchain_address.text()))
            self.attribution_summary.setVisible(expanded)

    def _emit_activity(self, state, origin='search'):
        if origin == 'ai':
            self._ai_activity = state
        if self._busy:
            chosen = 'thinking' if origin == 'search' and state == 'thinking' else 'working'
        elif self._ai_busy:
            chosen = self._ai_activity if self._ai_activity in ('thinking', 'working') else 'thinking'
        else:
            chosen = state
        if chosen != self._last_activity:
            self._last_activity = chosen
            self.character.activity(chosen)
            self.search_state.emit(chosen)

    def set_settings(self, settings):
        self.settings = settings
        apply_theme(QApplication.instance(),settings.ui_theme)
        self.ai_state.set_settings(settings)
        self.settings_dialog.set_settings(settings)
        self.chat_widget.set_settings(settings)
        self._update_analysis_button()
        QApplication.instance().setProperty('reduced_motion',getattr(settings,'reduced_motion',False))

    def open_settings(self, section=None):
        if self.desktop_surface:
            self.desktop_surface.bridge.route='settings'
            self.desktop_surface.bridge.mark_dirty()
            return
        self.open_native_settings(section)

    def open_native_settings(self, section=None):
        if self.desktop_surface:
            self.desktop_surface.bridge.route='settings'
            self.desktop_surface.bridge.mark_dirty()
            if self.isMinimized(): self.showNormal()
            self.show();self.raise_();self.activateWindow()
            return
        if isinstance(section, str):
            tabs = self.connections.tabs
            for index in range(tabs.count()):
                if tabs.tabText(index) == section:
                    tabs.setCurrentIndex(index)
                    break
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()
        if self.settings_dialog.readiness.rowCount() == 0:
            self.settings_dialog.refresh_readiness()

    def open_dorks(self):
        self.dork_dialog.text.setText(self.text.text())
        self.dork_dialog.show()
        self.dork_dialog.raise_()

    def _use_dork(self, query):
        self.text.setText(query)
        self.choose_kind('dork')
        self.text.setFocus()

    def set_query_kind(self, kind):
        index = self.direction.findData(kind)
        if index >= 0:
            self.direction.blockSignals(True)
            self.direction.setCurrentIndex(index)
            self.direction.blockSignals(False)
        self.choose_kind(kind)

    def _compat_kind_changed(self):
        self.choose_kind(self.direction.currentData())

    def choose_kind(self, kind):
        self._chosen_text = self.text.text().strip()
        self._chosen_kind = None if kind == 'auto' else kind
        self._refresh_detection()

    def _query_changed(self):
        if self.text.text().strip() != self._chosen_text:
            self._chosen_kind = None
        self._refresh_detection()

    def _resolution(self):
        chosen = self._chosen_kind if self._chosen_text == self.text.text().strip() else None
        return detect_query(self.text.text(), chosen_kind=chosen,
            options={'source_root': getattr(self.settings, 'source_root', ''),
                     'runtime_python': getattr(self.settings, 'runtime_python', '')})

    def _refresh_detection(self):
        if not self.text.text().strip():
            self.detection.setText('Вставьте запрос, чтобы определить направление')
            self.clarification.hide()
            self.change_kind.hide()
            if not self._busy:
                self._set_phase('idle')
            return
        resolution = self._resolution()
        self.clarification.setVisible(resolution.requires_clarification)
        original = detect_query(self.text.text(), options={'source_root': getattr(self.settings, 'source_root', '')})
        self.change_kind.setVisible(original.requires_clarification and not resolution.requires_clarification)
        self.profiles_choice.setChecked(self._chosen_kind == 'username')
        self.mentions_choice.setChecked(self._chosen_kind == 'dork')
        if not resolution.valid:
            self.detection.setText(resolution.error)
        elif resolution.requires_clarification:
            self.detection.setText('Определено: текстовый запрос')
            if not self._busy:
                self._set_phase('needs_clarification')
        else:
            self.detection.setText(' · '.join(v for v in (resolution.label, resolution.source_label) if v))

    def _main_action(self):
        self.cancel_search() if self._busy else self.start_search()

    def _google_key(self):
        try:
            return getattr(self.settings, 'api_key', '') or get_secret('google_api_key')
        except CredentialError:
            return ''

    def _has_api(self):
        return bool(self._google_key() and getattr(self.settings, 'api_cx', ''))

    def _search_options(self, kind=None):
        kind = kind or self._resolution().kind
        options = {name: getattr(self.settings, name, '') for name in ('source_root', 'runtime_python', 'telegram_api_id', 'instagram_username')}
        options.update(tools_root=getattr(self.settings, 'source_root', ''), google_cx=getattr(self.settings, 'api_cx', ''),
                       enable_snoop=getattr(self.settings, 'enable_snoop', False))
        chain = self._resolution().chain or self.chain.currentData()
        if chain:
            options['chain'] = chain
        names = {'web': ('google_api_key',), 'dork': ('google_api_key',), 'telegram': ('telegram_api_hash', 'telegram_session'),
                 'vk': ('vk_token',), 'instagram': ('instagram_session',)}.get(kind, ())
        for name in names:
            try:
                options[name] = self._google_key() if name == 'google_api_key' else get_secret(name)
            except CredentialError:
                options[name] = ''
        return options

    def _clear_results(self):
        self.result_model.clear()
        self._result_types.clear()
        self._executions.clear()
        self.diagnostics.clear()
        self.errors_button.hide()
        self.configure_access.hide()
        self.errors_button.setChecked(False)
        self.diagnostics.hide()
        self.checked_label.clear()
        self.email_notice.hide()
        self.blockchain_overview.hide()

    def start_search(self):
        if self._ending:
            return
        resolution = self._resolution()
        if not resolution.valid:
            self.status.show()
            self.status.setText(resolution.error)
            self._emit_activity('error')
            return
        if resolution.requires_clarification:
            self.clarification.show()
            self._set_phase('needs_clarification')
            return
        if self._busy:
            # The controller bounds children across generations. Replacing a
            # request can start immediately while the previous generation exits;
            # queued old evidence is rejected by the generation below.
            self._accept_results = False
            self.controller.cancel()
            self._busy = False
        self._pending_search = None
        self._clear_results()
        self._query = resolution.text
        self._busy, self._accept_results = True, True
        self.find.setText('Остановить')
        self.activity.show()
        self._set_phase('detecting')
        options = self._search_options(resolution.kind)
        request = SearchQuery(resolution.text, kind=resolution.kind,
            limit=getattr(self.settings, 'request_limit', 20), timeout=getattr(self.settings, 'search_timeout', 25), options=options)
        self._generation = getattr(self.controller, 'generation', self._generation) + 1
        if self.controller.start(request, options):
            self._generation = getattr(self.controller, 'generation', self._generation + 1)
        else:
            self._busy = self._accept_results = False
            self.find.setText('Найти')
            self.activity.hide()

    def _start_pending(self):
        if self._ending or not self._pending_search:
            self._pending_timer.stop()
            return
        if self.controller.running:
            return
        text, kind = self._pending_search
        self._pending_search = None
        self._pending_timer.stop()
        self.text.setText(text)
        self.choose_kind(kind or 'auto')
        self.start_search()

    def cancel_search(self):
        if not self._busy:
            return
        self._accept_results = False
        self.controller.cancel()
        self._busy = False
        self.find.setText('Найти')
        self.activity.hide()
        self._set_phase('cancelled')
        self._emit_activity('idle')

    def _controller_event(self, generation, kind, payload):
        if self._ending or generation != self._generation:
            return
        if kind == 'result':
            if self._accept_results:
                self._engine_result(payload)
        elif kind == 'execution':
            self._source_status(payload)
        elif kind == 'progress':
            self._progress(*payload)
        elif kind == 'finished':
            self._engine_finished(payload)
        elif kind == 'phase' and self._accept_results:
            self._set_phase(str(payload))
        elif kind == 'error':
            self._engine_error(payload)
        elif kind == 'state':
            self._engine_state(payload)
        elif kind == 'stage' and self._accept_results:
            event = payload.get('stage', '') if isinstance(payload, dict) else str(payload)
            message = {'collectors.start': 'Получение данных блокчейна…', 'source.start': 'Получение данных источника…',
                'source.result': 'Обработка полученных данных…', 'inference.frontier.start': 'Анализ подтверждённых связей…',
                'analysis.start': 'Анализ блокчейн-адреса…', 'analysis.complete': 'Обработка результатов…'}.get(event)
            if message:
                self.status.setText(message)

    def _engine_result(self, result):
        if self._ending:
            return
        if isinstance(result, GoogleResult):
            result = {'id': result.url, 'title': result.title, 'type': 'web', 'platform': 'Google', 'url': result.url,
                      'description': result.snippet, 'details': {'query': result.query}, 'status': 'indexed', 'sources': ['Google API']}
        accepted = self.result_model.upsert(result)
        if accepted is None:
            return
        self.results_stack.setCurrentIndex(1 if self.result_model.rowCount() else 0)
        value = result.to_dict() if hasattr(result, 'to_dict') else result
        self._result_types.add(value.get('type'))
        self._update_result_context()
        self._update_count()
        if self._busy:
            self._set_phase('partial_results')
        self._update_analysis_button()

    def _update_count(self, *_):
        count = self.result_model.confirmed_count
        total = self.result_model.rowCount()
        uncertain = total - count
        self.count_label.setText(f'Найдено: {count}' + (f' · требуют проверки: {uncertain}' if uncertain else ''))
        self.results_stack.setCurrentIndex(1 if total else 0)
        self._selection_changed()

    def _update_result_context(self):
        self.email_notice.setVisible('email_check' in self._result_types)
        blockchain = bool(self._result_types & BLOCKCHAIN_TYPES)
        self.blockchain_overview.setVisible(blockchain)
        if not blockchain:
            return
        records = [value for value in self._records.values() if value.get('type') in BLOCKCHAIN_TYPES]
        if not records:
            return
        network = str(records[0].get('platform') or 'Блокчейн').split('·')[-1].strip()
        self.blockchain_summary.setText(f'{network} · наблюдений: {len(records)}')
        address = next((str((value.get('details') or {}).get('normalized_address')) for value in records
                        if (value.get('details') or {}).get('normalized_address')), self._query)
        self.blockchain_address.setVisible(self.height() >= 500 and bool(address))
        self.blockchain_address.setText(address)
        self.blockchain_address.setCursorPosition(0)
        self.blockchain_address.setToolTip(address)
        labels = [value for value in records if value.get('type') in ('label', 'attribution')]
        confirmed = [str(value.get('title')) for value in labels if is_confirmed(value)]
        self.attribution_summary.setText('Атрибуция: ' + ('; '.join(confirmed) if confirmed else 'требует проверки источника' if labels else 'нет подтверждённых сведений'))
        self.attribution_summary.setVisible(self.height() >= 500)
        self.blockchain_summary.setToolTip(address + '\n' + self.attribution_summary.text())
        chosen = self.fact_group.currentData()
        groups = (('Все наблюдения', ''), ('Транзакции', 'transaction'), ('Контрагенты', 'relationship'),
                  ('Атрибуция', 'attribution'), ('Другие сведения', 'other'))
        self.fact_group.blockSignals(True)
        self.fact_group.clear()
        for title, group in groups:
            count = sum(self._fact_group(value) == group for value in records) if group else len(records)
            if count:
                self.fact_group.addItem(f'{title} · {count}', group)
        index = self.fact_group.findData(chosen)
        self.fact_group.setCurrentIndex(max(0, index))
        self.fact_group.blockSignals(False)
        self._filter_fact_group()

    @staticmethod
    def _fact_group(value):
        kind = value.get('type')
        return 'attribution' if kind in ('label', 'attribution') else kind if kind in ('transaction', 'relationship') else 'other'

    def _filter_fact_group(self, *_):
        group = self.fact_group.currentData() or ''
        for row in range(self.result_model.rowCount()):
            self.results_view.setRowHidden(row, bool(group and self._fact_group(self.result_model.record(row)) != group))

    def _source_status(self, status):
        source = getattr(status, 'source', '') or getattr(status, 'source_id', '')
        self._executions[source] = status
        failures = [value for value in self._executions.values() if getattr(value, 'state', '') in ('error', 'unavailable', 'auth_required', 'timeout')]
        self.configure_access.setVisible(any(getattr(value, 'state', '') == 'auth_required' for value in failures))
        self.errors_button.setText(f'Показать ошибки: {len(failures)}' if failures else 'Диагностика источников')
        self.errors_button.setVisible(bool(self._executions))
        titles = {'queued': 'ожидание', 'running': 'выполняется', 'complete': 'завершён', 'empty': 'совпадений нет',
                  'error': 'ошибка', 'unavailable': 'недоступен', 'auth_required': 'нужна авторизация', 'timeout': 'таймаут', 'cancelled': 'отменён', 'partial': 'неполное покрытие'}
        text = '\n'.join(f'{getattr(value, "label", "") or key}: {titles.get(getattr(value, "state", ""), getattr(value, "state", ""))}'
            + (f' — {getattr(value, "message", "")}' if getattr(value, 'message', '') else '')
            for key, value in self._executions.items())
        self.diagnostics.setPlainText(text)

    def _toggle_diagnostics(self, checked):
        self.diagnostics.setVisible(checked)

    def _progress(self, done, total):
        self.checked_label.setText(f'Проверено: {done}/{total}')

    def _engine_state(self, state):
        if not self._ending and self._busy:
            self._emit_activity(state)

    def _engine_error(self, message):
        self.status.show()
        self.status.setText(str(message))

    def _engine_finished(self, summary):
        if self._ending:
            return
        self._busy = False
        self._accept_results = False
        self.find.setText('Найти')
        self.activity.hide()
        statuses = getattr(summary, 'statuses', [])
        errors = sum(getattr(item, 'state', '') in ('error', 'unavailable', 'auth_required', 'timeout', 'partial') for item in statuses)
        if getattr(summary, 'cancelled', False):
            phase = 'cancelled'
        elif getattr(summary, 'phase', '') == 'failed':
            phase = 'failed'
        elif self.result_model.rowCount():
            phase = 'completed_with_errors' if errors else 'completed'
        else:
            phase = 'completed_with_errors' if errors else 'completed_empty'
        self._set_phase(phase)
        checked = getattr(summary, 'checked_sources', sum(bool(getattr(item, 'started_at', None)) for item in statuses))
        self.checked_label.setText(f'Проверено: {checked}')
        self._update_count()
        confirmed = self.result_model.confirmed_count
        self._emit_activity('happy' if confirmed and not getattr(summary, 'cancelled', False) else 'error' if phase == 'failed' else 'idle')
        if self._pending_search:
            self._pending_timer.start()

    def _set_phase(self, phase):
        self.phase = phase
        labels = {'idle': 'Введите запрос', 'detecting': 'Определяю направление…', 'needs_clarification': 'Выберите, что искать',
                  'searching': 'Поиск выполняется…', 'partial_results': 'Получены результаты · поиск продолжается',
                  'completed': 'Поиск завершён', 'completed_empty': 'Совпадений не найдено',
                  'completed_with_errors': 'Часть источников недоступна · проверка неполная',
                  'failed': 'Не удалось выполнить поиск', 'cancelled': 'Поиск отменён'}
        self.status.setText(labels.get(phase, phase))
        self.status.setVisible(phase != 'idle')
        if not self.result_model.rowCount():
            self.empty.setText('Совпадений не найдено' if phase in ('completed_empty', 'completed_with_errors') else 'Поиск отменён' if phase == 'cancelled'
                else 'Проверяю доступные источники…' if phase in ('detecting', 'searching') else 'Здесь появятся найденные объекты.\nНастройки открываются отдельно кнопкой шестерёнки.')

    def _selected(self):
        return self.results_view.currentIndex().data(ResultListModel.RecordRole)

    def _selection_changed(self, *_):
        value = self._selected()
        self.open_button.setEnabled(bool(value and source_url(value)))
        self.copy_button.setEnabled(bool(value))
        self.details_button.setEnabled(bool(value))

    def _open_result(self, url):
        address = QUrl(url)
        if address.scheme() not in ('http', 'https') or not QDesktopServices.openUrl(address):
            self.status.setText('Не удалось открыть источник в браузере.')

    def open_selected(self):
        value = self._selected()
        if value and source_url(value):
            self._open_result(source_url(value))

    def _open_inline_result(self, url):
        # QListView may also emit clicked after a delegate handles release. The
        # inline arrow opens only the source, the rest of the row opens details.
        self._inline_open_until = time.monotonic() + 0.15
        self._open_result(url)

    def _show_index_details(self, index):
        if time.monotonic() < getattr(self, '_inline_open_until', 0):
            return
        if index.isValid():
            self.results_view.setCurrentIndex(index)
            self.show_selected_details()

    def copy_selected(self):
        value = self._selected()
        if value:
            QApplication.clipboard().setText(source_url(value) or json.dumps(value, ensure_ascii=False, indent=2))

    def show_selected_details(self):
        value = self._selected()
        if not value:
            return
        self.details_dialog = ResultDetails(value, self)
        self.details_dialog.show()
        self.details_dialog.raise_()

    def _result_menu(self, point):
        index = self.results_view.indexAt(point)
        if not index.isValid():
            return
        self.results_view.setCurrentIndex(index)
        menu = QMenu(self)
        if source_url(self._selected()):
            menu.addAction('Открыть источник', self.open_selected)
            menu.addAction('Скопировать URL', self.copy_selected)
        menu.addAction('Полные сведения', self.show_selected_details)
        menu.exec(self.results_view.viewport().mapToGlobal(point))

    def _update_analysis_button(self):
        provider = getattr(self.settings, 'ai_provider', 'none')
        self.analyze.setVisible(provider in ('deepseek', 'ollama'))
        self.analyze.setText('Объяснить с помощью Гермионы')
        ready = bool(self.chat_widget and getattr(self.chat_widget, '_ready', False))
        self.analyze.setEnabled(bool(self._records) and ready and not self._ai_busy)
        self.analyze.setToolTip('Выбрать сведения и передать их модели для объяснения' if ready else 'Подключите ИИ в настройках')

    def analyze_current_results(self):
        if not self._records or not self.chat_widget or self._ai_busy:
            return
        self.mode_tabs.setCurrentWidget(self.chat_widget)
        self.chat_widget.analyze_results(list(self._records.values()))

    def shutdown(self):
        if self.desktop_surface is not None:
            self.desktop_surface.shutdown()
        if self.canvas is not None:
            self.canvas.shutdown()
        if self._ending:
            return
        self._ending = True
        self._accept_results = False
        self._pending_timer.stop()
        self.controller.shutdown()
        self.settings_dialog.shutdown()
        self.dork_dialog.hide()
        self.chat_widget.shutdown()
        for dialog in self.findChildren(ResultDetails):
            dialog.close()
        self._busy = False
        self.hide()

    def closeEvent(self, event):
        event.ignore()
        self.chat_widget.cancel()
        for dialog in self.findChildren(ResultDetails):
            dialog.close()
        self.hide()
        self.closed.emit()
