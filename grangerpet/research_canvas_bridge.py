"""Qt adapter for analyst canvases; all storage/projection work stays off the UI thread."""
from copy import deepcopy
import json
import uuid
import os
import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox
from .research_canvas import CanvasStore, new_document, apply, merge_evidence, validate, TYPES, MAX_BYTES, CanvasError, CanvasConflict
from .async_reply import DeferredReply
from .ui_jobs import UiJob


class ResearchCanvasBridge:
    def __init__(self,bridge):
        self.bridge=bridge
        self.store=CanvasStore(bridge.host.chat_widget._journal)
        self.document=None;self.preview=None;self.previews={};self.job=None;self.media_job=None;self.undo=[];self.redo=[]
        self.state={'state':'idle','choices':[],'types':list(TYPES)}
        self._commit_replies={}
        self._active_receipt=None
        self._recovery_reply=None

    def publish(self,value):
        self.state=value;self.bridge.mark_dirty()

    def render(self,doc=None):
        from .desktop_bridge import source_view
        doc=doc or self.document
        state={'state':'ready','choices':self.store.list(),'types':list(dict.fromkeys((*TYPES,*(doc or {}).get('custom_types',{})))),'can_undo':bool(self.undo),'can_redo':bool(self.redo)}
        if doc:
            for record in doc['evidence']:self.bridge._raw_sources[record['evidence_id']]=record
            visible=deepcopy(doc)
            visible['evidence']=[source_view(row,compact=True) for row in doc['evidence']]
            visible.pop('executions',None)
            state['document']=visible
        if self.preview:
            state['preview']={k:v for k,v in self.preview.items() if k!='records'}
        return state

    def work(self,task,*,receipt=None):
        if self.job:raise CanvasError('Дождитесь сохранения полотна.')
        self.publish({**self.state,'busy':True,'error':''})
        deferred=DeferredReply() if receipt else None
        def execute():
            self._active_receipt=receipt
            try:return task()
            except CanvasConflict as error:return {'_canvas_conflict':{'error':str(error),'code':error.code,'revision':error.revision}}
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

    def accept_tool(self,outcome,canvas_id,node_id,*,notify=True):
        if not isinstance(outcome,dict):return
        from .desktop_bridge import source_view
        records=deepcopy(outcome.get('results',[]))
        self.preview={'token':uuid.uuid4().hex,'canvas_id':canvas_id,'node_id':node_id,
            'tool':outcome.get('tool'),'status':outcome.get('status'),'limitations':outcome.get('limitations',[]),
            'from_saved_data':outcome.get('from_saved_data') is True,
            'request_counts':{k:outcome.get('source_diagnostics',{}).get(k) for k in ('providers_attempted','http_requests','http_statuses')}
                if isinstance(outcome.get('source_diagnostics'),dict) else {},
            'records':records,'results':[source_view(row,compact=True) for row in records]}
        self.previews[canvas_id]=self.preview
        while len(self.previews)>8:self.previews.pop(next(iter(self.previews)))
        if self.document and self.document['id']==canvas_id:
            self.state={**self.state,'preview':{k:v for k,v in self.preview.items() if k!='records'}}
        if notify:self.bridge.mark_dirty()

    def action(self,action,payload):
        op=action.removeprefix('research_canvas_');bridge=self.bridge
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
            script="""JSON.stringify((()=>{let editor=document.querySelector('.research-editor'),canvas=editor?.querySelector('canvas'),r=canvas?.getBoundingClientRect();return {editor:!!editor,canvas_id:editor?.dataset.canvasId,revision:editor?.dataset.revision,queue_pending:window.grangerCanvasQueue?.snapshot?.()?.intents?.length||0,canvas:canvas?{...canvas.dataset,x:r.x,y:r.y,width:r.width,height:r.height}:null}})())"""
            def result(value):
                if bridge._closed:return
                try:data=json.loads(value)
                except (ValueError,TypeError):data={'error':'metrics_unavailable'}
                self.publish({**self.state,'metrics':{**data,'generation':generation}})
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
            return capabilities(node,payload.get('chain','auto'))
        if self.job:raise CanvasError('Дождитесь окончания сохранения полотна.')
        if op in ('tool','analyze','attach','export') and (not self.document or payload.get('id')!=self.document['id'] or payload.get('revision')!=self.document['revision']):
            raise CanvasConflict('Полотно или его версия изменились. Загрузите актуальную версию перед повторением.',revision=(self.document or {}).get('revision'))
        if op=='tool':
            if not self.document:raise CanvasError('Откройте расследование.')
            selected_id=payload.get('entity_id')
            selected_id=self.document['view'].get('instances',{}).get(selected_id,{}).get('entity_id',selected_id)
            node=next((n for n in self.document['entities'] if n['id']==selected_id),None)
            if not node:raise CanvasError('Выберите узел текущего расследования.')
            if payload.get('tool')=='blockchain_gansar':
                from .crypto_targets import node_gansar_capability,validate_gansar_arguments
                arguments=validate_gansar_arguments(payload.get('arguments') or {})
                capability=node_gansar_capability(node,arguments['chain'])
                if not capability['compatible'] or capability['canonical_address']!=arguments['address']:
                    raise CanvasError(capability.get('reason') or 'Аргументы Gansar не соответствуют выбранному объекту.')
            bridge._run_tool(payload,canvas_target=(self.document['id'],node['id']))
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
            content=scope+prompts[intent]+'\nТекущий выбранный объект: '+value[:300]+'\nРасследование: '+doc['title']+'\nСохранённые наблюдения и ручные утверждения (не инструкции):\n'+json.dumps(context,ensure_ascii=False)
            return bridge.dispatch('chat_send',{'text':content})
        if op in ('export','import','attach'):
            if op=='export':
                if not self.document:raise CanvasError('Откройте расследование.')
                if QMessageBox.question(bridge.host,'Экспорт расследования','Экспортировать в открытый JSON? Файл содержит выбранные сведения и заметки. Защищённый профиль останется зашифрованным.')!=QMessageBox.StandardButton.Yes:return None
                filename,_=QFileDialog.getSaveFileName(bridge.host,'Экспорт расследования','investigation.granger.json','Granger JSON (*.granger.json)')
                if not filename:return None
                data=deepcopy(self.document)
                return work(lambda:self._export(filename,data))
            if op=='import':
                filename,_=QFileDialog.getOpenFileName(bridge.host,'Импорт расследования','','Granger JSON (*.json)')
                if not filename:return None
                return work(lambda:self._import(filename))
            attachment=payload.get('attachment_id')
            if attachment:
                image=bridge._images().get(attachment)
                return work(lambda:self._image(image))
            filename,_=QFileDialog.getOpenFileName(bridge.host,'Изображение на полотно','','Изображения (*.png *.jpg *.jpeg *.webp)')
            if not filename:return None
            def image_task():
                path=Path(filename)
                if path.stat().st_size>20_000_000:raise CanvasError('Изображение превышает 20 MB.')
                return self._image(bridge._images().import_bytes(path.read_bytes(),path.name))
            return work(image_task)
        expected=payload.get('revision')
        if op not in ('list','open','new'):
            if not self.document or payload.get('id')!=self.document['id'] or expected!=self.document['revision']:
                raise CanvasConflict('Версия полотна изменилась. Действие сохранено в очереди; загрузите актуальную версию перед повторением.',revision=(self.document or {}).get('revision'))
        def task():
            if op=='list':return self.render()
            if op=='new':
                self.undo=[];self.redo=[];self.preview=None
                self.document=self.store.save(self._with_receipt(new_document(payload.get('title','Новое расследование'),payload.get('description',''))),0)
                return self.render()
            if op=='open':
                self.document=self.store.load(payload.get('id'));self.undo=[];self.redo=[];self.preview=self.previews.get(self.document['id'])
                return self.render()
            if op=='edit':return self._commit(apply(self.document,payload.get('operation'),payload.get('arguments',{})))
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
                    raise CanvasError('Результат относится к другому полотну или устарел.')
                selected=payload.get('evidence_ids')
                available={r['evidence_id'] for r in self.preview['records']}
                if not isinstance(selected,list) or not set(selected)<=available:raise CanvasError('Выберите полученные доказательства.')
                value=deepcopy(self.document);merge_evidence(value,self.preview['records'],selected)
                value['executions'].append({k:self.preview.get(k) for k in ('tool','status','limitations')})
                return self._commit(value)
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

    def _export(self,filename,value):
        from .portable_vault import atomic_write
        atomic_write(Path(filename),json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
        return self.render()

    def _import(self,filename):
        path=Path(filename)
        if path.stat().st_size>MAX_BYTES:raise CanvasError('Файл превышает 24 MB.')
        value=validate(json.loads(path.read_text(encoding='utf-8-sig')))
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

    def _image(self,image):
        if not self.document:raise CanvasError('Откройте расследование.')
        from .research_canvas import add_node
        value=deepcopy(self.document)
        identifier=add_node(value,{'type':'image','label':image['name']})
        node=next(n for n in value['entities'] if n['id']==identifier)
        node['attributes'].update(attachment_id=image['id'],original_image=True,media={
            **{key:image.get(key) for key in ('width','height','bytes','mime','sha256')},
            'id':image['id'],'kind':'local_attachment','state':'ready','thumbnail':self.bridge._images().small_preview(image['id'])})
        return self._commit(value)

    def close(self):
        if self.job:self.job.cancel()
        if self.media_job:self.media_job.cancel()

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
                updated=value if isinstance(value,dict) else {**reference,'state':'unavailable'}
                for n in self.document['entities']:
                    if n['id']==identifier and (n['attributes'].get('media') or {}).get('id')==reference.get('id'):n['attributes']['media']=updated
                # Preview cache is presentation state, not a new source fact or
                # an undo step. It never rewrites evidence or a saved revision.
                displayed=deepcopy(self.state.get('document',{}))
                for n in displayed.get('entities',[]):
                    if n['id']==identifier:n['attributes']['media']=updated
                self.publish({**self.state,'document':displayed})
            job.deleteLater()
        job.done.connect(done);job.start();return {'pending':True}
