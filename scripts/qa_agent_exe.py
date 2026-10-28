"""Final EXE: actual saved DeepSeek key, chat, agent, OSINT and source list.

Fresh application profile, normal authorized Windows key (never copied to IPC,
environment or disk). Existing instances are never stopped by this script.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from PySide6.QtCore import QCoreApplication
    from grangerpet.ai_keys import resolve_deepseek_key
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    from smoke_exe import _terminate_spawned_binary_tree
    app=QCoreApplication([])
    output=ROOT/'output/agent-qa/exe-live';exe=ROOT/'dist/GrangerPet.exe'
    if output.exists():raise SystemExit('Previous EXE evidence preserved')
    if send_command('pet','status') or send_command('launcher','status'):raise SystemExit('Close existing GrangerPet before isolated EXE QA')
    output.mkdir(parents=True);profile=output/'appdata/GrangerPet';profile.mkdir(parents=True)
    report={'tested_at_utc':datetime.now(timezone.utc).isoformat(),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
            'method':'Final EXE actual chat UiJob→AgentRunner→DeepSeek→existing local adapters, no mock replies',
            'checks':[],'mock':False,'screenshots':[]}
    key=resolve_deepseek_key()
    if not key:
        report.update(passed=False,reason='missing_key',actual_requests=0)
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return 2
    settings=Settings(ai_provider='deepseek',deepseek_model='deepseek-v4-flash',size=195,x=100,y=320,source_root=str(ROOT),request_limit=3)
    (profile/'settings.json').write_text(json.dumps(settings.to_dict()),encoding='utf-8')
    env=os.environ.copy()
    for name in ('QT_QPA_PLATFORM','GRANGERPET_QA_VAULT','GRANGERPET_QA_INPUT_KEY','GEMINI_API_KEY','DEEPSEEK_API_KEY'):
        env.pop(name,None)
    env.update(APPDATA=str(output/'appdata'),GRANGERPET_INTERACTION_TRACE=str(output/'interaction.jsonl'))
    process=None;pid=None
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    def status():
        result=send_command('pet','status',timeout=600)
        if not result or pid and result.get('pid')!=pid:raise RuntimeError('Owned EXE unavailable')
        return result
    def command(name,payload=None):
        status();result=send_command('pet',name,payload,timeout=700)
        if not result or not result.get('ok'):raise RuntimeError('QA command failed')
    def wait(predicate,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=status()
            if predicate(value):return value
            time.sleep(.08)
        raise TimeoutError('Bounded EXE scenario timed out')
    def capture(name):
        time.sleep(.3);command('qa_snapshot',{'name':name});report['screenshots'].append(name+'-search.png')
    try:
        process=subprocess.Popen([str(exe),'--pet','--interaction-qa'],env=env,cwd=ROOT,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        end=time.monotonic()+25;initial=None
        while time.monotonic()<end:
            initial=send_command('pet','status',timeout=200)
            if initial:break
            time.sleep(.1)
        check('fresh_pet_started',bool(initial));pid=initial['pid']
        check('exact_executable',Path(process_image(pid)).resolve()==exe.resolve())
        check('saved_key_recognized_without_environment',initial['chat_can_send'] and initial['ai_connection']['credential_available'])
        command('panel');command('qa_show_chat');capture('initial-chat')
        # First normal conversation exercises the actual SSE path in this EXE.
        command('qa_chat',{'text':'Привет, Гермиона! Ответь одним коротким предложением.'})
        wait(lambda v:v['ai_busy'],3);normal=wait(lambda v:not v['ai_busy'],55)
        check('ordinary_real_sse_reply',normal['ai_request'].get('code')=='ok' and normal['ai_model_messages']==1)
        capture('ordinary-real-reply')
        # Now the existing chat chooses and runs tools without opening Search.
        query='Найди публичные упоминания никнейма solvnox: проверь публичные профили и индексируемые упоминания. Сопоставь реальные результаты. Для каждого инструмента limit=3, не больше трёх инструментов. Не проверяй email и не используй авторизованные сессии.'
        command('qa_chat',{'text':query});wait(lambda v:v['ai_busy'],3);capture('agent-working')
        final=wait(lambda v:not v['ai_busy'],145)
        report['agent']=final.get('agent',{});report['request']=final['ai_request']
        check('real_agent_reply',final['ai_request'].get('code')=='ok' and final['ai_model_messages']==2)
        check('agent_executed_tools',report['agent'].get('tool_calls',0)>0)
        check('agent_retained_real_evidence',report['agent'].get('evidence_count',0)>0)
        check('findings_in_existing_search_model',final.get('result_count',0)>0)
        check('shared_connected_status',final['ai_connection']['connection_status']=='connected')
        capture('agent-real-answer')
        journals=list((profile/'investigations').glob('*.json'))
        check('evidence_journal_saved',len(journals)==1)
        journal=json.loads(journals[0].read_text(encoding='utf-8'))
        check('journal_has_source_url_query_time',all(row.get('evidence_id') and row.get('provenance',{}).get('tool') and row.get('provenance',{}).get('obtained_at') for row in journal['evidence']))
        # Copy only the sanitized source ledger, never profile or credentials.
        (output/'evidence.json').write_text(json.dumps(journal,ensure_ascii=False,indent=2),encoding='utf-8')
        command('qa_settings',{'page':2});time.sleep(.3);capture('connected-settings');command('qa_ai_close')
        command('panel');command('panel');command('qa_show_chat')
        check('history_survives_panel_toggle',status()['ai_model_messages']==2)
        report['passed']=True
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__)
    finally:
        current=send_command('pet','status',timeout=300)
        if current and current.get('pid')==pid:send_command('pet','stop',timeout=600)
        if process:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:_terminate_spawned_binary_tree(exe,process.pid)
        leaked=[]
        for path in output.rglob('*'):
            if path.is_file() and path.suffix in ('.json','.jsonl','.log') and key.encode() in path.read_bytes():leaked.append(path.name)
        check('key_absent_from_profile_journal_logs',not leaked)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(report['checks']),'agent':report.get('agent'),'error_type':report.get('error_type')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':main()
