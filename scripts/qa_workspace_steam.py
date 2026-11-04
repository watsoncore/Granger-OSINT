"""One bounded real public Steam inventory/resume through the frozen UI bridge."""
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
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve()
    if out.exists():raise SystemExit('Preserve old receipts')
    out.mkdir(parents=True);ns=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=ns,GRANGERPET_QA_VAULT='GrangerPet/QA/steam_'+ns,GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    from grangerpet.agent_journal import InvestigationJournal
    from perf_process_metrics import ProcessSampler
    app=QCoreApplication([]);SettingsStore().save(Settings(source_root=str(ROOT),cursor_reaction=False,reduced_motion=True))
    report={'origin':'frozen-EXE/source-live','exe_sha256':hashlib.sha256(a.exe.read_bytes()).hexdigest(),'gateway_calls':0,'cookies_or_keys':False,'operations':[]}
    process=None;owned=None;monitor=ProcessSampler(a.exe,gpu=False)
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def wait(fn,seconds=70):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.3)
        raise TimeoutError('Own Steam QA deadline')
    def status():
        r=send_command('pet','status',timeout=8000)
        if r and owned and r.get('pid')!=owned:raise RuntimeError('Unrelated app')
        return r
    def command(name,payload=None):
        r=send_command('pet',name,payload or {},timeout=12000)
        if not r or not r.get('ok'):raise RuntimeError('Own Steam command failed')
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.3)
    def snapshot():
        command('qa_desktop',{'action':'save_state','name':'current-state'})
        return json.loads((out/'current-state.json').read_text(encoding='utf-8'))
    def inventory(cursor=None):
        args={'profile':'76561198045277210','page_size':100,'max_pages':2,'price_limit':0,**({'cursor':cursor} if cursor else {})}
        action('tool_run',{'tool':'steam_inventory','arguments':args,'limit':10});wait(lambda:snapshot()['search']['busy'],5)
        result=wait(lambda:s if not (s:=snapshot())['search']['busy'] else None,70)
        activity=next(row for row in result['activity'] if row['id']=='steam_inventory')
        journal=InvestigationJournal(Path(os.environ['APPDATA'])/'GrangerPet/investigations').load(result['search']['investigation_id'])
        rows=journal.get('evidence',[])
        summaries=[r for r in rows if r['type']=='steam_inventory']
        summary=max(summaries,key=lambda r:r.get('provenance',{}).get('obtained_at',''))['details'] if summaries else {}
        receipt={'status':activity['status'],'coverage':summary.get('coverage',{}),'source_failures':summary.get('source_failures',[]),
            'retained_item_records':sum(r['type']=='steam_item' for r in rows),'gui_busy_after_completion':result['search']['busy'],'resume_cursor_supplied':bool(cursor)}
        report['operations'].append(receipt);save();return receipt
    try:
        with (out/'process.log').open('wb') as log:process=subprocess.Popen([str(a.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(status)['pid'];monitor.sample([process.pid]);wait(lambda:status()['desktop']['ready'])
        command('show_workspace',{'route':'search'});r=inventory();cursor=r['coverage'].get('next_cursor')
        if cursor and r['coverage'].get('more_items'):inventory(cursor)
        report['live_item_data_verified']=any(r['retained_item_records'] for r in report['operations'])
        report['fresh_prices_verified']=False
        report['passed']=all(not r['gui_busy_after_completion'] for r in report['operations'])
    except Exception as e:report.update(passed=False,error_type=type(e).__name__,error=str(e)[:180]);raise
    finally:
        if process and process.poll() is None:
            if status():command('stop')
            process.wait(timeout=30)
        if process:
            report['owned_processes_left']=monitor.sample([process.pid])['process_count']
            if report['owned_processes_left']:report['passed']=False
        monitor.close();save()
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
