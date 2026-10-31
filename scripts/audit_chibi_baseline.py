"""Capture the released reading scene in an isolated native EXE profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Existing evidence preserved')
    out.mkdir(parents=True);ns=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=ns,
        GRANGERPET_QA_VAULT='GrangerPet/QA/chibi_'+ns,GRANGERPET_INTERACTION_TRACE=str(out/'trace.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    SettingsStore().save(Settings(ai_provider='none',size=195,cursor_reaction=False))
    report={'method':'Released native EXE; QA snapshots of the live production pet surface, not a new storyboard',
        'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'api_requests':0,'captures':[]}
    process=None;owned=None
    def cmd(name,payload=None):
        value=send_command('pet',name,payload,timeout=3000)
        if not value or not value.get('ok'):raise RuntimeError('Own command failed: '+name)
        return value
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.1)
        raise TimeoutError('Own baseline wait expired')
    try:
        with (out/'process.log').open('wb') as log:
            process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(lambda:send_command('pet','status'))['pid'];wait(lambda:cmd('status').get('desktop',{}).get('ready'))
        cmd('qa_figure',{'action':'away'});cmd('qa_life',{'action':'reading','duration':18});start=time.monotonic()
        for i in range(39):
            due=start+i*.5
            while time.monotonic()<due:time.sleep(min(.05,due-time.monotonic()))
            current=cmd('status')
            if current['pid']!=owned:raise RuntimeError('Own PID mismatch')
            name='reading-'+str(i).zfill(3);cmd('qa_snapshot',{'name':name})
            report['captures'].append({'name':name,'elapsed':round(time.monotonic()-start,3),'life':current['life']})
        cmd('stop');process.wait(timeout=30);owned=None
        images=[]
        for row in report['captures']:
            image=Image.open(out/(row['name']+'-pet.png')).convert('RGBA')
            bg=Image.new('RGBA',image.size,'#17212b');bg.alpha_composite(image);images.append(bg.convert('RGB'))
        images[0].save(out/'released-reading.gif',save_all=True,append_images=images[1:],duration=500,loop=0)
        report['completed']=process.returncode==0
    finally:
        if owned and process and process.poll() is None:
            cmd('stop');process.wait(timeout=30)
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'captures':len(report['captures']),'completed':report.get('completed')}))


if __name__=='__main__':main()
