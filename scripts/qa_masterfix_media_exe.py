"""Native automatic-search reproduction in an isolated frozen Windows app.

No gateway credentials, original histories or Gansar databases are used.
The default target is the public TON address explicitly requested by the owner.
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
TARGET='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--target',default=TARGET)
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Prior evidence retained; choose a new output')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),GRANGERPET_QA_VAULT='GrangerPet/QA/masterfix_'+namespace)
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY','GRANGERPET_QA_INPUT_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(ai_provider='none',source_root=str(ROOT),
        cursor_reaction=False,reduced_motion=True).to_dict()),encoding='utf-8')
    from grangerpet.blockchain_store import BlockchainStore,target_key
    from grangerpet.engine.blockchain_rows import normalize_dossier
    from grangerpet.agent_evidence import normalize_evidence,utc_now
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.investigation_workspace import InvestigationWorkspace
    from grangerpet.evidence_graph import build
    original=BlockchainStore(ROOT/'output/masterfix/live-ton-quick-04/appdata/GrangerPet/blockchain')
    dossier=original.load(next(original.directory.glob('*.dpapi')).stem)
    registry=ToolRegistry(Settings(source_root=str(ROOT)),secret_getter=lambda name:'')
    registry._blockchain_refs[target_key(args.target)]=BlockchainStore().save(dossier)
    rows=[normalize_evidence(row,'blockchain_gansar',args.target,utc_now(),())for row in normalize_dossier(dossier)]
    workspace=InvestigationWorkspace(InvestigationJournal())
    saved=workspace.manual_result(args.target,{'tool':'blockchain_gansar','status':'partial','query':args.target,'results':rows},
        {'address':args.target},registry,None)
    topology=build(rows,limit=5000,full=True,goal=args.target)
    media_node=next(node for node in topology['entities'] if node['type']=='asset' and 'nft.fragment.com' in str(node['attributes'].get('media',{}).get('url','')))
    workspace.views.save(saved['id'],{'version':1,'mode':'graph','selected_id':media_node['id'],'positions':{},'filters':{}})
    report={'mode':'actual_frozen_Qt_WebEngine_native_automatic_search','mock':False,'gateway_calls':0,
        'user_data_read':False,'target':args.target,'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'checks':[]}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});save()
        if not ok:raise AssertionError(name)
    owned=None;process=None
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=4000)
        if not value or not value.get('ok'):raise RuntimeError('Own isolated command failed: '+name)
        if name=='status' and owned and value['pid']!=owned:raise RuntimeError('Own IPC PID mismatch')
        return value
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.2)
    def dom():
        action('dom');value=command('status')['desktop'].get('dom',{})
        (out/'last-dom.json').write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return value
    def wait(fn,seconds=70):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.15)
        raise TimeoutError('Bounded own-GUI wait expired')
    def snapshot(name='current'):
        command('qa_desktop',{'action':'save_state','name':name})
        return json.loads((out/(name+'.json')).read_text(encoding='utf-8'))
    def click(e):action('input',{'kind':'click','at':[e['x']+e['width']/2,e['y']+min(e['height']/2,18)]})
    try:
        with (out/'process.log').open('wb') as log:process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        end=time.monotonic()+55
        while time.monotonic()<end:
            state=send_command('pet','status',timeout=500)
            if state:owned=state['pid'];break
            time.sleep(.1)
        if not owned:raise TimeoutError('Own EXE did not start')
        wait(lambda:command('status')['desktop']['ready']);command('show_workspace',{'route':'search'})
        media_started=time.monotonic()
        action('investigation_graph_get',{'id':saved['id']})
        wait(lambda:snapshot().get('investigation_graph',{}).get('state')=='ready')
        action('graph_scroll')
        def graph():return dom().get('graph') or {}
        wait(lambda:graph().get('canvas') and graph().get('layoutPending')=='false')
        button=wait(lambda:next((e for e in dom()['elements'] if e.get('text')=='В центр' and e['width']>0),None))
        click(button)
        c=wait(lambda:graph().get('canvas'))
        node=next(row for row in json.loads(c['qaNodes']) if row['id']==media_node['id'])
        action('input',{'kind':'click','at':[c['x']+node['x'],c['y']+node['y']]})
        value=wait(lambda:media if (media:=next((node.get('attributes',{}).get('media',{})for node in snapshot().get('investigation_graph',{}).get('entities',[]) if node['id']==media_node['id']),{})).get('state') in ('ready','unavailable') else None,35)
        check('native_selected_real_nft_media_loaded',value.get('state')=='ready' and str(value.get('thumbnail','')).startswith('data:image/jpeg;base64,'))
        report['media']={key:val for key,val in value.items() if key!='thumbnail'}
        wait(lambda:any(image.get('loaded') and image.get('source_is_local') for image in graph().get('images',[])),15)
        check('actual_renderer_decodes_backend_thumbnail',True)
        check('media_selection_has_no_error_toast',not snapshot().get('errors'))
        snapshot('nft-inspector');command('qa_snapshot',{'name':'nft-inspector'})
        report['native_node_selected']=graph().get('selectedId')==media_node['id']
        check('actual_node_selection_retains_evidence',report['native_node_selected'])
        report['elapsed_seconds']=round(time.monotonic()-media_started,3);report['result_count']=len(rows);report['search']={'investigation_id':saved['id']}
        command('stop');process.wait(timeout=30);owned=None;check('clean_exit',process.returncode==0)
        report['passed']=True;save()
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:200]);save();raise
    finally:
        if process and process.poll() is None:command('stop');process.wait(timeout=30)
    print(json.dumps({key:report[key] for key in ('passed','elapsed_seconds','result_count','search')},ensure_ascii=True))


if __name__=='__main__':main()
