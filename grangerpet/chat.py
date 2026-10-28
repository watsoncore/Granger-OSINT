"""Explicit, cancellable conversation and evidence explanation beside search."""
from __future__ import annotations

from copy import deepcopy
import math
import json
from pathlib import Path
import re
import threading
import time
import uuid

from PySide6.QtCore import QPointF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTextLayout, QTextOption
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QApplication, QFrame, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget, QMessageBox)

from .ai import AIError, DeepSeekClient, OllamaClient, analyze_results as explain_evidence
from .ai_keys import resolve_deepseek_key
from .engine.models import is_confirmed
from .ui_jobs import UiJob
from .ai_state import AIState
from .message_view import MessageHistory
from .typography import ui_font
from .agent import AgentRunner, AgentLimits
from .agent_tools import ToolRegistry
from .agent_journal import InvestigationJournal
from .chat_archive import ChatArchive
from .conversations import ConversationLibrary
from .context import conversation_context


def no_tools_requested(text):
    return bool(re.search(r'(?iu)(без\s+(?:веб[- ]?)?(?:поиска|инструментов)|не\s+(?:используй|запускай)\s+(?:никакие\s+)?инструмент|не\s+обращайся\s+в\s+интернет)', text))


def investigation_requested(text):
    """Route explicit research requests; ordinary conversation keeps its fast path."""
    return not no_tools_requested(text) and bool(re.search(r'(?iu)(найд[иуё]|найти|поищ|поиск|провер[ьить]|исслед|упоминан|сопостав|пробей|whois|rdap|dns|lookup|investigat|search\b|профил|кошел[её]к|блокчейн|прочита|прочти|открой|изучи|страниц|https?://)', text))


def label(text, name='Muted'):
    value = QLabel(text)
    value.setObjectName(name)
    value.setTextFormat(Qt.TextFormat.PlainText)
    value.setWordWrap(True)
    return value


class MessageInput(QPlainTextEdit):
    send_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fitting = False
        self.setObjectName('ChatComposerInput')
        self.setFont(ui_font(14))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.textChanged.connect(self._fit)
        self.setFixedHeight(46)

    def _fit(self, *_):
        if self._fitting:
            return
        self._fitting = True
        available = max(40, self.viewport().width())
        try:
            # QPlainTextDocumentLayout reports document height in text lines,
            # unlike QTextDocument's rich-text layout. Measure actual wrapped
            # lines explicitly so Cyrillic and pasted paragraphs grow equally.
            lines = 0
            option = QTextOption()
            option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            for paragraph in self.toPlainText().split('\n'):
                text_layout = QTextLayout(paragraph or ' ', self.font())
                text_layout.setTextOption(option)
                text_layout.beginLayout()
                while True:
                    line = text_layout.createLine()
                    if not line.isValid():
                        break
                    line.setLineWidth(available)
                    lines += 1
                text_layout.endLayout()
            lines = max(1, lines)
            height = max(46, min(122, 20 + lines * self.fontMetrics().lineSpacing()))
            self.setFixedHeight(height)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if lines > 5 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        finally:
            self._fitting = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if not event.isAutoRepeat():
                self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class SendButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__('Отправить', parent)
        self.setObjectName('ChatSendButton')
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stopping = False

    def set_stopping(self, stopping):
        self._stopping = bool(stopping)
        self.setText('Остановить' if stopping else 'Отправить')
        self.setAccessibleName(self.text())
        self.setToolTip(self.text())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor('#6C9ED2' if self.isEnabled() else '#34475A')
        if self.underMouse() and self.isEnabled():
            color = QColor('#80AFE0')
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        painter.setBrush(QColor('#FFFFFF' if self.isEnabled() else '#8292A3'))
        if self._stopping:
            painter.drawRoundedRect(14, 14, 12, 12, 2, 2)
        else:
            path = QPainterPath(QPointF(12, 11))
            path.lineTo(30, 20)
            path.lineTo(12, 29)
            path.lineTo(16, 21)
            path.lineTo(24, 20)
            path.lineTo(16, 19)
            path.closeSubpath()
            painter.drawPath(path)


