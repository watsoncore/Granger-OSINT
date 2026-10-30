"""Actual frozen launcher/pet smoke with isolated profile and minimal PATH."""
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
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Prior evidence retained; choose a new output')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),GRANGERPET_QA_VAULT='GrangerPet/QA/smoke_'+namespace)
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY','GRANGERPET_QA_INPUT_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(ai_provider='none',source_root=str(ROOT),cursor_reaction=False,reduced_motion=True).to_dict()),encoding='utf-8')
    env=os.environ.copy();env['PATH']=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32')
    report={'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'gateway_calls':0,'user_data_read':False,'checks':[]}
    for role in ('launcher','pet'):
        argv=[str(args.exe.resolve()),'--interaction-qa','--smoke-test']+(['--pet'] if role=='pet' else [])
        with (out/(role+'.log')).open('wb') as log:process=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        ready=False;end=time.monotonic()+55;owned=None
        try:
            while time.monotonic()<end and process.poll() is None:
                state=send_command(role,'status',timeout=500)
                if state:
                    owned=state['pid']
                    ready=state.get('desktop_ready') if role=='launcher' else state.get('desktop',{}).get('ready')
                    if ready:break
                time.sleep(.1)
            process.wait(timeout=25)
        finally:
            if process.poll() is None:
                if role=='pet':send_command(role,'stop',timeout=1000)
                else:send_command(role,'qa_launcher',{'action':'launcher_exit','name':'stopped'},timeout=1000)
                process.wait(timeout=25)
        report['checks'].append({'surface':role,'real_renderer_ready':bool(ready),'exit_zero':process.returncode==0,'owned_pid':owned})
    report['passed']=all(row['real_renderer_ready'] and row['exit_zero'] for row in report['checks'])
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
