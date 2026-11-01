"""Actual packaged Qt/WebChannel/manual-tools/chat check in an isolated QA profile."""
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
    from grangerpet.ai_keys import resolve_deepseek_key
    from grangerpet.credentials import WindowsLegacyStore
    from grangerpet.config import Settings
    from PySide6.QtCore import QCoreApplication
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    from perf_process_metrics import ProcessSampler
    from qa_intelligence_agent import GOALS
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();exe=args.exe.resolve();out=args.output.resolve()
    if out.exists():raise SystemExit('Prior native evidence preserved; choose a new directory')
    key=resolve_deepseek_key();namespace=uuid.uuid4().hex;out.mkdir(parents=True)
    profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    prefix='GrangerPet/QA/intelligence_'+namespace
    qa_vault=WindowsLegacyStore(prefix=prefix,directory=profile/'vault')
    if key:qa_vault.set('deepseek_api_key',key)
    settings=Settings(source_root=str(ROOT),cursor_reaction=False,reduced_motion=True,
        ai_provider='deepseek',agent_steps=14,agent_calls=20,agent_timeout=480,agent_tokens=200000)
    (profile/'settings.json').write_text(json.dumps(settings.to_dict(),ensure_ascii=False),encoding='utf-8')
    for name in ('QT_QPA_PLATFORM','QT_SCALE_FACTOR','QTWEBENGINE_CHROMIUM_FLAGS','DEEPSEEK_API_KEY','GEMINI_API_KEY'):
        os.environ.pop(name,None)
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'),
        GRANGERPET_QA_VAULT=prefix,GRANGERPET_QA_NAMESPACE=namespace)
    app=QCoreApplication.instance() or QCoreApplication([])
    report={'test_kind':'actual_frozen_EXE_real_public_sources_and_gateway','exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
        'isolated_profile_and_ipc':True,'user_history_read':False,'checks':[],'operations':[],'gateway_available':bool(key)}
    process=None;owned=None;monitor=ProcessSampler(exe,gpu=False)
    def write():
        raw=json.dumps(report,ensure_ascii=False,indent=2)
        if key and key in raw:raise RuntimeError('Refuse secret in QA receipt')
        (out/'report.json').write_text(raw,encoding='utf-8')
    def check(name,passed):
        report['checks'].append({'name':name,'passed':bool(passed)});write()
        if not passed:raise AssertionError(name)
    def wait(function,seconds=45):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=function()
            if value:return value
            time.sleep(.2)
        raise TimeoutError('native_qa_deadline')
    def state():
        value=send_command('pet','status',timeout=2000)
        if value and owned and value.get('pid')!=owned:raise RuntimeError('Unrelated process left untouched')
        return value
    def command(action,payload=None):
        if owned and not state():raise RuntimeError('Own instance missing')
        value=send_command('pet',action,payload or {},timeout=3000)
        if not value or not value.get('ok'):raise RuntimeError('Own action rejected: '+action)
    def action(name,payload=None):
        command('qa_desktop',{'action':name,'payload':payload or {}});time.sleep(.3)
    def snapshot():
        command('qa_desktop',{'action':'save_state','name':'current-state'})
        return json.loads((out/'current-state.json').read_text(encoding='utf-8'))
    def tool(name,args):
        action('route',{'route':'search'});start=time.monotonic()
        from grangerpet.agent_tools import _SPECS
        spec=next(spec for spec in _SPECS if spec.name==name)
        payload={'arguments':args} if spec.input_schema is not None else {'query':args[spec.argument]}
        action('tool_run',{'tool':name,**payload})
        row=wait(lambda:s if (s:=snapshot()) and not s['search']['busy'] and any(a.get('id')==name and a['status']!='running' for a in s['activity']) else None,100)
        status=next(a['status'] for a in row['activity'] if a.get('id')==name)
        count=next(a.get('resultCount',0) for a in row['activity'] if a.get('id')==name)
        if count:
            row=wait(lambda:s if (s:=snapshot()) and len(s['search']['results'])==count else None,25)
        report['operations'].append({'tool':name,'status':status,'records':len(row['search']['results']),'seconds':round(time.monotonic()-start,3)});write()
        return row
    try:
        started=time.monotonic()
        with (out/'process.log').open('wb') as log:
            process=subprocess.Popen([str(exe),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        first=wait(state,70);owned=first['pid']
        monitor.sample([process.pid])
        check('actual_expected_executable',Path(process_image(owned)).resolve()==exe)
        wait(lambda:(s:=state()) and s.get('desktop',{}).get('ready'),60)
        command('show_workspace',{'route':'chat'});check('native_desktop_ready',True)
        report['startup_seconds']=round(time.monotonic()-started,3)
        for name,args in [('network_rdap',{'resource':'66.249.67.41'}),('network_routing',{'resource':'66.249.67.41'}),
                ('domain_dns',{'domain':'example.org'}),('steam_profile',{'profile':'https://steamcommunity.com/id/robinwalker'}),
                ('steam_friends',{'profile':'https://steamcommunity.com/id/robinwalker'}),
                ('wikidata_places',{'query':'Moscow Kremlin','latitude':55.7517,'longitude':37.6176}),
                ('telegram_public',{'username':'https://t.me/telegram','access_mode':'public','limit':1}),
                ('blockchain_gansar',{'address':'UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ','operation':'balances','chain':'ton','mode':'quick','limit':1,'depth':0})]:
            tool(name,args)
        check('native_public_tools_returned_data',all(row['records']>0 for row in report['operations'][:6]))
        if key:
            action('connection_test');connected=wait(lambda:s if (s:=snapshot()) and s['connection']['status']=='connected' else None,60)
            check('native_saved_key_connection_consistent',connected['connection']['canSend'])
            action('chat_new');action('chat_send',{'text':GOALS['browser']})
            live=wait(lambda:s if (s:=snapshot()) and s.get('browser',{}).get('url') else None,90)
            check('native_browser_panel_state',live['browser']['image'].startswith('data:image/jpeg;base64,'))
            command('qa_snapshot',{'name':'browser-active'})
            finished=wait(lambda:s if (s:=snapshot()) and not s['busy'] and s.get('investigation',{}).get('status') else None,500)
            browser_tools={a.get('tool') for a in finished.get('investigation',{}).get('calls',[])}
            report['browser_chat']={'status':finished['investigation']['status'],'tools':sorted(browser_tools),
                'final_url':finished.get('browser',{}).get('url'),'evidence_count':len(finished.get('evidence',[]))}
            actions=finished.get('browser',{}).get('actions',[])
            page_two=[row for row in actions if 'page_num=2' in row.get('target','')]
            report['browser_chat']['page_two_actions']=[{k:row.get(k) for k in ('action','target','status')} for row in page_two]
            check('native_agent_reached_second_page',bool(page_two))
            check('native_second_page_screenshot',any(row['action']=='screenshot' and row.get('status')=='complete' for row in page_two))
            check('native_browser_actual_OCR_call','browser_screenshot' in browser_tools)
            command('qa_snapshot',{'name':'browser-final'})
            action('browser_stop');wait(lambda:not snapshot().get('browser',{}).get('url'))
            action('chat_new');action('chat_send',{'text':'Привет, Гермиона! Как твои дела?'})
            casual=wait(lambda:s if (s:=snapshot()) and not s['busy'] and any(m.get('role')=='model' for m in s['messages']) else None,90)
            report['casual']={'model_messages':sum(m.get('role')=='model' for m in casual['messages']),'investigation_id':bool(casual.get('investigation',{}).get('id'))}
            check('native_new_dialog_casual_without_investigation',not report['casual']['investigation_id'])
            command('qa_snapshot',{'name':'casual'})
        monitor.sample([process.pid]);time.sleep(1);report['idle_resources']=monitor.sample([process.pid])
        report['passed']=True;write()
    finally:
        if process and process.poll() is None:
            if state():command('stop')
            process.wait(timeout=30)
        if process:
            time.sleep(1);check('own_process_tree_exited',monitor.sample([process.pid])['process_count']==0)
        monitor.close();qa_vault.delete('deepseek_api_key');write()
    print(json.dumps({'passed':report.get('passed',False),'checks':len(report['checks']),'operations':report['operations']},ensure_ascii=False))


if __name__=='__main__':main()
