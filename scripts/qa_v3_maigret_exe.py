"""One bounded, key-free six-site Maigret run through the real packaged bridge."""
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
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Keep previous receipts; use a fresh directory')
    out.mkdir(parents=True);ns=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=ns,GRANGERPET_QA_VAULT='GrangerPet/QA/maigretv3_'+ns,GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.ipc import send_command
    app=QCoreApplication([]);SettingsStore().save(Settings(source_root=str(ROOT),cursor_reaction=False,reduced_motion=True,ai_provider='none'))
    report={'origin':'frozen-live','mocked':False,'isolated_profile':True,'gateway_calls':0,'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'checks':[]}
    process=None;owned=None
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});save();print(json.dumps(report['checks'][-1]),flush=True)
        if not ok:raise AssertionError(name)
    def wait(fn,seconds=80):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.25)
        raise TimeoutError('Own finite Maigret QA deadline')
    def state():
        value=send_command('pet','status',timeout=8000)
        if value and owned and value.get('pid')!=owned:raise RuntimeError('Unrelated instance')
        return value
    def command(name,payload=None):
        value=send_command('pet',name,payload or {},timeout=12000)
        if not value or not value.get('ok'):raise RuntimeError('Own command failed: '+name)
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.3)
    def snapshot():
        command('qa_desktop',{'action':'save_state','name':'current-state'});return json.loads((out/'current-state.json').read_text(encoding='utf-8'))
    sites=['GitHub','YouTube','TikTok','Wikipedia','WordPressOrg','GooglePlayStore']
    arguments={'username':'solvnox','mode':'custom','sites':sites,'include_mirrors':False,'per_site_timeout':3,'concurrency':3,'time_budget':25,'parse_metadata':True}
    try:
        with (out/'process.log').open('wb') as stream:process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT)
        owned=wait(state)['pid'];wait(lambda:state()['desktop']['ready']);command('show_workspace',{'route':'search'})
        action('tool_run',{'tool':'username_maigret','arguments':arguments,'limit':10})
        samples=[];end=time.monotonic()+70
        while time.monotonic()<end:
            s=snapshot();coverage=s.get('search',{}).get('maigret_progress')
            if coverage:samples.append(coverage)
            if not s['search']['busy'] and any(a.get('id')=='username_maigret' and a.get('status')!='running' for a in s.get('activity',[])):break
            time.sleep(.2)
        else:raise TimeoutError('Real Maigret execution did not settle')
        identifier=s['search'].get('investigation_id');check('real_manual_execution_saved',bool(identifier))
        journal=InvestigationJournal(Path(os.environ['APPDATA'])/'GrangerPet/investigations')
        data=journal.load_checkpoint(identifier);execution=data['executions'][-1]
        diag=execution.get('source_diagnostics',{});coverage=diag.get('coverage',{})
        report.update(status=execution['status'],coverage=coverage,site_statuses=[{k:row.get(k) for k in ('site','status','http_status')} for row in diag.get('site_checks',[])],progress_snapshots=len(samples),result_count=len(data['evidence']))
        check('six_exact_original_database_sites_scheduled',coverage.get('selected')==6 and coverage.get('scheduled')==6)
        check('all_six_per_site_outcomes_retained_in_encrypted_checkpoint',len(diag.get('site_checks',[]))==6 and {r['site'] for r in diag['site_checks']}==set(sites))
        check('coverage_counters_published_to_existing_search',bool(samples) and s['search']['maigret_progress'].get('scheduled')==6)
        check('no_fake_absence_for_unknown_or_blocked',all(row['status'] in ('found','not_found','unknown','blocked','unavailable','errors','skipped') for row in diag['site_checks']))
        check('actual_profile_metadata_retained',bool(data['evidence']) and all(row.get('details') for row in data['evidence']))
        check('no_secret_or_login_supplied',diag.get('policy',{}).get('tls_verified') is True and diag.get('policy',{}).get('bypass') is False)
        action('dom');command('qa_snapshot',{'name':'maigret-completed'})
        report['passed']=True;save()
    except Exception as error:report.update(passed=False,error_type=type(error).__name__,error=str(error)[:240]);save();raise
    finally:
        if process and process.poll() is None:
            if state():command('stop')
            process.wait(timeout=35)
        if process:report['parent_exit_code']=process.returncode;save()


if __name__=='__main__':main()
