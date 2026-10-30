"""Inspect actual saved live-EXE observations, with no key or network execution.

Input is restricted to a previous isolated QA profile inside output/stability.
It proves real geographic coordinate rendering and transfer expansion separately
from the live producer tests, never substitutes synthetic model predictions.
"""
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
    p.add_argument('--exe',type=Path,required=True)
    p.add_argument('--live-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();live=args.live_dir.resolve();out=args.output.resolve()
    if not live.is_relative_to(ROOT/'output/stability') or not (live/'report.json').is_file():raise SystemExit('Input must be a retained isolated QA run')
    producer=json.loads((live/'report.json').read_text(encoding='utf-8'))
    if not producer.get('passed') or producer.get('mock') is not False or not producer.get('qa_gateway_secret_removed'):raise SystemExit('Live producer must be complete, real and its temporary key removed')
    if out.exists():raise SystemExit('Prior evidence retained')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(live/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),GRANGERPET_QA_VAULT='GrangerPet/QA/view_'+namespace)
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY','GRANGERPET_QA_INPUT_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    from grangerpet.ipc import send_command
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.graph_store import GraphViewStore
    # Reset only presentation state in this explicit QA profile so repeated
    # native expansion tests start collapsed. Primary observations are intact.
    ton_state=json.loads((live/'ton-manual.json').read_text(encoding='utf-8'))
    views=GraphViewStore(InvestigationJournal(live/'appdata/GrangerPet/investigations'))
    ton_id=ton_state['search']['investigation_id'];view=views.load(ton_id)
    view.update(mode='graph',expanded=[],collapsed=[],selected_id='',selected_relation='')
    view['filters']={**view.get('filters',{}),'show_transactions':False}
    views.save(ton_id,view)
    report={'mock':False,'mode':'actual_frozen_Qt_WebEngine_saved_live_results','gateway_calls':0,
        'user_history_read':False,'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'checks':[]}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,condition):
        report['checks'].append({'name':name,'passed':bool(condition)});save()
        if not condition:raise AssertionError(name)
    owned=None;process=None
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=4000)
        if not value or not value.get('ok'):raise RuntimeError('Own QA command failed: '+name)
        if name=='status' and owned and value['pid']!=owned:raise RuntimeError('Own isolated PID mismatch')
        return value
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.2)
    def dom():
        action('dom');value=command('status')['desktop'].get('dom',{})
        (out/'last-dom.json').write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return value
    def wait(fn,seconds=45):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.15)
        raise TimeoutError('Own saved-view GUI wait expired')
    def click(text,partial=False):
        e=wait(lambda:next((e for e in dom().get('elements',[]) if (e.get('text')==text or e.get('label')==text or partial and text in e.get('text','')) and e['width']>0 and 0<e['y']<dom()['height']-30),None))
        action('input',{'kind':'click','at':[e['x']+e['width']/2,e['y']+min(e['height']/2,18)]})
    def snapshot():
        command('qa_desktop',{'action':'save_state','name':'current'})
        return json.loads((out/'current.json').read_text(encoding='utf-8'))
    def graph(identifier):
        action('route',{'route':'search'});action('investigation_graph_get',{'id':identifier})
        result=wait(lambda:g if (g:=snapshot().get('investigation_graph',{})).get('state')=='ready' and g.get('investigation_id')==identifier else None)
        action('graph_scroll');click('Граф');wait(lambda:(g:=dom().get('graph') or {}).get('canvas') and g.get('layoutPending')=='false')
        return result
    try:
        with (out/'process.log').open('wb') as log:process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        end=time.monotonic()+55
        while time.monotonic()<end:
            state=send_command('pet','status',timeout=500)
            if state:owned=state['pid'];break
            time.sleep(.15)
        if not owned:raise TimeoutError('Own saved-view app did not start')
        wait(lambda:command('status')['desktop']['ready']);command('show_workspace',{'route':'search'})
        visual=json.loads((live/'visual-geoint-live.json').read_text(encoding='utf-8'))
        data=graph(visual['investigation']['id'])
        check('real_model_coordinates_in_graph',sum(n['type']=='geographic_candidate' for n in data['entities'])>=2)
        command('qa_snapshot',{'name':'real-geoint-graph'})
        click('Доказательства')
        action('graph_scroll')
        click('Географические кандидаты',partial=True)
        wait(lambda:'Визуальные географические кандидаты' in dom()['headings'])
        check('real_model_result_dialog_opened',True)
        # The existing QA body-text inventory is deliberately capped at18k.
        # The large catalog can precede the dialog, so do not infer missing
        # coordinate graphics from that truncated string. Review the real grab.
        report['coordinate_map_visual_review_required']=True;save()
        d=dom();action('input',{'kind':'wheel','at':[d['width']/2,d['height']*.65],'delta':-480})
        command('qa_snapshot',{'name':'real-geoint-coordinate-map'})
        d=dom();action('input',{'kind':'wheel','at':[d['width']/2,d['height']*.65],'delta':-480})
        command('qa_snapshot',{'name':'real-geoint-coordinate-table'})
        for _ in range(3):
            d=dom();action('input',{'kind':'wheel','at':[d['width']/2,d['height']/2],'delta':1200})
        click('Закрыть источник')
        ton=json.loads((live/'ton-manual.json').read_text(encoding='utf-8'))
        data=graph(ton['search']['investigation_id'])
        check('real_ton_aggregate_has_saved_transactions',any(e.get('aggregate',{}).get('transaction_ids') for e in data['relations']))
        c=dom()['graph']['canvas']
        candidates=json.loads(c['qaEdges'])
        aggregate_ids={e['id']for e in data['relations']if e.get('aggregate')}
        e=next(row for row in candidates if row['id'] in aggregate_ids)
        action('input',{'kind':'click','at':[c['x']+e['x'],c['y']+e['y']]})
        wait(lambda:'Раскрыть транзакции' in dom()['text'])
        before=int(dom()['graph']['canvas']['drawnNodes'])
        click('Раскрыть транзакции')
        wait(lambda:int(dom()['graph']['canvas']['drawnNodes'])>before)
        check('native_aggregate_expansion_shows_individual_transactions',True)
        command('qa_snapshot',{'name':'real-ton-expanded-aggregate'})
        check('no_gateway_configured_in_viewer',not snapshot()['connection']['canSend'])
        command('stop');process.wait(timeout=30);owned=None
        check('clean_exit',process.returncode==0);report['passed']=True;save()
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:200]);save();raise
    finally:
        if process and process.poll() is None:command('stop');process.wait(timeout=30)
    print(json.dumps({'passed':True,'checks':len(report['checks'])}))


if __name__=='__main__':main()
