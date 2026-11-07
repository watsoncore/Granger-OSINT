"""Owned native graph acceptance. Uses isolated encrypted fixtures, never the user profile."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import os

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.qa_clean_release import isolated_environment,wait_for,QaFailure
from scripts.qa_workspace_v7 import V7Session
from scripts.qa_canvas_stress import observed_document,evidence_digest


def run(exe,out,source=False,skip_dpi=False,*,observed_result,observed_profiles,matrix_only=False,search_only=False):
    frontend_build=None
    if source:
        from scripts.build_release import build_frontend
        frontend_build=build_frontend(ROOT,os.environ.copy())
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore,new_document,apply,record_canvas_event
    from grangerpet.graph_store import GraphViewStore
    import uuid
    app=QCoreApplication.instance() or QCoreApplication([])
    out.mkdir(parents=True,exist_ok=False)
    report={'origin':'native-source' if source else 'frozen-EXE','frontend_build':frontend_build,'exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),'checks':[],'captures':[],'geometry':[],'passed':False,'fresh_osint_searches_requested':0,'remote_previews':'Production renderer can fetch thumbnails from supplied observations; these are not new OSINT searches.'}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    def check(name,condition):
        report['checks'].append({'name':name,'passed':bool(condition)});save();print(json.dumps(report['checks'][-1]),flush=True)
        if not condition:raise QaFailure(name)
    if not source:
        from scripts.qa_clean_release import frozen_frontend_current
        check('frozen_frontend_matches_current_build',frozen_frontend_current(exe))
    with isolated_environment(out):
        SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
        store=CanvasStore(InvestigationJournal(out/'appdata/GrangerPet/investigations'))
        documents={'empty':store.save(new_document('V10 · Новое расследование'),0)}
        import base64,io
        from PIL import Image
        from scripts.qa_canvas_stress import synthetic_document
        pixels=io.BytesIO();Image.new('RGB',(64,64),'#427277').save(pixels,'PNG')
        mixed=synthetic_document(50,'data:image/png;base64,'+base64.b64encode(pixels.getvalue()).decode())
        mixed=apply(mixed,'group',{'ids':[node['id'] for node in mixed['entities'][:3]],'label':'Группа QA'})
        record_canvas_event(mixed,'group',[mixed['entities'][-1]['id']],count=3)
        documents['mixed']=store.save(mixed,0)
        inputs={'crypto':(observed_result,'blockchain_gansar'),'social':(observed_profiles,'username_maigret')}
        for key,(path,tool) in inputs.items():
            document,receipt=observed_document(path,tool)
            document['title']='V10 · '+('Криптовалютное исследование' if key=='crypto' else 'Публичные профили')
            documents[key]=store.save(document,0)
        journal=InvestigationJournal(out/'appdata/GrangerPet/investigations')
        from grangerpet.investigation import new_investigation
        record,protocol=new_investigation(json.loads(observed_result.read_text(encoding='utf-8'))['query'])
        saved_search=record['id'];record['status']='completed'
        journal.save_checkpoint({**protocol,'version':1,'id':saved_search,'record':record,
                                 'evidence':documents['crypto']['evidence'],'executions':[]})
        search_views=GraphViewStore(journal)
        legacy_positions=documents['crypto']['view']['positions']
        search_views.save(saved_search,{'version':1,'mode':'graph','positions':legacy_positions})
        search_views.select(saved_search)
        session=V7Session(exe,out,source)
        def capture(name,geometry=True):
            name=name.replace('.','p')  # Snapshot filenames use the existing ASCII allowlist.
            session.idle();dom=session.dom()
            if geometry:
                layout=wait_for(lambda:session.dom().get('graphLayout'),8)
                report['geometry'].append({'name':name,**layout});save()
                check(name+'_no_chrome_overlap',not layout['overlaps'])
                check(name+'_no_control_overlap',not layout.get('controlOverlaps'))
                check(name+'_no_horizontal_control_clipping',not layout.get('clippedControls'))
                heights=[row['height'] for row in layout.get('commandControls',[])]
                if heights:check(name+'_aligned_command_heights',max(heights)-min(heights)<1.5)
                check(name+'_no_page_overflow',not dom.get('overflow'))
            elif dom.get('graphLayout'):
                layout=dom['graphLayout'];report['geometry'].append({'name':name,'popup_only':True,**layout})
                check(name+'_popup_within_viewport',not layout.get('popupOverflow'))
            session.command('qa_snapshot',{'name':name})
            image=out/(name+'-search.png');wait_for(lambda:image.is_file() and image.stat().st_size>10000,12)
            report['captures'].append({'name':image.name,'sha256':hashlib.sha256(image.read_bytes()).hexdigest()});save()
        def open_doc(key):
            session.action('research_canvas_open',{'id':documents[key]['id']})
            wait_for(lambda:session.document().get('id')==documents[key]['id'])
            session.idle()
        def style(value):
            if json.loads(session.snapshot()['settings'].get('workspace_appearance') or '{}').get('graphStyle','glass')==value:return
            identifier=session.settled()['id']
            durable=store.load(identifier)
            preserved=lambda doc:{key:doc.get(key,[]) for key in ('entities','relations','evidence','annotations','activity')}|{'positions':doc['view']['positions'],'instances':doc['view'].get('instances',{}),'card_sizes':doc['view'].get('card_sizes',{})}
            before=evidence_digest(preserved(durable))
            for attempt in range(3):
                if json.loads(session.snapshot()['settings'].get('workspace_appearance') or '{}').get('graphStyle','glass')==value:break
                try:
                    session.click('Настройки');session.click('Оформление')
                    target='Minimal Graph' if value=='minimal' else 'Glass Graph'
                    wait_for(lambda:(e:=session.find(target)[0]) and e.get('hit'),8)
                    session.click(target)
                    wait_for(lambda:(e:=session.find('Применить')[0]) and not e.get('disabled'),8)
                    session.click('Применить')
                    wait_for(lambda:json.loads(session.snapshot()['settings']['workspace_appearance'])['graphStyle']==value,6)
                    break
                except QaFailure:
                    (out/f'style-retry-{value}-{attempt}-private.json').write_text(json.dumps(session.dom(),ensure_ascii=False),encoding='utf-8')
                    if attempt==2:raise
            session.click('Поиск');session.click('Мой граф');session.idle()
            wait_for(lambda:session.dom().get('graphLayout',{}).get('style')==value,8)
            check('style_'+value+'_preserves_saved_facts_and_positions',before==evidence_digest(preserved(store.load(identifier))))
        try:
            if search_only:
                session.start(0);session.click('Поиск');session.click('Поиск и результаты')
                session.action('investigation_graph_get',{'id':saved_search})
                wait_for(lambda:any(row.get('role')=='tab' and row.get('text')=='Обзор' for row in session.dom().get('elements',[])),15)
                session.click('Открыть дерево');session.action('graph_scroll')
                wait_for(lambda:int((session.dom().get('graph',{}).get('canvas') or {}).get('drawnNodes',0))>0,30)
                session.click('Вписать граф в окно')
                wait_for(lambda:int((session.dom().get('graph',{}).get('canvas') or {}).get('onScreenNodes',0))>0,10)
                capture('saved-tree-fitted',False)
                check('saved_tree_renders_observed_data',True)
                check('legacy_positions_unchanged_after_tree_fit',search_views.load(saved_search)['positions']==legacy_positions)
                report['passed']=True;save();return report
            if not matrix_only:
                session.start(0);session.click('Поиск');session.click('Мой граф');open_doc('empty')
                capture('01-empty-glass');style('minimal');capture('02-empty-minimal')
                open_doc('mixed')
                for visual in ('glass','minimal','glass'):
                    style(visual)
                capture('mixed-images-groups-preserved')
                kept=store.load(documents['mixed']['id'])
                check('mixed_contains_images_groups_relations_history',
                      any(node['type']=='image' and node['attributes'].get('media') for node in kept['entities'])
                      and any(node['type']=='entity_group' for node in kept['entities'])
                      and bool(kept['relations']) and bool(kept['activity']))
                for kind in ('social','crypto'):
                    open_doc(kind)
                    for visual in ('minimal','glass'):
                        style(visual);session.click('Показать всё');capture(kind+'-'+visual)
                        if kind=='crypto':
                            metrics=session.metrics()['canvas'];wallets={node['id'] for node in session.document()['entities'] if node['type']=='blockchain_address'}
                            visible=[node for node in json.loads(metrics['qaNodes']) if node['id'] in wallets and 100<node['x']<metrics['width']-100 and 180<node['y']<metrics['height']-150]
                            wallet=min(visible,key=lambda node:(node['x']-metrics['width']/2)**2+(node['y']-metrics['height']/2)**2)
                            at=[metrics['x']+wallet['x'],metrics['y']+wallet['y']]
                            session.action('input',{'kind':'click','at':at})
                            for _ in range(36):
                                if float(session.metrics()['canvas'].get('zoom',1))>=.7:break
                                session.action('input',{'kind':'wheel','at':at,'delta':480})
                            check('readable_card_zoom_'+visual,float(session.metrics()['canvas']['zoom'])>=.7)
                            session.click('Сведения');capture('crypto-card-'+visual)
                            check('crypto_canvas_icons_'+visual,int(session.metrics()['canvas'].get('drawnCryptoIcons',0))>0)
                            session.click('Закрыть редактор')
                session.click('Новый объект');session.pick('Тип нового узла','Криптокошелёк','Криптокошелёк')
                session.click('Сеть нового объекта');capture('crypto-network-selector',False)
                icons=session.dom()['graphLayout']['icons'];check('network_selector_real_icons_loaded',len(icons)>=6 and all(row['loaded'] for row in icons))
                session.action('input',{'kind':'key','key':'escape'});session.click('Закрыть редактор')
                session.click('Настроить граф');capture('07-command-bar')
                session.click('Фильтры');capture('08-filter-menu',False)
                boxes=[row for row in session.dom()['elements'] if row.get('type')=='checkbox' and row.get('hit') and row.get('width',0)>0]
                check('filter_has_source_and_minimap_controls',len(boxes)==2)
                box=boxes[1];session.action('input',{'kind':'click','at':[box['x']+box['width']/2,box['y']+box['height']/2]})
                session.action('input',{'kind':'key','key':'escape'})
                session.click('Настроить граф')
                capture('08b-minimap-safe-zone')
                session.click('Показать редактор');capture('09-inspector')
                document=session.settled()
                session.action('research_canvas_from_search',{'id':document['id'],'revision':document['revision'],'investigation_id':saved_search})
                wait_for(lambda:session.canvas().get('preview'),10)
                session.click('Результаты для добавления');capture('09b-inspector-and-results')
                session.click('Закрыть результаты')
                # Camera dimensions and camera values remain stable across panel visibility.
                before=session.metrics()['canvas']
                session.click('Скрыть редактор');after=session.metrics()['canvas']
                check('dock_does_not_move_camera',all(before.get(key)==after.get(key) for key in ('width','height','zoom','panX','panY')))
                for width,height in ((1366,768),(1600,900),(1920,1080),(2560,1440)):
                    session.command('qa_window_mode',{'size':[width,height],'mode':'size'})
                    capture(f'window-{width}x{height}')
                session.click('Чистое расследование');capture('10-clean-expanded')
                session.action('window',{'mode':'fullscreen'});capture('11-clean-fullscreen')
                session.action('input',{'kind':'key','key':'escape'});session.click('Чистое расследование')
                session.click('Встроить');capture('12-normal-restored')
                session.click('Настройки');session.click('Оформление');capture('13-style-settings',False)
                session.click('Minimal Graph');session.click('Применить')
                facts={key:evidence_digest(store.load(documents['crypto']['id']).get(key,[])) for key in ('entities','relations','evidence','annotations','activity')}
                session.stop();session.start(1);session.click('Поиск');session.click('Мой граф');open_doc('crypto')
                check('minimal_persists_after_restart',wait_for(lambda:session.dom().get('graphLayout',{}).get('style')=='minimal'))
                check('style_roundtrip_preserves_facts',facts=={key:evidence_digest(store.load(documents['crypto']['id']).get(key,[])) for key in facts})
                capture('14-restarted-minimal')
                session.click('Поиск и результаты')
                session.action('investigation_graph_get',{'id':saved_search})
                wait_for(lambda:any(row.get('role')=='tab' and row.get('text')=='Обзор' for row in session.dom().get('elements',[])),15)
                check('saved_search_has_no_graph_tab',not any(row.get('role')=='tab' and row.get('text')=='Граф' for row in session.dom()['elements']))
                for key,name in (('overview','Обзор'),('tree','Дерево'),('evidence','Доказательства')):
                    session.click(name,role='tab');wait_for(lambda:session.dom().get('graph',{}).get('graphMode')==key,10);capture('search-'+key,False)
                check('legacy_positions_preserved',search_views.load(saved_search)['positions']==legacy_positions)
                session.click('Мой граф');capture('15-my-graph-preserved')
            # Qt scale-factor emulation over this host's unchanged Windows DPI.
            report['dpi_method']='Qt scale-factor emulation, Windows DPI unchanged; actual WebEngine DPR recorded per case'
            for number,(factor,expected) in enumerate(() if skip_dpi else ((1,1.25),(.8,1),(1.2,1.5),(1.6,2)),2):
                session.stop();os.environ['QT_SCALE_FACTOR']=str(factor);session.start(number)
                session.click('Поиск');session.click('Мой граф');open_doc('crypto')
                for width,height in ((1366,768),(1600,900),(1920,1080),(2560,1440)):
                    for visual in ('minimal','glass'):
                        # Prepare controls on the available monitor before testing
                        # a virtual window larger than its physical pixel bounds.
                        session.command('qa_window_mode',{'mode':'maximized'})
                        style(visual)
                        session.command('qa_window_mode',{'size':[width,height],'mode':'size'})
                        wait_for(lambda:abs(session.dom().get('width',0)-width)<2,8)
                        capture(f'dpr-{expected}-{width}-{visual}')
                        session.command('qa_window_mode',{'mode':'maximized'})
                        session.click('Показать редактор')
                        session.command('qa_window_mode',{'size':[width,height],'mode':'size'})
                        wait_for(lambda:abs(session.dom().get('width',0)-width)<2,8)
                        capture(f'dpr-{expected}-{width}-{visual}-inspector')
                        session.command('qa_window_mode',{'mode':'maximized'});session.click('Скрыть редактор')
                check('actual_dpr_'+str(expected),abs(session.dom()['graphLayout']['dpr']-expected)<.02)
            report['passed']=True;save()
        except BaseException as error:
            report.update(error_type=type(error).__name__,error=str(error)[:180]);save()
            (out/'failed-dom-private.json').write_text(json.dumps(session.dom(),ensure_ascii=False),encoding='utf-8')
            (out/'failed-state-private.json').write_text(json.dumps(session.snapshot(),ensure_ascii=False),encoding='utf-8')
            capture('failed-tree' if search_only else 'failed-graph',False)
            raise
        finally:session.stop()
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',action='store_true');p.add_argument('--skip-dpi',action='store_true');p.add_argument('--matrix-only',action='store_true');p.add_argument('--search-only',action='store_true')
    p.add_argument('--observed-result',type=Path,required=True);p.add_argument('--observed-profiles',type=Path,required=True)
    a=p.parse_args()
    run(a.exe.resolve(),a.output.resolve(),a.source,a.skip_dpi,observed_result=a.observed_result.resolve(),observed_profiles=a.observed_profiles.resolve(),matrix_only=a.matrix_only,search_only=a.search_only)
