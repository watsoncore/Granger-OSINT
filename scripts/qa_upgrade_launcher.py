"""Actual packaged launcher/independent pet lifecycle in a disposable profile."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'output/upgrade-qa/launcher-release')
    parser.add_argument('--scale',type=float)
    args=parser.parse_args()
    app = QApplication([])
    native_dpr=app.primaryScreen().devicePixelRatio()
    area=app.primaryScreen().availableGeometry()
    physical_area=(round(area.width()*native_dpr),round(area.height()*native_dpr))
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('Prior launcher evidence is preserved')
    if send_command('pet','status') or send_command('launcher','status'):
        raise SystemExit('Close existing app before isolated launcher QA')
    out.mkdir(parents=True)
    profile = out/'appdata/GrangerPet'
    profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(ai_provider='none', source_root=str(ROOT)).to_dict()),encoding='utf-8')
    env=os.environ.copy()
    for key in ('QT_QPA_PLATFORM','QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS','GRANGERPET_QA_VAULT','GRANGERPET_QA_INPUT_KEY','DEEPSEEK_API_KEY','GEMINI_API_KEY'):
        env.pop(key,None)
    env.update(APPDATA=str(out/'appdata'), GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    if args.scale: env['QT_SCALE_FACTOR']=str(args.scale/native_dpr)
    exe=ROOT/'dist/Granger-OSINT.exe'
    report={'tested_at_utc':datetime.now(timezone.utc).isoformat(), 'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
        'method':'Actual Windows EXE React launcher, native IPC and independently launched pet; no API calls',
        'measured_native_dpr':native_dpr,'requested_child_dpr':args.scale or native_dpr,'available_physical_size':physical_area,'checks':[]}
    processes=[]
    pid=None
    pet_pid=None
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value: raise AssertionError(name)
    def wait(predicate,seconds=40):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            result=predicate()
            if result: return result
            time.sleep(.15)
        raise TimeoutError('Bounded launcher wait expired')
    def launch():
        nonlocal pid
        process=subprocess.Popen([str(exe),'--interaction-qa'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(process)
        status=wait(lambda:send_command('launcher','status',timeout=200))
        pid=status['pid']
        check('verified_launcher_executable',Path(process_image(pid)).resolve()==exe.resolve())
        wait(lambda:send_command('launcher','status').get('desktop_ready'),20)
    def action(name,action=None,payload=None):
        status=send_command('launcher','status')
        if not status or status['pid']!=pid: raise RuntimeError('Unexpected launcher instance')
        receipt=name+'-action'
        response=send_command('launcher','qa_launcher',{'name':receipt,'action':action,'payload':payload or {}})
        if not response or not response.get('ok'): raise RuntimeError('QA action rejected')
        wait(lambda:(out/(receipt+'.json')).is_file(),5)
        # WebChannel acknowledgements precede the Chromium compositor paint.
        # Capture after the renderer has received and painted its state patch.
        time.sleep(.65)
        send_command('launcher','qa_launcher',{'name':name})
        wait(lambda:(out/(name+'.json')).is_file(),5)
        return json.loads((out/(name+'.json')).read_text(encoding='utf-8'))
    def pet_ready():
        status=send_command('pet','status',timeout=200)
        return status if status and status.get('desktop',{}).get('ready') else None
    try:
        launch()
        initial=action('01-launcher-ready')
        check('initial_ready',initial['launcher']['state']=='ready' and not initial['launcher']['running'])
        image=QImage(str(out/'01-launcher-ready.png'))
        report['launcher_physical_size']=[image.width(),image.height()]
        check('launcher_fits_physical_work_area',not image.isNull() and image.width()<=physical_area[0] and image.height()<=physical_area[1])
        action('02-preferences','launcher_preferences',{'size':150,'fps':18,'cursor_reaction':False})
        saved=json.loads((profile/'settings.json').read_text())
        check('preferences_persisted',(saved['size'],saved['fps'],saved['cursor_reaction'])==(150,18,False))
        action('03-starting','launcher_start')
        pet=wait(pet_ready);pet_pid=pet['pid']
        check('verified_independent_pet_executable',pet_pid!=pid and Path(process_image(pet_pid)).resolve()==exe.resolve())
        check('actual_pet_initial_size',pet['size']==150)
        wait(lambda:send_command('launcher','status').get('state')=='running',5)
        running=action('04-running')
        check('launcher_state_matches_real_process',running['launcher']['running'] and running['launcher']['state']=='running')
        action('04a-live-preferences','launcher_preferences',{'size':180,'fps':24,'cursor_reaction':True})
        wait(lambda:send_command('pet','status').get('size')==180,5)
        check('live_size_update',True)
        action('04b-restore-preferences','launcher_preferences',{'size':150,'fps':18,'cursor_reaction':False})
        wait(lambda:send_command('pet','status').get('size')==150,5)
        action('05-open-settings','route',{'route':'settings'})
        wait(lambda:send_command('pet','status').get('desktop',{}).get('route')=='settings',5)
        check('opens_existing_workspace',send_command('pet','status')['pid']==pet_pid)
        action('06-stopping','launcher_stop')
        wait(lambda:send_command('pet','status',timeout=100) is None,15)
        wait(lambda:send_command('launcher','status').get('state')=='stopped',5)
        check('actual_stop_and_status',True);pet_pid=None
        action('07-restart','launcher_start');pet=wait(pet_ready);pet_pid=pet['pid']
        wait(lambda:send_command('launcher','status').get('state')=='running',5)
        action('08-before-close')
        send_command('launcher','qa_launcher',{'name':'09-close','action':'window','payload':{'mode':'close'}})
        wait(lambda:send_command('launcher','status',timeout=100) is None,10)
        check('close_leaves_independent_pet_alive',send_command('pet','status')['pid']==pet_pid)
        launch();wait(lambda:send_command('launcher','status').get('state')=='running',5)
        restored=action('10-reopened')
        check('reopened_preferences_preserved',(restored['launcher']['size'],restored['launcher']['fps'],restored['launcher']['cursorReaction'])==(150,18,False))
        check('reopen_reuses_existing_pet',send_command('pet','status')['pid']==pet_pid)
        send_command('launcher','qa_launcher',{'name':'11-exit-all','action':'launcher_exit'})
        wait(lambda:send_command('launcher','status',timeout=100) is None and send_command('pet','status',timeout=100) is None,15)
        check('exit_all_stops_both',True);pet_pid=None
        report['passed']=True
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:180])
    finally:
        status=send_command('pet','status',timeout=100)
        if status and status['pid']==pet_pid: send_command('pet','stop')
        status=send_command('launcher','status',timeout=100)
        if status and status['pid']==pid:
            send_command('launcher','qa_launcher',{'name':'cleanup','action':'launcher_exit'})
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(report['checks']),'error':report.get('error')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
