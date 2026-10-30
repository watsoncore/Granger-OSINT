"""Actual Qt/WebEngine input tests, isolated encrypted graph profile, no API keys.

The stress evidence is explicitly synthetic. It passes the normal journal,
projection, WebChannel and bundled renderer; no DOM or graph results are mocked.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Choose a new output directory')
    out.mkdir(parents=True)
    namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),GRANGERPET_QA_VAULT='GrangerPet/QA/graph_'+namespace)
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.config import Settings
    from grangerpet.credentials import CredentialsStore
    from grangerpet.graph_store import GraphViewStore
    from grangerpet.investigation import new_investigation
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.ipc import send_command
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(cursor_reaction=False,reduced_motion=True,source_root=str(ROOT)).to_dict()),encoding='utf-8')
    journal=InvestigationJournal(profile/'investigations')
    record,protocol=new_investigation('СИНТЕТИЧЕСКИЙ стресс-тест графа https://graph-fixture.example/0')
    record.update(status='completed',synthetic=True)
    rows=[]
    for i in range(1000):
        rows.append(normalize_evidence({'id':'synthetic-'+str(i),'type':'web','title':'Синтетический объект '+str(i),
            'platform':'Synthetic QA','url':f'https://graph-fixture.example/{i}', 'status':'content_observed',
            'description':'Синтетические данные для измерения интерфейса, не сведения о реальном объекте.',
            'details':{'reading_method':'direct_http','body_sha256':'a'*64,
                'links':[{'url':f'https://graph-fixture.example/{(i+j)%1000}'}for j in range(1,6)]}},'synthetic_fixture','graph fixture'))
    protocol['messages']=[{'role':'user','content':record['goal']}]
    protocol['protocol_archive']=protocol['messages'][:]
    journal.save_checkpoint({**protocol,'version':1,'id':record['id'],'record':record,'evidence':rows,'executions':[]})
    journal.save({**record,'evidence':rows,'executions':[]})
    views=GraphViewStore(journal);views.select(record['id'])
    report={'mode':'actual_frozen_Qt_WebEngine' if args.exe else 'actual_source_Qt_WebEngine',
        'synthetic_stress_data':True,'gateway_calls':0,'user_data_read':False,'checks':[],'metrics':{}}
    if args.exe:report['exe_sha256']=hashlib.sha256(args.exe.read_bytes()).hexdigest()
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});save()
        if not ok:raise AssertionError(name)
    def wait(fn,seconds=45):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.15)
        raise TimeoutError('Own graph GUI wait expired')
    owned=None;process=None
    def state():
        value=send_command('pet','status',timeout=2500)
        if value and owned and value.get('pid')!=owned:raise RuntimeError('Own isolated PID mismatch')
        return value
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=4000)
        if not value or not value.get('ok'):raise RuntimeError('Own action failed: '+name)
        return value
    def action(name,payload=None):
        command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.15)
    def dom():
        action('dom');value=state()['desktop'].get('dom',{})
        (out/'last-dom.json').write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return value
    def element(label):
        return wait(lambda:next((e for e in dom().get('elements',[]) if (e.get('label')==label or e.get('text')==label) and e['width']>0 and 0<=e['y']<dom_height[0]-5),None))
    dom_height=[10000]
    def click(label):
        e=element(label);action('input',{'kind':'click','at':[e['x']+e['width']/2,e['y']+min(e['height']/2,18)]})
    def graph():return dom().get('graph') or {}
    def screenshot(name):command('qa_snapshot',{'name':name});time.sleep(.2)
    def start(run):
        nonlocal process,owned
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        with (out/f'process-{run}.log').open('wb') as log:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(state)['pid'];wait(lambda:state()['desktop']['ready'])
        command('show_workspace',{'route':'search'})
        wait(lambda:graph().get('investigationId')==record['id'])
        action('graph_scroll');time.sleep(.5);dom_height[0]=dom()['height']
    try:
        start(0)
        check('four_views_in_real_search',all(any(e.get('text')==label for e in dom()['elements']) for label in ('Обзор','Дерево','Граф','Доказательства')))
        click('Граф');wait(lambda:graph().get('canvas',{}).get('drawnNodes'))
        check('bundled_layout_worker_runs',graph().get('worker')=='worker')
        click('Показать до 1 200 узлов');wait(lambda:int(graph().get('canvas',{}).get('drawnNodes',0))>=1000)
        wait(lambda:graph().get('layoutPending')=='false');click('Вписать граф в окно')
        wait(lambda:int(graph().get('canvas',{}).get('drawnEdges',0))>=5000)
        g=graph();c=g['canvas'];report['metrics'].update(layout_ms=float(g['layoutMs']),paint_ms=float(c['paintMs']),displayed_nodes=int(c['drawnNodes']),displayed_edges=int(c['drawnEdges']))
        check('1000_nodes_5000_edges_in_actual_canvas',int(c['drawnNodes'])>=1000 and int(c['drawnEdges'])>=5000)
        nodes=json.loads(c['qaNodes']);n=next(n for n in nodes if c['y']+n['y']<dom_height[0]-45 and n['x']>30)
        at=[c['x']+n['x'],c['y']+n['y']]
        action('input',{'kind':'click','at':at});wait(lambda:graph().get('selectedId')==n['id'])
        check('native_click_opens_node_inspector','Свойства узла' in [e.get('label') for e in dom()['elements']] or 'Доказательства основания' in dom()['text'])
        c=graph()['canvas'];n=next(row for row in json.loads(c['qaNodes']) if row['id']==n['id']);at=[c['x']+n['x'],c['y']+n['y']]
        action('input',{'kind':'drag','at':at,'to':[at[0]+35,at[1]+25]});time.sleep(.6)
        saved=views.load(record['id']);check('native_node_drag_pins_and_persists',saved['positions'][n['id']].get('pinned'))
        c=graph()['canvas'];oldzoom=float(c['zoom']);at=[c['x']+c['width']/2,c['y']+min(120,c['height']/2)]
        action('input',{'kind':'wheel','at':at,'delta':240});wait(lambda:float(graph()['canvas']['zoom'])>oldzoom)
        check('native_wheel_zooms',True)
        c=graph()['canvas'];pan=float(c['panX']);at=[c['x']+12,c['y']+25]
        action('input',{'kind':'drag','at':at,'to':[at[0]+22,at[1]+15]});wait(lambda:abs(float(graph()['canvas']['panX'])-pan)>5)
        check('native_background_drag_pans',True)
        action('graph_scroll');click('Свернуть ветвь');wait(lambda:int(graph()['canvas']['drawnNodes'])==1)
        check('native_collapse_hides_branch_without_deleting',len(views.load(record['id'])['positions'])>=1000)
        click('Раскрыть соседей (12)');wait(lambda:int(graph()['canvas']['drawnNodes'])>=1000)
        check('native_expand_restores_branch',True)
        click('Поиск по узлам');action('input',{'kind':'text','text':'graph-fixture.example/777'})
        wait(lambda:1<int(graph()['canvas']['drawnNodes'])<100)
        check('native_node_search_limits_to_matching_neighborhood',True)
        action('input',{'kind':'key','key':'all','ctrl':True});action('input',{'kind':'key','key':'backspace'})
        wait(lambda:int(graph()['canvas']['drawnNodes'])>=1000)
        action('graph_scroll');click('Дерево');wait(lambda:graph().get('graphMode')=='tree' and graph().get('canvas'))
        check('tree_has_independent_layout',bool(views.load(record['id']).get('positions')))
        click('Доказательства');wait(lambda:'нормализованных записей' in dom()['text'])
        screenshot('evidence')
        check('evidence_virtualized',len([e for e in dom()['elements'] if e.get('text','').startswith('Синтетический объект')])<80)
        click('Граф');wait(lambda:graph().get('graphMode')=='graph' and graph().get('canvas'))
        for theme in ('dark','black','light','mono'):
            action('settings_save',{'values':{'ui_theme':theme}});wait(lambda:dom().get('theme')==theme)
            check('graph_no_overflow_'+theme,not dom()['overflow']);screenshot('graph-'+theme)
        time.sleep(.8);before=views.load(record['id'])
        command('stop');process.wait(timeout=30);check('clean_first_exit',process.returncode==0);owned=None
        start(1)
        wait(lambda:graph().get('graphMode')=='graph' and graph().get('canvas'))
        after=views.load(record['id'])
        check('graph_state_survives_actual_restart',all(after.get(key)==before.get(key) for key in ('selected_id','viewport','positions','tree_positions','filters','mode')))
        check('restart_never_auto_executes',not state().get('search',{}).get('busy') and not state().get('busy'))
        screenshot('restored-graph')
        command('stop');process.wait(timeout=30);owned=None;check('clean_second_exit',process.returncode==0)
        report['passed']=True;save()
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:250]);save();raise
    finally:
        if process and process.poll() is None:
            command('stop');process.wait(timeout=30)
    print(json.dumps({'passed':True,'checks':len(report['checks']),'metrics':report['metrics']}))


if __name__=='__main__':main()
