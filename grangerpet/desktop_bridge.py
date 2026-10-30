"""Finite, secret-free application protocol for the bundled local renderer.

No HTTP server, shell, eval, arbitrary file access or remote WebChannel clients.
Existing Python controllers remain the sole owners of requests and evidence.
"""
from __future__ import annotations

from dataclasses import asdict
from copy import deepcopy
import base64
import hashlib
import json
import re
import logging
from pathlib import Path
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QEvent, QObject, QRect, QTimer, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QFileDialog

from .agent_evidence import normalize_evidence, redact, sanitize_evidence
from .agent_tools import ToolRegistry, _SPECS
from .ai_keys import resolve_deepseek_key
from .credential_dialog import CredentialDialog, credential_presence, SERVICES
from .credentials import get_secret, CredentialError
from .gateway_balance import GatewayBalance, fetch_balance
from .config import Settings
from .markdown_view import public_link
from .product import PRODUCT_NAME, VERSION
from .ui_jobs import UiJob


SETTINGS_FIELDS = frozenset(('ui_theme','geoint_nominatim_url','geoint_overpass_url','size','fps','cursor_reaction','agent_steps','agent_calls','agent_timeout',
    'agent_tokens','agent_page_limit','agent_page_depth','agent_parallel','agent_tool_timeout',
    'agent_request_timeout','agent_no_progress_rounds','agent_download_mb','agent_auto_continue','agent_budget_behavior','notifications_enabled',
    'notifications_animate','notifications_reply','notifications_investigation','notifications_errors','reduced_motion',
    'ai_provider','deepseek_model','ollama_url','ollama_model','api_cx','source_root','runtime_python',
    'telegram_api_id','instagram_username','request_limit','search_timeout','enable_snoop','nuclei_enabled'))
ROUTES = frozenset(('chat','search','history','canvas','settings'))
TOOL_NAMES={'web_search':'Веб-поиск','web_read':'Чтение страниц','username_maigret':'Maigret',
    'username_blackbird':'Blackbird','username_social_analyzer':'Social Analyzer','username_snoop':'Snoop',
    'email_holehe':'Holehe','phone_metadata':'PhoneInfoga','blockchain_gansar':'Gansar',
    'web_archive':'Веб-архив','telegram_public':'Telegram','vk_public':'VK','instagram_public':'Instagram',
    'domain_lookup':'DNS и регистрация домена','ip_lookup':'Сети и ASN','evidence_get':'Сохранённое свидетельство'}
MAX_PAYLOAD = 2_100_000


def source_view(record, limits=()):
    value = sanitize_evidence(record)
    details, origin = value.get('details') or {}, value.get('provenance') or {}
    acquisition = origin.get('acquisition')
    kind = 'api' if details.get('acquisition')=='official_api' else 'page' if details.get('reading_method') in ('direct_http','browser_dom') else 'snippet' if acquisition=='search_index' or value.get('status')=='indexed' else 'adapter'
    kind={'image_analysis':'image','map':'map','repository':'repository','archive':'archive'}.get(value.get('type'),kind)
    notes = list(limits) + list(details.get('limitations') or [])
    if any('JavaScript' in str(note) and 'не' in str(note) for note in notes):
        details={**details,'javascript_shell':True}
    if details.get('javascript_shell'):
        notes.append('JavaScript-содержимое не исполнено; доступны только HTTP-текст и метаданные.')
    identifier=value.get('evidence_id') or details.get('evidence_id') or ''
    read = (details.get('reading_method') in ('direct_http','browser_dom') and not details.get('javascript_shell')
            and bool(str(details.get('content_text') or details.get('content_excerpt') or '').strip())
            and value.get('status') not in ('error','failed','blocked','restricted','unconfirmed'))
    details = {**details,'content_fetched':read}
    return {'evidence_id':identifier, 'title':value.get('title') or value.get('platform') or 'Источник',
        'url':value.get('url',''), 'domain':urlsplit(value.get('url','')).hostname or value.get('platform',''),
        'excerpt':str(details.get('content_excerpt') or value.get('description') or '')[:2000],
        'status':'partial' if details.get('javascript_shell') else value.get('status','unconfirmed'), 'kind':kind,
        'obtained_at':origin.get('obtained_at') or details.get('retrieved_at') or value.get('date'),
        'limitations':list(dict.fromkeys(str(v)[:500] for v in notes))[:8], 'details':details,
        'verification':value.get('verification') or details.get('evidence_verification','unconfirmed'),
        'provenance':origin or {'tool':details.get('agent_tool',''),'query':details.get('original_query',''),
                              'obtained_at':details.get('obtained_at','')}}


