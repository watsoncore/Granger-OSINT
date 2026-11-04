"""Actual native input/paint/resource measurements on explicitly synthetic canvases."""
import argparse
import base64
import io
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--counts',type=int,nargs='+',default=[50,100,500,1000,5000])
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Use a fresh receipt directory')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_QA_VAULT='GrangerPet/QA/stress_'+namespace,GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtWidgets import QApplication
    from grangerpet.config import Settings
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore,new_document
    from grangerpet.evidence_graph import _id
    from grangerpet.ipc import send_command
    from perf_process_metrics import ProcessSampler,summarize
    app=QApplication.instance() or QApplication([])
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(source_root=str(ROOT),cursor_reaction=False,reduced_motion=True).to_dict()),encoding='utf-8')
    store=CanvasStore(InvestigationJournal(profile/'investigations'));cases=[]
    from PIL import Image
    pixels=io.BytesIO();Image.new('RGB',(64,64),'#497077').save(pixels,'PNG')
    thumbnail='data:image/png;base64,'+base64.b64encode(pixels.getvalue()).decode('ascii')
    for count in args.counts:
        if count not in (50,100,500,1000,5000):raise ValueError('Use documented stress sizes')
        d=new_document(f'SYNTHETIC QA · {count} objects')
        for i in range(count):
            kind=['person','domain','blockchain_address','image','analyst_note','entity_group'][i%6];identifier=_id(kind,'synthetic-qa-'+str(i))
            d['entities'].append({'id':identifier,'type':kind,'label':f'СИНТЕТИЧЕСКИЙ {kind} {i}','attributes':{'origin':'synthetic_fixture','member_count':0},'evidence_ids':[],'source':['Synthetic QA'],'verification_status':'inferred' if i%7==0 else 'unverified'})
            if kind=='image':d['entities'][-1]['attributes']['media']={'id':'synthetic_image','kind':'local_attachment','state':'ready','thumbnail':thumbnail}
            d['view']['positions'][identifier]={'x':i%20*310,'y':i//20*150}
            if i:d['relations'].append({'id':'rel_'+hashlib.sha256(str(i).encode()).hexdigest()[:24],'from_id':d['entities'][(i-1)//3]['id'],'to_id':identifier,'relation_type':'potentially_related','direction':'directed','origin':'synthetic_fixture','verification_status':'inferred','evidence_ids':[]})
        start=time.perf_counter();saved=store.save(d,0)
        cases.append({'id':saved['id'],'underlying_nodes':count,'edges':count-1,'encrypted_seed_write_ms':round((time.perf_counter()-start)*1000,2)})
    report={'origin':'frozen-EXE' if args.exe else 'native-source','data_origin':'synthetic_fixture','exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest() if args.exe else None,'cases':[],'checks':[],
        'metric_semantics':'Paint timings are actual WebEngine Canvas draw durations. Active frame intervals exclude gaps >=100 ms; their reciprocal is not whole-session FPS. Event-to-paint begins at JS pointer handler. IPC pauses are excluded from that latency.'}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.2)
        raise TimeoutError('Own stress QA deadline')
    owned=None;process=None;monitor=ProcessSampler(args.exe)
    def state():
        r=send_command('pet','status',timeout=8000)
        if r and owned and r.get('pid')!=owned:raise RuntimeError('Unrelated instance')
        return r
    def command(name,payload=None):
        r=send_command('pet',name,payload or {},timeout=12000)
        if not r or not r.get('ok'):
            report['ipc_failure']={'command':name,'action':(payload or {}).get('action'),'response':r,'parent_exit_code':process.poll() if process else None};save()
            raise RuntimeError('Own IPC command failed: '+name+'/'+str((payload or {}).get('action')))
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.15)
    def snapshot():
        command('qa_desktop',{'action':'save_state','name':'current-state'})
        return json.loads((out/'current-state.json').read_text(encoding='utf-8'))
    def dom():action('dom');return state()['desktop'].get('dom',{})
    def click(label):
        def find():
            r=dom();return next((x for x in r.get('elements',[]) if (x.get('label')==label or x.get('text')==label) and x['width']>0 and 0<x['y']<r['height']-10),None)
        e=wait(find);action('input',{'kind':'click','at':[e['x']+e['width']/2,e['y']+min(18,e['height']/2)]})
    def metrics():
        old=snapshot().get('research_canvas',{}).get('metrics',{}).get('generation',0)
        action('research_canvas_metrics')
        return wait(lambda:m if (m:=snapshot().get('research_canvas',{}).get('metrics',{})).get('generation',0)>old else None)
    try:
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        with (out/'process.log').open('wb') as stream:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT)
        owned=wait(state,80)['pid'];wait(lambda:state()['desktop']['ready']);monitor.sample([process.pid])
        command('show_workspace',{'route':'search'});action('window',{'mode':'maximize'});click('Мои расследования')
        for index,case in enumerate(cases):
            start=time.perf_counter();action('research_canvas_open',{'id':case['id']})
            wait(lambda:s if not (s:=snapshot().get('research_canvas',{})).get('busy') and s.get('document',{}).get('id')==case['id'] else None)
            wait(lambda:metrics().get('canvas_id')==case['id'])
            if index==0:click('Развернуть полотно')
            # Progressive expansion remains bounded, and all original members stay saved.
            target=case['underlying_nodes']
            while int((metrics().get('canvas') or {}).get('drawnNodes',0))<target:click('Раскрыть ещё 100')
            current=metrics();c=current['canvas'];case['open_and_expand_seconds']=round(time.perf_counter()-start,3)
            samples=[]
            for i in range(12):
                at=[c['x']+c['width']*.45,c['y']+c['height']*.42]
                action('input',{'kind':'drag','at':at,'to':[at[0]+(34 if i%2==0 else -34),at[1]+12]})
                samples.append(monitor.sample([process.pid]))
            for delta in (-120,120,-120,120):action('input',{'kind':'wheel','at':[c['x']+c['width']/2,c['y']+c['height']/2],'delta':delta})
            final=metrics()['canvas'];frame=json.loads(final.get('frameMetrics','{}'))
            case['renderer']={k:final.get(k) for k in ('paintMs','drawnNodes','onScreenNodes','modelEdges','drawnImages','zoom')}
            for key,values in frame.items():
                if values:case[key]={'count':len(values),'median':round(statistics.median(values),3),'p95':round(sorted(values)[max(0,int(len(values)*.95)-1)],3),'max':round(max(values),3)}
            intervals=frame.get('active_intervals_ms',[])
            case['active_interval_reciprocal_fps']=round(1000/statistics.median(intervals),2) if intervals else None
            case['resources']=summarize(samples)
            report['cases'].append(case);save();print(json.dumps({'nodes':target,'paint':case.get('paint_ms'),'active_interval_reciprocal_fps':case['active_interval_reciprocal_fps']}),flush=True)
        report['passed']=True;save()
    except Exception as error:report.update(passed=False,error_type=type(error).__name__,error=str(error)[:200]);save();raise
    finally:
        if process and process.poll() is None:
            if state():command('stop')
            process.wait(timeout=30)
        if process:
            report['parent_exit_code']=process.poll()
            time.sleep(.3);report['owned_processes_left']=monitor.sample([process.pid])['process_count']
            if report['owned_processes_left']:report.update(passed=False,error='Owned QA processes remain after exit')
            save()
        monitor.close()


if __name__=='__main__':main()
