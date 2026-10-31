"""Record owned production Qt windows; never capture other desktop content."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenes',nargs='+',default=['reading']);parser.add_argument('--variants',type=int,default=0)
    parser.add_argument('--duration',type=float,default=0);parser.add_argument('--size',type=int,default=195)
    parser.add_argument('--mode',choices=('widget','native_text'),default='widget')
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Existing evidence preserved')
    out.mkdir(parents=True);ns=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=ns,
        GRANGERPET_QA_VAULT='GrangerPet/QA/chibi_'+ns,GRANGERPET_INTERACTION_TRACE=str(out/'trace.jsonl'))
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    SettingsStore().save(Settings(ai_provider='none',size=args.size,cursor_reaction=False,x=30,y=400))
    owned=None;process=None;report={'mode':'native EXE' if args.exe else 'native current source','api_requests':0,'captures':[]}
    report['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'grangerpet').glob('*.py')}
    if args.exe:report['exe_sha256']=hashlib.sha256(args.exe.read_bytes()).hexdigest()
    def cmd(name,payload=None):
        result=send_command('pet',name,payload,timeout=3000)
        if not result or not result.get('ok'):raise RuntimeError('Own command failed: '+name)
        if name=='status' and owned and result['pid']!=owned:raise RuntimeError('Own PID mismatch')
        return result
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.15)
        raise TimeoutError('Own native capture timed out')
    try:
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        with (out/'process.log').open('wb') as log:process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(lambda:send_command('pet','status'))['pid'];wait(lambda:cmd('status').get('desktop',{}).get('ready'))
        cmd('qa_figure',{'action':'away'})
        if args.mode=='native_text':
            cmd('show_workspace',{'route':'chat'});time.sleep(1.)
            cmd('qa_desktop',{'action':'dom','payload':{}});time.sleep(.2)
            elements=cmd('status').get('desktop',{}).get('dom',{}).get('elements',[])
            restore=next((e for e in elements if e.get('label')=='Показать Гермиону и источники' and e.get('width',0)>0),None)
            if restore:
                cmd('qa_desktop',{'action':'input','payload':{'kind':'click','at':[restore['x']+restore['width']/2,restore['y']+restore['height']/2]}})
            wait(lambda:cmd('status').get('desktop',{}).get('dock_geometry',[0,0,0,0])[2]>100,10)
            time.sleep(.5)
        for scene in args.scenes:
            counts={'reading':3,'shy':3,'annoyed':3,'wand_play':4,'malfoy':2,'harry':2,'ron_chat':2}
            for variant in range(args.variants or counts.get(scene,1)):
                from grangerpet.pet_life import SCENES
                legacy={'cast':2.5,'avada':3.2,'yawn':2.1,'sleep':60.,'leave':2.8,'away':6.,'return':1.6,'wake':.65,'settle':.3}
                duration=args.duration or (SCENES[scene].duration if scene in SCENES else legacy.get(scene,6.))
                if not args.duration and scene=='malfoy' and variant==0:duration=9.
                capture_duration=15. if scene=='leave' and not args.duration else duration+1. if scene=='sleep' else duration+.3
                name=f'{scene}-v{variant}'
                cmd('qa_life',{'action':scene,'duration':duration,'variant':variant})
                cmd('qa_record',{'name':name,'duration':capture_duration,'fps':12 if scene=='sleep' else 24,'mode':args.mode})
                wait(lambda:(out/name/'capture.json').is_file(),capture_duration+12)
                data=json.loads((out/name/'capture.json').read_text(encoding='utf-8'))
                active=[r for r in data['frames'] if r['action']==scene]
                if not active or (scene!='leave' and len(active)<len(data['frames'])*(.4 if duration<1 else .75)) or max((r['progress'] for r in active),default=0)<(.75 if duration<1 else .95):
                    raise AssertionError('Visual capture interrupted; retained as failed evidence: '+name)
                from assemble_chibi_capture import assemble
                assembly=assemble(out/name);times=[r['at'] for r in data['frames']]
                row={'name':name,'frames':assembly['frames'],'seconds':times[-1]-times[0],'mode':args.mode,'production_duration':duration,
                    'mean_capture_fps':(len(times)-1)/(times[-1]-times[0]),
                    'production_frame_signatures':len({r['signature'] for r in data['frames']})}
                report['captures'].append(row);print(json.dumps(row),flush=True)
        cmd('stop');process.wait(timeout=30);owned=None;report['completed']=process.returncode==0
    finally:
        if owned and process and process.poll() is None:cmd('stop');process.wait(timeout=30)
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
