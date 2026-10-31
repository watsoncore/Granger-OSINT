"""Compare owned EXE process trees under idle/reading/two-actor production load."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--exe',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--cycles',type=int,default=25)
    p.add_argument('--scenarios',nargs='+',default=['idle','reading','malfoy'])
    p.add_argument('--cycle-scenes',nargs='+',default=['malfoy','harry','ron_note']);args=p.parse_args()
    out=args.output.resolve()
    if out.exists():raise SystemExit('Existing evidence preserved')
    out.mkdir(parents=True);ns=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=ns,
        GRANGERPET_QA_VAULT='GrangerPet/QA/chibi_'+ns,GRANGERPET_INTERACTION_TRACE=str(out/'trace.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    from perf_process_metrics import ProcessSampler,summarize
    SettingsStore().save(Settings(ai_provider='none',size=195,cursor_reaction=False,x=30,y=400))
    process=None;owned=None;monitor=ProcessSampler(args.exe,gpu=False)
    report={'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'scenarios':[],
        'method':'Own image-verified EXE tree only; 100% CPU = one logical core; private commit is not private working set',
        'api_requests':0,'capture_during_measurement':False}
    def cmd(name,payload=None):
        v=send_command('pet',name,payload,timeout=3000)
        if not v or not v.get('ok'):raise RuntimeError('Own command failed: '+name)
        if name=='status' and owned and v['pid']!=owned:raise RuntimeError('Own PID mismatch')
        return v
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            v=fn()
            if v:return v
            time.sleep(.1)
        raise TimeoutError('Own performance wait failed')
    try:
        with (out/'process.log').open('wb') as log:process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(lambda:send_command('pet','status'))['pid'];wait(lambda:cmd('status').get('desktop',{}).get('ready'))
        cmd('qa_figure',{'action':'away'});time.sleep(3)
        for name in args.scenarios:
            if name!='idle':cmd('qa_life',{'action':name,'duration':28})
            time.sleep(2);first=cmd('status');monitor.sample([owned]);start=time.monotonic();samples=[]
            for _ in range(20):time.sleep(.5);samples.append(monitor.sample([owned]))
            last=cmd('status');elapsed=time.monotonic()-start
            a=first['pet_render'].get('render_count');b=last['pet_render'].get('render_count')
            report['scenarios'].append({'name':name,'seconds':elapsed,'metrics':summarize(samples),
                'production_render_fps':(b-a)/elapsed if a is not None and b is not None else None,
                'tick_ms_p50':last['pet_render'].get('tick_ms_p50'),'tick_ms_p95':last['pet_render'].get('tick_ms_p95'),
                'owned_timer_count':last['pet_render']['owned_timer_count'],'dpr':last['pet_render'].get('dpr')})
            print(json.dumps(report['scenarios'][-1]),flush=True)
        before=monitor.sample([owned]);timers=[]
        for cycle in range(args.cycles):
            cmd('qa_life',{'action':args.cycle_scenes[cycle%len(args.cycle_scenes)],'duration':.4});time.sleep(.55)
            state=cmd('status');timers.append(state['pet_render']['owned_timer_count'])
        after=monitor.sample([owned]);report['cycles']={'count':args.cycles,'timer_counts':sorted(set(timers)),
            'private_commit_before':before['private_commit_bytes_sum'],'private_commit_after':after['private_commit_bytes_sum']}
        cmd('stop');process.wait(timeout=30);owned=None
        wait(lambda:monitor.sample()['process_count']==0,30);report['passed']=process.returncode==0 and max(timers)<=3
    finally:
        if owned and process and process.poll() is None:cmd('stop');process.wait(timeout=30)
        monitor.close();(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