class DesktopBridge(QObject):
    response = Signal(str, str)
    stateChanged = Signal(str)
    toolProgress = Signal(object)
    visualProgress = Signal(object)
    rendererReady = Signal()

    def __init__(self, host, surface='main'):
        super().__init__(host)
        self.host, self.surface = host, surface
        self.route = 'chat' if surface=='main' else 'launcher'
        self._last = {}
        self._last_messages = []
        self._tools = []
        self._tools_job = None
        self._tools_generation = 0
        self._balance = GatewayBalance()
        self._balance_job = None
        self._balance_generation = 0
        self._models_job = None
        self._models = []
        self._models_error = ''
        self._visual_job=None
        self._visual_operation=''
        self._visual_progress={}
        self._visual_error=''
        self._credentials = {}
        self._secret_redactions = set()
        self.settingsCategory = 'ai'
        self._manual_job = None
        self._attachment_job=None
        self._attachments=[]
        self._attachment_store=None
        self._attachment_error=''
        self._manual_registry = None
        self._manual_activity = []
        self._source_cache = {}
        self._raw_sources = {}
        self._sources_fingerprint = None
        self._sources_view = []
        self._search_sources_view = []
        self._history_cache = []
        self._history_key = None
        self._usage_cache_key = None
        self._usage_cache = ({}, {})
        self._dock_rect = QRect()
        self._publication_enabled = True
        self._force_next = False
        self._closed = False
        self._snapshot_fault = None
        self._graph_job = None
        self._graph_generation = 0
        self._graph_data = {'state':'idle'}
        self._graph_records = []
        self._graph_signature = None
        self._investigation_choices = []
        self._workspace = None
        self._seen_chat_investigation = ''
        self._launcher_fingerprint = None
        self.ui_ready = False
        self._key = resolve_deepseek_key()
        if getattr(self, '_errors', None) is not None:
            self._errors.register_secrets((self._key,))
        self._load_credential_flags()
        from .errors import error_center
        self._errors = error_center()
        if self._errors is not None:
            self._errors.register_secrets(self._secret_redactions)
            self._errors.changed.connect(self.mark_dirty)
            self._errors.taskFailed.connect(self._fail_active_task)
        self.toolProgress.connect(self._tool_progress)
        self.visualProgress.connect(self._visual_progressed)
        self._flush = QTimer(self)
        self._flush.setSingleShot(True)
        self._flush.setInterval(80)
        self._flush.timeout.connect(self.publish)
        # State already arrives through Qt signals. Rebuilding the entire
        # conversation/usage snapshot on an idle650ms timer did needless work,
        # including while the WebEngine view was hidden.
        host.installEventFilter(self)
        if surface=='main':
            chat = host.chat_widget
            from .investigation_workspace import InvestigationWorkspace
            self._workspace = InvestigationWorkspace(chat._journal)
            self._seen_chat_investigation = chat._last_investigation.get('id','')
            if not self._workspace.active_id:self._workspace.active_id=self._seen_chat_investigation
            chat.state_changed.connect(self.mark_dirty)
            chat.busy_changed.connect(self.mark_dirty)
            chat.turn_completed.connect(self.mark_dirty)
            chat._archive_timer.timeout.connect(self.mark_dirty)
            host.ai_state.changed.connect(self._connection_changed)
            host.result_model.dataChanged.connect(self.mark_dirty)
            host.result_model.rowsInserted.connect(self.mark_dirty)
            host.result_model.modelReset.connect(self.mark_dirty)
            host.search_state.connect(self.mark_dirty)
            host.controller.search_event.connect(self.mark_dirty)
            host.character.changed.connect(self.mark_dirty)
        elif hasattr(host, 'poll_timer'):
            # The launcher still needs its existing IPC poll for an independent
            # Pet. Only a real status change needs a renderer update.
            host.poll_timer.timeout.connect(self._launcher_changed)

    def _connection_changed(self, *_):
        self._key = resolve_deepseek_key()
        self.mark_dirty()

    def _fail_active_task(self, fingerprint):
        if self._closed or self.surface != 'main':
            return
        chat = self.host.chat_widget
        if chat.busy:
            chat.fail_investigation(fingerprint)
        if self._manual_job is not None:
            self._manual_job.cancel()
            self._manual_job = None
            for row in self._manual_activity:
                if row.get('status') == 'running':
                    row.update(status='failed', error='data_contract_error')
        if getattr(self.host, '_busy', False):
            self.host.controller.cancel()
        self.mark_dirty()

    def _load_credential_flags(self):
        self._credentials = credential_presence(getter=get_secret)
        self._secret_redactions = {self._key} if self._key else set()
        for _, names in SERVICES.values():
            for name, _ in names:
                try:
                    value = get_secret(name)
                except CredentialError:
                    value = ''
                if value:
                    self._secret_redactions.add(value)

    def mark_dirty(self, *_):
        if not self._closed and self._publication_enabled and not self._flush.isActive(): self._flush.start()

    def set_publication_visible(self, visible):
        """Suspend only renderer work; Python requests and archive writes run on."""
        visible = bool(visible)
        if self._closed or visible == self._publication_enabled:
            return
        self._publication_enabled = visible
        if not visible:
            self._flush.stop()
        else:
            self._force_next = True
            self.mark_dirty()

    def eventFilter(self, watched, event):
        if watched is self.host and event.type() in (QEvent.Type.Show, QEvent.Type.Hide,
                QEvent.Type.WindowStateChange, QEvent.Type.ActivationChange):
            self.set_publication_visible(self.host.isVisible() and not self.host.isMinimized())
            self.mark_dirty()
        return super().eventFilter(watched, event)

    def _launcher_changed(self):
        signature = (self.host.running, self.host.process_state, self.host.status.text(),
            self.host.settings.size, self.host.settings.fps, self.host.settings.cursor_reaction,self.host.settings.ui_theme)
        if signature != self._launcher_fingerprint:
            self._launcher_fingerprint = signature
            self.mark_dirty()

    def _usage(self, chat):
        ledger = chat._usage_ledger
        if ledger is None:
            return {}, {}
        # The SQLite ledger is written by Python workers. Its committed file
        # fingerprint invalidates this read cache without reopening/querying
        # the database for every streaming token or window activation.
        try:
            stamp = ledger.path.stat()
            fingerprint = (stamp.st_mtime_ns, stamp.st_size)
        except OSError:
            fingerprint = None
        key = (id(ledger), fingerprint, chat.conversation_id, chat._last_investigation.get('id'))
        if key != self._usage_cache_key:
            conversation = ledger.snapshot(conversation_id=chat.conversation_id)
            investigation = ledger.snapshot(investigation_id=key[-1]) if key[-1] else {}
            self._usage_cache_key = key
            self._usage_cache = conversation, investigation
        return self._usage_cache

    def _json(self, value):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)
        for secret in self._secret_redactions | ({self._key} if self._key else set()):
            raw = raw.replace(json.dumps(secret, ensure_ascii=False)[1:-1], '[скрытый ключ]')
        return raw

    def _history(self):
        chat = self.host.chat_widget
        if not chat._library:return []
        try:
            stamp=chat._archive.path.stat()
            fingerprint=(stamp.st_mtime_ns,stamp.st_size)
        except OSError:
            fingerprint=None
        key=(chat.conversation_id,fingerprint)
        if key!=self._history_key:
            self._history_cache = chat._library.list()
            self._history_key=key
        return self._history_cache

    def _sources(self):
        chat = self.host.chat_widget
        from .investigation_contracts import recover_public_snapshot
        fingerprint=(chat.conversation_id,chat._last_investigation.get('id'),
            len(chat._last_investigation.get('evidence',[])),len(chat._last_investigation.get('executions',[])),
            tuple(row.get('investigation_id') for row in chat.messages if row.get('investigation_id')),
            tuple(id(value) for value in self.host.result_model.records.values()))
        if fingerprint==self._sources_fingerprint: return self._sources_view
        self._raw_sources={}
        sources, seen = [], set()
        investigations = [recover_public_snapshot(chat._last_investigation,
            chat._last_investigation.get('id'), stop_running=False)] if chat._last_investigation else []
        for row in chat.messages:
            identifier = row.get('investigation_id')
            if identifier and identifier not in self._source_cache:
                try: self._source_cache[identifier] = chat._journal.load(identifier)
                except (OSError, ValueError): self._source_cache[identifier] = {}
            if identifier: investigations.append(self._source_cache[identifier])
        for investigation in investigations:
            limitations = {entry.get('query'):entry.get('limitations',[]) for entry in investigation.get('executions',[]) if entry.get('limitations')}
            for record in investigation.get('evidence',[]):
                identifier = record.get('evidence_id')
                if identifier and identifier not in seen:
                    seen.add(identifier)
                    self._raw_sources[identifier] = record
                    sources.append(source_view(record, limitations.get(record.get('provenance',{}).get('query'),())))
        search_sources=[]
        for index in range(min(500, self.host.result_model.rowCount())):
            record = self.host.result_model.record(index)
            identifier = record.get('details',{}).get('evidence_id') or record.get('evidence_id')
            if not identifier:
                record = normalize_evidence(record, 'manual_search', self.host.text.text())
                identifier = record['evidence_id']
            elif not record.get('provenance') and record.get('details',{}).get('agent_tool'):
                details=record['details']
                restored=normalize_evidence(record,details['agent_tool'],details.get('original_query',''),details.get('obtained_at') or None)
                if restored['evidence_id']!=identifier:
                    continue
                if details.get('evidence_verification')=='contradictory':
                    restored['verification']='contradictory'
                record=restored
            search_sources.append(source_view(record))
            if identifier not in seen:
                seen.add(identifier)
                self._raw_sources[identifier] = record
                sources.append(source_view(record))
        self._sources_fingerprint=fingerprint
        self._sources_view=sources
        self._search_sources_view=search_sources
        for record in self._graph_records:
            if record.get('evidence_id'):self._raw_sources.setdefault(record['evidence_id'],record)
        return sources

    def _activity(self):
        result = {}
        for index, event in enumerate(self.host.chat_widget._activity_log):
            tool = event.get('tool')
            if not tool: continue
            key = event.get('tool_call_id') or tool
            state = 'running' if event['type']=='tool_start' else event.get('status','completed')
            spec=next((spec for spec in _SPECS if spec.name==tool),None)
            query=event.get('query','')
            summary=event.get('message') or (json.dumps(query,ensure_ascii=False)[:240] if isinstance(query,dict) else str(query)[:240])
            result[key] = {'id':str(key),'tool':TOOL_NAMES.get(tool,tool),'status':state,'summary':summary,
                'inputType':spec.kind if spec else '', 'resultCount':event.get('count'),
                'error':event.get('error') or event.get('error_code') or ''}
        # The delta publisher retains its previous snapshot. Sharing mutable
        # rows would mutate that snapshot too and hide completion from React.
        return list(result.values())[-30:] + [dict(row) for row in self._manual_activity]

    def snapshot(self):
        settings = self.host.settings
        values = {key:getattr(settings,key) for key in SETTINGS_FIELDS if hasattr(settings,key)}
        base = {'product':PRODUCT_NAME,'version':VERSION,'surface':self.surface,'route':self.route,
            'settings':values,'window':{'maximized':self.host.isMaximized(),'fullscreen':self.host.isFullScreen(),
            'active':bool(self.host.isActiveWindow() and self.host.isVisible() and not self.host.isMinimized())}}
        base['errors'] = self._errors.snapshot() if self._errors is not None else []
        from .credentials import vault_status
        base['vault']=vault_status()
        if self.surface=='launcher':
            state = getattr(self.host,'process_state','running' if self.host.running else 'ready')
            base.update(launcher={'state':state,'running':self.host.running,'size':settings.size,'fps':settings.fps,
                'cursorReaction':settings.cursor_reaction,'error':self.host.status.text() if state=='error' else ''})
            return base
        chat = self.host.chat_widget
        current_id=chat._last_investigation.get('id','')
        if current_id and current_id!=self._seen_chat_investigation:
            self._seen_chat_investigation=current_id
            self._workspace.active_id=current_id
            self._workspace.manual=None
        ai = self.host.ai_state.committed_snapshot()
        base.update(attachments=[dict(row) for row in self._attachments],attachment_busy=self._attachment_job is not None,attachment_error=self._attachment_error)
        sources = self._sources()
        by_id = {s['evidence_id']:s for s in sources}
        messages = []
        for index, row in enumerate(chat.messages):
            value = dict(row)
            value['streaming'] = chat.busy and index==chat._stream_index
            value['sources'] = [by_id[i] for i in row.get('evidence_ids',[]) if i in by_id]
            messages.append(value)
        for source in sources:
            source['message_ids']=[row.get('id') for row in chat.messages
                                   if source['evidence_id'] in row.get('evidence_ids',[])]
        canvas = self.host.canvas
        conversation_usage, investigation_usage = self._usage(chat)
        balance=self._balance.snapshot() if settings.ai_provider=='deepseek' else {
            'status':'not_supported','amount':None,'message':'Баланс доступен только для подключённого шлюза DeepSeek.'}
        investigation = {key:value for key,value in chat._last_investigation.items() if key not in ('evidence','executions','messages')}
        investigation['canResume'] = False
        if investigation.get('stop_reason'):
            code=investigation['stop_reason'];investigation['stop_reason_code']=code
            investigation['stop_reason']={'step_limit':'Достигнут выбранный вами бюджет ходов.',
                'tool_limit':'Достигнут выбранный вами бюджет инструментов.','token_limit':'Достигнут выбранный вами бюджет токенов.',
                'time_limit':'Достигнут выбранный вами бюджет времени.','page_limit':'Достигнут выбранный вами предел страниц.',
                'manual_pause':'Автоматическое продолжение отключено.','no_progress':'Новые проверки пока не добавляют сведений.',
                'cancelled':'Вы остановили расследование.','api_error':'Провайдер прервал запрос. Полученные сведения сохранены.',
                'interrupted':'Запрос был прерван; его результат неизвестен.','context_limit':'Текущий протокольный контекст требует сокращения.'}.get(code,'Работа приостановлена; план и полученные сведения сохранены.')
        if investigation.get('id') and investigation.get('status') not in ('completed','running'):
            investigation['canResume'] = (chat._journal.directory/(investigation['id']+'.checkpoint.dpapi')).is_file()
        base.update(connection={'provider':ai['provider'],'model':ai['model_id'],'status':ai['connection_status'],
                'statusText':self.host.ai_state.status_text(ai),
                'canSend':chat._ready,'error':ai.get('last_error',''),'contextLimit':None,'balance':balance.get('amount'),
                'balanceMessage':balance.get('message','')},
            credentials=self._credentials,settingsCategory=self.settingsCategory,toolsChecking=self._tools_job is not None,
            archiveError=getattr(chat,'archive_error',''),
            conversation_id=chat.conversation_id,messages=messages,busy=chat.busy,activity=self._activity(),evidence=sources,
            message_focus=getattr(self,'message_focus',None),
            search={'query':self.host.text.text(),'kind':self.host.direction.currentData(),'busy':self.host._busy or self._manual_job is not None,
                'phase':self.host.phase,'count':self.host.result_model.rowCount(),
                'checked':int((re.search(r'\d+',self.host.checked_label.text()) or ['0'])[0]),
                'checkedLabel':self.host.checked_label.text(),
                'status':self.host.status.text() if self.host.phase!='idle' else '',
                'error':self.host.status.text() if self.host.phase in ('error','failed','completed_with_errors') else '',
                'choices':[{'label':name,'value':kind} for name,kind in self.host._resolution().choices], 'results':self._search_sources_view},
            tools=self._tools or [{'id':spec.name,'name':TOOL_NAMES.get(spec.name,spec.name),'description':spec.description,'inputTypes':[spec.kind],
                'available':False,'state':'checking' if self._tools_job else 'unverified','reason':'Проверяется локальная готовность.' if self._tools_job else 'Локальная готовность ещё не проверена.',
                'sensitive':spec.requires_approval} for spec in _SPECS],
            investigation=investigation,usage={'request':conversation_usage.get('last_request'),
                'conversation':conversation_usage.get('totals'), 'investigation':investigation_usage.get('totals'),
                'balance':balance}, history=self._history(),
            canvas={'id':canvas.document_id,'text':canvas.editor.toPlainText(),'title':canvas.title.text(),'dirty':canvas._dirty} if canvas else None,
            hermione={'state':self.host._last_activity or 'idle','visible':True})
        base['investigation_graph']=self._graph_data
        base['investigation_choices']=self._investigation_choices
        base['search']['investigation_id']=self._workspace.active_id or current_id
        current=chat._last_investigation.get('evidence',[])
        current_ids={r.get('evidence_id') for r in current}
        base['task_sources']=self._search_sources_view if self.route=='search' else [s for s in sources if s['evidence_id'] in current_ids]
        if self.route=='search' and self._graph_data.get('state')=='ready' and self._graph_data.get('investigation_id')==self._workspace.active_id:
            base['task_sources']=self._graph_data.get('evidence',[])[:20]
        installed=list(base['tools'])
        from .visual_models.manager import get_manager
        visual_state=get_manager().status()
        if self._visual_job is not None:
            visual_state={**visual_state,'state':
                'removing' if self._visual_operation=='visual_remove' else
                'installing' if self._visual_operation=='visual_install' and self._visual_progress.get('phase')=='extracting' else
                'downloading' if self._visual_operation=='visual_install' else 'loading'}
        if not visual_state['installed']:
            model_names={spec.name for spec in _SPECS if spec.execution_mode=='LOCAL_MODEL'}
            installed=[row for row in installed if row['id'] not in model_names]
        base['tool_counts']={'candidates':0,'implemented':len(_SPECS),
            'ready_local':sum(bool(row.get('available')) for row in installed),
            'verified_execution':sum(row.get('readiness_status')=='live_verified' for row in installed)}
        # Candidate research remains in the technical audit, never executable UI.
        base['tools']=installed
        base['connection'].update(models=self._models,modelsChecking=self._models_job is not None,modelsError=self._models_error)
        base['visual_models']={**visual_state,'installing':self._visual_job is not None,
            'progress':dict(self._visual_progress),'installation_error':self._visual_error}
        base['hermione'].update(self.host.character.snapshot())
        if base['vault']['enabled'] and not base['vault']['unlocked']:
            base['connection'].update(canSend=False,status='vault_locked',statusText='Разблокируйте переносимое хранилище в настройках.')
            base['investigation_graph']={'state':'locked'}
            base['investigation_choices']=[]
        return base

    def publish(self, *, force=False):
        if self._closed or not self._publication_enabled and not force:
            return
        force = force or self._force_next
        self._force_next = False
        investigation = getattr(self.host.chat_widget, '_last_investigation', {}) if self.surface == 'main' else {}
        fault_key = (getattr(self.host.chat_widget, 'conversation_id', ''),
                     investigation.get('id') if isinstance(investigation, dict) else id(investigation)) if self.surface == 'main' else ('launcher',)
        if self._snapshot_fault == fault_key:
            # Keep the last good view and all controls usable. A failed task
            # cannot re-enter its broken publisher every streaming/poll signal.
            self.stateChanged.emit(self._json({'patch': True, 'busy': False,
                'errors': self._errors.snapshot() if self._errors is not None else []}))
            return
        try:
            state = self.snapshot()
        except Exception as error:
            self._snapshot_fault = fault_key
            from .errors import report_exception
            report_exception(error, operation='desktop_snapshot', stop_task=True)
            self.stateChanged.emit(self._json({'patch': True, 'busy': False,
                'errors': self._errors.snapshot() if self._errors is not None else []}))
            return
        messages = state.pop('messages', None)
        changes = {key:value for key,value in state.items() if force or self._last.get(key)!=value}
        if messages is not None:
            same_ids = len(messages)==len(self._last_messages) and all(a.get('id')==b.get('id') for a,b in zip(messages,self._last_messages))
            if force or not same_ids:
                changes['messages'] = messages
            else:
                updates = [{'index':i,'message':row} for i,row in enumerate(messages) if row!=self._last_messages[i]]
                if updates: changes.update(message_updates=updates,message_count=len(messages))
            self._last_messages = messages
        self._last = state
        if changes:
            changes['patch'] = not force
            self.stateChanged.emit(self._json(changes))

    def _message(self, identifier):
        return next((row for row in self.host.chat_widget.messages if row.get('id')==identifier), None)

    @Slot(str,str,str)
    def request(self, identifier, action, payload_json):
        maximum=29_000_000 if action=='attachment_import' else MAX_PAYLOAD
        if not isinstance(identifier,str) or len(identifier)>100 or len(payload_json)>maximum:
            return
        try:
            payload = json.loads(payload_json)
            if not isinstance(payload,dict): raise ValueError('Ожидался объект параметров.')
            result = self.dispatch(action,payload)
            self.response.emit(identifier,self._json({'ok':True,'result':result}))
        except (ValueError,TypeError,KeyError) as error:
            self.response.emit(identifier,self._json({'ok':False,'error':str(error)[:300]}))
        except Exception:
            self.response.emit(identifier,self._json({'ok':False,'error':'Операция не завершена. Проверьте состояние приложения.'}))
        self.mark_dirty()

    def dispatch(self, action, payload):
        if not isinstance(action, str) or not isinstance(payload, dict):
            raise ValueError('Ожидались действие и объект параметров.')
        if action == 'error_dismiss':
            if self._errors is not None:
                self._errors.dismiss(payload.get('id'))
            return None
        if action=='ui_ready':
            if payload.get('surface') != self.surface: raise ValueError('Некорректная поверхность.')
            if not self.ui_ready:
                self.ui_ready=True
                self.rendererReady.emit()
                logging.getLogger('grangerpet.desktop').info('Desktop surface ready: %s',self.surface)
                if self.surface=='main':
                    QTimer.singleShot(0,self._refresh_tools)
                    QTimer.singleShot(0,self._refresh_balance)
            return None
        if action=='snapshot':
            self.publish(force=True)
            return self.snapshot()
        if action=='window':
            mode = payload.get('mode')
            operations = {'minimize':self.host.showMinimized,'maximize':self.host.toggle_maximized,
                'fullscreen':self.host.toggle_fullscreen,'close':self.host.close,
                'drag':lambda:self.host.windowHandle() and self.host.windowHandle().startSystemMove()}
            if mode not in operations: raise ValueError('Неизвестное действие окна.')
            operations[mode]()
            return None
        if action=='copy':
            value = payload.get('text')
            if not isinstance(value,str) or len(value)>2_000_000: raise ValueError('Слишком большой текст.')
            QApplication.clipboard().setText(value)
            return None
        if action=='open_url':
            value = payload.get('url')
            if not isinstance(value,str) or not public_link(value): raise ValueError('Ссылка не прошла проверку.')
            return QDesktopServices.openUrl(QUrl(value))
        if action=='vault_manage':
            if set(payload) != {'operation'}: raise ValueError('Парольная фраза вводится только в защищённом окне.')
            return self._vault_manage(payload.get('operation'))
        if self.surface=='launcher': return self._launcher_action(action,payload)
        from .credentials import portable_enabled,portable_unlocked
        if portable_enabled() and not portable_unlocked() and action in (
            'chat_send','chat_new','chat_clear','chat_regenerate','history_load','investigation_continue',
            'canvas_open','canvas_edit','canvas_save','canvas_export','search_run','tool_run','search_analyze','attachment_choose','attachment_import'):
            raise ValueError('Сначала разблокируйте переносимое хранилище в настройках.')
        if action.startswith('investigation_graph_'):
            if portable_enabled() and not portable_unlocked():raise ValueError('Сначала разблокируйте хранилище.')
            return self._graph_action(action,payload)
        chat = self.host.chat_widget
        if action=='layout':
            dock = payload.get('dock')
            if dock is None:
                self._dock_rect = QRect()
                return None
            if not isinstance(dock,dict): raise ValueError('Некорректная геометрия.')
            coordinates = [dock.get(key,0) for key in ('x','y','width','height')]
            if not all(type(v) in (int,float) and -10000<v<20000 for v in coordinates): raise ValueError('Некорректная геометрия.')
            self._dock_rect = QRect(*(round(v) for v in coordinates))
        elif action=='route':
            if payload.get('route') not in ROUTES: raise ValueError('Неизвестный раздел.')
            self.route = payload['route']
            category=payload.get('category')
            if category in ('ai','tools','auth','appearance','notifications','research'):
                self.settingsCategory=category
            if self.route in ('settings','search') and not self._tools and not self._tools_job:
                self._refresh_tools()
            if self.route=='settings': self._refresh_balance()
        elif action=='chat_send':
            text = payload.get('text')
            if not isinstance(text,str) or not text.strip() or len(text)>12000: raise ValueError('Сообщение: 1–12 000 символов.')
            if chat.busy: raise ValueError('Предыдущая задача ещё выполняется.')
            if not chat._ready: raise ValueError('Сначала подключите ИИ в настройках.')
            ids=payload.get('attachment_ids',[])
            if not isinstance(ids,list) or len(ids)>4 or any(not isinstance(v,str) for v in ids): raise ValueError('Выберите не более четырёх изображений.')
            chosen={row['id'] for row in self._attachments}
            if any(value not in chosen for value in ids): raise ValueError('Вложение не выбрано для этой задачи.')
            if ids:
                store=self._images()
                records=[{k:v for k,v in store.get(identifier).items() if k in ('id','name','mime','format','bytes','width','height','sha256')} for identifier in ids]
                chat.set_image_attachments(records,store)
                self._attachments=[row for row in self._attachments if row['id'] not in ids]
            chat.input.setPlainText(text)
            chat.send_message()
            self.route='chat'
        elif action=='chat_stop': chat.cancel()
        elif action in ('attachment_choose','attachment_import','attachment_remove','attachment_cancel'):
            return self._attachment_action(action,payload)
        elif action=='chat_new': chat.new_conversation(); self._history_time=0
        elif action=='chat_clear':
            conversation_id=chat.conversation_id
            ids=[r['id'] for r in chat.messages if r.get('id')]
            chat.clear_history(); self._history_time=0
            if hasattr(self.host,'report_messages_removed'):
                self.host.report_messages_removed(conversation_id,ids)
        elif action=='chat_regenerate': chat.regenerate(payload.get('message_id'))
        elif action=='message_focus':
            identifier=payload.get('message_id')
            if not self._message(identifier): raise ValueError('Сообщение не найдено.')
            self.message_focus=identifier
        elif action=='history_load': chat.load_conversation(payload.get('id')); self.route='chat'; self._history_time=0
        elif action=='messages_seen':
            ids=payload.get('message_ids')
            if not isinstance(ids,list) or len(ids)>500 or any(not isinstance(v,str) or len(v)>100 for v in ids):
                raise ValueError('Некорректные идентификаторы сообщений.')
            return self.host.report_messages_seen(payload.get('conversation_id'),ids)
        elif action=='investigation_continue': chat.continue_investigation(payload.get('id')); self.route='chat'
        elif action=='canvas_open':
            row = self._message(payload.get('message_id'))
            if not row or row['role']!='model': raise ValueError('Ответ не найден.')
            self.host.open_canvas(row['text']); self.route='canvas'
        elif action in ('canvas_edit','canvas_save','canvas_export'):
            canvas = self.host.canvas
            if not canvas or not canvas.document_id: raise ValueError('Сначала откройте документ.')
            if action=='canvas_edit':
                if payload.get('document_id') != canvas.document_id: raise ValueError('Документ изменился. Откройте нужный отчёт снова.')
                text = payload.get('text')
                if not isinstance(text,str) or len(text.encode('utf-8'))>2_000_000: raise ValueError('Документ: не более 2 МБ.')
                canvas.editor.setPlainText(text)
            elif action=='canvas_save':
                if canvas.save_document() is None: raise ValueError('Документ не был сохранён.')
            else:
                path = canvas.export_document()
                return {'exported':bool(path),'filename':path.name if path else None}
        elif action=='search_run':
            text = payload.get('query')
            if not isinstance(text,str) or not 0<len(text)<=2000: raise ValueError('Некорректный запрос.')
            kind = payload.get('kind','auto')
            if kind not in ('auto','username','email','phone','telegram','vk','instagram','web','blockchain','dork'): raise ValueError('Неизвестное направление.')
            from .entity_router import route as route_entity
            target = route_entity(text)
            specialized = None
            if kind in ('auto', 'telegram') and target and target.platform == 'telegram':
                specialized = {'tool': 'telegram_public', 'arguments': {'username': target.canonical_url, 'access_mode': 'public'}}
            elif kind == 'auto' and target and target.entity_type == 'github_repository':
                specialized = {'tool': 'github_repository', 'query': target.identifier}
            elif kind == 'auto' and target and target.entity_type == 'github_profile':
                specialized = {'tool': 'github_profile', 'query': target.identifier}
            elif kind == 'auto' and target and target.entity_type == 'infrastructure_asset' and target.properties.get('public'):
                specialized = {'tool': 'ip_lookup', 'query': target.identifier}
            elif kind == 'auto' and target and target.entity_type == 'geographic_coordinates':
                specialized = {'tool': 'map_wikimedia', 'query': target.identifier}
            elif kind in ('auto','blockchain') and target and target.entity_type == 'blockchain_address' and 'blockchain_gansar' in target.tools:
                # Use the same normalized evidence/checkpoint pipeline as the
                # catalog and agent; the legacy form-only route never saved an
                # investigation and could not publish its graph.
                specialized = {'tool':'blockchain_gansar','query':text}
            self.route='search'
            if specialized:
                self._run_tool(specialized)
            else:
                self.host.text.setText(text); self.host.set_query_kind(kind); self.host.start_search()
        elif action=='search_dorks':
            text=payload.get('query','')
            if not isinstance(text,str) or len(text)>2000: raise ValueError('Некорректный запрос.')
            self.host.text.setText(text)
            self.host.open_dorks()
            self.route='search'
        elif action=='search_stop':
            if self._manual_job:
                self._manual_job.cancel(); self._manual_job.deleteLater(); self._manual_job=None
                self.host._set_phase('cancelled')
            for row in self._manual_activity:
                if row['status']=='running': row['status']='cancelled'
            self.host.search_state.emit('idle')
            self.host.cancel_search()
        elif action=='tools_refresh': self._refresh_tools(force=True)
        elif action in ('visual_install','visual_cancel','visual_probe','visual_remove'):
            return self._visual_action(action,payload)
        elif action=='tool_run': self._run_tool(payload)
        elif action=='source_open':
            self._sources()
            if payload.get('evidence_id') not in self._raw_sources: raise ValueError('Источник не найден.')
            return source_view(self._raw_sources[payload['evidence_id']])
        elif action=='search_analyze':
            self._sources()
            ids = payload.get('evidence_ids',[])
            if not isinstance(ids,list) or not 1<=len(ids)<=20: raise ValueError('Выберите 1–20 находок.')
            records = [self._raw_sources[i] for i in ids if i in self._raw_sources]
            if len(records)!=len(ids): raise ValueError('Одна из находок недоступна.')
            chat.analyze_selected(records); self.route='chat'
        elif action=='settings_save': self._save_settings(payload.get('values'))
        elif action=='credentials_edit': return self._edit_credentials(payload.get('service'))
        elif action=='connection_test': self.host.settings_dialog.connections.check_connection()
        elif action=='connection_models': self._list_models()
        elif action=='balance_refresh': self._refresh_balance(force=True)
        elif action=='settings_path': return self._settings_path(payload.get('field'))
        elif action=='public_search_open':
            from urllib.parse import urlencode
            query=payload.get('query')
            if payload.get('source')!='avito' or not isinstance(query,str) or not 0<len(query.strip())<=300 or any(ord(c)<32 for c in query):
                raise ValueError('Укажите поисковый запрос Avito: 1–300 символов.')
            url='https://www.avito.ru/rossiya/telefony?'+urlencode({'q':query.strip()})
            opened=QDesktopServices.openUrl(QUrl(url))
            return {'opened':opened,'url':url,'machine_results':False}
        elif action=='settings_native':
            category = payload.get('category')
            if category not in ('ai','tools','auth'): raise ValueError('Неизвестная категория.')
            self.route='settings'; self.settingsCategory=category
        else: raise ValueError('Неизвестное действие приложения.')
        self.host.user_activity.emit()
        return None

    def _save_settings(self, values):
        if not isinstance(values,dict) or set(values)-SETTINGS_FIELDS: raise ValueError('Недопустимые параметры настроек.')
        previous_model_source=(self.host.settings.ai_provider,self.host.settings.ollama_url)
        merged = asdict(self.host.settings)
        merged.update(values)
        settings = Settings.from_dict(merged)
        if (settings.ai_provider,settings.ollama_url)!=previous_model_source:
            self._models=[];self._models_error=''
            if self._models_job:
                self._models_job.cancel();self._models_job.deleteLater();self._models_job=None
        if self.host.store: self.host.store.save(settings)
        self.host.set_settings(settings)
        from .theme import apply_theme
        apply_theme(QApplication.instance(),settings.ui_theme)
        QApplication.instance().setProperty('reduced_motion',getattr(settings,'reduced_motion',False))
        self.host.settings_dialog.settings_saved.emit(settings)
        self._manual_registry = None
        if self._tools_job:
            self._tools_job.cancel(); self._tools_job.deleteLater(); self._tools_job=None
        self._tools_generation += 1
        self._tools=[]
        QTimer.singleShot(0,self._refresh_tools)

    def _vault_manage(self, operation):
        from . import credentials
        from .vault_dialog import VaultDialog
        if operation not in ('create','unlock','lock','change'): raise ValueError('Неизвестная операция хранилища.')
        vault=credentials.vault_status()
        if operation=='create' and vault['enabled']:
            raise ValueError('Переносимое хранилище уже существует. Разблокируйте его.')
        if operation!='create' and not vault['enabled']:
            raise ValueError('Сначала создайте переносимое защищённое хранилище.')
        if operation=='change' and not vault['unlocked']:
            raise ValueError('Сначала разблокируйте защищённое хранилище.')
        chat=getattr(self.host,'chat_widget',None)
        connections=getattr(getattr(self.host,'settings_dialog',None),'connections',None)
        jobs=(self._manual_job,self._balance_job,self._models_job,self._tools_job,self._visual_job,self._graph_job,
              getattr(self,'_attachment_job',None))
        if ((chat and chat.busy) or getattr(self.host,'_busy',False) or any(jobs)
                or bool(getattr(connections,'_jobs',[]))):
            raise ValueError('Дождитесь текущих запросов или остановите задачу перед изменением хранилища.')
        canvas=getattr(self.host,'canvas',None)
        if operation in ('create','lock') and canvas and canvas._dirty:
            if canvas.save_document() is None:
                raise ValueError('Не удалось сохранить изменения Canvas. Хранилище не изменено; документ остаётся открыт.')
        if operation in ('create','lock') and chat and not chat._save_archive(): raise ValueError(chat.archive_error)
        if operation=='lock':
            from .visual_models.manager import get_manager
            get_manager().close()
            credentials.lock_portable_vault()
            if chat:
                chat._archive_timer.stop();chat.messages.clear();chat._context.clear();chat.history.clear()
                chat._last_investigation={};chat._activity_log=[];chat._agent_registry=chat._agent_runner=None
                chat._resume_state=None;chat._agent_followup=False;chat._last_failed_text=''
                if chat._library: chat._library._metadata_cache.clear()
                self.host.result_model.clear()
                if canvas:
                    canvas._save_timer.stop();canvas._preview_timer.stop()
                    canvas._loading=True
                    canvas.editor.clear();canvas.preview.set_source('');canvas.heading_list.clear()
                    canvas._loading=False;canvas._dirty=False;canvas.document_id=''
                    canvas._documents.clear();canvas._original_source=''
                    canvas.title.setText('Canvas · Хранилище заблокировано')
            self._manual_activity=[]
            attachment_store=getattr(self,'_attachment_store',None)
            clear_sensitive=getattr(attachment_store,'clear_sensitive_cache',None)
            if callable(clear_sensitive): clear_sensitive()
        else:
            dialog=VaultDialog(operation,self.host)
            if dialog.exec()!=QDialog.DialogCode.Accepted: return {'completed':False}
            if chat and operation in ('unlock','create'):
                saved=chat._archive.load() if chat._archive else {}
                if chat._library: chat._library._metadata_cache.clear()
                chat.messages.clear();chat.history.clear();chat._context=saved.get('context',[])
                chat._restore_archive_rows(saved.get('messages',[]));chat._restore_investigation()
                chat._set_archive_error('' if not chat._archive or not chat._archive.last_error else
                    'Не удалось прочитать локальную историю. Прежний архив сохранён без изменений.')
        self._history_key=self._sources_fingerprint=self._usage_cache_key=None
        self._history_cache=[];self._source_cache={};self._raw_sources={};self._sources_view=[];self._search_sources_view=[]
        self._attachment_store=None;self._attachments=[];self._attachment_error=''
        self._manual_registry=None;self._tools=[]
        self._graph_generation+=1;self._graph_data={'state':'idle'};self._graph_records=[];self._investigation_choices=[]
        if chat:
            from .investigation_workspace import InvestigationWorkspace
            self._workspace=InvestigationWorkspace(chat._journal)
            self._seen_chat_investigation=chat._last_investigation.get('id','')
        self._secret_redactions.clear();self._key=resolve_deepseek_key();self._load_credential_flags()
        settings=self.host.store.load() if self.host.store else self.host.settings
        if hasattr(self.host,'set_settings'): self.host.set_settings(settings)
        else: self.host.settings=settings
        if chat: chat._update_actions();chat.state_changed.emit()
        self.publish(force=True)
        return {'completed':True,**credentials.vault_status()}

    def _images(self):
        from .geoint_tools import attachment_store
        if self._attachment_store is None:
            self._attachment_store=attachment_store(Path(self.host.store.path).parent if self.host.store else None)
        return self._attachment_store

    def _attachment_action(self,action,payload):
        if action=='attachment_cancel':
            if self._attachment_job:
                self._attachment_job.cancel();self._attachment_job.deleteLater();self._attachment_job=None
            self._attachment_error='';return None
        if action=='attachment_remove':
            self._attachments=[row for row in self._attachments if row['id']!=payload.get('id')]
            return None
        if self.host.chat_widget.busy or self._attachment_job: raise ValueError('Дождитесь обработки текущего изображения или остановите её.')
        if len(self._attachments)>=4: raise ValueError('В одном сообщении можно выбрать до четырёх изображений.')
        from .geoint import MAX_IMAGE_BYTES
        store=self._images()
        if action=='attachment_choose':
            path,_=QFileDialog.getOpenFileName(self.host,'Выбрать изображение','','Изображения (*.jpg *.jpeg *.png *.webp)')
            if not path: return {'started':False}
            selected=Path(path)
            def load():
                if not selected.is_file() or selected.stat().st_size>MAX_IMAGE_BYTES: raise ValueError('Изображение должно занимать не более 20 МиБ.')
                with selected.open('rb') as stream: data=stream.read(MAX_IMAGE_BYTES+1)
                return store.import_bytes(data,selected.name,cancel_event=job.cancelled)
        else:
            name,encoded=payload.get('name'),payload.get('base64')
            if not isinstance(name,str) or len(name)>500 or not isinstance(encoded,str) or len(encoded)>28_000_000:
                raise ValueError('Некорректное вложение.')
            def load():
                try: data=base64.b64decode(encoded,validate=True)
                except ValueError: raise ValueError('Некорректное кодирование изображения.') from None
                return store.import_bytes(data,name,cancel_event=job.cancelled)
        job=UiJob(load,self);self._attachment_job=job;self._attachment_error=''
        def done(result,error):
            if self._attachment_job is not job:return
            self._attachment_job=None
            if error:self._attachment_error=error
            elif result and not any(row['id']==result['id'] for row in self._attachments): self._attachments=self._attachments+[result]
            job.function=lambda:None;job.deleteLater();self.mark_dirty()
        job.done.connect(done);job.start()
        return {'started':True}

    def _list_models(self):
        if self.host.settings.ai_provider!='ollama':
            raise ValueError('Для DeepSeek используется заданная модель deepseek-v4-flash. Этот шлюз не предоставляет проверенный каталог моделей.')
        if self._models_job:return
        from .ai import OllamaClient
        address=self.host.settings.ollama_url
        job=UiJob(lambda:OllamaClient(address).list_models(),self)
        self._models_job=job;self._models_error=''
        def done(result,error):
            if self._models_job is not job:return
            self._models_job=None
            if self.host.settings.ai_provider=='ollama' and self.host.settings.ollama_url==address:
                self._models=[{'id':value} for value in (result or []) if isinstance(value,str)][:200] if not error else []
                self._models_error=error or ''
            job.deleteLater();self.mark_dirty()
        job.done.connect(done);job.start();self.mark_dirty()

    def _edit_credentials(self,service):
        if service not in SERVICES: raise ValueError('Неизвестный источник учётных данных.')
        dialog=CredentialDialog(service,self.host)
        try: saved=dialog.exec()==QDialog.DialogCode.Accepted
        finally: dialog.deleteLater()
        if saved:
            self._key=resolve_deepseek_key()
            self._load_credential_flags()
            settings=self.host.store.load() if self.host.store else self.host.settings
            self.host.set_settings(settings)
            self.host.ai_state.commit(settings)
            self.host.settings_dialog.settings_saved.emit(settings)
            self._manual_registry=None
            self._tools=[]
            if self._tools_job:
                self._tools_job.cancel();self._tools_job.deleteLater();self._tools_job=None
            self._tools_generation+=1
            self._balance_generation+=1
            if self._balance_job:
                self._balance_job.cancel();self._balance_job.deleteLater();self._balance_job=None
                self._balance.cancel_pending()
            QTimer.singleShot(0,self._refresh_tools)
            QTimer.singleShot(0,self._refresh_balance)
        return {'saved':saved}

    def _settings_path(self,field):
        if field=='source_root':
            path=QFileDialog.getExistingDirectory(self.host,'Папка локальных инструментов',self.host.settings.source_root)
        elif field=='runtime_python':
            path,_=QFileDialog.getOpenFileName(self.host,'Python для локальных инструментов',self.host.settings.runtime_python,'Python (python.exe pythonw.exe);;Все файлы (*)')
        else: raise ValueError('Неизвестный путь настроек.')
        return {'path':path or ''}

    def _refresh_balance(self,*,force=False):
        if self.surface!='main' or self.host.settings.ai_provider!='deepseek' or self._balance_job:
            return
        key=resolve_deepseek_key()
        if not self._balance.prepare(key,force=force): return
        generation=self._balance_generation
        job=UiJob(lambda:fetch_balance(key),self)
        self._balance_job=job
        def done(result,error):
            if generation!=self._balance_generation or self._balance_job is not job: return
            self._balance_job=None
            self._balance.finish(result or {'status':'unavailable','error':'Баланс шлюза временно недоступен.'})
            job.deleteLater();self.mark_dirty()
        job.done.connect(done);job.start();self.mark_dirty()

    def _launcher_action(self, action, payload):
        if action=='launcher_start': self.host.start_pet()
        elif action=='launcher_stop': self.host.stop_pet()
        elif action=='launcher_exit': self.host.exit_all()
        elif action=='launcher_preferences':
            if set(payload)-{'size','fps','cursor_reaction'}: raise ValueError('Недопустимые параметры.')
            if 'size' in payload: self.host.size_slider.setValue(max(100,min(195,int(payload['size']))))
            if 'fps' in payload: self.host.fps_spin.setValue(max(8,min(30,int(payload['fps']))))
            if 'cursor_reaction' in payload:
                if type(payload['cursor_reaction']) is not bool: raise ValueError('Ожидался переключатель.')
                self.host.reaction_box.setChecked(payload['cursor_reaction'])
            self.host.save_preferences()
        elif action=='route':
            route=payload.get('route')
            if route not in ROUTES: raise ValueError('Неизвестный раздел.')
            self.host.open_workspace(route)
        else: raise ValueError('Неизвестное действие лаунчера.')

    def _registry(self):
        if self._manual_registry is None:
            self._manual_registry = ToolRegistry(self.host.settings,redactions=(self._key,),image_store=self._images())
        return self._manual_registry

    def _refresh_tools(self,*,force=False):
        if self._tools_job: return
        registry = self._registry()
        self._tools_generation+=1
        generation=self._tools_generation
        job = UiJob(lambda:registry.catalog(cancel_event=job.cancelled,force_refresh=force,
            on_update=lambda row:self.toolProgress.emit((generation,row))),self)
        self._tools_job = job
        def done(rows,error):
            if generation!=self._tools_generation or self._tools_job is not job: return
            self._tools_job=None
            if not error:
                self._tools=[self._tool_view(row) for row in rows]
            else:
                self._tools=[{**self._tool_view({'name':spec.name,'description':spec.description,'kind':spec.kind,
                    'requires_approval':spec.requires_approval,'available':False,'state':'configuration_error',
                    'reason':'Не удалось проверить окружение. Повторите проверку локальных инструментов.'}),
                    'diagnostic':{'code':'probe_failed','remedy':'Проверьте папку источников и выбранный Python.'}} for spec in _SPECS]
            job.deleteLater(); self.mark_dirty()
        job.done.connect(done); job.start(); self.mark_dirty()

    @staticmethod
    def _tool_view(row):
        return {'id':row['name'],'name':TOOL_NAMES.get(row['name'],row['name']),'description':row['description'],
            'inputTypes':[row['kind']],'available':row['available'],'state':row['state'],'reason':row['reason'],
            'diagnostic':row.get('diagnostic',{}),'last_execution':row.get('last_execution'),
            'lastChecked':row.get('diagnostic',{}).get('checked_at'),
            'sensitive':row.get('requires_approval',False),'implemented':True,
            'manifest':row.get('manifest'),'readiness_status':row.get('readiness_status'),
            'documentation_url':(row.get('manifest') or {}).get('documentation_url','')}

    def _tool_progress(self,value):
        generation,row=value
        if generation!=self._tools_generation or not self._tools_job: return
        by_id={item['id']:item for item in self._tools}
        by_id[row['name']]=self._tool_view(row)
        self._tools=[by_id[spec.name] if spec.name in by_id else self._tool_view({
            'name':spec.name,'kind':spec.kind,'description':spec.description,'available':False,
            'state':'checking','reason':'Проверяется локальный запуск.','requires_approval':spec.requires_approval}) for spec in _SPECS]
        self.mark_dirty()

    def _run_tool(self,payload):
        if self._manual_job or self.host.chat_widget.busy or self.host._busy: raise ValueError('Сначала дождитесь или остановите текущую задачу.')
        spec = next((s for s in _SPECS if s.name==payload.get('tool')),None)
        query = payload.get('query')
        if not spec:raise ValueError('Некорректный инструмент.')
        if spec.input_schema is not None:
            from .tool_inputs import validate_object
            arguments=validate_object(payload.get('arguments'),spec.input_schema)
            query=arguments.get(spec.argument)
            if not isinstance(query,str):query=json.dumps(arguments,ensure_ascii=False,separators=(',',':'))[:2000]
        elif not isinstance(query,str) or not 0<len(query)<=spec.max_length: raise ValueError('Некорректный инструмент или запрос.')
        maximum=10 if spec.name=='web_search' else 20
        limit = payload.get('limit',min(maximum,self.host.settings.request_limit))
        if type(limit) is not int or not 1<=limit<=maximum: raise ValueError(f'Число результатов: 1–{maximum}.')
        if spec.input_schema is None:arguments={spec.argument:query,'limit':limit}
        approved = not (spec.requires_approval or spec.source == 'telegram_preview' and arguments.get('access_mode') == 'authorized')
        if not approved:
            approved = QMessageBox.question(self.host,PRODUCT_NAME,'Разрешить '+spec.name+'?\n\n'+spec.description+'\n\nПараметры: '+json.dumps(arguments,ensure_ascii=False),
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes
        if not approved: raise ValueError('Действие не подтверждено.')
        registry = self._registry(); registry.seed_urls_from_user(query)
        if spec.kind=='image':
            self._images().get(query)
            registry.allow_attachments([query])
        if spec.source=='visual_model':
            for field in ('attachment_id','reference_id'):
                if field in arguments:
                    self._images().get(arguments[field]);registry.allow_attachments([arguments[field]])
        if spec.source=='graph':
            self._sources()
            registry.evidence.restore(list(self._raw_sources.values()),registry.evidence.executions())
        registry._validate(spec,arguments)
        if spec.source=='evidence_get':
            self._sources()
            record=self._raw_sources.get(query)
            if record and not registry.evidence.get(query):
                registry.evidence.restore(registry.evidence.records()+[record],registry.evidence.executions())
        self.host.result_model.clear()
        self.host.text.setText(query)
        self.host.checked_label.clear()
        self.host._set_phase('searching')
        self._manual_activity=[{'id':spec.name,'tool':TOOL_NAMES.get(spec.name,spec.name),'status':'running',
            'inputType':spec.kind,'summary':'Запрос пользователя'}]
        self.host.search_state.emit('working')
        job = UiJob(lambda:registry.execute(spec.name,arguments,cancel_event=job.cancelled,
            deadline=time.monotonic()+registry.timeout_for(spec.name,self.host.settings.search_timeout),approved=approved),self)
        self._manual_job=job
        def done(outcome,error):
            if self._manual_job is not job:return
            self._manual_job=None
            status = outcome.get('status','error') if isinstance(outcome,dict) else 'error'
            self._manual_activity[0]['status']=status
            self._manual_activity[0]['summary']=error or str((outcome or {}).get('error') or '')
            self._manual_activity[0]['resultCount']=len((outcome or {}).get('results',[]))
            self._manual_activity[0]['error']=error or str((outcome or {}).get('error') or '')
            self.host.checked_label.setText('Адаптеров выполнено: 1')
            if isinstance(outcome,dict):
                self.host._agent_evidence(outcome.get('results',[]))
                for row in outcome.get('results',[]): self._raw_sources[row['evidence_id']]=row
                if spec.source not in ('graph','evidence_get'):
                    try:
                        self._workspace.manual_result(query,outcome,arguments,registry,self.host.chat_widget.conversation_id)
                        self._graph_signature=None
                    except (OSError,ValueError,CredentialError) as failure:
                        from .errors import report_exception
                        report_exception(failure,operation='manual_investigation_save')
            # A timed-out source can retain streamed observations. Keep the
            # execution's timeout status, but describe the usable Search result
            # as incomplete rather than saying the whole search failed.
            has_results=bool((outcome or {}).get('results'))
            self.host._set_phase('completed_with_errors' if status=='partial' or has_results and status not in ('complete','completed') else
                'completed' if status in ('complete','completed') and (outcome or {}).get('results') else
                'completed_empty' if status in ('complete','completed','empty') else 'failed')
            self.host.search_state.emit('happy' if not error and status in ('complete','completed','partial','empty') else 'error')
            QTimer.singleShot(0,self._refresh_tools)
            job.deleteLater(); self.mark_dirty()
        job.done.connect(done); job.start()

    def _graph_action(self,action,payload):
        if self.surface!='main' or self._workspace is None:raise ValueError('Откройте рабочее пространство.')
        identifier=payload.get('id') or self._workspace.active_id or self.host.chat_widget._last_investigation.get('id')
        if not identifier:
            self._graph_data={'state':'empty'}
            return {'pending':False,'empty':True}
        self.host.chat_widget._journal._identifier(identifier)
        if action=='investigation_graph_get':
            self._workspace.active_id=identifier
            self._graph_generation+=1
            generation=self._graph_generation
            if self._graph_job is not None:self._graph_job.cancel();self._graph_job.deleteLater()
            live=self.host.chat_widget._last_investigation
            live=deepcopy(live) if live.get('id')==identifier else None
            self._graph_data=({**self._graph_data,'refreshing':True} if self._graph_data.get('state')=='ready' and self._graph_data.get('investigation_id')==identifier
                else {'state':'loading','investigation_id':identifier})
            def prepare():
                from .investigation_results import project
                snapshot=self._workspace.load(identifier,live)
                data=project(snapshot,cancel_event=job.cancelled)
                try:data['view']=self._workspace.views.load(identifier)
                except (ValueError,OSError):
                    data['view']={'version':1,'mode':'overview','positions':{}}
                    data['warnings'].append('Сохранённое положение графа не прочитано; первичные данные сохранены.')
                raw=data.pop('evidence',[])
                data['evidence']=[{key:value for key,value in source_view(row).items() if key!='details'} |
                    {'relevance':row.get('relevance'),'related_evidence_ids':row.get('related_evidence_ids',[]),
                     'duplicate_count':row.get('duplicate_count',0)} for row in raw]
                for section in ('findings','hypotheses'):
                    data['summary'][section]=[{'evidence_id':row['evidence_id'],'title':row['title'],
                        'description':row['description'],'url':row.get('url',''),'status':row.get('status'),
                        'relevance':row.get('relevance')} for row in data['summary'][section]]
                data['state']='ready'
                data['generation']=generation
                choices=[]
                directory=self.host.chat_widget._journal.directory
                paths=sorted(directory.glob('*.checkpoint.dpapi'),key=lambda path:path.stat().st_mtime,reverse=True)[:40]
                for path in paths:
                    if job.cancelled.is_set():raise InterruptedError('Graph cancelled')
                    try:
                        record=self.host.chat_widget._journal.load_checkpoint(path.name.split('.')[0])['record']
                        choices.append({'id':record['id'],'title':str(record.get('goal') or 'Расследование')[:120],
                            'status':'interrupted' if record.get('status')=='running' and record['id']!=identifier else record.get('status'),
                            'updated_at':record.get('updated_at') or record.get('finished_at') or record.get('started_at')})
                    except (OSError,ValueError):continue
                return data,snapshot.get('evidence',[]),choices
            job=UiJob(prepare,self)
            self._graph_job=job
            def ready(result,error):
                if self._closed or generation!=self._graph_generation:return
                self._graph_job=None
                if error or not isinstance(result,tuple):
                    self._graph_data={'state':'error','investigation_id':identifier,'error':'Не удалось подготовить граф. Исходные данные сохранены.'}
                else:
                    self._graph_data,self._graph_records,self._investigation_choices=result
                    try:self._workspace.select(identifier)
                    except (OSError,ValueError,CredentialError):
                        self._graph_data['warnings'].append('Выбор графа не сохранён; данные доступны в текущем сеансе.')
                    for record in self._graph_records:
                        if isinstance(record,dict) and record.get('evidence_id'):self._raw_sources[record['evidence_id']]=record
                job.deleteLater();self.mark_dirty()
            job.done.connect(ready);job.start()
            self.mark_dirty()
            return {'pending':True,'id':identifier,'generation':generation}
        if action=='investigation_graph_cancel':
            if self._graph_job:self._graph_job.cancel();self._graph_job=None
            self._graph_generation+=1
            self._graph_data={'state':'cancelled','investigation_id':identifier}
            return None
        if self._graph_data.get('investigation_id')!=identifier or self._graph_data.get('state')!='ready':raise ValueError('Сначала откройте граф этого расследования.')
        if action=='investigation_graph_view_save':
            view=self._workspace.views.save(identifier,payload.get('view'))
            return {'saved':True,'version':view['version']}
        if action=='investigation_graph_select':
            entity=payload.get('entity_id','');relation=payload.get('relation_id','')
            if entity and entity not in {row['id']for row in self._graph_data['entities']}:raise ValueError('Узел не относится к открытому графу.')
            if relation and relation not in {row['id']for row in self._graph_data['relations']}:raise ValueError('Связь не относится к открытому графу.')
            self._graph_selection={'entity_id':entity,'relation_id':relation}
            return self._graph_selection
        if action=='investigation_graph_analyze':
            return self._analyze_graph(identifier,payload)
        raise ValueError('Неизвестное действие графа.')

    def _analyze_graph(self,identifier,payload):
        chat=self.host.chat_widget
        if chat.busy or self._manual_job:raise ValueError('Сначала завершите или остановите текущую задачу.')
        if not chat._ready:raise ValueError('Сначала подключите ИИ в настройках.')
        intent=payload.get('intent','explain')
        if intent not in ('explain','investigate','compare'):raise ValueError('Неизвестное действие анализа.')
        nodes={row['id']:row for row in self._graph_data['entities']}
        edges={row['id']:row for row in self._graph_data['relations']}
        selected=payload.get('entity_id') or (getattr(self,'_graph_selection',{}) or {}).get('entity_id') or self._graph_data.get('root_id')
        relation_id=payload.get('relation_id') or (getattr(self,'_graph_selection',{}) or {}).get('relation_id')
        other=payload.get('other_entity_id')
        if selected and selected not in nodes or other and other not in nodes or relation_id and relation_id not in edges:
            raise ValueError('Выбранные объекты не относятся к открытому графу.')
        requested={value for value in (selected,other) if value}
        if relation_id:requested.update((edges[relation_id]['from_id'],edges[relation_id]['to_id']))
        if not requested:raise ValueError('Выберите узел или связь в графе.')
        from .graph_context import selection_context
        context=selection_context(nodes,edges,requested,relation_id,self._graph_records)
        snapshot=self._workspace.load(identifier,chat._last_investigation)
        conversation=snapshot.get('conversation_id')
        if conversation and conversation!=chat.conversation_id:
            chat.load_conversation(conversation)
        text={'explain':'Объясни основания выбранного узла или связи по сохранённым доказательствам; новых сетевых проверок не запускай.',
            'investigate':'Продолжи исследование выбранного узла. Учитывай сохранённую цель, выполненные проверки, граф и ограничения; повторов без новых оснований не делай.',
            'compare':'Сравни выбранные объекты по сохранённым данным, покажи различия и неопределённости; общего владельца не угадывай.'}[intent]
        chat.continue_investigation(identifier,followup={'text':text,'context':context,'intent':intent})
        self.route='chat'
        return {'investigation_id':identifier,'selected_entity_ids':sorted(requested)}

    def _visual_progressed(self,row):
        if not self._visual_job:return
        if 'bytes' in row:row={**row,'downloaded_bytes':row['bytes']}
        self._visual_progress={**self._visual_progress,**row}
        self.mark_dirty()

    def _visual_action(self,action,payload):
        from .visual_models.manager import get_manager
        manager=get_manager()
        if payload:raise ValueError('Установка моделей не принимает пути или команды.')
        if action=='visual_cancel':
            if self._visual_job:
                self._visual_job.cancel();self._visual_job.deleteLater();self._visual_job=None
                self._visual_error='Установка или проверка отменена; незавершённые загрузки сохранены для возобновления.'
            self.mark_dirty();return
        if self._visual_job or self._manual_job or self.host.chat_widget.busy or self.host._busy:
            raise ValueError('Дождитесь завершения текущей задачи или остановите её.')
        if action=='visual_install':
            state=manager.status()
            accepted=QMessageBox.question(self.host,PRODUCT_NAME,
                f"Скачать отдельный CPU-runtime GeoCLIP/Waypoint?\n\nЗагрузка: {state['download_bytes']:,} байт. Рекомендуется 8 ГБ диска и 6 ГБ RAM. Только CPU, без CUDA. Основное окружение Python не изменяется. Версии, SHA-256 и лицензии закреплены в manifest.json.",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if accepted!=QMessageBox.StandardButton.Yes:return
        if action=='visual_remove':
            accepted=QMessageBox.question(self.host,PRODUCT_NAME,
                'Удалить только скачанный Granger CPU-runtime и его кэш моделей? Изображения, история и другие инструменты сохранятся.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if accepted!=QMessageBox.StandardButton.Yes:return
        manager.close();self._visual_progress={};self._visual_error=''
        def work():
            if action=='visual_remove':
                from .visual_models.installation import remove_runtime
                remove_runtime(manager.root);return {'status':'completed','removed':True}
            if action=='visual_install':
                from .visual_models.installation import install
                install(manager.root,consent=True,cancel_event=job.cancelled,progress=self.visualProgress.emit)
            return manager.probe(cancel_event=job.cancelled,deadline=time.monotonic()+90)
        job=UiJob(work,self);self._visual_job=job;self._visual_operation=action
        def done(result,error):
            if self._visual_job is not job:return
            self._visual_job=None
            if error:self._visual_error='Не удалось завершить установку. Части загрузок сохранены; повторите после проверки соединения и свободного диска.'
            elif not isinstance(result,dict) or result.get('status')!='completed':self._visual_error='CPU-runtime не прошёл проверку: '+str((result or {}).get('error_code','probe_failed'))
            job.deleteLater();self._refresh_tools(force=True);self.mark_dirty()
        job.done.connect(done);job.start();self.mark_dirty()

    def shutdown(self):
        if self._closed:return
        self._closed = True
        self._flush.stop()
        self.host.removeEventFilter(self)
        from .visual_models.manager import get_manager
        get_manager().close()
        for job in (self._tools_job,self._balance_job,self._models_job,self._attachment_job,self._visual_job,self._graph_job):
            if job: job.cancel();job.deleteLater()
        self._tools_job=None;self._balance_job=None
        if self._manual_job:
            self._manual_job.cancel(); self._manual_job.deleteLater(); self._manual_job=None