class EvidenceSelection(QDialog):
    """Explicit scope of the outgoing request; uncertain facts are opt-in."""
    def __init__(self, results, provider, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Гермиона · объяснить находки')
        self.resize(490, 410)
        self.setMinimumSize(380, 300)
        self.results = [deepcopy(item.to_dict() if hasattr(item, 'to_dict') else dict(item)) for item in list(results)[:50]]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(label('Выберите сведения для объяснения', 'SectionTitle'))
        text = ('Выбранные сведения будут переданы DeepSeek через api.aikeysforyou.com, внешнему облачному провайдеру. '
                'Исходная выдача останется в поиске.') if provider == 'deepseek' else 'Выбранные сведения будут переданы установленной локальной модели Ollama.'
        layout.addWidget(label(text))
        self.items = QListWidget()
        self.items.setWordWrap(True)
        for value in self.results:
            confirmed = is_confirmed(value)
            text = str(value.get('platform', '')) + ' · ' + str(value.get('title') or value.get('id') or '')
            if not confirmed:
                text += ' · требует проверки'
            item = QListWidgetItem(text, self.items)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if confirmed else Qt.CheckState.Unchecked)
        layout.addWidget(self.items, 1)
        layout.addWidget(label('В запрос войдут только выбранные находки, максимум 50. Ключи, сессии и диагностика не передаются.', 'SmallMuted'))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Отмена')
        self.submit = self.buttons.addButton('Отправить и объяснить', QDialogButtonBox.ButtonRole.AcceptRole)
        self.submit.setObjectName('PrimaryButton')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.items.itemChanged.connect(self._selection_changed)
        layout.addWidget(self.buttons)
        self._selection_changed()

    def _selection_changed(self, *_):
        self.submit.setEnabled(any(self.items.item(row).checkState() == Qt.CheckState.Checked for row in range(self.items.count())))

    def selected_results(self):
        return [deepcopy(value) for row, value in enumerate(self.results) if self.items.item(row).checkState() == Qt.CheckState.Checked]


