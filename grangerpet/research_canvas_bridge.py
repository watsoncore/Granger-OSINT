"""Qt adapter for analyst canvases; all storage/projection work stays off the UI thread."""
from copy import deepcopy
from collections import OrderedDict
import json
import uuid
import os
import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox
from .research_canvas import CanvasStore, new_document, apply, merge_evidence, position_added_profiles, record_canvas_event, validate, TYPES, MAX_BYTES, CanvasError, CanvasConflict
from .async_reply import DeferredReply
from .ui_jobs import UiJob


class ResearchCanvasBridge:
    def __init__(self,bridge):
        self.bridge=bridge
        self.store=CanvasStore(bridge.host.chat_widget._journal)
        self.document=None;self.preview=None;self.previews={};self.job=None;self.media_job=None;self.undo=[];self.redo=[]
        self.insertions={}
        self.result_job=None
        self.state={'state':'idle','choices':[],'types':list(TYPES)}
        self._commit_replies={}
        self._active_receipt=None
        self._recovery_reply=None
        self.media_previews=OrderedDict()

    def source_record(self,identifier):
        for row in (self.document or {}).get('evidence',[]):
            if row.get('evidence_id')==identifier:return row
        for row in self.previews.get((self.document or {}).get('id'),{}).get('records',[]):
            if row.get('evidence_id')==identifier:return row
        return None

    def publish(self,value):
        self.state=value;self.bridge.mark_dirty()

    def render(self,doc=None):
        from .desktop_bridge import source_view
        doc=doc or self.document
        state={'state':'ready','choices':self.store.list(),'types':list(dict.fromkeys((*TYPES,*(doc or {}).get('custom_types',{})))),'can_undo':bool(self.undo),'can_redo':bool(self.redo)}
        from .entity_forms import organization_catalog
        state['company_jurisdictions']=organization_catalog()
        if doc:
            if doc['id'] in self.insertions:state['insertion']=deepcopy(self.insertions[doc['id']])
            visible=deepcopy(doc)
            if self.media_previews:
                for node in visible['entities']:
                    reference=node['attributes'].get('media') or {}
                    cached=self.media_previews.get((doc['id'],node['id'],reference.get('id')))
                    if cached:node['attributes']['media']=deepcopy(cached)
            visible['evidence']=[source_view(row,compact=True) for row in doc['evidence']]
            executions=visible.pop('executions',[])
            visible['execution_summary']=[
                {key:entry[key] for key in ('tool','status','limitations') if key in entry}
                for entry in (executions[-30:] if isinstance(executions,list) else []) if isinstance(entry,dict)
            ]
            state['document']=visible
        preview=self.previews.get(doc['id']) if doc else None
        if preview:
            state['preview']={k:v for k,v in preview.items() if k!='records'}
        return state

    def work(self,task,*,receipt=None):
        if self.job:raise CanvasError('Дождитесь сохранения графа.',code='canvas_busy')
        self.publish({**self.state,'busy':True,'error':''})
        deferred=DeferredReply() if receipt else None
        def execute():
            self._active_receipt=receipt
            try:return task()
            except CanvasConflict as error:return {'_canvas_conflict':{'error':str(error),'code':error.code,'revision':error.revision}}
            except CanvasError as error:return {'_canvas_conflict':{'error':str(error),'code':'canvas_validation_failed'}}
            finally:self._active_receipt=None
        job=UiJob(execute,self.bridge);self.job=job
        def done(value,error):
            self.job=None
            failure=value.get('_canvas_conflict') if isinstance(value,dict) else None
            if error:failure={'error':error,'code':'canvas_save_failed'}
            if not self.bridge._closed:
                if failure:self.publish({**self.state,'busy':False,'error':failure['error'],'conflict':failure if failure.get('code')==CanvasConflict.code else None})
                else:self.publish(value)
            if deferred:
                document=self.document or {}
                deferred.resolve({'mutation_id':receipt['mutation_id'],'canvas_id':document.get('id'),'revision':document.get('revision',0)},failure)
            job.deleteLater()
        job.done.connect(done);job.start()
        return deferred if deferred else {'pending':True}

    def _commit(self,value,*,history=True):
        old=self.document
        value=self._with_receipt(value,previous=old if old and old['id']==value['id'] else None)
        saved=self.store.save(value,old['revision'] if old and old['id']==value['id'] else 0)
        if history and old and old['id']==saved['id']:
            self.undo=(self.undo+[old['revision']])[-40:];self.redo=[]
        self.document=saved
        return self.render()

    def _with_receipt(self,value,*,previous=None):
        value=deepcopy(value)
        receipts=list((previous or {}).get('mutation_receipts',[]))+list(value.get('mutation_receipts',[]))
        active=self._active_receipt
        if active:receipts.append(active['mutation_id'])
        value['mutation_receipts']=list(dict.fromkeys(receipts))[-128:]
        return value

    def begin_tool(self,tool,canvas_id,node_id,*,operation=''):
        self.previews.pop(canvas_id,None)
        self.accept_tool({'tool':tool,'operation':operation,'status':'running','results':[]},canvas_id,node_id,streaming=True)

    def accept_tool(self,outcome,canvas_id,node_id,*,notify=True,streaming=False):
        if not isinstance(outcome,dict):return
        from .desktop_bridge import source_view
        previous=self.previews.get(canvas_id)
        same=bool(previous and previous.get('node_id')==node_id and previous.get('tool')==outcome.get('tool') and previous.get('running'))
        records={row['evidence_id']:row for row in (previous['records'] if same else [])}
        compact={row['evidence_id']:row for row in (previous['results'] if same else [])}
        for incoming in outcome.get('results',[]):
            identifier=incoming['evidence_id']
            if identifier in compact and records[identifier]==incoming:
                continue
            record=deepcopy(incoming)
            records[identifier]=record
            compact[identifier]=source_view(record,compact=True)
        preview={'token':previous['token'] if same else uuid.uuid4().hex,'canvas_id':canvas_id,'node_id':node_id,
            'operation':outcome.get('operation') or (previous.get('operation','') if same else ''),
            'tool':outcome.get('tool'),'status':outcome.get('status'),'limitations':outcome.get('limitations',[]),
            'running':streaming,'error':str(outcome.get('error') or ''),'error_code':outcome.get('error_code'),
            'from_saved_data':outcome.get('from_saved_data') is True,
            'request_counts':{k:outcome.get('source_diagnostics',{}).get(k) for k in ('providers_attempted','http_requests','http_statuses')}
                if isinstance(outcome.get('source_diagnostics'),dict) else {},
            'records':list(records.values()),'results':list(compact.values())}
        self.previews[canvas_id]=preview
        while len(self.previews)>8:self.previews.pop(next(iter(self.previews)))
        if self.document and self.document['id']==canvas_id:
            self.preview=preview
            self.state={**self.state,'preview':{k:v for k,v in preview.items() if k!='records'}}
        if notify:self.bridge.mark_dirty()

    def action(self,action,payload):
        op=action.removeprefix('research_canvas_');bridge=self.bridge
        if op in ('open','new','import'):bridge.host.chat_widget._graph_focus={}
        if op=='media_prepare':
            from .canvas_media import prepare_attachment
            return prepare_attachment(bridge,payload)
        if op in ('queue_recovery','queue_read','queue_clear'):
            from .canvas_pending import PendingCanvasStore
            pending=PendingCanvasStore(self.store)
            if op=='queue_clear':
                if set(payload)!={'draft_id'}:raise CanvasError('Передайте идентификатор сохранённой очереди.')
                pending.clear(payload['draft_id']);return {'cleared':True}
            if payload:raise CanvasError('Восстановление очереди не принимает пути или команды.')
            if self._recovery_reply:return self._recovery_reply
            deferred=DeferredReply();self._recovery_reply=deferred
            job=UiJob(pending.recovery,bridge)
            def recovered(value,error):
                self._recovery_reply=None
                deferred.resolve(value,{'code':'canvas_queue_recovery_failed','error':'Сохранённая очередь не прочитана. Исходные файлы оставлены без изменений.'} if error else None)
                job.deleteLater()
            job.done.connect(recovered);job.start()
            return deferred
        receipt=None
        if payload.get('await_commit') is True:
            mutation_id=payload.get('mutation_id')
            if not isinstance(mutation_id,str) or not re.fullmatch(r'[a-f0-9]{32}',mutation_id):raise CanvasError('Некорректный идентификатор сохранения.')
            import hashlib
            signature=hashlib.sha256(json.dumps({'op':op,**{k:v for k,v in payload.items() if k not in ('revision','await_commit','mutation_id')}},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            previous=self._commit_replies.get(mutation_id)
            if previous:
                if previous[0]!=signature:raise CanvasError('Идентификатор сохранения уже относится к другому действию.')
                return previous[1]
            receipt={'mutation_id':mutation_id,'signature':signature,'intent':{
                'op':op,'payload':{k:v for k,v in payload.items() if k not in ('id','revision','await_commit','mutation_id')},
                'token':mutation_id,**({'target':payload['id']} if payload.get('id') else {})}}
            if op=='open' and payload.get('id'):receipt['intent']['payload']['id']=payload['id']
        def work(task):
            result=self.work(task,receipt=receipt)
            if receipt:
                self._commit_replies[receipt['mutation_id']]=(receipt['signature'],result)
                while len(self._commit_replies)>128:self._commit_replies.pop(next(iter(self._commit_replies)))
            return result
        if op=='metrics':
            if not (os.environ.get('GRANGERPET_INTERACTION_TRACE') and re.fullmatch(r'[a-f0-9]{32}',os.environ.get('GRANGERPET_QA_NAMESPACE','')) and re.fullmatch(r'GrangerPet/QA/[a-zA-Z0-9_-]{8,80}',os.environ.get('GRANGERPET_QA_VAULT',''))):
                raise CanvasError('Измерения доступны только в изолированном QA.')
            surface=bridge.host.desktop_surface
            generation=getattr(self,'_metric_generation',0)+1;self._metric_generation=generation
            script="""JSON.stringify((()=>{let editor=document.querySelector('.research-editor'),canvas=editor?.querySelector('.investigation-graph-canvas'),r=canvas?.getBoundingClientRect();return {editor:!!editor,canvas_id:editor?.dataset.canvasId,revision:editor?.dataset.revision,queue_pending:window.grangerCanvasQueue?.snapshot?.()?.intents?.length||0,canvas:canvas?{...canvas.dataset,x:r.x,y:r.y,width:r.width,height:r.height,dpr:devicePixelRatio}:null,wallpaper:(()=>{let layer=editor?.querySelector('.wallpaper-layer[data-wallpaper=image]'),art=layer?.querySelector('.wallpaper-art');if(!layer||!art)return null;let b=layer.getBoundingClientRect(),style=getComputedStyle(art);return {...layer.dataset,width:b.width,height:b.height,fit:style.backgroundSize,position:style.backgroundPosition,transform:style.transform,dpr:devicePixelRatio}})()}})())"""
            def result(value):
                if bridge._closed:return
                try:data=json.loads(value)
                except (ValueError,TypeError):data={'error':'metrics_unavailable'}
                self.publish({**self.state,'metrics':{**data,'generation':generation,
                    'publication_visible':bridge._publication_enabled,'surface_visible':surface.isVisible(),
                    'javascript_diagnostic_count':len(getattr(surface.page(),'diagnostics',[]))}})
            surface.page().runJavaScript(script,result)
            return {'generation':generation}
        if op=='media':
            if not self.document or payload.get('id')!=self.document['id']:return None
            return self._media(payload.get('entity_id'))
        if op=='capability':
            if not self.document or payload.get('id')!=self.document['id']:raise CanvasError('Откройте нужное расследование.')
            identifier=payload.get('entity_id')
            identifier=self.document['view'].get('instances',{}).get(identifier,{}).get('entity_id',identifier)
            node=next((n for n in self.document['entities'] if n['id']==identifier),None)
            if not node:raise CanvasError('Выбранный объект отсутствует.')
            from .canvas_capabilities import capabilities
            return capabilities(node,payload.get('chain','auto'),getattr(bridge,'_tools',None))
        if op in ('result_image','result_export'):
            return self._result_action(op,payload)
        if op=='screenshot':
            return self._screenshot(payload)
        if self.job:raise CanvasError('Дождитесь окончания сохранения графа.',code='canvas_busy')
        if op in ('tool','analyze','attach','export') and (not self.document or payload.get('id')!=self.document['id'] or payload.get('revision')!=self.document['revision']):
            raise CanvasConflict('Граф или его версия изменились. Загрузите актуальную версию перед повторением.',revision=(self.document or {}).get('revision'))
        if op=='tool':
            if not self.document:raise CanvasError('Откройте расследование.')
            selected_id=payload.get('entity_id')
            selected_id=self.document['view'].get('instances',{}).get(selected_id,{}).get('entity_id',selected_id)
            node=next((n for n in self.document['entities'] if n['id']==selected_id),None)
            if not node:raise CanvasError('Выберите узел текущего расследования.')
            from .canvas_capabilities import execution_payload
            bridge._run_tool(execution_payload(node,payload),canvas_target=(self.document['id'],node['id']))
            return {'pending':True}
        if op=='analyze':
            if not self.document:raise CanvasError('Откройте расследование.')
            ids={self.document['view'].get('instances',{}).get(i,{}).get('entity_id',i) for i in payload.get('ids',[])}
            selected=[n for n in self.document['entities'] if n['id'] in ids][:2]
            if not selected:raise CanvasError('Выберите один или два узла.')
            intent=payload.get('intent','explain')
            prompts={'explain':'Объясни происхождение выбранных объектов по сохранённым данным. Новые сетевые запросы не нужны.',
                'investigate':'Исследуй выбранный публичный объект доступными инструментами, сохраняя исходную цель.',
                'compare':'Сравни два выбранных объекта. Не угадывай общий владелец.',
                'hypothesis':'Проверь указанную аналитическую гипотезу и отдели её от наблюдений.',
                'next':'Предложи следующий шаг без запуска новых сетевых операций.',
                'report':'Сформируй краткий отчёт только по сохранённым данным.',
                'connections':'Найди разрешённые публичные связи выбранного объекта.'}
            if intent not in prompts:raise CanvasError('Неизвестное действие ИИ.')
            from .graph_context import selection_context
            doc=self.document
            context=selection_context({n['id']:n for n in doc['entities']},{e['id']:e for e in doc['relations']},
                {n['id'] for n in selected},None,doc['evidence'])
            context['analyst_annotations']={n['id']:{'claim_kind':'analyst_assertion','text':str(doc['annotations'].get(n['id'],{}).get('markdown') or n['attributes'].get('markdown') or '')[:1000]} for n in selected}
            selected_ids={n['id'] for n in selected}
            while len(json.dumps(context,ensure_ascii=False))>8500:
                if context['relations']:context['relations'].pop()
                elif context['sources']:context['sources'].pop()
                elif len(context['entities'])>len(selected_ids):context['entities'].pop()
                else:
                    for item in context['entities']:item['attributes']={k:v for k,v in item['attributes'].items() if k in ('address','url','chain','attachment_id','identity_verified','owner_verified')}
                    break
            scope='Не используй инструменты. ' if intent in ('explain','compare','next','report') else ''
            target=selected[0];value=str(target['attributes'].get('address') or target['attributes'].get('url') or target['attributes'].get('value') or target['label'])
            content=scope+prompts[intent]+'\nТекущий выбранный объект: '+value[:300]+'\nРасследование: '+doc['title']
            chat=bridge.host.chat_widget
            if chat.busy:raise CanvasError('Предыдущая задача ещё выполняется.')
            entity_target=None
            if target['type']=='organization':
                entity_target={'entity_type':'organization','identifier':target['attributes'].get('identifier') or value,
                    'properties':target['attributes']}
            chat._submit_text(content,context_scope='canvas:'+doc['id'],evidence_context=context,entity_target=entity_target)
            bridge.route='chat'
            bridge.mark_dirty()
            return {'pending':chat.busy}
        if op in ('export','import','attach'):
            if op=='export':
                if not self.document:raise CanvasError('Откройте расследование.')
                if QMessageBox.question(bridge.host,'Экспорт расследования','Экспортировать сведения, заметки и оригиналы изображений? Экспорт открытый: храните его как обычные конфиденциальные файлы. Пакет ZIP содержит также JSON Canvas для других редакторов; отдельный .canvas создаёт соседнюю папку оригиналов.')!=QMessageBox.StandardButton.Yes:return None
                filename,_=QFileDialog.getSaveFileName(bridge.host,'Экспорт расследования','investigation.granger.zip','Переносимое расследование (*.granger.zip);;JSON Canvas и оригиналы (*.canvas);;Granger JSON без оригиналов (*.granger.json)')
                if not filename:return None
                data=deepcopy(self.document)
                return work(lambda:self._export(filename,data))
            if op=='import':
                filename,_=QFileDialog.getOpenFileName(bridge.host,'Импорт расследования','','Расследование (*.granger.zip *.canvas *.json)')
                if not filename:return None
                return work(lambda:self._import(filename))
            attachment=payload.get('attachment_id')
            if attachment:
                store=bridge._images()
                return work(lambda:self._image(store.get(attachment),payload))
            filename,_=QFileDialog.getOpenFileName(bridge.host,'Изображение на граф','','Изображения (*.png *.jpg *.jpeg *.webp)')
            if not filename:return None
            def image_task():
                path=Path(filename)
                if path.stat().st_size>20_000_000:raise CanvasError('Изображение превышает 20 MB.')
                return self._image(bridge._images().import_bytes(path.read_bytes(),path.name))
            return work(image_task)
        expected=payload.get('revision')
        if op not in ('list','open','new'):
            if not self.document or payload.get('id')!=self.document['id'] or expected!=self.document['revision']:
                raise CanvasConflict('Версия графа изменилась. Действие сохранено в очереди; загрузите актуальную версию перед повторением.',revision=(self.document or {}).get('revision'))
        def task():
            if op=='list':return self.render()
            if op=='new':
                self.undo=[];self.redo=[];self.preview=None
                value=new_document(payload.get('title','Новое расследование'),payload.get('description',''))
                record_canvas_event(value,'created')
                self.document=self.store.save(self._with_receipt(value),0)
                return self.render()
            if op=='open':
                self.document=self.store.load(payload.get('id'));self.undo=[];self.redo=[];self.preview=self.previews.get(self.document['id'])
                return self.render()
            if op=='edit':
                operation,args=payload.get('operation'),payload.get('arguments',{})
                value=apply(self.document,operation,args)
                kind={'node':'node','edge':'link','edge_edit':'link','group':'group','rename':'rename'}.get(operation)
                if kind:
                    key='relations' if kind=='link' else 'entities'
                    old={item['id'] for item in self.document[key]}
                    added=[item['id'] for item in value[key] if item['id'] not in old]
                    if kind=='link' and not added and args.get('relation_id'):added=[args['relation_id']]
                    record_canvas_event(value,kind,added,len(added))
                return self._commit(value)
            if op in ('undo','redo'):
                stack=self.undo if op=='undo' else self.redo
                if not stack:raise CanvasError('Нет доступной версии для отмены.')
                revision=stack[-1];old=self.store._read(self.store._folder(self.document['id'])/f'r{revision:010d}.dpapi')
                previous=self.document['revision'];self._commit(old,history=False);stack.pop()
                (self.redo if op=='undo' else self.undo).append(previous)
                return self.render()
            if op=='duplicate':
                value=deepcopy(self.document);value.update(id=uuid.uuid4().hex,revision=0,title=value['title']+' · копия')
                self.document=None;self.undo=[];self.redo=[]
                return self._commit(value)
            if op=='delete':
                if payload.get('confirmed') is not True:raise CanvasError('Удаление требует подтверждения.')
                value=deepcopy(self.document);value['deleted']=True;self._commit(value)
                self.document=None;self.preview=None;self.undo=[];self.redo=[]
                return self.render()
            if op=='insert':
                if not self.preview or self.preview['token']!=payload.get('token') or self.preview['canvas_id']!=self.document['id']:
                    raise CanvasError('Результат относится к другому графу или устарел.')
                selected=payload.get('evidence_ids')
                available={r['evidence_id'] for r in self.preview['records']}
                if not isinstance(selected,list) or not set(selected)<=available:raise CanvasError('Выберите полученные доказательства.')
                value=deepcopy(self.document)
                old_nodes={node['id'] for node in value['entities']}
                old_edges={edge['id'] for edge in value['relations']}
                old_evidence={row['evidence_id'] for row in value['evidence']}
                added=merge_evidence(value,self.preview['records'],selected)
                owner=self.preview.get('node_id')
                target=next((node for node in value['entities'] if node['id']==owner),None)
                if target and target['type']=='blockchain_address' and self.preview['tool']=='blockchain_gansar':
                    value['view'].setdefault('ui',{}).update(graph_mode='assets' if self.preview.get('operation') in ('nft','assets') else 'wallet',crypto_root_id=owner)
                    if not self.document['evidence'] and not value['view'].get('manual_position_ids'):
                        value['view']['ui']['initial_layout']='wallet'
                if target and target['type'] in ('username','nickname'):
                    value['view'].setdefault('ui',{}).update(graph_mode='socmint',username_root_id=owner)
                    if not self.document['evidence'] and not value['view'].get('manual_position_ids'):
                        value['view']['ui']['initial_layout']='identity'
                    else:
                        position_added_profiles(value,owner,added)
                    # These accounts were returned for this identifier; this
                    # relation never asserts a shared person or account owner.
                    import hashlib
                    existing={edge['id'] for edge in value['relations']}
                    for node in value['entities']:
                        proof=[eid for eid in node['evidence_ids'] if eid in selected]
                        if node['type']!='public_profile' or not proof:continue
                        identifier='rel_'+hashlib.sha256((owner+'|'+node['id']+'|returned_for_query').encode()).hexdigest()[:24]
                        if identifier in existing:continue
                        value['relations'].append({'id':identifier,'from_id':owner,'to_id':node['id'],
                            'relation_type':'returned_for_query','direction':'directed','origin':'tool',
                            'verification_status':'source_reported','claim_kind':'lookup_result',
                            'evidence_ids':proof,'source_urls':[],'provenance':[],
                            'attributes':{'tool':self.preview['tool'],'identity_verified':False,'owner_verified':False}})
                if target and target['type']=='organization':
                    import hashlib
                    existing={edge['id'] for edge in value['relations']}
                    for node in value['entities']:
                        proof=[eid for eid in node['evidence_ids'] if eid in selected]
                        if node['id']==owner or node['type']!='organization' or not proof:continue
                        identifier='rel_'+hashlib.sha256((owner+'|'+node['id']+'|candidate_for_company_query').encode()).hexdigest()[:24]
                        if identifier in existing:continue
                        value['relations'].append({'id':identifier,'from_id':owner,'to_id':node['id'],
                            'relation_type':'candidate_for_company_query','direction':'directed','origin':'tool',
                            'verification_status':'unverified','claim_kind':'lookup_candidate','evidence_ids':proof,
                            'source_urls':[],'provenance':[],'attributes':{'identity_match_verified':False}})
                if target and target['type'] in ('public_profile','github_profile','social_profile') and self.preview['tool']=='github_profile':
                    position_added_profiles(value,owner,added,kinds=('repository','organization','website','public_post'))
                value['executions'].append({k:self.preview.get(k) for k in ('tool','status','limitations')})
                record_canvas_event(value,'findings',added or ([owner] if owner else []),len(set(selected)),self.preview['tool'])
                result=self._commit(value)
                projected={eid for node in value['entities'] for eid in node['evidence_ids']}
                projected.update(eid for edge in value['relations'] for eid in edge['evidence_ids'])
                summary={'canvas_id':value['id'],'preview_token':self.preview['token'],
                    'insertion_id':uuid.uuid4().hex,
                    'added_node_ids':added,'added_nodes':len(set(added)-old_nodes),
                    'added_relations':len({edge['id'] for edge in value['relations']}-old_edges),
                    'selected_records':len(set(selected)),
                    'existing_records':len(set(selected)&old_evidence),
                    'unprojected_records':len(set(selected)-projected),
                    'limitations':['Некоторые сохранённые наблюдения не имеют отдельного графического объекта.'] if set(selected)-projected else []}
                self.insertions[value['id']]=summary
                while len(self.insertions)>8:self.insertions.pop(next(iter(self.insertions)))
                result['insertion']=summary
                return result
            if op=='from_search':
                identifier=payload.get('investigation_id') or bridge._workspace.active_id
                snapshot=bridge._workspace.load(identifier,bridge.host.chat_widget._last_investigation)
                records=snapshot.get('evidence',[])
                # work() publishes its result on the GUI thread; never start a Qt
                # timer here in the storage/projection worker.
                self.accept_tool({'results':records,'tool':'saved_investigation','status':snapshot.get('status'),'from_saved_data':True,
                    'source_diagnostics':{'providers_attempted':0,'http_requests':0},'limitations':['Сохранённые наблюдения; свежие запросы не выполнялись.']},self.document['id'],'',notify=False)
                return self.render()
            raise CanvasError('Неизвестное действие расследования.')
        return work(task)

    def _result_action(self,op,payload):
        if self.result_job:
            raise CanvasError('Дождитесь обработки предыдущей находки.')
        preview=self.previews.get((self.document or {}).get('id'))
        if not preview or payload.get('token')!=preview['token'] or payload.get('id')!=preview['canvas_id']:
            raise CanvasError('Находки относятся к другому расследованию.')
        if op=='result_image':
            identifier=payload.get('evidence_id')
            if set(payload)!={'token','id','evidence_id'} or not isinstance(identifier,str):
                raise CanvasError('Укажите найденное наблюдение.')
            from .public_media import MediaStore, media_reference
            from .agent_evidence import current_observation
            row=next((item for item in preview['records'] if item['evidence_id']==identifier),None)
            reference=media_reference(current_observation(row)) if row else None
            if not reference:
                return None

            def task():
                import asyncio
                try:
                    image=asyncio.run(MediaStore().fetch(reference,cancel_event=job.cancelled))
                    return {'preview':image.get('thumbnail','')}
                except Exception:
                    return None
        else:
            ids=payload.get('evidence_ids')
            if (set(payload)!={'token','id','evidence_ids'} or not isinstance(ids,list) or not 0<len(ids)<=5000
                    or not all(isinstance(item,str) for item in ids)):
                raise CanvasError('Выберите наблюдения для экспорта.')
            chosen=set(ids)
            rows=[row for row in preview['results'] if row['evidence_id'] in chosen]
            if len(rows)!=len(chosen):
                raise CanvasError('Одна из находок больше недоступна.')
            filename,_=QFileDialog.getSaveFileName(self.bridge.host,'Экспортировать находки','findings.csv','CSV (*.csv)')
            if not filename:
                return None
            path=Path(filename)
            if path.suffix.lower()!='.csv':
                path=path.with_suffix('.csv')

            def task():
                import csv
                import io
                from .portable_vault import atomic_write
                stream=io.StringIO(newline='')
                writer=csv.writer(stream)
                writer.writerow(('Название','Публичный URL','Источник','Статус','Время получения'))
                for row in rows:
                    fields=[str(row.get(key) or '') for key in ('title','url','domain','status','obtained_at')]
                    writer.writerow("'" + value if value.lstrip()[:1] in ('=','+','-','@') else value for value in fields)
                atomic_write(path,stream.getvalue().encode('utf-8-sig'))
                return {'exported':len(rows)}
        reply=DeferredReply()

        def safe_task():
            try:
                return task(),False
            except OSError:
                return None,True

        job=UiJob(safe_task,self.bridge);self.result_job=job

        def done(value,error):
            self.result_job=None
            result,failed=value or (None,True)
            reply.resolve(result,{'code':'result_export_failed','error':'Не удалось сохранить CSV.'} if failed else None)
            job.deleteLater()

        job.done.connect(done);job.start();return reply

    def _screenshot(self,payload):
        if set(payload)!={'id'} or payload['id']!=(self.document or {}).get('id'):
            raise CanvasError('Откройте граф для снимка.')
        surface=self.bridge.host.desktop_surface
        if not surface.isVisible():
            raise CanvasError('Откройте видимый граф для снимка.')
        filename,_=QFileDialog.getSaveFileName(self.bridge.host,'Сохранить снимок графа','investigation.png','PNG (*.png)')
        if not filename:
            return None
        from PySide6.QtCore import QTimer
        from .appearance import decode_appearance
        from .portable_vault import atomic_write
        from PySide6.QtCore import QBuffer, QIODevice
        hide=decode_appearance(self.bridge.host.settings.workspace_appearance).get('hidePrivate') is not False
        page=surface.page()
        identifier=json.dumps(payload['id'])
        mask='true' if hide else 'false'
        reply=DeferredReply()
        script=f"""(()=>{{
          const editor=document.querySelector('.research-editor');
          if(editor?.dataset.canvasId!=={identifier}||!editor.getBoundingClientRect().width)return false;
          document.documentElement.dataset.maskWallpaper='{mask}';
          return !{mask}||[...editor.querySelectorAll('[data-wallpaper="image"]')].every(e=>getComputedStyle(e).visibility==='hidden');
        }})()"""

        def finish(result,error=None):
            if not self.bridge._closed:
                page.runJavaScript("delete document.documentElement.dataset.maskWallpaper")
                reply.resolve(result,error)

        def capture(ready):
            failure={'code':'canvas_screenshot_failed','error':'Не удалось безопасно сохранить снимок графа.'}
            if not ready:
                finish(None,failure);return

            def save():
                if self.bridge._closed:
                    return
                if not surface.isVisible() or payload['id']!=(self.document or {}).get('id'):
                    finish(None,failure);return
                try:
                    buffer=QBuffer()
                    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                    if not surface.grab().save(buffer,'PNG'):
                        finish(None,failure);return
                    path=Path(filename)
                    atomic_write(path if path.suffix.lower()=='.png' else path.with_suffix('.png'),bytes(buffer.data()))
                    finish({'saved':True,'private_wallpaper_hidden':hide})
                except OSError:
                    finish(None,failure)

            QTimer.singleShot(120,save)

        page.runJavaScript(script,capture)
        return reply

    def _export(self,filename,value):
        from .canvas_portable import export_package,export_canvas
        from .portable_vault import atomic_write
        value={key:item for key,item in value.items() if key!='activity'}
        path=Path(filename)
        if path.suffix.lower()=='.zip':export_package(path,value,self.bridge._images())
        elif path.suffix.lower()=='.canvas':export_canvas(path,value,self.bridge._images())
        else:atomic_write(path,json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
        return self.render()

    def _import(self,filename):
        from .canvas_portable import import_document
        value=import_document(filename,self.bridge._images())
        for node in value['entities']:
            node['attributes']['imported_unverified']=True
            node['attributes']['imported_claimed_verification']=node.get('verification_status','unverified')
            node['verification_status']='unverified'
        for relation in value['relations']:
            relation.setdefault('attributes',{})['imported_claimed_verification']=relation['verification_status']
            relation['verification_status']='unverified'
        value.update(id=uuid.uuid4().hex,revision=0)
        self.document=None;self.undo=[];self.redo=[]
        return self._commit(value)

    def _image(self,image,payload=None):
        if not self.document:raise CanvasError('Откройте расследование.')
        from .canvas_media import ATTACHMENT_FIELDS, linked_images
        from .research_canvas import add_node, point
        payload=payload or {}
        value=deepcopy(self.document)
        media={key:image[key] for key in ATTACHMENT_FIELDS if key in image}
        media.update(kind='local_attachment',state='ready')
        orientation=image.get('orientation')
        if orientation in (5,6,7,8):
            media['width'],media['height']=media['height'],media['width']
        source=payload.get('provenance')
        if isinstance(source,dict):
            from .agent_browser import public_url
            for key in ('source_url','final_url'):
                if source.get(key):
                    url=public_url(source[key])
                    if not url.startswith('https://'):raise CanvasError('Источнику изображения требуется HTTPS.')
                    media[key]=url
            evidence=source.get('evidence_id')
            if evidence and any(record['evidence_id']==evidence for record in value['evidence']):
                media['evidence_id']=evidence
        target=payload.get('entity_id')
        if target:
            target=value['view'].get('instances',{}).get(target,{}).get('entity_id',target)
            node=next((n for n in value['entities'] if n['id']==target),None)
            if not node:raise CanvasError('Объект для прикрепления изображения отсутствует.')
            attachments=linked_images(node['attributes'])
            if not any(row['id']==image['id'] for row in attachments):
                if len(attachments)>=20:raise CanvasError('К одному объекту можно прикрепить до 20 изображений.')
                node['attributes']['image_attachments']=[*attachments,media]
        else:
            position=payload.get('position')
            if position is not None:position={**point(position),'pinned':True}
            identifier=add_node(value,{'type':'image','label':image['name'],'position':position})
            node=next(n for n in value['entities'] if n['id']==identifier)
            node['attributes'].update(attachment_id=image['id'],original_image=True,media=media)
            if position is not None:value['view'].setdefault('manual_position_ids',[]).append(identifier)
        record_canvas_event(value,'image',[target or identifier],1)
        return self._commit(value)

    def close(self):
        self.media_previews.clear()
        if self.job:self.job.cancel()
        if self.media_job:self.media_job.cancel()
        if self.result_job:self.result_job.cancel()

    def _media(self,identifier):
        if self.media_job:return {'busy':True}
        node=next((n for n in (self.document or {}).get('entities',[]) if n['id']==identifier),None)
        reference=deepcopy((node or {}).get('attributes',{}).get('media'))
        if not reference or reference.get('kind')=='local_attachment' or reference.get('state') in ('ready','unavailable'):return None
        from .public_media import MediaStore
        import asyncio
        canvas_id=self.document['id'];bridge=self.bridge
        def task():
            try:return asyncio.run(MediaStore().fetch(reference,cancel_event=job.cancelled))
            except Exception:return {**reference,'state':'unavailable','error':'Публичное изображение недоступно.'}
        job=UiJob(task,bridge);self.media_job=job
        def done(value,error):
            self.media_job=None
            if not bridge._closed and self.document and self.document['id']==canvas_id:
                fetched=value if isinstance(value,dict) else {'state':'unavailable'}
                updated={**reference,**{key:fetched[key] for key in
                    ('state','thumbnail','width','height','mime','bytes','sha256','error') if key in fetched}}
                current=next((node for node in self.document['entities'] if node['id']==identifier),None)
                if not current or (current['attributes'].get('media') or {}).get('id')!=reference.get('id'):
                    job.deleteLater()
                    return
                key=(canvas_id,identifier,reference.get('id'))
                self.media_previews[key]=updated
                self.media_previews.move_to_end(key)
                while len(self.media_previews)>1 and (len(self.media_previews)>24 or
                    sum(len(item.get('thumbnail','')) for item in self.media_previews.values())>8_000_000):
                    self.media_previews.popitem(last=False)
                # Preview cache is presentation state, not a new source fact or
                # an undo step. It never rewrites evidence or a saved revision.
                displayed=deepcopy(self.state.get('document',{}))
                for n in displayed.get('entities',[]):
                    if n['id']==identifier:n['attributes']['media']=updated
                self.publish({**self.state,'document':displayed})
            job.deleteLater()
        job.done.connect(done);job.start();return {'pending':True}
