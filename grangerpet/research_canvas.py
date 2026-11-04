"""Versioned analyst compositions over the existing evidence graph contracts.

Entities/relations/evidence keep their common IDs. Only membership, positions and
analyst annotations belong to a canvas. Never opens or writes a conversation.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import uuid
import zlib

from .agent_evidence import utc_now, validate_saved_evidence
from .credentials import CredentialsStore, CredentialError, protected_path
from .evidence_graph import ENTITY_TYPES, _id, build
from .portable_vault import atomic_write

class CanvasError(ValueError):
    code='analyst_canvas_invalid_operation'


class CanvasConflict(CanvasError):
    code='analyst_canvas_revision_conflict'

    def __init__(self,message,*,revision=None):
        super().__init__(message)
        self.revision=revision


MAX_BYTES = 24_000_000
MANUAL_TYPES = ('person','analyst_note','hypothesis','custom_entity','document','contract','nft','collection','token')
TYPES = tuple(dict.fromkeys((*ENTITY_TYPES, *MANUAL_TYPES)))
STATUSES = ('verified','source_reported','inferred','unverified','contradicted')
LAYOUTS = ('manual','hierarchical','radial','types','communities','timeline',
           'wallet','flow','counterparties','paths')
GRAPH_MODES = ('wallet','flow','counterparties','transactions','paths','manual')
CARD_MODES = ('auto','compact','standard','expanded')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def text(value, limit=2000):
    if not isinstance(value, str) or len(value)>limit: raise CanvasError('Некорректный текст полотна.')
    return value


def point(value):
    if not isinstance(value, dict) or set(value)-{'x','y','pinned'}: raise CanvasError('Некорректная позиция.')
    for key in ('x','y'):
        if type(value.get(key)) not in (int,float) or not math.isfinite(value[key]) or abs(value[key])>10_000_000:
            raise CanvasError('Некорректная координата.')
    if 'pinned' in value and type(value['pinned']) is not bool: raise CanvasError('Некорректное закрепление.')
    return deepcopy(value)


def card_size(value):
    if not isinstance(value,dict) or set(value)!={'width','height'}:raise CanvasError('Некорректный размер карточки.')
    for key,minimum,maximum in (('width',160,720),('height',72,640)):
        number=value.get(key)
        if type(number) not in (int,float) or not math.isfinite(number) or not minimum<=number<=maximum:
            raise CanvasError('Размер карточки вне допустимых границ.')
    return deepcopy(value)


def view_ui(value):
    if not isinstance(value,dict) or set(value)-{'inspector_tab','inspector_width','inspector_open','card_mode','graph_mode'}:
        raise CanvasError('Неизвестные настройки представления.')
    if 'inspector_tab' in value and value['inspector_tab'] not in ('details','evidence','actions'):raise CanvasError('Неизвестная вкладка инспектора.')
    if 'inspector_width' in value:
        width=value['inspector_width']
        if type(width) not in (int,float) or not math.isfinite(width) or not 220<=width<=650:raise CanvasError('Некорректная ширина инспектора.')
    if 'inspector_open' in value and type(value['inspector_open']) is not bool:raise CanvasError('Некорректная видимость инспектора.')
    if 'card_mode' in value and value['card_mode'] not in CARD_MODES:raise CanvasError('Неизвестный режим карточек.')
    if 'graph_mode' in value and value['graph_mode'] not in GRAPH_MODES:raise CanvasError('Неизвестный режим графа.')
    return deepcopy(value)


def viewport(value):
    if not isinstance(value,dict) or set(value)!={'x','y','scale'}:raise CanvasError('Некорректная область просмотра.')
    point({key:value[key] for key in ('x','y')})
    if type(value['scale']) not in (int,float) or not math.isfinite(value['scale']) or not .001<=value['scale']<=10:
        raise CanvasError('Неверный масштаб.')
    return deepcopy(value)


def validate(value):
    if not isinstance(value,dict) or value.get('schema')!='granger-investigation/1': raise CanvasError('Неизвестный формат расследования.')
    if not re.fullmatch(r'[a-f0-9]{32}', str(value.get('id',''))): raise CanvasError('Некорректный ID расследования.')
    if type(value.get('revision')) is not int or value['revision']<0: raise CanvasError('Некорректная версия.')
    text(value.get('title'),200);text(value.get('description',''),10000)
    nodes=value.get('entities');edges=value.get('relations');evidence=value.get('evidence')
    if not isinstance(nodes,list) or len(nodes)>5000 or not isinstance(edges,list) or len(edges)>20000 or not isinstance(evidence,list) or len(evidence)>5000:
        raise CanvasError('Превышены ограничения расследования: 5000 узлов / 20000 связей / 5000 evidence.')
    ids=set();evs=set()
    for record in evidence:
        validate_saved_evidence(record);evs.add(record['evidence_id'])
    for node in nodes:
        if not isinstance(node,dict) or not re.fullmatch(r'ent_[a-f0-9]{24}', str(node.get('id',''))) or node['id'] in ids:
            raise CanvasError('Некорректный или повторный узел.')
        ids.add(node['id']);text(node.get('type'),80);text(node.get('label'),300)
        if not isinstance(node.get('attributes'),dict) or not isinstance(node.get('evidence_ids'),list) or not set(node['evidence_ids'])<=evs:
            raise CanvasError('Узел ссылается на отсутствующие доказательства.')
        if node.get('verification_status','unverified') not in STATUSES:raise CanvasError('Неизвестный статус узла.')
    relation_ids=set()
    for edge in edges:
        if not isinstance(edge,dict) or not re.fullmatch(r'rel_[a-f0-9]{24}',str(edge.get('id',''))) or edge['id'] in relation_ids:
            raise CanvasError('Некорректная связь.')
        relation_ids.add(edge['id'])
        if edge.get('from_id') not in ids or edge.get('to_id') not in ids or edge.get('verification_status') not in STATUSES:
            raise CanvasError('Некорректные концы или статус связи.')
        text(edge.get('relation_type'),100)
        if not isinstance(edge.get('evidence_ids'),list) or not set(edge['evidence_ids'])<=evs:raise CanvasError('Отсутствует evidence связи.')
    view=value.get('view')
    if not isinstance(view,dict) or not isinstance(view.get('positions'),dict):raise CanvasError('Нет представления полотна.')
    instances=view.get('instances',{})
    if not isinstance(instances,dict) or len(instances)+len(ids)>5000:raise CanvasError('Слишком много визуальных экземпляров.')
    for identifier,instance in instances.items():
        if not re.fullmatch(r'ent_[a-f0-9]{24}',identifier) or identifier in ids or not isinstance(instance,dict) or instance.get('entity_id') not in ids:
            raise CanvasError('Некорректный визуальный экземпляр.')
        point(instance.get('position'))
    view_ids=ids|set(instances)
    for key in ('positions','manual_positions'):
        positions=view.get(key,{})
        if not isinstance(positions,dict) or len(positions)>5000:raise CanvasError('Некорректные позиции.')
        for identifier,p in positions.items():
            # Older revisions retained stale manual-layout snapshots after an
            # entity deletion. Keep them readable; current deletion cleans up.
            if identifier not in ids and key=='positions':raise CanvasError('Позиция неизвестного узла.')
            point(p)
    if view.get('layout','manual') not in LAYOUTS:raise CanvasError('Неизвестная раскладка.')
    if 'viewport' in view:viewport(view['viewport'])
    if 'query' in view:text(view['query'],2000)
    for key in ('hidden','removed','collapsed','expanded'):
        identifiers=view.get(key,[])
        if not isinstance(identifiers,list) or not all(isinstance(i,str) for i in identifiers) or not set(identifiers)<=view_ids:raise CanvasError('Некорректная видимость.')
    expanded_relations=view.get('expanded_relations',[])
    if not isinstance(expanded_relations,list) or not all(isinstance(i,str) for i in expanded_relations) or not set(expanded_relations)<=relation_ids:
        raise CanvasError('Неизвестная раскрытая связь.')
    sizes=view.get('card_sizes',{})
    if not isinstance(sizes,dict) or len(sizes)>5000 or not set(sizes)<=view_ids:raise CanvasError('Размер неизвестной карточки.')
    for size in sizes.values():card_size(size)
    view_ui(view.get('ui',{}))
    annotations=value.get('annotations',{})
    if not isinstance(annotations,dict) or not set(annotations)<=view_ids|relation_ids:raise CanvasError('Некорректная аннотация.')
    for annotation in annotations.values():
        if not isinstance(annotation,dict) or set(annotation)-{'label','markdown','color'}:raise CanvasError('Некорректная аннотация.')
        for key,item in annotation.items():text(item,20000 if key=='markdown' else 300)
    retired=value.get('retired_tool_relations',{})
    if not isinstance(retired,dict) or len(retired)>20000:raise CanvasError('Некорректный архив связей.')
    for identifier,entry in retired.items():
        if not isinstance(entry,dict) or set(entry)!={'relation','annotation','retired_at'}:raise CanvasError('Некорректный архив связей.')
        edge=entry['relation'];annotation=entry['annotation']
        if (not isinstance(edge,dict) or not re.fullmatch(r'rel_[a-f0-9]{24}',identifier)
                or edge.get('id')!=identifier or edge.get('origin')!='tool'
                or not all(re.fullmatch(r'ent_[a-f0-9]{24}',str(edge.get(k,''))) for k in ('from_id','to_id'))
                or not isinstance(edge.get('evidence_ids'),list) or not set(edge['evidence_ids'])<=evs):
            raise CanvasError('Некорректная архивная связь.')
        if not isinstance(annotation,dict) or set(annotation)-{'label','markdown','color'}:raise CanvasError('Некорректная архивная аннотация.')
        for key,item in annotation.items():text(item,20000 if key=='markdown' else 300)
        text(entry['retired_at'],100)
    by_id={n['id']:n for n in nodes}
    parents={n['id']:n['attributes'].get('parent_group_id') for n in nodes}
    parents.update({i:v.get('parent_group_id') for i,v in instances.items()})
    for identifier in view_ids:
        seen=set();parent=parents[identifier]
        while parent:
            if not isinstance(parent,str) or parent not in view_ids or parent in seen or parent==identifier:raise CanvasError('Циклическая или отсутствующая группа.')
            owner=instances[parent]['entity_id'] if parent in instances else parent
            if by_id[owner]['type']!='entity_group':raise CanvasError('Родитель должен быть группой.')
            seen.add(parent);parent=parents[parent]
    if len(encoded(value))>MAX_BYTES:raise CanvasError('Расследование превышает 24 MB; сохранённые данные не изменены.')
    return value


def new_document(title='Новое расследование', description=''):
    now=utc_now()
    return {'schema':'granger-investigation/1','id':uuid.uuid4().hex,'revision':0,'title':text(title,200),
        'description':text(description,10000),'created_at':now,'updated_at':now,'entities':[],'relations':[],
        'evidence':[],'executions':[],'annotations':{},'custom_types':{},'view':{
            'positions':{},'instances':{},'viewport':{'x':380,'y':250,'scale':1},'hidden':[],'removed':[],'collapsed':[],
            'expanded':[],'expanded_relations':[],'card_sizes':{},'ui':{},'layout':'manual'}}


class CanvasStore:
    def __init__(self, journal):
        self.journal=journal

    @property
    def directory(self):return protected_path(self.journal.directory/'analyst-canvases')

    def _folder(self,identifier):
        self.journal._identifier(identifier)
        return self.directory/identifier

    def _read(self,path):
        if path.stat().st_size>MAX_BYTES+65536:raise CanvasError('Слишком большой файл расследования.')
        raw=CredentialsStore._protect(path.read_bytes(),decrypt=True)
        if raw.startswith(b'GCZ1'):
            decoder=zlib.decompressobj();raw=decoder.decompress(raw[4:],MAX_BYTES+1025)
            if len(raw)>MAX_BYTES+1024 or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:raise CanvasError('Превышен предел распаковки расследования.')
        envelope=json.loads(raw.decode('utf-8'))
        value=envelope['document']
        if hashlib.sha256(encoded(value)).hexdigest()!=envelope.get('sha256'):raise CanvasError('Контроль целостности не пройден.')
        return validate(value)

    def load(self,identifier):
        folder=self._folder(identifier)
        # Immutable revisions are the commit log. A valid newest revision also
        # recovers a crash between its durable write and the head pointer.
        paths=sorted(folder.glob('r[0-9]*.dpapi'),reverse=True)
        for path in paths:
            try:
                value=self._read(path)
                if value['id']!=identifier:continue
                value['recovered_revision']=path!=paths[0]
                return value
            except (OSError,ValueError,KeyError,UnicodeError,CredentialError,zlib.error):continue
        raise CanvasError('Расследование не прочитано. Исходные файлы сохранены.')

    def save(self,value,expected_revision):
        from PySide6.QtCore import QLockFile
        value=deepcopy(value);value.pop('recovered_revision',None)
        folder=self._folder(value['id']);folder.mkdir(parents=True,exist_ok=True)
        lock=QLockFile(str(folder/'writer.lock'));lock.setStaleLockTime(0)
        if not lock.tryLock(1500):raise CanvasError('Расследование сохраняет другой процесс. Повторите после завершения.')
        try:
            revisions=list(folder.glob('r[0-9]*.dpapi'))
            if revisions:
                previous=self.load(value['id'])
                if expected_revision!=previous['revision']:raise CanvasConflict('Конфликт версии. Другой редактор сохранил изменения. Загрузите актуальную версию перед повторением своих действий.',revision=previous['revision'])
                number=max(int(p.stem[1:]) for p in revisions)+1
            else:
                if expected_revision!=0:raise CanvasError('Не найдена исходная версия.')
                number=1
            value.update(revision=number,updated_at=utc_now());validate(value)
            envelope={'sha256':hashlib.sha256(encoded(value)).hexdigest(),'document':value}
            target=folder/f'r{number:010d}.dpapi'
            if target.exists():raise CanvasError('Версия уже существует; перезапись запрещена.')
            atomic_write(target,CredentialsStore._protect(b'GCZ1'+zlib.compress(encoded(envelope),6)))
            # Head contains only encrypted metadata; readers verify the revision.
            atomic_write(folder/'head.dpapi',CredentialsStore._protect(encoded({
                'id':value['id'],'revision':number,'title':value['title'],'updated_at':value['updated_at'],'deleted':value.get('deleted',False)})))
            return value
        finally:lock.unlock()

    def list(self):
        if not self.directory.exists():return []
        rows=[]
        for folder in self.directory.iterdir():
            if not folder.is_dir() or not re.fullmatch('[a-f0-9]{32}',folder.name):continue
            try:
                header=folder/'head.dpapi'
                row=json.loads(CredentialsStore._protect(header.read_bytes(),decrypt=True).decode('utf-8')) if header.is_file() else self.load(folder.name)
                if not row.get('deleted'):rows.append({k:row.get(k) for k in ('id','title','revision','updated_at')})
            except (OSError,ValueError,UnicodeError,CredentialError):continue
        return sorted(rows,key=lambda r:r.get('updated_at',''),reverse=True)[:100]


def add_node(doc,args):
    kind=text(args.get('type','custom_entity'),80);label=text(args.get('label','Новый объект'),300).strip()
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,79}',kind) or not label:raise CanvasError('Укажите тип и название.')
    attrs={'origin':'analyst','claim_kind':'analyst_assertion','identity_verified':False}
    key=uuid.uuid4().hex
    from .entity_router import route
    from .crypto_targets import resolve_crypto_target
    machine_value=args.get('value') or label
    target=route(machine_value)
    crypto=kind in ('blockchain_address','contract','nft','collection','token')
    if crypto:
        resolved=resolve_crypto_target(machine_value,args.get('chain','auto'))
        if not resolved['valid'] or resolved['requires_network']:raise CanvasError(resolved['reason'])
        key=resolved['identity_key']
        attrs.update(address=resolved['canonical_address'],value=resolved['canonical_address'],chain=resolved['chain'],
            platform=resolved['chain'],original_address=machine_value,representation=resolved['representation'],
            target_kind=resolved['target_kind'],name_resolution_pending=resolved['target_kind']!='address')
        if kind in ('nft','collection','token'):attrs['asset_id']=resolved['canonical_address']
        if kind=='contract':attrs.update(contract=resolved['canonical_address'],asset_type='blockchain_contract')
    elif target and kind not in ('analyst_note','hypothesis','person','custom_entity','entity_group','document','image'):
        kind={'network_range':'infrastructure_asset','autonomous_system':'infrastructure_asset'}.get(target.entity_type,kind)
        key=target.identifier
        attrs.update(target.properties or {},value=target.identifier,url=target.canonical_url,platform=target.platform)
        if kind=='blockchain_address':
            resolved=resolve_crypto_target(target.identifier,args.get('chain') or target.platform or 'auto')
            if not resolved['valid'] or resolved['requires_network']:raise CanvasError(resolved['reason'])
            key=resolved['identity_key'];attrs.update(address=resolved['canonical_address'],value=resolved['canonical_address'],
                chain=resolved['chain'],platform=resolved['chain'],representation=resolved['representation'])
        if kind=='infrastructure_asset':attrs.update(address=target.identifier,asset_type='ip')
        if kind in ('public_profile','social_profile','website') and target.canonical_url:key=target.canonical_url
    if kind not in TYPES:doc['custom_types'][kind]=kind
    identifier=_id(kind,key)
    if identifier not in {n['id'] for n in doc['entities']}:
        node={'id':identifier,'type':kind,'label':label,'attributes':attrs,'evidence_ids':[],
              'source':['Analyst'],'verification_status':'inferred' if kind=='hypothesis' else 'unverified'}
        if kind=='analyst_note':node['attributes']['markdown']=text(args.get('markdown',''),20000)
        doc['entities'].append(node)
        doc['annotations'][identifier]={'label':label}
        proposed=args.get('position')
        if proposed is None:
            index=len(doc['entities'])-1
            while True:
                proposed={'x':index%4*310,'y':index//4*150}
                if not any(abs(p['x']-proposed['x'])<285 and abs(p['y']-proposed['y'])<135 for p in doc['view']['positions'].values()):break
                index+=1
        doc['view']['positions'][identifier]=point(proposed)
    return identifier


def merge_evidence(doc,records,selected=None):
    """Only server-owned validated observations enter the shared graph builder."""
    if selected is not None:records=[r for r in records if r['evidence_id'] in selected]
    for record in records:validate_saved_evidence(record)
    ev={r['evidence_id']:r for r in doc['evidence']}
    from .agent_evidence import current_observation
    refreshed=set()
    for record in records:
        previous=ev.get(record['evidence_id'])
        if previous is None:ev[record['evidence_id']]=deepcopy(record);continue
        fields=('status','description','details','provenance')
        observation=lambda row:{key:deepcopy(row[key]) for key in fields}
        old=observation(current_observation(previous));incoming=observation(current_observation(record))
        if old!=incoming:
            refreshed.add(record['evidence_id'])
            # Match the shared evidence ledger: keep the original proof and
            # bounded observation history; the graph projects the latest entry.
            history=previous.setdefault('observations',[observation(previous)])
            for item in [*record.get('observations',[]),incoming]:
                if not history or history[-1]!=item:history.append(deepcopy(item))
            del history[:-8]
            if previous['status']!=incoming['status']:previous['verification']='contradictory'
    doc['evidence']=list(ev.values())
    # Recompute shared aggregates over all retained observations. Building only
    # the latest batch replaced an existing flow's count/amount/member IDs while
    # leaving its older evidence and transaction nodes in the document.
    graph=build(doc['evidence'],full=True,limit=5000)
    nodes={n['id']:n for n in doc['entities']};edges={e['id']:e for e in doc['relations']}
    # Old evidence survives an analyst's explicit membership deletion. Refresh
    # aggregate values without resurrecting those nodes during an unrelated import.
    incoming_ids={n['id'] for n in build(records,full=True,limit=5000)['entities']}
    members=set(nodes)|incoming_ids
    graph['entities']=[n for n in graph['entities'] if n['id'] in members]
    graph['relations']=[e for e in graph['relations'] if e['from_id'] in members and e['to_id'] in members]
    if refreshed and not (graph['truncated_input'] or graph['relations_truncated'] or graph['next_offset']):
        # Absence in a complete refreshed projection invalidates the previous
        # derived edge. Keep its exact snapshot and analyst note in this same
        # versioned document, outside the active financial graph.
        active={edge['id'] for edge in graph['relations']}
        retired=doc.setdefault('retired_tool_relations',{})
        for identifier,edge in list(edges.items()):
            if edge.get('origin')!='tool' or identifier in active or not refreshed.intersection(edge['evidence_ids']):continue
            annotation=doc['annotations'].pop(identifier,retired.get(identifier,{}).get('annotation',{}))
            retired[identifier]={'relation':deepcopy(edge),'annotation':deepcopy(annotation),'retired_at':utc_now()}
            del edges[identifier]
        doc['view']['expanded_relations']=[identifier for identifier in doc['view'].get('expanded_relations',[]) if identifier in edges]
    added=[]
    for node in graph['entities']:
        identifier=node['id']
        if identifier in nodes:
            old=nodes[identifier]
            node['evidence_ids']=list(dict.fromkeys(old['evidence_ids']+node['evidence_ids']))
            node['attributes']={**old['attributes'],**node['attributes']}
            # Analyst labels live in annotations, never overwrite source labels.
        else:added.append(identifier)
        nodes[identifier]=node
    for edge in graph['relations']:
        archived=doc.get('retired_tool_relations',{}).get(edge['id'])
        if archived and archived['annotation']:
            doc['annotations'].setdefault(edge['id'],deepcopy(archived['annotation']))
        if edge['id'] in edges:
            old=edges[edge['id']]
            for key in ('evidence_ids','source_urls','provenance'):
                values=old.get(key,[])+edge.get(key,[]);edge[key]=list({encoded(v):v for v in values}.values())
        edge['origin']='tool';edges[edge['id']]=edge
    doc.update(entities=list(nodes.values()),relations=list(edges.values()))
    for index,identifier in enumerate(added):
        doc['view']['positions'][identifier]={'x':(index%5)*310,'y':max((p['y'] for p in doc['view']['positions'].values()),default=-170)+170 if index%5==0 else doc['view']['positions'][added[index-1]]['y']}
    return added


def apply(doc,operation,args):
    doc=deepcopy(doc);nodes={n['id']:n for n in doc['entities']};edges={e['id']:e for e in doc['relations']}
    instances=doc['view'].setdefault('instances',{})
    canonical=lambda identifier:instances.get(identifier,{}).get('entity_id',identifier)
    ids=args.get('ids',[])
    if not isinstance(ids,list) or not set(ids)<=set(nodes)|set(instances):raise CanvasError('Выбран неизвестный узел.')
    if operation=='node':add_node(doc,args)
    elif operation=='rename':doc.update(title=text(args.get('title'),200),description=text(args.get('description',''),10000))
    elif operation=='annotate':
        identifier=args.get('entity_id')
        if identifier not in nodes and identifier not in instances and identifier not in edges:raise CanvasError('Объект не найден.')
        value=args.get('annotation')
        if not isinstance(value,dict) or set(value)-{'label','markdown','color'}:raise CanvasError('Некорректная аннотация.')
        for k,v in value.items():text(v,20000 if k=='markdown' else 300)
        doc['annotations'][identifier]={**doc['annotations'].get(identifier,{}),**value}
    elif operation in ('edge','edge_edit'):
        visual_a,visual_b=args.get('from_id'),args.get('to_id')
        a,b=canonical(visual_a),canonical(visual_b);kind=text(args.get('relation_type','potentially_related'),100)
        if a not in nodes or b not in nodes or not kind:raise CanvasError('Выберите два узла и тип связи.')
        identifier='rel_'+hashlib.sha256((a+'|'+b+'|'+kind).encode()).hexdigest()[:24]
        if operation=='edge_edit':
            previous=edges.get(args.get('relation_id'))
            if not previous or previous.get('origin')!='analyst':raise CanvasError('Источник связи нельзя переписать. Добавьте отдельную гипотезу.')
            doc['relations']=[e for e in doc['relations'] if e['id']!=previous['id']]
            if previous['id']!=identifier:
                annotation=doc['annotations'].pop(previous['id'],None)
                if annotation:doc['annotations'].setdefault(identifier,annotation)
                doc['view']['expanded_relations']=[identifier if old==previous['id'] else old for old in doc['view'].get('expanded_relations',[])]
        edge={'id':identifier,'from_id':a,'to_id':b,'relation_type':kind,'direction':'directed','evidence_ids':[],
              'source_urls':[],'verification_status':args.get('status','unverified'),'origin':'analyst',
              'claim_kind':'analyst_assertion','attributes':{'observed_at':utc_now(),'visual_from_id':visual_a,'visual_to_id':visual_b},'provenance':[]}
        if edge['verification_status'] not in ('unverified','inferred','contradicted'):raise CanvasError('Ручное утверждение не становится доказанным фактом.')
        if identifier not in {e['id'] for e in doc['relations']}:doc['relations'].append(edge)
    elif operation in ('positions','layout'):
        supplied=args.get('positions')
        if not isinstance(supplied,dict) or not set(supplied)<=set(nodes)|set(instances):raise CanvasError('Неизвестная позиция.')
        if operation=='layout':
            mode=args.get('mode')
            if mode not in LAYOUTS:raise CanvasError('Неизвестная раскладка.')
            if doc['view'].get('layout')=='manual':doc['view']['manual_positions']={**deepcopy(doc['view']['positions']),**{i:deepcopy(v['position']) for i,v in instances.items()}}
            if mode=='manual':supplied={key:value for key,value in doc['view'].get('manual_positions',{}).items() if key in nodes or key in instances}
            doc['view']['layout']=mode
        else:
            supplied={key:point(value) for key,value in supplied.items()}
            before={**doc['view']['positions'],**{i:v['position'] for i,v in instances.items()}}
            parents={i:n['attributes'].get('parent_group_id') for i,n in nodes.items()}
            parents.update({i:v.get('parent_group_id') for i,v in instances.items()})
            deltas={i:(p['x']-before[i]['x'],p['y']-before[i]['y']) for i,p in supplied.items()
                if i in before and nodes[canonical(i)]['type']=='entity_group'}
            # Renderer projection omits collapsed/filtered/progressive members.
            # Move those descendants here. Explicit renderer positions win so
            # visible members and nested groups are never translated twice.
            for identifier,previous in before.items():
                if identifier in supplied:continue
                parent=parents.get(identifier);seen=set()
                while parent and parent not in seen:
                    if parent in deltas:
                        dx,dy=deltas[parent];supplied[identifier]=point({**previous,'x':previous['x']+dx,'y':previous['y']+dy});break
                    seen.add(parent);parent=parents.get(parent)
        for key,value in supplied.items():
            if key in instances:instances[key]['position']=point(value)
            else:doc['view']['positions'][key]=point(value)
    elif operation=='view':
        patch=args.get('view',{})
        if not isinstance(patch,dict) or set(patch)-{'viewport','layout','collapsed','hidden','removed','query','card_sizes','ui','expanded','expanded_relations'}:raise CanvasError('Неизвестное представление.')
        patch=deepcopy(patch)
        if 'viewport' in patch:patch['viewport']=viewport(patch['viewport'])
        if 'ui' in patch:patch['ui']={**doc['view'].get('ui',{}),**view_ui(patch['ui'])}
        if 'card_sizes' in patch:
            if not isinstance(patch['card_sizes'],dict):raise CanvasError('Некорректные размеры карточек.')
            patch['card_sizes']={**doc['view'].get('card_sizes',{}),**patch['card_sizes']}
        doc['view'].update(patch)
    elif operation=='card_size':
        identifier=args.get('id')
        if identifier not in nodes and identifier not in instances:raise CanvasError('Карточка не найдена.')
        doc['view'].setdefault('card_sizes',{})[identifier]=card_size({key:args.get(key) for key in ('width','height')})
    elif operation=='group':
        parent=add_node(doc,{'type':'entity_group','label':args.get('label','Группа')})
        next(n for n in doc['entities'] if n['id']==parent)['attributes']['member_count']=len(ids)
        for identifier in ids:
            if identifier in instances:instances[identifier]['parent_group_id']=parent
            elif identifier!=parent:nodes[identifier]['attributes']['parent_group_id']=parent
    elif operation=='ungroup':
        for identifier in ids:
            if identifier in instances:instances[identifier].pop('parent_group_id',None)
            else:nodes[identifier]['attributes'].pop('parent_group_id',None)
    elif operation in ('hide','remove','restore','delete_entity'):
        if operation=='delete_entity':
            canonical_ids={canonical(i) for i in ids}
            ids=list(canonical_ids|{i for i,v in instances.items() if v['entity_id'] in canonical_ids})
            for i in ids:instances.pop(i,None)
            doc['entities']=[n for n in doc['entities'] if n['id'] not in ids]
            doc['relations']=[e for e in doc['relations'] if e['from_id'] not in ids and e['to_id'] not in ids]
            for n in doc['entities']:
                if n['attributes'].get('parent_group_id') in ids:n['attributes'].pop('parent_group_id')
            for instance in instances.values():
                if instance.get('parent_group_id') in ids:instance.pop('parent_group_id')
            for identifier in ids:doc['view']['positions'].pop(identifier,None);doc['annotations'].pop(identifier,None)
            doc['annotations']={k:v for k,v in doc['annotations'].items() if k in {n['id'] for n in doc['entities']}|{e['id'] for e in doc['relations']}|set(instances)}
            for key in ('card_sizes','manual_positions'):
                doc['view'][key]={i:v for i,v in doc['view'].get(key,{}).items() if i not in ids}
            doc['view']['expanded']=[i for i in doc['view'].get('expanded',[]) if i not in ids]
            doc['view']['expanded_relations']=[i for i in doc['view'].get('expanded_relations',[]) if i in {e['id'] for e in doc['relations']}]
        for key in ('hidden','removed','collapsed'):
            doc['view'][key]=[i for i in doc['view'][key] if i not in ids]
        if operation in ('hide','remove'):doc['view']['hidden' if operation=='hide' else 'removed']+=ids
        # Removing entity membership never removes original evidence observations.
    elif operation=='duplicate_nodes':
        for identifier in ids:
            new_id=_id('visual_instance',uuid.uuid4().hex)
            old=instances[identifier]['position'] if identifier in instances else doc['view']['positions'].get(identifier,{'x':0,'y':0})
            instances[new_id]={'entity_id':canonical(identifier),'position':{'x':old['x']+40,'y':old['y']+40}}
            if identifier in doc['annotations']:doc['annotations'][new_id]=deepcopy(doc['annotations'][identifier])
            if identifier in doc['view'].get('card_sizes',{}):doc['view']['card_sizes'][new_id]=deepcopy(doc['view']['card_sizes'][identifier])
    else:raise CanvasError('Неизвестная операция полотна.')
    return validate(doc)
