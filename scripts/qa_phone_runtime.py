"""Owned final EXE: interrupt active phone typing and cold-restart cleanly."""
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=args.output.resolve()
    if out.exists():raise SystemExit('Previous evidence preserved')
    out.mkdir(parents=True);ns=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=ns,GRANGERPET_QA_VAULT='GrangerPet/QA/phone_'+ns,GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    from perf_process_metrics import ProcessSampler
    SettingsStore().save(Settings(ai_provider='none',size=195,cursor_reaction=True))
    report={'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'checks':[],'isolated_profile':True,'api_requests':0}
    owned=None;process=None;monitor=ProcessSampler(args.exe,gpu=False)
    def cmd(name,payload=None):
        v=send_command('pet',name,payload,timeout=3000)
        if not v or not v.get('ok'):raise RuntimeError('Own command failed: '+name)
        if name=='status' and owned and v['pid']!=owned:raise RuntimeError('Own PID mismatch')
        return v
    def wait(fn,seconds=40):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            v=fn()
            if v:return v
            time.sleep(.15)
        raise TimeoutError('Own phone QA timeout')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});print(name+': '+str(bool(ok)),flush=True)
        if not ok:raise AssertionError(name)
    def typing():
        # Figure input and scene start are queued in the native event loop.
        # Flush the real mouse-leave event before starting the next scene;
        # otherwise that pending event legitimately interrupts it.
        cmd('qa_figure',{'action':'away'});time.sleep(.3)
        cmd('qa_life',{'action':'phone_solvnox','duration':13})
        wait(lambda:cmd('status')['life']['action']=='phone_solvnox',3)
        time.sleep(4.8);check('actual_phone_typing_active',cmd('status')['life']['action']=='phone_solvnox')
    argv=[str(args.exe.resolve()),'--pet','--interaction-qa']
    try:
        with (out/'process.log').open('wb') as log:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(lambda:send_command('pet','status',timeout=1500))['pid'];wait(lambda:cmd('status').get('desktop',{}).get('ready'))
        monitor.sample([owned])
        for event,reaction in (('hover',None),('drag_up','jerk_up'),('drag_down','jerk_down')):
            typing();cmd('qa_snapshot',{'name':'typing-before-'+event});cmd('qa_figure',{'action':event});time.sleep(.25)
            current=cmd('status');check(event+'_interrupts_phone',current['life']['action']!='phone_solvnox')
            if reaction:check(event+'_physical_reaction',current['drag_reaction']==reaction)
            cmd('qa_snapshot',{'name':'after-'+event})
            if reaction:wait(lambda:cmd('status')['drag_reaction']=='calm',8)
            check(event+'_no_added_timer',cmd('status')['pet_render']['owned_timer_count']==3)
        monitor.sample([owned]);cmd('stop');process.wait(timeout=30);owned=None;check('first_exit_zero',process.returncode==0)
        wait(lambda:monitor.sample()['process_count']==0,30);check('no_owned_orphans',True)
        with (out/'restart.log').open('wb') as log:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(lambda:send_command('pet','status',timeout=1500))['pid'];wait(lambda:cmd('status').get('desktop',{}).get('ready'))
        s=cmd('status');check('restart_has_no_phone_or_guest',not s['life']['active'] and not s['cameo']['visible'])
        cmd('qa_snapshot',{'name':'restarted-original-idle'});monitor.sample([owned]);cmd('stop');process.wait(timeout=30);owned=None
        wait(lambda:monitor.sample()['process_count']==0,30);check('restart_exit_zero_without_orphans',process.returncode==0);report['passed']=True
    finally:
        if owned and process and process.poll() is None:cmd('stop');process.wait(timeout=30)
        monitor.close();(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
