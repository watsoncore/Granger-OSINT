"""Keep an isolated synthetic-history EXE open for targeted native UI checks."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from PySide6.QtCore import QCoreApplication
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('start','check','finish'),required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'output/performance-qa/ui')
    args=parser.parse_args();app=QCoreApplication([]);out=args.output.resolve();target=out/'report.json'
    exe=ROOT/'dist/Granger-OSINT.exe';sha=hashlib.sha256(exe.read_bytes()).hexdigest()
    if args.phase=='start':
        if out.exists():raise SystemExit('Existing evidence preserved')
        if send_command('pet','status') or send_command('launcher','status'):raise SystemExit('An existing instance is active')
        out.mkdir(parents=True)
        profile=out/'appdata/GrangerPet'
        shutil.copytree(ROOT/'output/performance-qa/long-exe-final/long/appdata/GrangerPet',profile)
        settings=json.loads((profile/'settings.json').read_text(encoding='utf-8'));settings['ai_provider']='none'
        (profile/'settings.json').write_text(json.dumps(settings),encoding='utf-8')
        env=os.environ.copy()
        for key in ('QT_QPA_PLATFORM','QT_SCALE_FACTOR','QTWEBENGINE_CHROMIUM_FLAGS','GRANGERPET_QA_VAULT','DEEPSEEK_API_KEY','GEMINI_API_KEY'):env.pop(key,None)
        env.update(APPDATA=str(out/'appdata'),GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
        with (out/'process.log').open('wb') as log:
            process=subprocess.Popen([str(exe),'--pet','--interaction-qa'],cwd=ROOT,env=env,
                stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        report={'exe_sha256':sha,'pid':None,'checks':[],'synthetic_profile':True,'api_generation_enabled':False}
    else:
        report=json.loads(target.read_text(encoding='utf-8'));assert report['exe_sha256']==sha
    def save():target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def state():
        s=send_command('pet','status',timeout=3000)
        if s and report['pid'] and s['pid']!=report['pid']:raise RuntimeError('Unexpected instance')
        return s
    def wait(fn,seconds=40):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.2)
        raise TimeoutError('UI QA bounded wait expired')
    def command(name,payload=None):
        s=state();assert s and Path(process_image(s['pid'])).resolve()==exe.resolve()
        r=send_command('pet',name,payload,timeout=3000);assert r and r.get('ok')
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)});save();assert value,name
    if args.phase=='start':
        s=wait(lambda:s if (s:=state()) and s.get('desktop',{}).get('ready') else None)
        report['pid']=s['pid'];save();command('show_workspace',{'route':'chat'})
        print('Isolated real EXE ready for native checks',flush=True);process.wait();return
    elif args.phase=='check':
        command('qa_desktop',{'action':'dom'});time.sleep(.5);s=state();dom=s['desktop']['dom']
        report['mounted_messages']=dom.get('messages');report['history_model_messages']=s['ai_model_messages']
        report['font_loaded']=dom.get('font',{}).get('loaded')
        check('full_history_retained',s['ai_model_messages']>=500)
        check('bounded_mounted_messages',0<dom.get('messages',0)<50)
        check('no_horizontal_overflow',not dom.get('overflow',True))
        check('font_preserved',dom.get('font',{}).get('loaded'))
        command('qa_desktop',{'action':'window','payload':{'mode':'minimize'}})
        wait(lambda:(s:=state()) and s['desktop']['page_visible'] is False,8)
        check('minimized_page_hidden_from_chromium',True)
        command('show_workspace',{'route':'chat'})
        wait(lambda:(s:=state()) and s['desktop']['lifecycle_state']=='Active',8)
        check('restored_page_active',True)
        for mode in ('windowed','maximized','fullscreen','windowed'):
            command('qa_window_mode',{'mode':mode});time.sleep(.5);s=state()
            check('window_mode_'+mode,s['window']['fullscreen'] if mode=='fullscreen' else
                s['window']['maximized'] if mode=='maximized' else not s['window']['fullscreen'] and not s['window']['maximized'])
    else:
        command('stop');wait(lambda:not state(),15);check('own_exe_stopped',True)
        report['passed']=all(row['passed'] for row in report['checks'])
    save();print(json.dumps({'phase':args.phase,'checks':len(report['checks'])}))


if __name__=='__main__':main()
