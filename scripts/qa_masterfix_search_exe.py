"""Native automatic-search reproduction in an isolated frozen Windows app.

No gateway credentials, original histories or Gansar databases are used.
The default target is the public TON address explicitly requested by the owner.
"""
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
TARGET='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--target',default=TARGET)
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Prior evidence retained; choose a new output')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),GRANGERPET_QA_VAULT='GrangerPet/QA/masterfix_'+namespace)
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY','GRANGERPET_QA_INPUT_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    (profile/'settings.json').write_text(json.dumps(Settings(ai_provider='none',source_root=str(ROOT),
        cursor_reaction=False,reduced_motion=True).to_dict()),encoding='utf-8')
    report={'mode':'actual_frozen_Qt_WebEngine_native_automatic_search','mock':False,'gateway_calls':0,
        'user_data_read':False,'target':args.target,'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'checks':[]}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});save()
        if not ok:raise AssertionError(name)
    owned=None;process=None
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=4000)
        if not value or not value.get('ok'):raise RuntimeError('Own isolated command failed: '+name)
        if name=='status' and owned and value['pid']!=owned:raise RuntimeError('Own IPC PID mismatch')
        return value
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.2)
    def dom():
        action('dom');value=command('status')['desktop'].get('dom',{})
        (out/'last-dom.json').write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return value
    def wait(fn,seconds=70):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.15)
        raise TimeoutError('Bounded own-GUI wait expired')
    def snapshot(name='current'):
        command('qa_desktop',{'action':'save_state','name':name})
        return json.loads((out/(name+'.json')).read_text(encoding='utf-8'))
    def click(e):action('input',{'kind':'click','at':[e['x']+e['width']/2,e['y']+min(e['height']/2,18)]})
    try:
        with (out/'process.log').open('wb') as log:process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        end=time.monotonic()+55
        while time.monotonic()<end:
            state=send_command('pet','status',timeout=500)
            if state:owned=state['pid'];break
            time.sleep(.1)
        if not owned:raise TimeoutError('Own EXE did not start')
        wait(lambda:command('status')['desktop']['ready']);command('show_workspace',{'route':'search'})
        entry=wait(lambda:next((e for e in dom().get('elements',[]) if e.get('type')=='text' and e['width']>300 and e['y']>0),None))
        click(entry);action('input',{'kind':'text','text':args.target})
        find=wait(lambda:next((e for e in dom()['elements'] if e.get('text')=='Найти' and e['width']>0),None))
        check('native_address_entry',snapshot()['search'].get('query') in ('',args.target))
        started=time.monotonic();click(find)
        wait(lambda:snapshot()['search']['busy'])
        value=wait(lambda:s if not (s:=snapshot())['search']['busy'] else None,160)
        snapshot('finished')
        wait(lambda:value['search'].get('checkedLabel','') in dom().get('text','') and not any(e.get('text')=='Остановить' for e in dom()['elements']))
        command('qa_snapshot',{'name':'automatic-search'})
        report.update(elapsed_seconds=round(time.monotonic()-started,3),search={key:val for key,val in value['search'].items() if key not in ('results','choices')},
            result_count=len(value['search']['results']),result_kinds={},activity=value['activity'])
        for row in value['search']['results']:
            kind=row.get('kind','unknown');report['result_kinds'][kind]=report['result_kinds'].get(kind,0)+1
        report['rendered_status_text']=dom().get('text','')[:2500]
        from grangerpet.validators.ton_address import parse_ton_address
        target=parse_ton_address(args.target);query=parse_ton_address(value['search']['query'])
        check('actual_query_matches_requested_address',bool(query and target and query['raw']==target['raw']))
        check('completion_reaches_gui',not value['busy'] and not value['search']['busy'])
        command('stop');process.wait(timeout=30);owned=None;check('clean_exit',process.returncode==0)
        report['passed']=True;save()
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:200]);save();raise
    finally:
        if process and process.poll() is None:command('stop');process.wait(timeout=30)
    print(json.dumps({key:report[key] for key in ('passed','elapsed_seconds','result_count','search')},ensure_ascii=True))


if __name__=='__main__':main()
