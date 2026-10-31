"""Read-only native idle CPU/memory measurement in one empty namespaced profile."""
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Previous benchmark retained')
    out.mkdir(parents=True);ns=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=ns,
        GRANGERPET_QA_VAULT='GrangerPet/QA/perf_'+ns,GRANGERPET_INTERACTION_TRACE=str(out/'trace.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    from perf_process_metrics import ProcessSampler,summarize
    SettingsStore().save(Settings(ai_provider='none',size=195,fps=24,cursor_reaction=False,source_root=str(ROOT)))
    monitor=ProcessSampler(args.exe,gpu=False);owned=None;process=None
    report={'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'size':195,'fps':24,
        'cursor_reaction':False,'network_calls':0,'workspace':'hidden','samples':[]}
    def command(name):return send_command('pet',name,timeout=2000)
    try:
        with (out/'process.log').open('wb') as log:
            process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            current=command('status')
            if current and current.get('desktop',{}).get('ready'):
                owned=current['pid'];break
            time.sleep(.2)
        if not owned:raise TimeoutError('Own fresh EXE not ready')
        time.sleep(3);monitor.sample([owned])
        for _ in range(3):time.sleep(5);report['samples'].append(monitor.sample([owned]))
        report['summary']=summarize(report['samples'])
        command('stop');process.wait(timeout=30);owned=None
        deadline=time.monotonic()+20
        while monitor.sample()['process_count'] and time.monotonic()<deadline:time.sleep(.2)
        report['no_owned_orphans']=monitor.sample()['process_count']==0
        report['passed']=process.returncode==0 and report['no_owned_orphans']
    finally:
        if owned and process and process.poll() is None:command('stop');process.wait(timeout=30)
        monitor.close();(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'summary':report['summary']}))


if __name__=='__main__':main()
