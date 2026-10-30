"""Actual native graph rendering; synthetic stress and saved live evidence kept distinct."""
import argparse
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
    rows=[normalize_evidence({'id':str(i),'type':'post','platform':'Synthetic QA','title':f'Синтетическая публикация {i}',
        'url':f'https://t.me/qa_public_fixture/{i+1}','description':'Synthetic publication fixture, no public source requested.',
        'details':{'author':'qa_public_fixture'}},'synthetic_fixture','qa_public_fixture') for i in range(100)]
    case('synthetic-publications','СИНТЕТИЧЕСКИЕ публикации https://t.me/qa_public_fixture',rows,True)
    views.select(cases[0]['id'])
    report={'mode':'actual_frozen_Qt_WebEngine' if args.exe else 'actual_source_Qt_WebEngine','gateway_calls':0,
        'inference_calls':0,'cases':cases,'checks':[],'manual_visual_review':'pending'}
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
            time.sleep(.15)
        raise TimeoutError('Own graph UI wait expired')
    def state():
        value=send_command('pet','status',timeout=2500)
        if value and owned and value.get('pid')!=owned:raise RuntimeError('Own PID mismatch')
        return value
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=4000)
        if not value or not value.get('ok'):raise RuntimeError('Own command failed: '+name)
        return value
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.2)
    def dom():action('dom');return state()['desktop'].get('dom',{})
    def click(label):
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
        for case in cases:
            case['executed']=not args.only or case['name'] in args.only
            if not case['executed']:continue
            action('investigation_graph_get',{'id':case['id']})
            value=wait(lambda:opened(case['id']))
            click('Вписать граф в окно');time.sleep(.3)
            value=graph();case['canvas']={key:value['canvas'].get(key) for key in ('drawnNodes','drawnEdges','drawnLabels','drawnImages','paintMs','zoom','width','height')};save()
            check(case['name']+'_native_canvas',int(case['canvas']['drawnNodes'])>1 and value.get('worker')=='worker')
            check(case['name']+'_no_window_overflow',not dom()['overflow'])
            screenshot(case['name'])
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
        # The 1000-node evidence remains intact across process restart.
        action('investigation_graph_get',{'id':cases[3]['id']});wait(lambda:opened(cases[3]['id']))
        before=views.load(cases[3]['id']);time.sleep(.5)
        command('stop');process.wait(timeout=35);owned=None;start(1);wait(lambda:opened(cases[3]['id']))
        after=views.load(cases[3]['id'])
        check('restart_retains_graph_layout_and_group_state',all(after.get(key)==before.get(key) for key in ('positions','tree_positions','filters','expanded','collapsed','mode')))
        screenshot('restored-1000-grouped')
        check('no_unexpected_global_error_banner','Операция остановлена из-за ошибки' not in dom().get('text','') and 'Сначала откройте граф' not in dom().get('text',''))
        command('stop');process.wait(timeout=30);owned=None
    finally:
        if owned and process and process.poll() is None:
            try:command('stop');process.wait(timeout=30)
            except Exception:pass
        save()


if __name__=='__main__':main()
