"""User-authorized, bounded offline exchange; originals never go to a network."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

from .research_canvas import CanvasError,MAX_BYTES,add_node,encoded,new_document,validate
from .portable_vault import atomic_write

MAX_PACKAGE=512_000_000
MAX_ATTACHMENTS=128
MAX_ATTACHMENT=20_000_000
IMAGE_ID=re.compile(r'img_[a-f0-9]{64}')
EXTENSIONS={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}


def attachment_ids(document):
    ids=set()
    for node in document['entities']:
        attrs=node['attributes']
        identifier=attrs.get('attachment_id')
        if isinstance(identifier,str) and IMAGE_ID.fullmatch(identifier):ids.add(identifier)
        media=attrs.get('media')
        references=([media] if isinstance(media,dict) else [])+list(attrs.get('image_attachments') or [])
        for reference in references:
            if isinstance(reference,dict) and reference.get('kind')=='local_attachment' and isinstance(reference.get('id'),str) and IMAGE_ID.fullmatch(reference['id']):ids.add(reference['id'])
    if len(ids)>MAX_ATTACHMENTS:raise CanvasError('Перенос ограничен 128 оригиналами изображений в одном пакете.')
    return sorted(ids)


def json_canvas(document,files):
    """JSON Canvas 1.0 core with an optional lossless Granger extension."""
    validate(document)
    nodes=[];positions=document['view']['positions'];sizes=document['view'].get('card_sizes',{})
    visible=[(node['id'],node,positions.get(node['id'],{'x':0,'y':0})) for node in document['entities']]
    by_id={node['id']:node for node in document['entities']}
    visible.extend((identifier,by_id[instance['entity_id']],instance['position']) for identifier,instance in document['view'].get('instances',{}).items())
    for identifier,node,position in visible:
        attrs=node['attributes'];size=sizes.get(identifier,{'width':320 if node['type']=='image' else 240,'height':240 if node['type']=='image' else 140})
        width,height=round(size['width']),round(size['height'])
        row={'id':identifier,'x':round(position['x']-width/2),'y':round(position['y']-height/2),'width':width,'height':height}
        image=attrs.get('attachment_id') or (attrs.get('media') or {}).get('id')
        if node['type']=='entity_group':row.update(type='group',label=node['label'])
        elif image in files:row.update(type='file',file=files[image])
        elif isinstance(attrs.get('url'),str) and attrs['url'].startswith(('https://','http://')):row.update(type='link',url=attrs['url'])
        else:row.update(type='text',text=document['annotations'].get(identifier,{}).get('markdown') or attrs.get('markdown') or node['label'])
        color=document['annotations'].get(identifier,{}).get('color')
        if isinstance(color,str) and re.fullmatch(r'#[a-fA-F0-9]{6}',color):row['color']=color
        nodes.append(row)
    edges=[]
    for relation in document['relations']:
        attrs=relation.get('attributes',{});direction=relation.get('direction','directed')
        row={'id':relation['id'],'fromNode':attrs.get('visual_from_id') or relation['from_id'],'toNode':attrs.get('visual_to_id') or relation['to_id'],
             'fromEnd':'arrow' if direction=='bidirectional' else 'none','toEnd':'none' if direction=='undirected' else 'arrow','label':relation['relation_type']}
        if row['fromNode'] not in {n['id'] for n in nodes} or row['toNode'] not in {n['id'] for n in nodes}:continue
        if re.fullmatch(r'#[a-fA-F0-9]{6}',str(attrs.get('color',''))):row['color']=attrs['color']
        edges.append(row)
    return {'nodes':nodes,'edges':edges,'granger':{'schema':'granger-json-canvas/1','document':deepcopy(document),'attachments':files}}


def _originals(document,store):
    rows=[];total=0
    for identifier in attachment_ids(document):
        metadata=store.get(identifier);extension=EXTENSIONS.get(metadata['mime'])
        if not extension:raise CanvasError('Формат оригинала не поддерживается.')
        count=metadata['bytes'];total+=count
        if count>MAX_ATTACHMENT or total>MAX_PACKAGE-MAX_BYTES*2:raise CanvasError('Оригиналы превышают лимит переносимого пакета.')
        rows.append({'id':identifier,'path':'assets/'+identifier+extension,'sha256':identifier[4:],'bytes':count,'name':metadata['name']})
    return rows


def export_package(path,document,store):
    validate(document);path=Path(path);rows=_originals(document,store)
    manifest={'schema':'granger-portable/1','attachments':rows}
    canvas=json_canvas(document,{row['id']:row['path'] for row in rows})
    handle=tempfile.NamedTemporaryFile(prefix='.'+path.name+'.',suffix='.pending',dir=path.parent,delete=False)
    temporary=Path(handle.name);handle.close()
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            archive.writestr('manifest.json',encoded(manifest));archive.writestr('investigation.granger.json',encoded(document));archive.writestr('investigation.canvas',encoded(canvas))
            for row in rows:archive.writestr(row['path'],store.read_bytes(row['id']))
        with temporary.open('rb+') as stream:os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def export_canvas(path,document,store):
    path=Path(path);rows=_originals(document,store);folder=path.stem+'.assets'
    for row in rows:
        target=path.parent/folder/Path(row['path']).name
        if target.is_symlink() or target.parent.is_symlink():raise CanvasError('Нельзя записать оригиналы через символическую ссылку.')
        target.parent.mkdir(exist_ok=True)
        data=store.read_bytes(row['id'])
        if target.exists() and sha256(target.read_bytes()).hexdigest()!=row['sha256']:raise CanvasError('Файл оригинала уже существует с другим содержимым.')
        if not target.exists():atomic_write(target,data)
        row['path']=folder+'/'+target.name
    atomic_write(path,encoded(json_canvas(document,{row['id']:row['path'] for row in rows})))


def _json(data):
    if len(data)>MAX_BYTES*2:raise CanvasError('Описание расследования превышает лимит.')
    try:return json.loads(data.decode('utf-8-sig'))
    except (ValueError,UnicodeError,RecursionError):raise CanvasError('Некорректное описание расследования.') from None


def _safe_name(name):
    if not isinstance(name,str) or '\\' in name or ':' in name or any(ord(c)<32 for c in name):raise CanvasError('Некорректный путь вложения.')
    parts=PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or not parts.parts:raise CanvasError('Путь вложения выходит за пределы пакета.')
    return parts


def import_package(path,store):
    path=Path(path)
    if path.stat().st_size>MAX_PACKAGE:raise CanvasError('Пакет превышает 512 MB.')
    try:
        with zipfile.ZipFile(path) as archive:
            infos=archive.infolist();names=[info.filename for info in infos]
            if len(infos)>MAX_ATTACHMENTS+3 or len(names)!=len(set(names)):raise CanvasError('Слишком много или повторные файлы в пакете.')
            total=0
            for info in infos:
                _safe_name(info.filename);total+=info.file_size
                if stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1 or info.file_size>MAX_BYTES*2 or total>MAX_PACKAGE:raise CanvasError('Пакет содержит недопустимый файл или превышает лимит распаковки.')
            if not {'manifest.json','investigation.granger.json','investigation.canvas'}<=set(names):raise CanvasError('Не хватает описания пакета.')
            manifest=_json(archive.read('manifest.json'));document=validate(_json(archive.read('investigation.granger.json')))
            if manifest.get('schema')!='granger-portable/1' or not isinstance(manifest.get('attachments'),list):raise CanvasError('Неизвестная версия пакета.')
            rows=manifest['attachments'];expected=attachment_ids(document)
            if sorted(row.get('id','') for row in rows)!=expected:raise CanvasError('Список оригиналов не соответствует расследованию.')
            if set(names)!={'manifest.json','investigation.granger.json','investigation.canvas',*(row.get('path') for row in rows)}:raise CanvasError('Пакет содержит непредусмотренные файлы.')
            verified=[]
            for row in rows:
                name=row['path'];_safe_name(name);data=archive.read(name)
                if len(data)>MAX_ATTACHMENT or len(data)!=row.get('bytes') or sha256(data).hexdigest()!=row['id'][4:] or row.get('sha256')!=row['id'][4:]:raise CanvasError('Контрольная сумма оригинала не совпала.')
                verified.append((row,data))
            # Validate every manifest/hash before adding immutable, encrypted originals.
            for row,data in verified:
                if store.import_bytes(data,row.get('name') or Path(row['path']).name)['id']!=row['id']:raise CanvasError('Оригинал изменился при импорте.')
            return document
    except (zipfile.BadZipFile,KeyError,TypeError,AttributeError):raise CanvasError('Повреждённый переносимый пакет.') from None


def import_canvas(path,store,*,_core_only=False):
    path=Path(path);data=_json(path.read_bytes())
    if not isinstance(data,dict) or not isinstance(data.get('nodes'),list) or not isinstance(data.get('edges'),list):raise CanvasError('Некорректный JSON Canvas.')
    if len(data['nodes'])>5000 or len(data['edges'])>20000:raise CanvasError('Слишком большой JSON Canvas.')
    root=path.parent.resolve();total=0;originals={}
    def read_file(name):
        nonlocal total
        parts=_safe_name(name);candidate=root.joinpath(*parts.parts)
        current=root
        for part in parts.parts:
            current=current/part
            if current.is_symlink():raise CanvasError('Ссылки на внешние оригиналы не импортируются.')
        if not candidate.resolve().is_relative_to(root):raise CanvasError('Файл вне каталога графа.')
        size=candidate.stat().st_size;total+=size
        if size>MAX_ATTACHMENT or total>MAX_PACKAGE:raise CanvasError('Вложения превышают лимит импорта.')
        return candidate.read_bytes()
    extension=data.get('granger')
    if not _core_only and isinstance(extension,dict) and extension.get('schema')=='granger-json-canvas/1':
        document=validate(extension.get('document'));files=extension.get('attachments',{})
        if not isinstance(files,dict) or sorted(files)!=attachment_ids(document):raise CanvasError('Нет полного списка оригиналов.')
        for identifier,name in files.items():
            content=read_file(name)
            if 'img_'+sha256(content).hexdigest()!=identifier:raise CanvasError('Контрольная сумма оригинала не совпала.')
            originals[identifier]=(content,Path(name).name)
        for identifier,(content,name) in originals.items():store.import_bytes(content,name)
        expected=json_canvas(document,files)
        if data['nodes']==expected['nodes'] and data['edges']==expected['edges']:return document
        # Another JSON Canvas editor may change the core while preserving unknown
        # properties. Apply those edits; never let the extension mask them.
        core=import_canvas(path,store,_core_only=True)
        by_external={node['attributes']['json_canvas_id']:node for node in core['entities']}
        own={node['id']:node for node in document['entities']};instances=document['view'].get('instances',{})
        original_nodes={node['id']:node for node in expected['nodes']};mapping={}
        for external,node in by_external.items():
            identifier=external if external in own or external in instances else node['id'];mapping[node['id']]=identifier
            if identifier not in own and identifier not in instances:document['entities'].append(deepcopy(node));own[identifier]=document['entities'][-1]
            row=next(row for row in data['nodes'] if row['id']==external);old=original_nodes.get(external,{})
            if any(row.get(key)!=old.get(key) for key in ('x','y','width','height')):
                position=core['view']['positions'][node['id']]
                if identifier in instances:instances[identifier]['position']=position
                else:document['view']['positions'][identifier]=position
                document['view'].setdefault('card_sizes',{})[identifier]=core['view']['card_sizes'][node['id']]
            annotation=document['annotations'].setdefault(identifier,{})
            if row.get('type')=='text' and row.get('text')!=old.get('text'):annotation['markdown']=str(row.get('text',''))[:20000]
            if row.get('type')=='group' and row.get('label')!=old.get('label'):annotation['label']=str(row.get('label',''))[:300]
            if row.get('type')=='link' and row.get('url')!=old.get('url'):
                annotation['markdown']='Ссылка, изменённая в импортированном JSON Canvas: '+str(row.get('url',''))[:2000]
            if row.get('color')!=old.get('color'):
                if row.get('color'):annotation['color']=str(row['color'])[:20]
                else:annotation.pop('color',None)
        visible=set(mapping.values());removed=(set(own)|set(instances))-visible
        document['view']['hidden']=list(dict.fromkeys(document['view']['hidden']+sorted(removed)))
        for node in core['entities']:
            identifier=mapping[node['id']];parent=node['attributes'].get('parent_group_id')
            if identifier in instances:
                if parent:instances[identifier]['parent_group_id']=mapping[parent]
                else:instances[identifier].pop('parent_group_id',None)
            else:
                if parent:own[identifier]['attributes']['parent_group_id']=mapping[parent]
                else:own[identifier]['attributes'].pop('parent_group_id',None)
        previous_edges={row['id']:row for row in expected['edges']};actual_edges={row['id']:row for row in data['edges']}
        existing={row['id']:row for row in document['relations']};retained=[]
        for relation in document['relations']:
            # Observations stay immutable even when another editor removes a line.
            if relation.get('origin')!='analyst' or relation['id'] in actual_edges and actual_edges[relation['id']]==previous_edges.get(relation['id']):retained.append(relation)
        document['relations']=retained
        for relation in core['relations']:
            external=relation['attributes']['json_canvas_id']
            if external in existing and actual_edges[external]==previous_edges.get(external):continue
            relation=deepcopy(relation)
            relation['from_id']=mapping[relation['from_id']];relation['to_id']=mapping[relation['to_id']]
            relation['attributes'].update(visual_from_id=relation['from_id'],visual_to_id=relation['to_id'])
            document['relations'].append(relation)
        return validate(document)
    document=new_document(path.stem);mapping={};geometry={}
    for row in data['nodes']:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in mapping:raise CanvasError('Повторный или неизвестный узел JSON Canvas.')
        values=[row.get(key) for key in ('x','y','width','height')]
        if any(type(v) is not int or abs(v)>10_000_000 for v in values) or min(values[2:])<=0:raise CanvasError('Некорректная геометрия JSON Canvas.')
        x,y,w,h=values;kind=row.get('type');attrs={};note=''
        if kind=='group':node_type='entity_group';label=str(row.get('label') or 'Группа')[:300]
        elif kind=='link':
            node_type='website';label=row.get('url','');attrs={'url':label}
        elif kind=='file':
            name=row.get('file','');_safe_name(name)
            if Path(name).suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
                image=store.import_bytes(read_file(name),Path(name).name);node_type='image';label=image['name']
                attrs={'attachment_id':image['id'],'original_image':True,'media':{**{k:image[k] for k in ('id','name','mime','width','height','bytes','sha256')},'kind':'local_attachment','state':'ready'}}
            else:node_type='document';label=Path(name).name;note='Относительная ссылка JSON Canvas: '+name
        elif kind=='text':node_type='analyst_note';note=str(row.get('text',''))[:20000];label=(note.splitlines() or ['Заметка'])[0].lstrip('# ')[:300] or 'Заметка'
        else:raise CanvasError('Неизвестный тип JSON Canvas.')
        identifier=add_node(document,{'type':node_type,'label':label,'value':label,'markdown':note,'position':{'x':x+w/2,'y':y+h/2}})
        node=next(node for node in document['entities'] if node['id']==identifier);node['attributes'].update(attrs)
        node['attributes']['json_canvas_id']=row['id']
        document['view']['card_sizes'][identifier]={'width':max(160,min(2400 if kind=='group' else 720,w)),'height':max(72,min(1800 if kind=='group' else 640,h))}
        if row.get('color'):document['annotations'][identifier]={'color':str(row['color'])[:20]}
        mapping[row['id']]=identifier;geometry[identifier]=(x,y,w,h)
    for row in data['nodes']:
        identifier=mapping[row['id']];x,y,w,h=geometry[identifier]
        candidates=[(gw*gh,group) for group,(gx,gy,gw,gh) in geometry.items() if group!=identifier and next(n for n in document['entities'] if n['id']==group)['type']=='entity_group' and gx<=x and gy<=y and x+w<=gx+gw and y+h<=gy+gh and gw*gh>w*h]
        if candidates:next(n for n in document['entities'] if n['id']==identifier)['attributes']['parent_group_id']=min(candidates)[1]
    for row in data['edges']:
        if not isinstance(row,dict) or row.get('fromNode') not in mapping or row.get('toNode') not in mapping:raise CanvasError('Связь JSON Canvas ссылается на неизвестный объект.')
        a,b=mapping[row['fromNode']],mapping[row['toNode']];kind=str(row.get('label') or 'potentially_related')[:100]
        from_arrow=row.get('fromEnd','none')=='arrow';to_arrow=row.get('toEnd','arrow')=='arrow'
        if from_arrow and not to_arrow:a,b=b,a
        direction='bidirectional' if from_arrow and to_arrow else 'directed' if from_arrow or to_arrow else 'undirected'
        from .research_canvas import apply
        document=apply(document,'edge',{'from_id':a,'to_id':b,'relation_type':kind,'direction':direction,'status':'unverified'})
        document['relations'][-1]['attributes']['json_canvas_id']=row.get('id','')
    return validate(document)


def import_document(path,store):
    path=Path(path)
    if path.suffix.lower()=='.zip':return import_package(path,store)
    if path.stat().st_size>MAX_BYTES*2:raise CanvasError('Описание расследования превышает лимит.')
    if path.suffix.lower()=='.canvas':return import_canvas(path,store)
    return validate(_json(path.read_bytes()))