class ChatWidget(QWidget):
    activity_changed = Signal(str)
    busy_changed = Signal(bool)
    settings_requested = Signal()
    connection_changed = Signal(bool)
    evidence_received = Signal(object)
    report_requested = Signal(str)
    user_activity = Signal()
    state_changed = Signal()
    turn_completed = Signal(object)
    _agent_progress = Signal(int, object)
    _approval_requested = Signal(int, object)

    def __init__(self, settings, store=None, parent=None, ai_state=None):
        super().__init__(parent)
        self.settings, self.store = settings, store
        self.ai_state = ai_state or AIState(settings, self)
        self._context, self.messages = [], []
        self._job, self._generation, self._ending = None, 0, False
        self._busy = False
        self.last_request = {}
        self.archive_error = ''
        self._activity_log = []
        self._resume_state = None
        self._last_failed_text = ''
        self._agent_registry = None
        self._agent_runner = None
        self._last_investigation = {}
        self._agent_followup = False
        self._approval_box = None
        self._approval_waiter = None
        self._stream_bubble = None
        self._stream_index = None
        journal_dir = Path(store.path).parent / 'investigations' if store is not None else None
        self._journal = InvestigationJournal(journal_dir)
        self._archive = ChatArchive(Path(store.path).parent / 'chat-history.dpapi') if store is not None else None
        self._library = ConversationLibrary(self._archive) if self._archive is not None else None
        self.conversation_id = self._library.current_id if self._library else uuid.uuid4().hex
        self._usage_ledger = None
        if store is not None:
            from .usage import UsageLedger
            self._usage_ledger = UsageLedger(Path(store.path).parent / 'usage.sqlite3')
        self._archive_timer = QTimer(self)
        self._archive_timer.setSingleShot(True)
        self._archive_timer.setInterval(600)
        self._archive_timer.timeout.connect(self._save_archive)
        self._agent_progress.connect(self._on_agent_progress)
        self._approval_requested.connect(self._on_approval_requested)
        self.setObjectName('ChatPage')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setObjectName('ChatHeader')
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 10, 14, 10)
        row.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.title = label('Гермиона', 'SectionTitle')
        titles.addWidget(self.title)
        self.provider_status = label('ИИ не настроен', 'ProviderStatus')
        titles.addWidget(self.provider_status)
        row.addLayout(titles, 1)
        self.clear_button = QPushButton('Очистить')
        self.clear_button.setObjectName('QuietButton')
        self.clear_button.setToolTip('Очистить историю текущего диалога')
        self.clear_button.clicked.connect(self.clear_history)
        row.addWidget(self.clear_button)
        self.configure = QPushButton('Подключить')
        self.configure.setObjectName('QuietButton')
        self.configure.clicked.connect(self.settings_requested)
        row.addWidget(self.configure)
        layout.addWidget(header)
        self.notice = label('', 'ChatPrivacy')
        self.notice.setContentsMargins(16, 6, 16, 8)
        layout.addWidget(self.notice)
        self.history = MessageHistory()
        if hasattr(self.history, 'report_requested'):
            self.history.report_requested.connect(self.report_requested)
        layout.addWidget(self.history, 1)
        self.status = label('', 'TypingStatus')
        self.status.setContentsMargins(16, 6, 16, 4)
        self.status.hide()
        layout.addWidget(self.status)
        composer_area = QWidget()
        composer_area.setObjectName('ComposerArea')
        composer_layout = QVBoxLayout(composer_area)
        composer_layout.setContentsMargins(12, 8, 12, 10)
        composer_layout.setSpacing(0)
        composer = QFrame()
        composer.setObjectName('ChatComposer')
        controls = QHBoxLayout(composer)
        controls.setContentsMargins(9, 0, 4, 0)
        controls.setSpacing(6)
        self.input = MessageInput()
        self.input.setPlaceholderText('Сообщение Гермионе…')
        self.input.setAccessibleName('Сообщение Гермионе')
        self.input.send_requested.connect(self.send_message)
        self.input.textChanged.connect(self._update_actions)
        self.input.textChanged.connect(self.user_activity)
        controls.addWidget(self.input, 1)
        self.send = SendButton()
        self.send.clicked.connect(self._main_action)
        controls.addWidget(self.send, 0, Qt.AlignmentFlag.AlignBottom)
        composer_layout.addWidget(composer)
        layout.addWidget(composer_area)
        self.ai_state.changed.connect(self._on_state_changed)
        self.set_settings(settings)
        if self._archive is not None:
            saved = self._archive.load()
            self._context = saved.get('context', [])
            self._restore_archive_rows(saved.get('messages', []))
            if self._archive.last_error:
                self._set_archive_error('Не удалось прочитать локальную историю. Прежний архив сохранён без изменений.')
            self._restore_investigation()

    def _restore_archive_rows(self, rows):
        # The bundled renderer owns the full visible history. Building hundreds
        # of hidden native Markdown widgets adds no user-visible content and
        # blocks its GUI thread. Native mode retains its original bubble path;
        # subsequent runtime bubbles/stream handles still use their own indices.
        web = bool(QApplication.instance().property('web_desktop'))
        for row in rows:
            if web:
                self.messages.append({'id':row.get('id') or uuid.uuid4().hex,
                    'role':row['role'], 'text':row['text']})
            else:
                self._append(row['role'], row['text'], message_id=row.get('id'))
            for field in ('investigation_id', 'evidence_ids'):
                if field in row:self.messages[-1][field] = deepcopy(row[field])
        self._update_actions()

    @property
    def busy(self):
        return self._busy

    @property
    def _ready(self):
        return self.ai_state.can_send

    def set_settings(self, settings):
        if getattr(self, 'settings', None) != settings:
            self._agent_registry = None
        self.settings = settings
        self.ai_state.set_settings(settings)
        self._on_state_changed(self.ai_state.snapshot())

    def _on_state_changed(self, snapshot):
        self.settings = self.ai_state.settings
        detail = self.ai_state.status_text(snapshot)
        state = snapshot.get('connection_status')
        self.provider_status.setText('На связи' if state == 'connected' else
                                    'Готова к разговору' if state == 'configured_unverified' else detail)
        self.provider_status.setToolTip(detail)
        provider = self.ai_state.committed_snapshot()['provider']
        available = self.ai_state.can_send
        self.configure.setText('Настройки' if available else 'Подключить')
        self.notice.setText('Сообщения и выбранные источники передаются внешнему облачному провайдеру по вашему действию.' if provider == 'deepseek' else
            'Сообщения обрабатываются установленной локальной моделью Ollama.' if provider == 'ollama' else
            'Подключите DeepSeek или локальную Ollama. Поиск работает самостоятельно.')
        self.connection_changed.emit(available)
        self._update_actions()

    def _update_actions(self):
        self.send.set_stopping(self._busy)
        self.send.setEnabled(self._busy or (self._ready and bool(self.input.toPlainText().strip())))
        self.clear_button.setEnabled(bool(self.messages) and not self._busy)

    def _main_action(self):
        self.cancel() if self._busy else self.send_message()

    def _append(self, role, text, retry=None, *, message_id=None):
        self.messages.append({'id': message_id or uuid.uuid4().hex, 'role': role, 'text': str(text)})
        bubble = self.history.append_message(role, text, retry)
        self._archive_timer.start()
        self._update_actions()
        self.state_changed.emit()
        return bubble

    def send_message(self):
        self._submit_text(self.input.toPlainText().strip(), consume_draft=True)

    def _submit_text(self, text, consume_draft=False):
        if self._busy or not text:
            return
        if len(text) > 12000:
            self.status.setText('Сообщение: не более 12 000 символов.')
            self.status.show()
            return
        self.ai_state.set_settings(self.ai_state.settings)
        if not self._ready:
            self.status.setText('Подключите ИИ в настройках.')
            self.status.show()
            return
        if consume_draft:
            self.input.clear()
        self._append('user', text)
        history = conversation_context(self.messages, text)
        settings = self.ai_state.settings
        snapshot = self.ai_state.committed_snapshot()
        model = snapshot['model_id']
        generation = self._generation + 1
        conversation_id = self.conversation_id
        investigate = not no_tools_requested(text) and (investigation_requested(text) or self._agent_followup and bool(re.search(r'(?iu)(ещ[её]|подроб|дальше|сравни|почему|источник|ev_[a-f0-9]+)', text)))
        def request(cancelled):
            if snapshot['provider'] == 'deepseek':
                client = DeepSeekClient()
                if investigate:
                    if self._agent_registry is None:
                        self._agent_registry = ToolRegistry(settings, redactions=(getattr(client, '_key', ''),))
                    if hasattr(self._agent_registry, 'seed_urls_from_user'):
                        self._agent_registry.seed_urls_from_user(text)
                    limits = self._investigation_limits(settings)
                    runner = AgentRunner(client, self._agent_registry, limits=limits)
                    self._agent_runner = runner
                    return self._run_investigation(runner, model, history, cancel_event=cancelled,
                        on_event=lambda value: self._agent_progress.emit(generation, value),
                        approval_callback=lambda name, args: self._approve_tool(generation, name, args, cancelled),
                        conversation_id=conversation_id, usage_ledger=self._usage_ledger,
                        checkpoint_callback=lambda value: self._journal.save_checkpoint(value, secrets=(resolve_deepseek_key(),)))
                if hasattr(client, 'stream_chat'):
                    answer = client.stream_chat(model, history, cancel_event=cancelled,
                        on_text=lambda value: self._agent_progress.emit(generation, {'type': 'text', 'text': value}))
                else:
                    answer = client.chat(model, history, cancel_event=cancelled)
                return {'text': answer, 'metadata': dict(getattr(client, 'last_response_metadata', {}))}
            prompt = '\n\n'.join(('Гермиона: ' if value['role'] == 'model' else 'Пользователь: ') + value['text'] for value in history)
            return OllamaClient(settings.ollama_url).generate(model, prompt)
        self._start(request, 'thinking', history, text)

    def _retry_last(self):
        if self._last_failed_text:
            self._submit_text(self._last_failed_text, consume_draft=False)

    def analyze_results(self, results, task='summary'):
        if self._busy:
            self.status.setText('Дождитесь ответа или остановите текущий запрос.')
            self.status.show()
            return
        if not self._ready:
            self.settings_requested.emit()
            return
        snapshot = self.ai_state.committed_snapshot()
        dialog = EvidenceSelection(results, snapshot['provider'], self)
        if not dialog.results or dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_results()
        if not selected:
            return
        settings = self.ai_state.settings
        self._append('user', f'Объясни выбранные находки: {len(selected)}. Исходные сведения остаются во вкладке поиска.')
        def request(cancelled):
            return explain_evidence(snapshot['provider'], snapshot['model_id'], selected,
                api_key=resolve_deepseek_key() if snapshot['provider'] == 'deepseek' else '', ollama_url=settings.ollama_url,
                external_consent=snapshot['provider'] == 'deepseek', task=task, cancel_event=cancelled)
        self._start(request, 'working', None)

    def analyze_selected(self, results):
        """An explicit frontend selection is the consent and selection action."""
        if self.busy or not self._ready: raise ValueError('Подключите ИИ и дождитесь текущего ответа.')
        if not isinstance(results,list) or not 1<=len(results)<=20: raise ValueError('Выберите 1–20 находок.')
        snapshot=self.ai_state.committed_snapshot()
        self._append('user',f'Проанализируй выбранные открытые источники: {len(results)}. Различай факты, сниппеты и гипотезы.')
        def request(cancelled):
            return explain_evidence(snapshot['provider'],snapshot['model_id'],results,
                api_key=resolve_deepseek_key() if snapshot['provider']=='deepseek' else '',
                ollama_url=self.settings.ollama_url,external_consent=snapshot['provider']=='deepseek',
                task='summary',cancel_event=cancelled)
        self._start(request,'working',None)

    def _start(self, request, activity, context, submitted_text=''):
        snapshot = self.ai_state.committed_snapshot()
        provider, model = snapshot['provider'], snapshot['model_id']
        self.last_request = {'code':'pending', 'provider':provider, 'model':model}
        self._generation += 1
        generation = self._generation
        self._busy = True
        request_id = uuid.uuid4().hex
        conversation_id = self.conversation_id
        self._activity_log = []
        self._agent_runner = None
        self._stream_bubble = self._stream_index = None
        def execute():
            try:
                value = request(job.cancelled)
                if self._usage_ledger is not None and not (isinstance(value, dict) and value.get('investigation')):
                    self._usage_ledger.record_response(value.get('metadata', {}) if isinstance(value, dict) else {},
                        provider=provider, model=model, conversation_id=conversation_id, request_id=request_id)
                return value if isinstance(value, dict) else {'text': value}
            except AIError as error:
                if self._usage_ledger is not None:
                    self._usage_ledger.record_error(provider=provider, model=model, conversation_id=conversation_id,
                        request_id=request_id, error_code=error.code)
                return {'error': str(error), 'code': getattr(error, 'code', 'provider_error'),
                        'http_status': getattr(error, 'http_status', None), 'retry_after': getattr(error, 'retry_after', None)}
        job = UiJob(execute, self)
        self._job = job
        self._update_actions()
        self.status.setText('Гермиона объясняет находки…' if activity == 'working' else 'Печатает…')
        self.status.show()
        self.busy_changed.emit(True)
        self.ai_state.request_started(provider=provider, model_id=model)
        self.activity_changed.emit(activity)
        def finished(result, error):
            if self._ending or generation != self._generation:
                job.deleteLater()
                return
            self._busy, self._job = False, None
            self._close_approval()
            self.busy_changed.emit(False)
            metadata = {}
            investigation = result.get('investigation') if isinstance(result, dict) else None
            if isinstance(investigation, dict):
                self._last_investigation = investigation
                self._agent_followup = True
                self._persist_investigation(investigation)
            if isinstance(result, dict) and result.get('error'):
                self.last_request = {key: result.get(key) for key in ('code', 'http_status', 'retry_after')}
                error = result['error']
                result = None
            elif isinstance(result, dict):
                metadata = {key: result.get('metadata', {}).get(key) for key in ('model', 'model_version') if isinstance(result.get('metadata', {}).get(key), str)}
                usage = result.get('metadata', {}).get('usage')
                if isinstance(usage, dict):
                    metadata['usage'] = {key: value for key, value in usage.items()
                                         if key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                                         and isinstance(value, int) and not isinstance(value, bool) and value >= 0}
                result = result.get('text')
            if error:
                if self.last_request.get('code') in (None, 'ok', 'pending'):
                    self.last_request = {'code':'provider_error'}
                self.ai_state.request_failed(self.last_request, provider=provider, model_id=model)
                self._last_failed_text = submitted_text
                message = self.ai_state.committed_snapshot().get('last_error') or error
                retry_after = self.last_request.get('retry_after')
                if isinstance(retry_after, (int, float)) and retry_after > 0:
                    message += f' Повторите не раньше чем через {math.ceil(retry_after)} с.'
                bubble = self._append('status', message, self._retry_last if submitted_text else None)
                if submitted_text and isinstance(retry_after, (int, float)) and retry_after > 0:
                    bubble.retry.setEnabled(False)
                    timer = QTimer(bubble)
                    timer.setSingleShot(True)
                    timer.timeout.connect(lambda: bubble.retry.setEnabled(True))
                    timer.start(min(2_147_000_000, math.ceil(retry_after * 1000)))
                self.status.setText(message)
                self.status.hide()
                self.activity_changed.emit('error')
            elif not isinstance(result, str) or not result.strip():
                self.last_request = {'code':'empty_response'}
                self.ai_state.request_failed(self.last_request, provider=provider, model_id=model)
                self._last_failed_text = submitted_text
                self._append('status', 'Модель не вернула текст ответа.', self._retry_last if submitted_text else None)
                self.status.setText('Пустой ответ. История сохранена.')
                self.status.hide()
                self.activity_changed.emit('error')
            else:
                self.last_request = {'code':'ok', 'text_chars':len(result), 'model':model, 'provider':provider}
                self.last_request.update(metadata)
                if self._stream_bubble is not None:
                    self.history.update_message(self._stream_bubble, result)
                    self.messages[self._stream_index]['text'] = result
                else:
                    self._append('model', result)
                if context is not None:
                    self._context = context + [{'role':'model', 'text':result}]
                if investigation and self.messages:
                    self.messages[-1]['investigation_id'] = investigation['id']
                    self.messages[-1]['evidence_ids'] = [r['evidence_id'] for r in investigation.get('evidence', []) if r.get('evidence_id')]
                self.status.setText('Ответ получен')
                self.status.hide()
                api_error = investigation.get('api_error') if isinstance(investigation, dict) else None
                if api_error:
                    self.last_request.update(api_error)
                    self.ai_state.request_failed(api_error, provider=provider, model_id=model)
                    self.activity_changed.emit('error')
                else:
                    self.ai_state.request_succeeded(provider=provider, model_id=model)
                    self.activity_changed.emit('happy')
            self._update_actions()
            self._archive_timer.start()
            if investigation and self.messages:
                # The first provider request may fail before any source is
                # found. Its encrypted checkpoint still belongs to this turn.
                self.messages[-1]['investigation_id'] = investigation['id']
                self.messages[-1]['evidence_ids'] = [r['evidence_id'] for r in investigation.get('evidence', []) if r.get('evidence_id')]
            completion_kind = 'error' if self.last_request.get('code') != 'ok' else 'investigation' if investigation else 'reply'
            if investigation and investigation.get('status') != 'completed' and completion_kind != 'error':
                completion_kind = 'paused'
            self.turn_completed.emit({'kind':completion_kind,
                'message_id':self.messages[-1]['id'] if self.messages else '', 'index':len(self.messages)-1,
                'conversation_id':self.conversation_id})
            self.state_changed.emit()
            job.deleteLater()
        job.done.connect(finished)
        job.start()

    def cancel(self):
        if not self._job:
            return
        self._generation += 1
        self._job.cancel()
        self._job.deleteLater()
        self._close_approval()
        if self._agent_runner is not None:
            self._last_investigation = self._agent_runner.snapshot()
            self._last_investigation['status'] = 'cancelled'
            self._persist_investigation(self._last_investigation)
        self._job = None
        self._busy = False
        self.last_request = {'code':'cancelled'}
        self.status.setText('Запрос отменён. История сохранена.')
        self.status.show()
        self._append('status', 'Ожидание ответа отменено.')
        if self._last_investigation.get('id'):
            self.messages[-1]['investigation_id']=self._last_investigation['id']
            self.messages[-1]['evidence_ids']=[r['evidence_id'] for r in self._last_investigation.get('evidence',[]) if r.get('evidence_id')]
        self.busy_changed.emit(False)
        cancel_state = getattr(self.ai_state, 'cancel_request', None)
        if cancel_state:
            cancel_state()
        self.activity_changed.emit('idle')
        self.turn_completed.emit({'kind':'cancelled', 'message_id':'', 'index':len(self.messages)-1})
        self.state_changed.emit()
        self._update_actions()

    def clear_history(self):
        if self._busy:
            return False
        # Do not claim the clear was persisted and discard the in-memory copy
        # when the filesystem/vault refused the replacement archive.
        if not self._save_archive(messages=[], context=[]):
            return False
        self._context.clear()
        self._agent_registry = None
        self._agent_runner = None
        self._agent_followup = False
        self.messages.clear()
        self._last_investigation = {}
        self._activity_log = []
        self.history.clear()
        self.status.setText('Диалог очищен')
        self.status.hide()
        self._update_actions()
        self.state_changed.emit()
        return True

    @staticmethod
    def _investigation_limits(settings):
        return AgentLimits(max_steps=settings.agent_steps, max_tool_calls=settings.agent_calls,
            timeout=settings.agent_timeout, max_tokens=settings.agent_tokens,
            max_parallel=getattr(settings, 'agent_parallel', 2),
            per_tool_timeout=getattr(settings, 'agent_tool_timeout', 25),
            per_request_timeout=getattr(settings, 'agent_request_timeout', 90),
            auto_continue=getattr(settings, 'agent_auto_continue', True),
            budget_behavior=getattr(settings, 'agent_budget_behavior', 'pause'))

    def new_conversation(self):
        if self.busy: raise ValueError('Сначала остановите текущую задачу.')
        if not self._save_archive():
            raise ValueError(self.archive_error)
        previous_id=self.conversation_id
        try:
            self.conversation_id = self._library.new() if self._library else uuid.uuid4().hex
        except OSError:
            if self._library:self._library.current_id=previous_id
            self._set_archive_error('Не удалось создать новый диалог. Текущая переписка сохранена и остаётся открытой.')
            raise ValueError(self.archive_error) from None
        if not self.clear_history():
            self.conversation_id=previous_id
            if self._library:
                self._library.current_id=previous_id
                try:self._library._write_pointer()
                except OSError:pass
            raise ValueError(self.archive_error)
        self._last_investigation = {}
        self._activity_log = []
        self.state_changed.emit()

    def load_conversation(self, identifier):
        if self.busy: raise ValueError('Сначала остановите текущую задачу.')
        if self._library is None: raise ValueError('Локальная история недоступна.')
        if not self._save_archive():
            raise ValueError(self.archive_error)
        value = self._library.load(identifier)
        self.conversation_id = self._library.current_id
        self.messages.clear()
        self.history.clear()
        self._context = value.get('context', [])
        self._agent_registry = self._agent_runner = None
        self._last_investigation = {}
        self._agent_followup = False
        self._restore_archive_rows(value.get('messages', []))
        self._restore_investigation()
        self._activity_log = []
        self._update_actions()
        self.state_changed.emit()

    def regenerate(self, message_id=None):
        if self.busy: raise ValueError('Сначала остановите текущую задачу.')
        index = next((i for i,row in enumerate(self.messages) if row.get('id')==message_id), len(self.messages)-1)
        question = next((row['text'] for row in reversed(self.messages[:index+1]) if row['role']=='user'), '')
        if not question: raise ValueError('Нет вопроса для повторной генерации.')
        self._submit_text(question)

    def _restore_investigation(self):
        for row in reversed(self.messages):
            if row.get('investigation_id'):
                try: self._last_investigation = self._journal.load(row['investigation_id']) or {}
                except (OSError,ValueError):
                    try:
                        checkpoint=self._journal.load_checkpoint(row['investigation_id'])
                        self._last_investigation={**checkpoint['record'],'evidence':checkpoint.get('evidence',[])}
                    except (OSError,ValueError): self._last_investigation = {}
                self._agent_followup = bool(self._last_investigation)
                return

    def continue_investigation(self, identifier=None):
        if self.busy: raise ValueError('Сначала остановите текущую задачу.')
        identifier = identifier or self._last_investigation.get('id')
        resume = self._journal.load_checkpoint(identifier) if identifier else None
        if not resume: raise ValueError('Сохранённое продолжение этого расследования не найдено.')
        if self.ai_state.committed_snapshot()['provider'] != 'deepseek':
            raise ValueError('Для продолжения выберите DeepSeek в настройках.')
        settings = self.ai_state.settings
        model = self.ai_state.committed_snapshot()['model_id']
        generation = self._generation + 1
        conversation_id = self.conversation_id
        self._append('user', 'Продолжи сохранённое расследование с прежней целью и уже собранными доказательствами.')
        def request(cancelled):
            client = DeepSeekClient()
            if self._agent_registry is None:
                self._agent_registry = ToolRegistry(settings, redactions=(getattr(client, '_key', ''),))
            runner = AgentRunner(client, self._agent_registry, limits=self._investigation_limits(settings))
            self._agent_runner = runner
            return self._run_investigation(runner, model, [], resume_state=resume, cancel_event=cancelled,
                conversation_id=conversation_id, usage_ledger=self._usage_ledger,
                checkpoint_callback=lambda value:self._journal.save_checkpoint(value, secrets=(resolve_deepseek_key(),)),
                on_event=lambda value:self._agent_progress.emit(generation,value),
                approval_callback=lambda name,args:self._approve_tool(generation,name,args,cancelled))
        self._start(request, 'thinking', conversation_context(self.messages))

    def _run_investigation(self, runner, model, history, **kwargs):
        """Keep a failed first stage associated with its real request ledger.

        AgentRunner already accounts every provider call. Returning its snapshot
        alongside an error prevents the outer chat job from recording a second
        fictitious request, and gives the status message a restartable identity.
        """
        try:
            result = runner.run(model, history, **kwargs)
        except AIError as error:
            investigation = runner.snapshot()
            if not re.fullmatch(r'[a-f0-9]{32}', str(investigation.get('id', ''))):
                raise
            result = {'error': str(error), 'code': error.code, 'http_status': error.http_status,
                      'retry_after': error.retry_after, 'investigation': investigation,
                      'evidence': investigation.get('evidence', []), 'partial': True}
        # UiJob suppresses late delivery after cancel; preserve the journal in
        # this worker for both successful stages and provider failures.
        try:
            self._journal.save(result.get('investigation', {}))
        except (OSError, ValueError, TypeError):
            pass
        return result

    def shutdown(self):
        self._ending = True
        self.cancel()
        self._save_archive()

    def _set_archive_error(self, message):
        if message == self.archive_error:
            return
        self.archive_error = message
        self.history.setToolTip(message)
        self.state_changed.emit()

    def _save_archive(self, *, messages=None, context=None):
        self._archive_timer.stop()
        if self._archive is not None:
            try:
                self._archive.save(self.messages if messages is None else messages,
                    self._context if context is None else context, secrets=(resolve_deepseek_key(),))
                if self._library: self._library.seal()
            except Exception:
                self._set_archive_error('Не удалось сохранить локальную историю. Текущая переписка остаётся в окне; '
                    'переключение диалога отменено. Проверьте доступ к хранилищу, свободное место и предел архива 64 МиБ.')
                return False
        self._set_archive_error('')
        return True

    def _on_agent_progress(self, generation, event):
        if self._ending or generation != self._generation or not self._busy or not isinstance(event, dict):
            return
        kind = event.get('type')
        if kind != 'text':
            self._activity_log.append({key:deepcopy(value) for key,value in event.items() if key in
                ('type','tool','status','step','count','message','request_id','usage','error_code','evidence_ids','tool_call_id','id')})
            self._activity_log = self._activity_log[-120:]
        self.state_changed.emit()
        if kind == 'text':
            value = event.get('text')
            if not isinstance(value, str) or not value:
                return
            if self._stream_bubble is None:
                self._stream_bubble = self._append('model', value)
                self._stream_index = len(self.messages) - 1
            else:
                if not QApplication.instance().property('web_desktop'):
                    self.history.update_message(self._stream_bubble, value)
                self.messages[self._stream_index]['text'] = value
            return
        messages = {'planning': 'Гермиона выбирает доступные инструменты…',
                    'tool_start': 'Проверка источника: ' + str(event.get('tool', ''))[:80],
                    'tool_result': 'Получены результаты источника…', 'analyzing': 'Гермиона сопоставляет найденные сведения…',
                    'final': 'Гермиона формирует итог…', 'error': 'Исследование завершилось с ограничениями.'}
        if kind in messages:
            self.status.setText(messages[kind])
            self.status.show()
        if kind in ('planning', 'analyzing', 'final'):
            self.activity_changed.emit('thinking')
        elif kind in ('tool_start', 'tool_result'):
            self.activity_changed.emit('working')
        if kind == 'evidence':
            records = event.get('records', [])
            if isinstance(records, list):
                self.evidence_received.emit(deepcopy(records))
        if kind in ('evidence', 'tool_result') and self._agent_runner is not None:
            self._last_investigation = self._agent_runner.snapshot()
            self._persist_investigation(self._last_investigation)

    def _persist_investigation(self, value):
        try:
            self._journal.save(value)
        except (OSError, ValueError, TypeError):
            # A local journal failure must not discard already visible findings.
            self.status.setToolTip('Не удалось записать локальный журнал; сведения остаются в текущем сеансе.')

    def _approve_tool(self, generation, name, args, cancelled):
        waiter = {'event': threading.Event(), 'approved': False, 'name': name, 'arguments': deepcopy(args)}
        self._approval_requested.emit(generation, waiter)
        deadline = time.monotonic() + 60
        while not waiter['event'].wait(.05):
            if cancelled.is_set() or time.monotonic() >= deadline:
                return False
        return waiter['approved'] and not cancelled.is_set()

    def _on_approval_requested(self, generation, waiter):
        if self._ending or generation != self._generation or not self._busy:
            waiter['event'].set()
            return
        self._approval_waiter = waiter
        text = ('Гермиона предлагает проверку, требующую отдельного согласия.\n\n' + str(waiter['name']) + '\n' +
                json.dumps(waiter['arguments'], ensure_ascii=False)[:600] +
                '\n\nЭто может включать проверку регистрации или обращение через вашу авторизованную сессию. Разрешить этот вызов?')
        box = QMessageBox(QMessageBox.Icon.Question, 'Подтвердить проверку', text,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText('Разрешить этот вызов')
        box.button(QMessageBox.StandardButton.No).setText('Не выполнять')
        self._approval_box = box
        def finish(result):
            waiter['approved'] = result == QMessageBox.StandardButton.Yes
            waiter['event'].set()
            if self._approval_box is box:
                self._approval_box = self._approval_waiter = None
            box.deleteLater()
        box.finished.connect(finish)
        expiry = QTimer(box)
        expiry.setSingleShot(True)
        expiry.timeout.connect(box.reject)
        expiry.start(60000)
        box.open()

    def _close_approval(self):
        if self._approval_waiter is not None:
            self._approval_waiter['approved'] = False
            self._approval_waiter['event'].set()
        if self._approval_box is not None:
            self._approval_box.reject()
