from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import zipfile

from PIL import Image
import pytest

from grangerpet.canvas_portable import export_package,export_canvas,import_document,json_canvas
from grangerpet.research_canvas import CanvasError,add_node,apply,new_document


class Images:
    def __init__(self):self.values={}
    def import_bytes(self,data,name):
        with Image.open(BytesIO(data)) as image:w,h=image.size
        identifier='img_'+sha256(data).hexdigest()
        self.values[identifier]=(data,{'id':identifier,'bytes':len(data),'sha256':identifier[4:],'mime':'image/png','name':name,'width':w,'height':h})
        return deepcopy(self.values[identifier][1])
    def get(self,identifier):return deepcopy(self.values[identifier][1])
    def read_bytes(self,identifier):return self.values[identifier][0]


def fixture():
    images=Images();stream=BytesIO();Image.new('RGB',(310,170),'#305871').save(stream,'PNG');original=stream.getvalue()
    image=images.import_bytes(original,'Оригинал.png');doc=new_document('Переносимое расследование')
    note=add_node(doc,{'type':'analyst_note','label':'Гипотеза','markdown':'Русский **Markdown**','position':{'x':-12.5,'y':219.5}})
    picture=add_node(doc,{'type':'image','label':'Оригинал'})
    next(n for n in doc['entities'] if n['id']==picture)['attributes'].update(attachment_id=image['id'],original_image=True,media={**image,'kind':'local_attachment'})
    doc=apply(doc,'edge',{'from_id':note,'to_id':picture,'relation_type':'references','direction':'bidirectional','status':'inferred','confidence':65,'note':'Проверить источник'})
    return images,doc,original,image


def test_package_includes_exact_originals_and_json_canvas_and_lossless_model(tmp_path):
    images,doc,original,image=fixture();target=tmp_path/'investigation.granger.zip'
    export_package(target,doc,images)
    with zipfile.ZipFile(target) as archive:
        canvas=json.loads(archive.read('investigation.canvas'))
        path=next(n['file'] for n in canvas['nodes'] if n['type']=='file')
        assert archive.read(path)==original
        assert canvas['edges'][0]['fromEnd']==canvas['edges'][0]['toEnd']=='arrow'
        assert all(type(n[k]) is int for n in canvas['nodes'] for k in ('x','y','width','height'))
    destination=Images();restored=import_document(target,destination)
    assert restored==doc and destination.read_bytes(image['id'])==original


def test_json_canvas_sidecar_roundtrip_and_no_secret_profile_paths(tmp_path):
    images,doc,original,image=fixture();target=tmp_path/'Перенос.canvas'
    export_canvas(target,doc,images)
    raw=target.read_text(encoding='utf-8');assert 'C:\\Users' not in raw
    destination=Images();assert import_document(target,destination)==doc
    assert destination.read_bytes(image['id'])==original


def test_other_canvas_editor_changes_override_stale_extension_and_keep_originals(tmp_path):
    images,doc,original,image=fixture();target=tmp_path/'edited.canvas';export_canvas(target,doc,images)
    data=json.loads(target.read_text(encoding='utf-8'));note=next(n for n in data['nodes'] if n['type']=='text')
    note.update(x=700,y=-300,text='Изменённая заметка')
    data['nodes'].append({'id':'foreign-new','type':'text','x':1200,'y':0,'width':240,'height':150,'text':'Новый объект'})
    data['edges'].append({'id':'foreign-edge','fromNode':note['id'],'toNode':'foreign-new','label':'references'})
    target.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    destination=Images();restored=import_document(target,destination)
    assert len(restored['entities'])==3 and len(restored['relations'])==2
    assert restored['view']['positions'][note['id']]=={'x':820.0,'y':-230.0}
    assert restored['annotations'][note['id']]['markdown']=='Изменённая заметка'
    assert destination.read_bytes(image['id'])==original


def test_standard_canvas_text_link_group_edges_and_adjacent_image(tmp_path):
    images,_,original,_=fixture();(tmp_path/'photo.png').write_bytes(original)
    raw={'nodes':[
        {'id':'group','type':'group','x':-100,'y':-100,'width':900,'height':700,'label':'Область'},
        {'id':'note','type':'text','x':0,'y':0,'width':240,'height':150,'text':'# Проверка\nРусский текст'},
        {'id':'link','type':'link','x':300,'y':0,'width':250,'height':150,'url':'https://example.org'},
        {'id':'image','type':'file','x':0,'y':250,'width':310,'height':220,'file':'photo.png'}],
        'edges':[{'id':'edge','fromNode':'note','toNode':'link','label':'ссылается','toEnd':'arrow','fromEnd':'none'}]}
    path=tmp_path/'standard.canvas';path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    doc=import_document(path,Images());assert len(doc['entities'])==4 and len(doc['relations'])==1
    note=next(n for n in doc['entities'] if n['type']=='analyst_note');assert doc['view']['positions'][note['id']]=={'x':120.0,'y':75.0}
    assert note['attributes']['markdown']=='# Проверка\nРусский текст' and note['attributes']['parent_group_id']


@pytest.mark.parametrize('name',['../private.png','C:/private.png','/private.png','assets/../../private.png','assets\\private.png'])
def test_standard_canvas_rejects_external_file_before_opening(tmp_path,name):
    path=tmp_path/'unsafe.canvas';path.write_text(json.dumps({'nodes':[{'id':'x','type':'file','file':name,'x':0,'y':0,'width':240,'height':150}],'edges':[]}),encoding='utf-8')
    with pytest.raises(CanvasError):import_document(path,Images())


def test_zip_rejects_traversal_duplicate_and_tampered_original_without_extracting(tmp_path):
    images,doc,_,_=fixture();good=tmp_path/'good.zip';export_package(good,doc,images)
    for name,extra in [('traversal','../outside.txt'),('unknown','extra.txt')]:
        path=tmp_path/(name+'.zip');path.write_bytes(good.read_bytes())
        with zipfile.ZipFile(path,'a') as archive:archive.writestr(extra,b'bad')
        destination=Images()
        with pytest.raises(CanvasError):import_document(path,destination)
        assert not destination.values
    path=tmp_path/'tampered.zip'
    with zipfile.ZipFile(good) as source,zipfile.ZipFile(path,'w') as archive:
        for info in source.infolist():archive.writestr(info.filename,b'bad' if info.filename.startswith('assets/') else source.read(info.filename))
    with pytest.raises(CanvasError,match='сумма'):import_document(path,Images())


def test_missing_original_cannot_produce_deceptive_successful_package(tmp_path):
    _,doc,_,_=fixture();target=tmp_path/'no.zip'
    with pytest.raises(KeyError):export_package(target,doc,Images())
    assert not target.exists()
