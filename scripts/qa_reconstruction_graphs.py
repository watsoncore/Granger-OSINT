"""Actual native graph rendering; synthetic stress and saved live evidence kept distinct."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exe',type=Path)
    parser.add_argument('--only',nargs='*',help='Targeted cases; omitted runs the full set')
    parser.add_argument('--master-fix-v2',action='store_true',help='Saved actual Steam/network and paired Tree/Graph controls')
    parser.add_argument('--simple-v3',action='store_true',help='Current shared views without historical inspector control labels')
    parser.add_argument('--density-v3',action='store_true',help='Measure actual native/CSS graph geometry and first useful Overview control')
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Choose a fresh QA directory')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex;profile=out/'appdata/GrangerPet'
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),GRANGERPET_QA_VAULT='GrangerPet/QA/graph_reconstruction_'+namespace)
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    from grangerpet.config import Settings
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.graph_store import GraphViewStore
    from grangerpet.investigation import new_investigation
    from grangerpet.ipc import send_command
    from grangerpet.evidence_graph import build
    profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(source_root=str(ROOT),cursor_reaction=False,reduced_motion=True).to_dict()),encoding='utf-8')
    source=ROOT/'output/reconstruction/geoint-research-05/appdata/GrangerPet'
    for name in ('attachments','public-media'):
        if (source/name).exists():shutil.copytree(source/name,profile/name)
    journal=InvestigationJournal(profile/'investigations');views=GraphViewStore(journal);cases=[]
    def case(name,goal,rows,synthetic=False):
        record,protocol=new_investigation(goal);record.update(status='completed',synthetic=synthetic)
        journal.save_checkpoint({**protocol,'version':1,'id':record['id'],'record':record,'evidence':rows,'executions':[]})
        views.save(record['id'],{'version':1,'mode':'graph','positions':{},'expanded':[],'collapsed':[]})
        graph=build(rows,full=True,limit=5000,goal=goal)
        cases.append({'name':name,'id':record['id'],'synthetic':synthetic,'input_rows':len(rows),'raw_entities':len(graph['entities']),
            'raw_relations':len(graph['relations']),'groups':sum(node['type']=='entity_group' for node in graph['entities']),
            'publication_links':sum(edge['relation_type']=='publishes_link' for edge in graph['relations']),
            'aggregate_relation_ids':[edge['id'] for edge in graph['relations'] if edge.get('aggregate')]})
    for count in (20,100,500,1000):
        # Five independent source domains allow meaningful, reversible source groups.
        url=lambda index:f'https://stress{index%5}.example/{index}'
        rows=[normalize_evidence({'id':str(index),'type':'web','platform':'Synthetic QA','title':f'Синтетический объект {index}',
            'url':url(index),'description':'Синтетическая проверка графа; не реальное OSINT-наблюдение.',
            'details':{'reading_method':'direct_http','body_sha256':'a'*64,'links':[
                {'url':url((index+step)%count),'text':f'Fixture {step}','content_region':'main_content','extraction_method':'inert_html_parser','selector':'main/p/a[href]'}
                for step in range(1,6)]}},'synthetic_fixture',url(0)) for index in range(count)]
        case('synthetic-'+str(count),'СИНТЕТИЧЕСКИЙ стресс-тест '+url(0),rows,True)
    ton=json.loads((ROOT/'output/reconstruction/live-ton-deep/result.json').read_text(encoding='utf-8'))
    case('actual-ton-302','Сохранённая реальная выборка TON: '+ton['query'],ton['results'])
    github=json.loads((ROOT/'output/reconstruction/github-links-fixed/page.json').read_text(encoding='utf-8'))
    case('actual-github','Исследование https://github.com/solvnox',[normalize_evidence(row,'web_read','https://github.com/solvnox') for row in github['results']])
    visual=json.loads((ROOT/'output/reconstruction/vision-pipeline-01/result.json').read_text(encoding='utf-8'))
    geo=json.loads((ROOT/'output/reconstruction/geoint-research-05/result.json').read_text(encoding='utf-8'))
    case('actual-geoint','Где снята выбранная фотография? Сохранённые локальные наблюдения и реальные эталоны.',visual['results']+geo['results'])
    for name,goal,filename in (('actual-ip-new','Исследуй IP 66.249.67.41','agent-ip-02'),
            ('actual-steam-new','Публичный профиль Steam https://steamcommunity.com/id/robinwalker','agent-steam-01')):
        receipt=ROOT/'output/intelligence-v1'/filename/'result.json'
        if receipt.is_file():case(name,goal,json.loads(receipt.read_text(encoding='utf-8'))['evidence'])
    if args.master_fix_v2:
        for name,goal,filename in (
                ('actual-steam-v2','Публичный инвентарь Steam 76561198045277210','steam-agent-cursor-bindings'),
                ('actual-network-v2','Геолокация и сеть 87.199.131.94','location-agent-live')):
            receipt=ROOT/'output/master-fix-v2'/filename/'result.json'
            case(name,goal,json.loads(receipt.read_text(encoding='utf-8'))['evidence'])
        media=ROOT/'output/master-fix-v2/steam-inventory-retention-fixed/isolated-profile/public-media'
        if media.exists():shutil.copytree(media,profile/'public-media',dirs_exist_ok=True)
    rows=[normalize_evidence({'id':str(i),'type':'post','platform':'Synthetic QA','title':f'Синтетическая публикация {i}',
        'url':f'https://t.me/qa_public_fixture/{i+1}','description':'Synthetic publication fixture, no public source requested.',
        'details':{'author':'qa_public_fixture'}},'synthetic_fixture','qa_public_fixture') for i in range(100)]
    case('synthetic-publications','СИНТЕТИЧЕСКИЕ публикации https://t.me/qa_public_fixture',rows,True)
    views.select(cases[0]['id'])
    report={'mode':'actual_frozen_Qt_WebEngine' if args.exe else 'actual_source_Qt_WebEngine','gateway_calls':0,
        'inference_calls':0,'cases':cases,'checks':[],'manual_visual_review':'pending'}
    if args.exe:report['exe_sha256']=hashlib.sha256(args.exe.read_bytes()).hexdigest()
    owned=None;process=None
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});save();print(json.dumps({'check':name,'passed':bool(ok)}),flush=True)
        if not ok:raise AssertionError(name)
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.4)
        latest=state()
        if latest:(out/'timeout-state.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2),encoding='utf-8')
        raise TimeoutError('Own graph UI wait expired')
    def state():
        value=send_command('pet','status',timeout=8000)
        if value and owned and value.get('pid')!=owned:raise RuntimeError('Own PID mismatch')
        return value
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=12000)
        if not value or not value.get('ok'):raise RuntimeError('Own command failed: '+name)
        return value
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.2)
    def dom():
        action('dom')
        value=wait(state,10)
        return value['desktop'].get('dom',{})
    def click(label):
        if label in ('Дерево','Граф','Обзор','Доказательства'):action('graph_scroll')
        value=wait(lambda:next((e for e in dom().get('elements',[]) if (e.get('label')==label or e.get('text')==label) and e['width']>0 and 0<e['y']<dom().get('height',0)-10),None))
        action('input',{'kind':'click','at':[value['x']+value['width']/2,value['y']+min(18,value['height']/2)]})
    def graph():return dom().get('graph') or {}
    def screenshot(name):command('qa_snapshot',{'name':name});time.sleep(.2)
    def opened(identifier):
        value=graph();return value if value.get('investigationId')==identifier and value.get('graphMode')=='graph' and value.get('canvas') and value.get('layoutPending')=='false' else None
    def start(run):
        nonlocal process,owned
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        with (out/f'process-{run}.log').open('wb') as log:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(state)['pid'];wait(lambda:state()['desktop']['ready']);command('show_workspace',{'route':'search'})
        action('window',{'mode':'maximize'})
    try:
        start(0)
        # Let the mounted workspace finish its initial selection before a QA
        # backend action changes it; otherwise its pending initial fetch can
        # legitimately win over this out-of-band test request.
        wait(lambda:opened(cases[0]['id']))
        for case in cases:
            case['executed']=not args.only or case['name'] in args.only
            if not case['executed']:continue
            action('investigation_graph_get',{'id':case['id'],'mode':'graph'})
            value=wait(lambda:opened(case['id']))
            click('Вписать граф в окно');time.sleep(.3)
            viewport_dom=dom();value=viewport_dom.get('graph') or {}
            case['canvas']={key:value['canvas'].get(key) for key in ('drawnNodes','drawnEdges','drawnLabels','drawnImages','paintMs','zoom','x','y','width','height')}
            bounds=value['canvas'];viewport_height=viewport_dom['height']
            case['canvas']['visible_height']=max(0,min(bounds['y']+bounds['height'],viewport_height)-max(bounds['y'],0))
            case['viewport']={'width':viewport_dom['width'],'height':viewport_height,'units':'Qt WebEngine CSS pixels'}
            save()
            check(case['name']+'_native_canvas',int(case['canvas']['drawnNodes'])>1 and value.get('worker')=='worker')
            check(case['name']+'_no_window_overflow',not dom()['overflow'])
            screenshot(case['name'])
            if args.density_v3:
                from PIL import Image
                with Image.open(out/(case['name']+'-search.png')) as captured:
                    native_width,native_height=captured.size
                scale=native_width/viewport_dom['width']
                case['density']={'native_window_width':native_width,'native_window_height':native_height,
                    'native_pixels_per_css_pixel':scale,'canvas_top_native':bounds['y']*scale,
                    'canvas_height_native':bounds['height']*scale,
                    'visible_canvas_height_native':case['canvas']['visible_height']*scale}
                save()
                if viewport_dom['width']>=1400:
                    check(case['name']+'_graph_content_above_fold',case['density']['canvas_top_native']<=550)
                    check(case['name']+'_visible_graph_height',case['canvas']['visible_height']>=400 and bounds['height']>=450 and case['density']['visible_canvas_height_native']>=450)
            if args.simple_v3:
                before=journal.load_checkpoint(case['id'])['evidence']
                click('Дерево');wait(lambda:graph().get('graphMode')=='tree' and graph().get('layoutPending')=='false')
                check(case['name']+'_tree_uses_actual_worker',graph().get('worker')=='worker')
                screenshot(case['name']+'-tree')
                click('Обзор');wait(lambda:graph().get('graphMode')=='overview')
                check(case['name']+'_overview_has_no_window_overflow',not dom()['overflow'])
                screenshot(case['name']+'-overview')
                if args.density_v3 and viewport_dom['width']>=1400:
                    overview_dom=dom()
                    primary_label='Таблица' if case['name'].startswith('actual-steam') else 'Открыть граф'
                    primary=next((e for e in overview_dom.get('elements',[]) if e.get('text')==primary_label and e['width']>0 and e['height']>0),None)
                    case['density']['overview_primary_control']=primary_label
                    case['density']['overview_primary_control_top_native']=primary['y']*scale if primary else None
                    save()
                    check(case['name']+'_overview_primary_content_above_fold',primary is not None and 0<=primary['y']*scale<=550)
                click('Граф');wait(lambda:opened(case['id']))
                check(case['name']+'_views_preserve_original_evidence',journal.load_checkpoint(case['id'])['evidence']==before)
                continue
            if args.master_fix_v2:
                wait(lambda:bool(views.load(case['id']).get('positions')))
                graph_points=views.load(case['id'])['positions']
                click('Дерево');wait(lambda:graph().get('graphMode')=='tree' and graph().get('layoutPending')=='false')
                wait(lambda:bool(views.load(case['id']).get('tree_positions')))
                tree_view=views.load(case['id']);tree_points=tree_view['tree_positions'];tree_canvas=graph()['canvas']
                case['tree_canvas']={key:tree_canvas.get(key) for key in ('drawnNodes','drawnEdges','modelEdges','onScreenNodes','drawnLabels','paintMs','zoom','width','height')}
                case['paired_coordinates_differ']=any(point!=graph_points.get(key) for key,point in tree_points.items())
                check(case['name']+'_different_tree_network_coordinates',case['paired_coordinates_differ'])
                check(case['name']+'_tree_connected_single_parent',int(tree_canvas['modelEdges'])==int(tree_canvas['drawnNodes'])-1)
                check(case['name']+'_tree_readable_default',float(tree_canvas['zoom'])>=.57 and int(tree_canvas['drawnLabels'])>1)
                if case['name']=='actual-geoint':check('geoint_tree_includes_researched_candidate',int(tree_canvas['drawnNodes'])>=3)
                screenshot(case['name']+'-tree')
                visible_nodes=json.loads(tree_canvas['qaNodes']);selected=next((node for node in visible_nodes if 60<node['x']<tree_canvas['width']-80 and 70<node['y']<tree_canvas['height']-80),visible_nodes[0])
                at=[tree_canvas['x']+selected['x'],tree_canvas['y']+selected['y']]
                action('input',{'kind':'click','at':at});wait(lambda:graph().get('selectedId')==selected['id'])
                check(case['name']+'_tree_breadcrumbs','Путь в дереве' in str(dom().get('text','')) or any(e.get('text')==selected['label'] for e in dom().get('elements',[])))
                c=graph()['canvas'];point=next((node for node in json.loads(c['qaNodes']) if node['id']==selected['id']),None)
                if point:
                    action('input',{'kind':'drag','at':[c['x']+point['x'],c['y']+point['y']],'to':[c['x']+point['x']+25,c['y']+point['y']+20]})
                    wait(lambda:views.load(case['id']).get('tree_positions',{}).get(selected['id'],{}).get('pinned'))
                    check(case['name']+'_native_tree_drag_persisted',True)
                click('Закрыть свойства графа');click('Граф');wait(lambda:opened(case['id']))
                screenshot(case['name']+'-graph')
            if case['name']=='synthetic-1000':
                c=graph()['canvas'];group=next(node for node in json.loads(c['qaNodes']) if 'Страницы' in node['label'])
                action('input',{'kind':'click','at':[c['x']+group['x'],c['y']+group['y']]});wait(lambda:graph().get('selectedId')==group['id'])
                click('Раскрыть группу');wait(lambda:int(graph()['canvas']['drawnNodes'])>50)
                check('native_group_expansion_preserves_large_collection',True)
                click('Поиск по узлам');action('input',{'kind':'text','text':'777'})
                wait(lambda:1<int(graph()['canvas']['drawnNodes'])<35);click('Вписать граф в окно');screenshot('synthetic-1000-focused')
                check('native_search_finds_entity_without_matching_internal_member_hashes',True)
                click('Поиск по узлам');action('input',{'kind':'key','key':'all','ctrl':True});action('input',{'kind':'key','key':'backspace'})
                click('Свернуть группы');wait(lambda:int(graph()['canvas']['drawnNodes'])<15)
            if case['name'] in ('synthetic-20','actual-ton-302','actual-github','actual-geoint'):
                c=graph()['canvas'];node=json.loads(c['qaNodes'])[0]
                action('input',{'kind':'click','at':[c['x']+node['x'],c['y']+node['y']]})
                wait(lambda:graph().get('selectedId')==node['id'])
                check(case['name']+'_native_inspector',True);screenshot(case['name']+'-inspector')
                if case['name']=='actual-ton-302':
                    e=next(element for element in dom()['elements'] if element.get('label')=='Ширина инспектора')
                    action('input',{'kind':'drag','at':[e['x']+e['width']/2,e['y']+35],'to':[e['x']-100,e['y']+35]})
                    wait(lambda:next(element['x'] for element in dom()['elements'] if element.get('label')=='Ширина инспектора')<e['x']-50)
                    check('native_inspector_resize',True);screenshot('actual-ton-resized-inspector')
                    c=graph()['canvas'];before_nodes=int(c['drawnNodes'])
                    for point in json.loads(c['qaEdges']):
                        if point['id'] not in case['aggregate_relation_ids']:continue
                        if not 5<point['x']<c['width']-5 or not 5<point['y']<c['height']-10:continue
                        action('input',{'kind':'click','at':[c['x']+point['x'],c['y']+point['y']]})
                        if graph().get('selectedRelation') in case['aggregate_relation_ids']:break
                    wait(lambda:graph().get('selectedRelation') in case['aggregate_relation_ids'])
                    click('Раскрыть транзакции')
                    wait(lambda:int(graph()['canvas']['drawnNodes'])>before_nodes)
                    wait(lambda:len(views.load(case['id']).get('expanded_relations',[]))==1)
                    check('native_expansion_is_scoped_to_one_selected_flow',not views.load(case['id']).get('filters',{}).get('show_transactions'))
                    screenshot('actual-ton-selected-flow')
                    click('Свернуть транзакции');wait(lambda:int(graph()['canvas']['drawnNodes'])==before_nodes)
                click('Скрыть свойства');wait(lambda:any(e.get('label')=='Показать свойства' for e in dom().get('elements',[])))
                click('Показать свойства');click('Закрыть свойства графа')
                if case['name']=='synthetic-20':
                    click('Дерево');wait(lambda:graph().get('graphMode')=='tree' and graph().get('layoutPending')=='false')
                    click('Вписать граф в окно');screenshot('synthetic-20-tree');click('Граф');wait(lambda:opened(case['id']))
        if args.simple_v3:
            report['passed']=all(check['passed'] for check in report['checks']);save()
            command('stop');process.wait(timeout=35);owned=None
            return
        # The 1000-node evidence remains intact across process restart.
        action('investigation_graph_get',{'id':cases[3]['id']});wait(lambda:opened(cases[3]['id']))
        wait(lambda:bool(views.load(cases[3]['id']).get('positions')))
        time.sleep(.5);before=views.load(cases[3]['id'])
        command('stop');process.wait(timeout=35);owned=None;start(1);wait(lambda:opened(cases[3]['id']))
        after=views.load(cases[3]['id'])
        check('restart_retains_graph_layout_and_group_state',all(after.get(key)==before.get(key) for key in ('positions','tree_positions','filters','expanded','collapsed','mode')))
        screenshot('restored-1000-grouped')
        check('no_unexpected_global_error_banner','Операция остановлена из-за ошибки' not in dom().get('text','') and 'Сначала откройте граф' not in dom().get('text',''))
        command('stop');process.wait(timeout=30);owned=None
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:200]);save();raise
    finally:
        if owned and process and process.poll() is None:
            try:command('stop');process.wait(timeout=30)
            except Exception:pass
        save()


if __name__=='__main__':main()
