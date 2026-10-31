"""Own native Pet/Qt/WebEngine QA; isolated profile, no credentials or API calls."""
from __future__ import annotations
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
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exe',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Choose a new output; previous evidence retained')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_QA_VAULT='GrangerPet/QA/pet_'+namespace,GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    SettingsStore().save(Settings(ai_provider='none',size=160,cursor_reaction=True,source_root=str(ROOT)))
    report={'mode':'native_final_exe' if args.exe else 'native_current_source','network_calls':0,
        'empty_isolated_profile':True,'checks':[]}
    if args.exe:report['exe_sha256']=hashlib.sha256(args.exe.read_bytes()).hexdigest()
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});save();print(name+': '+str(bool(ok)),flush=True)
        if not ok:raise AssertionError(name)
    owned=None;process=None
    def state():
        value=send_command('pet','status',timeout=1500)
        if value and owned and value['pid']!=owned:raise RuntimeError('Own isolated PID mismatch')
        return value
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=3000)
        if not value or not value.get('ok'):raise RuntimeError('Own command failed: '+name)
        return value
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}})
    def wait(fn,seconds=40):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.12)
        raise TimeoutError('Own pet QA condition did not complete')
    def dom():
        action('dom');time.sleep(.12)
        return (state().get('desktop') or {}).get('dom',{})
    def capture(name):command('qa_snapshot',{'name':name})
    try:
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        with (out/'process.log').open('wb') as log:
            process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(state,60)['pid'];wait(lambda:state().get('desktop',{}).get('ready'))
        command('qa_figure',{'action':'away'})
        a=state();time.sleep(.4);b=state()
        check('native_idle_pixels_advance',a['pet_render']['signature']!=b['pet_render']['signature'])
        command('show_workspace',{'route':'chat'});action('window',{'mode':'maximize'})
        wait(lambda:next((e for e in dom().get('elements',[]) if e.get('label')=='Сообщение Гермионе'),None))
        restore=next((e for e in dom().get('elements',[]) if e.get('label')=='Показать Гермиону и источники' and e['width']>0),None)
        if restore:action('input',{'kind':'click','at':[restore['x']+restore['width']/2,restore['y']+restore['height']/2]})
        wait(lambda:state()['pet_render']['visible'])
        command('qa_figure',{'action':'away'});time.sleep(.3)
        command('qa_life',{'action':'schedule'})
        live=wait(lambda:s if (s:=state())['life']['active'] else None,10)
        name=live['life']['action'];check('scheduler_starts_while_workspace_active',name in ('reading','cast','avada'))
        for route in ('search','settings','history','chat'):
            action('route',{'route':route});time.sleep(.3)
            check('navigation_'+route+'_does_not_reset_figure_idle',state()['life']['action']==name)
        e=wait(lambda:next((e for e in dom().get('elements',[]) if e.get('label')=='Сообщение Гермионе' and e['width']>0),None))
        action('input',{'kind':'click','at':[e['x']+30,e['y']+15]})
        action('input',{'kind':'text','text':'Native QA draft, no request sent.'})
        check('typing_draft_does_not_cancel_autonomy',state()['life']['action']==name)
        capture('autonomy-during-work')
        command('qa_figure',{'action':'hover'})
        wait(lambda:not state()['life']['active'],4)
        check('real_figure_hover_interrupts_scene',state()['near'] or state()['hovered'])
        command('qa_figure',{'action':'away'})
        command('qa_life',{'action':'reading'});time.sleep(.8);capture('reading')
        command('qa_figure',{'action':'drag_up'});time.sleep(.2)
        check('actual_up_drag_reaction',state()['drag_reaction']=='jerk_up')
        capture('up-drag');time.sleep(2.6)
        command('qa_figure',{'action':'drag_down'});time.sleep(.2)
        check('actual_down_drag_reaction',state()['drag_reaction']=='jerk_down')
        capture('down-drag')
        wait(lambda:state()['drag_reaction']=='calm',8)
        check('release_recovers_without_drag_timer',not state()['pet_render']['drag_timer'])
        for size in (100,195,160):
            command('settings',{'size':size});time.sleep(.3)
            check('scale_'+str(size)+'_visible',state()['pet_render']['visible'])
        command('qa_figure',{'action':'away'});command('qa_life',{'action':'reading'})
        wait(lambda:state()['life']['active']);wait(lambda:not state()['life']['active'],8)
        check('scene_completes_and_clears',True)
        command('stop');process.wait(timeout=30);owned=None
        check('native_exit_zero',process.returncode==0);report['passed']=True
    except Exception as error:
        if owned:
            try:
                last=state();report['last_pet']={k:last.get(k) for k in ('state','near','hovered','life','pet_render')}
            except Exception:pass
        report.update(passed=False,error_type=type(error).__name__,error=str(error));raise
    finally:
        if owned and process and process.poll() is None:
            try:command('stop');process.wait(timeout=30)
            except Exception:process.terminate()
        save()


if __name__=='__main__':main()
