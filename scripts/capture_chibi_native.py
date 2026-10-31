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
    parser.add_argument('--scenes',nargs='+',default=['reading']);parser.add_argument('--variants',type=int,default=3)
    parser.add_argument('--duration',type=float,default=18);parser.add_argument('--size',type=int,default=195)
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
    SettingsStore().save(Settings(ai_provider='none',size=args.size,cursor_reaction=False))
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
        for scene in args.scenes:
            for variant in range(args.variants):
                name=f'{scene}-v{variant}'
                cmd('qa_life',{'action':scene,'duration':args.duration,'variant':variant})
                cmd('qa_record',{'name':name,'duration':args.duration+.3,'fps':24})
                wait(lambda:(out/name/'capture.json').is_file(),args.duration+12)
                data=json.loads((out/name/'capture.json').read_text(encoding='utf-8'))
                files=sorted((out/name).glob('*.png'));frames=[]
                for file in files:
                    im=Image.open(file).convert('RGBA');bg=Image.new('RGBA',im.size,'#17212b');bg.alpha_composite(im);frames.append(bg.convert('RGB'))
                times=[r['at'] for r in data['frames']];durations=[max(1,round((b-a)*1000)) for a,b in zip(times,times[1:])]+[42]
                frames[0].save(out/f'{name}.webp',save_all=True,append_images=frames[1:],duration=durations,lossless=True,loop=0)
                frames[0].save(out/f'{name}.gif',save_all=True,append_images=frames[1:],duration=durations,loop=0)
                indices=[round((len(frames)-1)*q) for q in (.04,.12,.20,.29,.39,.475,.515,.565,.63,.81,.86,.94)]
                w,h=frames[0].size;sheet=Image.new('RGB',((w+10)*4,(h+30)*3),'#17212b');draw=ImageDraw.Draw(sheet)
                for i,index in enumerate(indices):
                    x=i%4*(w+10);y=i//4*(h+30);sheet.paste(frames[index],(x,y+25));draw.text((x,y+4),f'{times[index]:.2f}s',fill='white')
                sheet.save(out/f'{name}-timeline.png')
                row={'name':name,'frames':len(frames),'seconds':times[-1]-times[0],
                    'mean_capture_fps':(len(times)-1)/(times[-1]-times[0]),
                    'production_frame_signatures':len({r['signature'] for r in data['frames']})}
                report['captures'].append(row);print(json.dumps(row),flush=True)
        cmd('stop');process.wait(timeout=30);owned=None;report['completed']=process.returncode==0
    finally:
        if owned and process and process.poll() is None:cmd('stop');process.wait(timeout=30)
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
