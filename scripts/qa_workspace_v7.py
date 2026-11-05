"""Owned Windows V7 canvas acceptance using real Qt pointer/keyboard events.

Manual entities are explicitly analyst assertions. Public tools are a separate,
opt-in phase; this offline interaction receipt never claims live OSINT results.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure,validate_report_path
from scripts.qa_v5_acceptance import V5Session
from scripts.qa_v4_investigation import TON

EVM='0x6B175474E89094C44Da98b954EedeAC495271d0F'
FORMS=(
    ('Человек','Имя или подпись','Аналитический объект A',None),
    ('Компания / организация','Название','Northstar Labs',None),
    ('Никнейм','Никнейм','solvnox',None),('Email','Email','octocat@github.com',None),
    ('Телефон','Телефон','+12025550123',None),('IP-адрес','IP-адрес','66.249.67.41',None),
    ('Домен','Домен','example.org',None),('URL','URL','https://example.org/path',None),
    ('Профиль','Ссылка на профиль','https://github.com/octocat',None),
    ('Криптокошелёк','Адрес кошелька',TON,'TON'),('Транзакция','Хеш транзакции','a'*64,None),
    ('NFT','Адрес NFT',TON,'TON'),('Токен','Адрес токена',EVM,'Ethereum'),
    ('Контракт','Адрес контракта',EVM,'Ethereum'),('Коллекция','Адрес коллекции',TON,'TON'),
    ('Документ','Ссылка или название документа','Публичный документ',None),
    ('Географическая точка','Координаты','51.50, -0.12',None),
    ('Заметка','Название заметки','Проверить независимые источники',None),
    ('Гипотеза','Гипотеза','Возможная связь требует проверки',None),
    ('Произвольный объект','Название объекта','Дополнительный объект',None),
)


class V7Session(V5Session):
    def create_v7(self,kind,field,value,chain=None):
        self.click('Новый объект');self.pick('Тип нового узла',kind,kind)
        if chain:self.pick('Сеть нового объекта',chain,chain)
        self.fill(field,value);before=self.settled();ids={node['id'] for node in before['entities']}
        self.click('Добавить объект');wait_for(lambda:self.document().get('revision',0)>before['revision'])
        added=[node for node in self.settled()['entities'] if node['id'] not in ids]
        if len(added)!=1:raise QaFailure('typed_form_not_durably_created_'+kind)
        return added[0]

    def point(self,identifier,*,port=False,header=False,corner=False):
        canvas=self.metrics()['canvas'];node=next((n for n in json.loads(canvas.get('qaNodes','[]')) if n['id']==identifier),None)
        if not node:raise QaFailure('expected_visible_node_geometry')
        x=node['x']+(node['width']/2-3 if corner else node['width']/2 if port else 0)
        y=node['y']+(node['height']/2-5 if corner else -node['height']/2+16 if header else 0)
        return [canvas['x']+x,canvas['y']+y]


def run(exe,report_path,shots,*,source=False):
    from PySide6.QtCore import QCoreApplication
    from PIL import Image,ImageDraw
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    app=QCoreApplication.instance() or QCoreApplication([])
    report_path.parent.mkdir(parents=True,exist_ok=True);shots.mkdir(parents=True,exist_ok=True)
    result={'origin':'native-source' if source else 'frozen-Windows-EXE','passed':False,
        'exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
        'manual_entities':True,'live_osint_executed':False,'checks':[],'captures':[]}
    def save():report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,condition):
        result['checks'].append({'name':name,'passed':bool(condition)});save();print(json.dumps(result['checks'][-1]),flush=True)
        if not condition:raise QaFailure(name)
    with tempfile.TemporaryDirectory(prefix='.granger-v7-qa-',dir=ROOT) as name:
        directory=Path(name).resolve();assert directory.parent==ROOT.resolve()
        with isolated_environment(directory):
            SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
            session=V7Session(exe,directory,source)
            def capture(name):
                session.command('qa_snapshot',{'name':name});path=directory/(name+'-search.png')
                def ready_image():
                    try:
                        with Image.open(path) as image:image.verify()
                        return path.stat().st_size>0
                    except (OSError,ValueError):return False
                wait_for(ready_image,10);target=shots/(name+'.png');target.write_bytes(path.read_bytes())
                result['captures'].append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()});save()
            try:
                session.start(0);session.click('Поиск');session.click('Моё полотно');session.click('Новое')
                wait_for(lambda:session.document().get('id'));session.ensure_expanded()
                check('canvas_first_default_panels_closed',not session.find('Редактор полотна')[0] and not session.find('Индекс контрагентов')[0])
                nodes=[]
                for kind,field,value,chain in FORMS:
                    nodes.append(session.create_v7(kind,field,value,chain));check('typed_form_'+kind,True)
                document=session.settled();identifier=document['id']
                check('twenty_manual_objects_without_fabricated_evidence',len(document['entities'])==20 and document['evidence']==[])
                session.click('Закрыть редактор');session.click('Показать всё');session.idle();capture('manual20')
                # Center through the finite viewport command, then connect actual ports.
                a,b=nodes[0]['id'],nodes[1]['id'];session.select(a);session.idle()
                session.action('input',{'kind':'drag','at':session.point(a,port=True),'to':session.point(b)})
                wait_for(lambda:session.find('Уверенность аналитика')[0]);session.fill('Уверенность аналитика','65')
                session.fill('Источник связи','https://example.org/source');session.fill('Комментарий к связи','Ручная гипотеза для проверки')
                session.click('Направление связи');session.action('input',{'kind':'key','key':'home'})
                session.action('input',{'kind':'key','key':'down'});session.action('input',{'kind':'key','key':'down'});session.action('input',{'kind':'key','key':'enter'})
                capture('relation-dialog');session.click('Сохранить связь')
                wait_for(lambda:len(session.document()['relations'])==1);session.idle()
                edge=session.settled()['relations'][0]
                check('native_port_drag_and_relation_metadata',edge['direction']=='bidirectional' and edge['attributes']['analyst_confidence']==65 and edge['source_urls']==['https://example.org/source'] and edge['claim_kind']=='analyst_assertion')
                session.click('Отменить');wait_for(lambda:not session.document()['relations'])
                session.click('Повторить');wait_for(lambda:len(session.document()['relations'])==1)
                check('native_relation_undo_redo',True)
                # Real additive pointer selection and floating group command.
                session.action('input',{'kind':'click','at':session.point(b),'ctrl':True});session.click('Группа')
                wait_for(lambda:any(n['type']=='entity_group' for n in session.document()['entities']));session.idle()
                group=next(n for n in session.document()['entities'] if n['type']=='entity_group')
                position=session.document()['view']['positions'][group['id']]
                session.viewport_patch({'x':680-position['x'],'y':410-position['y'],'scale':1})
                session.action('input',{'kind':'click','at':session.point(group['id'],header=True)});session.idle()
                before=deepcopy(session.document()['view']['positions']);start=session.point(group['id'],header=True)
                session.action('input',{'kind':'drag','at':start,'to':[start[0]+40,start[1]+24]});session.idle()
                after=session.document()['view']['positions']
                group_metrics=session.metrics()['canvas'];check('expanded_group_keeps_members_and_relation_visible',int(group_metrics['modelNodes'])==21 and int(group_metrics['modelEdges'])==1)
                check('native_group_drag_preserves_descendant_offsets',all(abs(after[i]['x']-before[i]['x']-40)<2 and abs(after[i]['y']-before[i]['y']-24)<2 for i in (a,b,group['id'])))
                size_before=session.document()['view']['card_sizes'][group['id']];start=session.point(group['id'],corner=True)
                session.action('input',{'kind':'drag','at':start,'to':[start[0]+40,start[1]+35]});session.idle()
                size_after=session.document()['view']['card_sizes'][group['id']]
                result['group_resize']={'before':size_before,'after':size_after,'pointer':start,'viewport':session.document()['view']['viewport']};capture('group-resize');save()
                check('native_group_resize',size_after['width']>size_before['width'] and size_after['height']>size_before['height'])
                session.click('Свернуть / раскрыть');session.idle();check('native_group_collapse',group['id'] in session.document()['view']['collapsed'])
                session.click('Свернуть / раскрыть');session.idle();check('native_group_expand',group['id'] not in session.document()['view']['collapsed'])
                capture('group-workspace')
                # Existing import dialog, local source path, exact original bytes.
                picture=directory/'original.png'
                with Image.new('RGB',(640,320),'#264456') as image:
                    ImageDraw.Draw(image).text((30,30),'ORIGINAL V7 QA',fill='#e5c79b');image.save(picture)
                session.click('Добавить изображение');session.fill('Путь на диске или публичный HTTPS-адрес',str(picture))
                session.click('Загрузить');wait_for(lambda:any(n['type']=='image' for n in session.document()['entities']));session.idle()
                store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'));saved=store.load(identifier)
                image_node=next(n for n in saved['entities'] if n['type']=='image')
                from grangerpet.geoint_tools import attachment_store
                images=attachment_store(directory/'appdata/GrangerPet')
                check('native_image_import_preserves_original',images.read_bytes(image_node['attributes']['attachment_id'])==picture.read_bytes())
                session.click('Показать всё');capture('image-workspace')
                # Confirm the whole composition survives the process boundary.
                expected=deepcopy(store.load(identifier));session.stop();session.start(1);session.click('Поиск');session.click('Моё полотно');session.open_document(identifier)
                reopened=store.load(identifier)
                check('restart_preserves_manual_composition',reopened['entities']==expected['entities'] and reopened['relations']==expected['relations'] and reopened['view']==expected['view'] and reopened['evidence']==expected['evidence'])
                result['passed']=True;save()
            except BaseException as error:
                result.update(error_type=type(error).__name__,error=str(error)[:200]);save()
                raise
            finally:session.stop()
    result['temporary_profile_removed']=not directory.exists();save()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--screenshots',type=Path,required=True);parser.add_argument('--source',action='store_true')
    args=parser.parse_args();validate_report_path(args.report)
    run(args.exe.resolve(),args.report.resolve(),args.screenshots.resolve(),source=args.source)


if __name__=='__main__':main()
