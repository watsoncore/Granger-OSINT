"""Finite, secret-free application protocol for the bundled local renderer.

No HTTP server, shell, eval, arbitrary file access or remote WebChannel clients.
Existing Python controllers remain the sole owners of requests and evidence.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import re
import logging
from pathlib import Path
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QRect, QTimer, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QMessageBox

from .agent_evidence import normalize_evidence, redact
from .agent_tools import ToolRegistry, _SPECS
from .ai_keys import resolve_deepseek_key
from .config import Settings
from .markdown_view import public_link
from .product import PRODUCT_NAME, VERSION
from .ui_jobs import UiJob


SETTINGS_FIELDS = frozenset(('size','fps','cursor_reaction','agent_steps','agent_calls','agent_timeout',
    'agent_tokens','agent_page_limit','agent_page_depth','agent_parallel','agent_tool_timeout',
    'agent_request_timeout','agent_auto_continue','agent_budget_behavior','notifications_enabled',
    'notifications_animate','notifications_reply','notifications_investigation','notifications_errors','reduced_motion'))
ROUTES = frozenset(('chat','search','history','canvas','settings'))
TOOL_NAMES={'web_search':'Веб-поиск','web_read':'Чтение страниц','username_maigret':'Maigret',
    'username_blackbird':'Blackbird','username_social_analyzer':'Social Analyzer','username_snoop':'Snoop',
    'email_holehe':'Holehe','phone_metadata':'PhoneInfoga','blockchain_gansar':'Gansar',
    'web_archive':'Веб-архив','telegram_public':'Telegram','vk_public':'VK','instagram_public':'Instagram',
    'domain_lookup':'DNS и регистрация домена','ip_lookup':'Сети и ASN','evidence_get':'Сохранённое свидетельство'}
MAX_PAYLOAD = 2_100_000


def source_view(record, limits=()):
    value = redact(record)
    details, origin = value.get('details') or {}, value.get('provenance') or {}
    acquisition = origin.get('acquisition')
    kind = 'page' if details.get('reading_method')=='direct_http' else 'snippet' if acquisition=='search_index' or value.get('status')=='indexed' else 'adapter'
    notes = list(limits) + list(details.get('limitations') or [])
    if any('JavaScript' in str(note) and 'не' in str(note) for note in notes):
        details={**details,'javascript_shell':True}
    if details.get('javascript_shell'):
        notes.append('JavaScript-содержимое не исполнено; доступны только HTTP-текст и метаданные.')
    return {'evidence_id':value.get('evidence_id',value.get('id','')), 'title':value.get('title') or value.get('platform') or 'Источник',
        'url':value.get('url',''), 'domain':urlsplit(value.get('url','')).hostname or value.get('platform',''),
        'excerpt':str(details.get('content_excerpt') or value.get('description') or '')[:2000],
        'status':'partial' if details.get('javascript_shell') else value.get('status','unconfirmed'), 'kind':kind,
        'obtained_at':origin.get('obtained_at') or details.get('retrieved_at') or value.get('date'),
        'limitations':list(dict.fromkeys(str(v)[:500] for v in notes))[:8], 'details':details,
        'verification':value.get('verification','unconfirmed'), 'provenance':origin}


class DesktopBridge(QObject):
    response = Signal(str, str)
    stateChanged = Signal(str)

    def __init__(self, host, surface='main'):
        super().__init__(host)
        self.host, self.surface = host, surface
        self.route = 'chat' if surface=='main' else 'launcher'
        self._last = {}
        self._last_messages = []
        self._tools = []
        self._manual_job = None
        self._manual_registry = None
        self._manual_activity = []
        self._source_cache = {}
        self._raw_sources = {}
        self._sources_fingerprint = None
        self._sources_view = []
        self._history_cache = []
        self._history_time = 0
        self._dock_rect = QRect()
        self.ui_ready = False
        self._key = resolve_deepseek_key()
        self._flush = QTimer(self)
        self._flush.setSingleShot(True)
        self._flush.setInterval(80)
        self._flush.timeout.connect(self.publish)
        self._poll = QTimer(self)
        self._poll.setInterval(650)
        self._poll.timeout.connect(self.mark_dirty)
        self._poll.start()
        if surface=='main':
            chat = host.chat_widget
            chat.state_changed.connect(self.mark_dirty)
            chat.busy_changed.connect(self.mark_dirty)
            chat.turn_completed.connect(self.mark_dirty)
            host.ai_state.changed.connect(self._connection_changed)
            host.result_model.dataChanged.connect(self.mark_dirty)
            host.result_model.rowsInserted.connect(self.mark_dirty)
            host.result_model.modelReset.connect(self.mark_dirty)

    def _connection_changed(self, *_):
        self._key = resolve_deepseek_key()
        self.mark_dirty()

    def mark_dirty(self, *_):
        if not self._flush.isActive(): self._flush.start()

    def _json(self, value):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)
        if self._key: raw = raw.replace(self._key, '[скрытый ключ]')
        return raw

    def _history(self):
        chat = self.host.chat_widget
        if chat._library and time.monotonic()-self._history_time>2:
            self._history_cache = chat._library.list()
            self._history_time = time.monotonic()
        return self._history_cache

    def _sources(self):
        chat = self.host.chat_widget
        fingerprint=(chat.conversation_id,chat._last_investigation.get('id'),
            len(chat._last_investigation.get('evidence',[])),len(chat._last_investigation.get('executions',[])),
            tuple(row.get('investigation_id') for row in chat.messages if row.get('investigation_id')),
            tuple(id(value) for value in self.host.result_model.records.values()))
        if fingerprint==self._sources_fingerprint: return self._sources_view
        self._raw_sources={}
        sources, seen = [], set()
        investigations = [chat._last_investigation] if chat._last_investigation else []
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
        for index in range(min(500, self.host.result_model.rowCount())):
            record = self.host.result_model.record(index)
            identifier = record.get('details',{}).get('evidence_id') or record.get('evidence_id')
            if not identifier:
                record = normalize_evidence(record, 'manual_search', self.host.text.text())
                identifier = record['evidence_id']
            if identifier not in seen:
                seen.add(identifier)
                self._raw_sources[identifier] = record
                sources.append(source_view(record))
        self._sources_fingerprint=fingerprint
        self._sources_view=sources
        return sources

    def _activity(self):
        result = {}
        for index, event in enumerate(self.host.chat_widget._activity_log):
            tool = event.get('tool')
            if not tool: continue
            key = event.get('tool_call_id') or tool
            state = 'running' if event['type']=='tool_start' else event.get('status','completed')
            result[key] = {'id':str(key),'tool':TOOL_NAMES.get(tool,tool),'status':state,'summary':event.get('message','')}
        return list(result.values())[-30:] + self._manual_activity

    def snapshot(self):
        settings = self.host.settings
        values = {key:getattr(settings,key) for key in SETTINGS_FIELDS if hasattr(settings,key)}
        base = {'product':PRODUCT_NAME,'version':VERSION,'surface':self.surface,'route':self.route,
            'settings':values,'window':{'maximized':self.host.isMaximized(),'fullscreen':self.host.isFullScreen()}}
        if self.surface=='launcher':
            state = getattr(self.host,'process_state','running' if self.host.running else 'ready')
            base.update(launcher={'state':state,'running':self.host.running,'size':settings.size,'fps':settings.fps,
                'cursorReaction':settings.cursor_reaction,'error':self.host.status.text() if state=='error' else ''})
            return base
        chat = self.host.chat_widget
        ai = self.host.ai_state.committed_snapshot()
        sources = self._sources()
        by_id = {s['evidence_id']:s for s in sources}
        messages = []
        for index, row in enumerate(chat.messages):
            value = dict(row)
            value['streaming'] = chat.busy and index==chat._stream_index
            value['sources'] = [by_id[i] for i in row.get('evidence_ids',[]) if i in by_id]
            messages.append(value)
        canvas = self.host.canvas
        usage = chat._usage_ledger
        conversation_usage = usage.snapshot(conversation_id=chat.conversation_id) if usage else {}
        investigation_usage = usage.snapshot(investigation_id=chat._last_investigation.get('id')) if usage and chat._last_investigation.get('id') else {}
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
                'canSend':chat.ai_state.can_send,'error':ai.get('last_error',''),'contextLimit':None,'balance':None,
                'balanceMessage':'Провайдер не предоставляет данные об остатке'},
            conversation_id=chat.conversation_id,messages=messages,busy=chat.busy,activity=self._activity(),evidence=sources,
            message_focus=getattr(self,'message_focus',None),
            search={'query':self.host.text.text(),'kind':self.host.direction.currentData(),'busy':self.host._busy or self._manual_job is not None,
                'phase':self.host.phase,'count':self.host.result_model.rowCount(),
                'checked':int((re.search(r'\d+',self.host.checked_label.text()) or ['0'])[0]),
                'checkedLabel':self.host.checked_label.text(),
                'status':self.host.status.text() if self.host.phase!='idle' else '',
                'error':self.host.status.text() if self.host.phase in ('error','failed','completed_with_errors') else '',
                'choices':[{'label':name,'value':kind} for name,kind in self.host._resolution().choices], 'results':sources},
            tools=self._tools or [{'id':spec.name,'name':TOOL_NAMES.get(spec.name,spec.name),'description':spec.description,'inputTypes':[spec.kind],
                'available':False,'state':'unverified','reason':'Нажмите «Проверить готовность» для фактической проверки.',
                'sensitive':spec.requires_approval} for spec in _SPECS],
            investigation=investigation,usage={'request':conversation_usage.get('last_request'),
                'conversation':conversation_usage.get('totals'), 'investigation':investigation_usage.get('totals'),
                'balance':conversation_usage.get('provider_balance')}, history=self._history(),
            canvas={'id':canvas.document_id,'text':canvas.editor.toPlainText(),'title':canvas.title.text(),'dirty':canvas._dirty} if canvas else None,
            hermione={'state':self.host._last_activity or 'idle','visible':True})
        return base

    def publish(self, *, force=False):
        try: state = self.snapshot()
        except RuntimeError: return
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
        if not isinstance(identifier,str) or len(identifier)>100 or len(payload_json)>MAX_PAYLOAD:
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
        if action=='ui_ready':
            if payload.get('surface') != self.surface: raise ValueError('Некорректная поверхность.')
            if not self.ui_ready:
                self.ui_ready=True
                logging.getLogger('grangerpet.desktop').info('Desktop surface ready: %s',self.surface)
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
        if self.surface=='launcher': return self._launcher_action(action,payload)
        chat = self.host.chat_widget
        if action=='layout':
            dock = payload.get('dock',{})
            coordinates = [dock.get(key,0) for key in ('x','y','width','height')]
            if not all(type(v) in (int,float) and -10000<v<20000 for v in coordinates): raise ValueError('Некорректная геометрия.')
            self._dock_rect = QRect(*(round(v) for v in coordinates))
        elif action=='route':
            if payload.get('route') not in ROUTES: raise ValueError('Неизвестный раздел.')
            self.route = payload['route']
        elif action=='chat_send':
            text = payload.get('text')
            if not isinstance(text,str) or not text.strip() or len(text)>12000: raise ValueError('Сообщение: 1–12 000 символов.')
            if chat.busy: raise ValueError('Предыдущая задача ещё выполняется.')
            if not chat._ready: raise ValueError('Сначала подключите ИИ в настройках.')
            chat.input.setPlainText(text)
            chat.send_message()
            self.route='chat'
        elif action=='chat_stop': chat.cancel()
        elif action=='chat_new': chat.new_conversation(); self._history_time=0
        elif action=='chat_clear': chat.clear_history(); self._history_time=0
        elif action=='chat_regenerate': chat.regenerate(payload.get('message_id'))
        elif action=='history_load': chat.load_conversation(payload.get('id')); self.route='chat'; self._history_time=0
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
            self.host.text.setText(text); self.host.set_query_kind(kind); self.host.start_search(); self.route='search'
        elif action=='search_stop':
            if self._manual_job: self._manual_job.cancel(); self._manual_job.deleteLater(); self._manual_job=None
            for row in self._manual_activity:
                if row['status']=='running': row['status']='cancelled'
            self.host.search_state.emit('idle')
            self.host.cancel_search()
        elif action=='tools_refresh': self._refresh_tools()
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
        elif action=='settings_native':
            category = payload.get('category')
            if category not in ('ai','tools','auth'): raise ValueError('Неизвестная категория.')
            self.host.open_native_settings({'ai':'ИИ','tools':'Источники','auth':'Авторизация'}[category])
        else: raise ValueError('Неизвестное действие приложения.')
        self.host.user_activity.emit()
        return None

    def _save_settings(self, values):
        if not isinstance(values,dict) or set(values)-SETTINGS_FIELDS: raise ValueError('Недопустимые параметры настроек.')
        merged = asdict(self.host.settings)
        merged.update(values)
        settings = Settings.from_dict(merged)
        if self.host.store: self.host.store.save(settings)
        self.host.set_settings(settings)
        QApplication.instance().setProperty('reduced_motion',getattr(settings,'reduced_motion',False))
        self.host.settings_dialog.settings_saved.emit(settings)
        self._manual_registry = None

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
            self._manual_registry = ToolRegistry(self.host.settings,redactions=(self._key,))
        return self._manual_registry

    def _refresh_tools(self):
        if self._manual_job: raise ValueError('Дождитесь текущей проверки.')
        registry = self._registry()
        job = UiJob(lambda:registry.catalog(cancel_event=job.cancelled),self)
        self._manual_job = job
        def done(rows,error):
            self._manual_job=None
            if not error:
                self._tools=[{'id':r['name'],'name':TOOL_NAMES.get(r['name'],r['name']),'description':r['description'],
                    'inputTypes':[r['kind']],'available':r['available'],'state':r['state'],'reason':r['reason'],
                    'sensitive':r.get('requires_approval',False)} for r in rows]
            job.deleteLater(); self.mark_dirty()
        job.done.connect(done); job.start()

    def _run_tool(self,payload):
        if self._manual_job or self.host.chat_widget.busy or self.host._busy: raise ValueError('Сначала дождитесь или остановите текущую задачу.')
        spec = next((s for s in _SPECS if s.name==payload.get('tool')),None)
        query = payload.get('query')
        if not spec or not isinstance(query,str) or not 0<len(query)<=spec.max_length: raise ValueError('Некорректный инструмент или запрос.')
        limit = payload.get('limit',self.host.settings.request_limit)
        if type(limit) is not int or not 1<=limit<=20: raise ValueError('Число результатов: 1–20.')
        approved = not spec.requires_approval
        if not approved:
            approved = QMessageBox.question(self.host,PRODUCT_NAME,'Разрешить '+spec.name+'?\n\n'+spec.description,
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes
        if not approved: raise ValueError('Действие не подтверждено.')
        registry = self._registry(); registry.seed_urls_from_user(query)
        self._manual_activity=[{'id':spec.name,'tool':spec.name,'status':'running','summary':'Запрос пользователя'}]
        self.host.search_state.emit('working')
        job = UiJob(lambda:registry.execute(spec.name,{spec.argument:query,'limit':limit},cancel_event=job.cancelled,
            deadline=time.monotonic()+self.host.settings.search_timeout,approved=approved),self)
        self._manual_job=job
        def done(outcome,error):
            self._manual_job=None
            status = outcome.get('status','error') if isinstance(outcome,dict) else 'error'
            self._manual_activity[0]['status']=status
            self._manual_activity[0]['summary']=error or str((outcome or {}).get('error') or '')
            if isinstance(outcome,dict):
                self.host._agent_evidence(outcome.get('results',[]))
                for row in outcome.get('results',[]): self._raw_sources[row['evidence_id']]=row
            self.host.search_state.emit('happy' if not error and status in ('complete','completed','partial','empty') else 'error')
            job.deleteLater(); self.mark_dirty()
        job.done.connect(done); job.start()

    def shutdown(self):
        self._poll.stop(); self._flush.stop()
        if self._manual_job:
            self._manual_job.cancel(); self._manual_job.deleteLater(); self._manual_job=None
