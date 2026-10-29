"""Actual final EXE checks, with reserved documentation targets and real APIs.

No fabricated provider responses, private history or transcript keys. Separate
phases allow physical overlay interaction and visual review between requests.
"""
from __future__ import annotations

import argparse
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
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',required=True,choices=('start','tools','chat','reply','finish'))
    parser.add_argument('--output',type=Path,default=ROOT/'output/refinement-qa/exe-final')
    args=parser.parse_args();app=QCoreApplication([])
    out=args.output.resolve();exe=ROOT/'dist/Granger-OSINT.exe';target=out/'report.json'
    if args.phase=='start':
        if target.exists():raise SystemExit('Prior evidence preserved; use another output directory')
        if send_command('pet','status') or send_command('launcher','status'):raise SystemExit('An existing instance is active')
        profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
        # Empty source_root must find installed neighbour tools from frozen EXE.
        settings=Settings(ai_provider='deepseek',source_root='',request_limit=5,search_timeout=25,
            agent_steps=3,agent_calls=5,agent_tokens=30000,agent_page_limit=3)
        (profile/'settings.json').write_text(json.dumps(settings.to_dict()),encoding='utf-8')
        report={'tested_at':datetime.now(timezone.utc).isoformat(),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
                'mock':False,'checks':[],'tools':[],'pid':None}
        env=os.environ.copy()
        for name in ('QT_QPA_PLATFORM','QT_SCALE_FACTOR','GRANGERPET_QA_VAULT','GRANGERPET_QA_INPUT_KEY','DEEPSEEK_API_KEY','GEMINI_API_KEY'):
            env.pop(name,None)
        env.update(APPDATA=str(out/'appdata'),GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
        process=subprocess.Popen([str(exe),'--pet','--interaction-qa'],cwd=ROOT,env=env,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        report['launcher_pid']=process.pid
    else:
        report=json.loads(target.read_text(encoding='utf-8'))
        if report['exe_sha256']!=hashlib.sha256(exe.read_bytes()).hexdigest():raise SystemExit('EXE changed; evidence is from another binary')

    def save():target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        save()
        if not value:raise AssertionError(name)
    def state():
        row=send_command('pet','status',timeout=2500)
        if not row or report['pid'] and row['pid']!=report['pid']:raise RuntimeError('Verified QA process unavailable')
        if Path(process_image(row['pid'])).resolve()!=exe.resolve():raise RuntimeError('Unexpected binary')
        return row
    def wait(predicate,seconds=25):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            try:
                row=state()
                if predicate(row):return row
            except RuntimeError:
                if report['pid']:raise
            time.sleep(.2)
        raise TimeoutError('QA state did not arrive')
    def command(name,payload=None):
        result=send_command('pet',name,payload,timeout=3000)
        if not result or not result.get('ok'):raise RuntimeError('QA command rejected '+name)
    def action(name,payload=None):
        command('qa_desktop',{'action':name,'payload':payload or {}})
        time.sleep(.25)
        response=state()['desktop'].get('last_response') or {}
        if response.get('ok') is False:raise RuntimeError(response.get('error','Action failed'))
    def snapshot(name):
        # Wait for the state patch and exit/enter route animation to paint.
        time.sleep(.65)
        command('qa_snapshot',{'name':name});time.sleep(.3)
    def desktop(name='state'):
        command('qa_desktop',{'action':'save_state','name':name});time.sleep(.15)
        return json.loads((out/(name+'.json')).read_text(encoding='utf-8'))
    def dom():
        command('qa_desktop',{'action':'dom'});time.sleep(.2)
        return state()['desktop']['dom']
    def wait_tools():
        end=time.monotonic()+25
        while time.monotonic()<end:
            row=desktop()
            if not row.get('toolsChecking'):return row
            time.sleep(.3)
        raise TimeoutError('Tool readiness did not complete')

    try:
        if args.phase=='start':
            row=wait(lambda row:row.get('desktop',{}).get('ready'),35)
            report['pid']=row['pid'];save()
            command('show_workspace',{'route':'search'});time.sleep(.4)
            row=wait_tools();tools=row['tools']
            report['readiness']=[{key:value for key,value in item.items() if key in ('id','name','state','available','reason','diagnostic')} for item in tools]
            check('all_16_checked_automatically',len(tools)==16 and all(item['state']!='checking' for item in tools))
            check('available_tools_not_zero',sum(item['available'] for item in tools)>=5)
            check('auth_missing_not_faked_ready',all(not item['available'] for item in tools if item['state']=='auth_required'))
            data=dom();report['font']=data['font']
            check('cyrillic_manrope_loaded_in_windows_webengine',data['font']['loaded'] and data['font']['size']=='15px')
            check('no_horizontal_overflow',not data['overflow'])
            check('hermione_label', 'ВАША ГЕРМИОНА' in data['text'])
            snapshot('01-tools')
            end=time.monotonic()+20
            balance=desktop()['usage']['balance']
            while balance.get('status') in ('checking','unknown') and time.monotonic()<end:
                time.sleep(.3);balance=desktop()['usage']['balance']
            report['balance']={key:value for key,value in balance.items() if key!='amount'}
            report['balance']['numeric_value_received']=balance.get('amount') is not None
            check('live_balance_has_no_invented_denomination',balance.get('status')=='available' and balance.get('unit')=='gateway_units')
            # Keep start's parent alive for stable independent GUI ownership.
            save();print('QA EXE ready for tools/chat/physical UI phases',flush=True)
            process.wait()
            return
        elif args.phase=='tools':
            targets={
                'username_maigret':'granger_osint_qa_zz_42791', 'username_blackbird':'granger_osint_qa_zz_42791',
                'username_social_analyzer':'granger_osint_qa_zz_42791','username_snoop':'granger_osint_qa_zz_42791',
                'email_holehe':'granger-osint-qa@example.invalid','phone_metadata':'+12025550123',
                'blockchain_gansar':'0x000000000000000000000000000000000000dEaD',
                'web_archive':'https://example.org/','web_search':'site:example.org "Example Domain"',
                'web_read':'https://example.org/','domain_lookup':'example.org','ip_lookup':'1.1.1.1',
                'instagram_public':'granger_osint_qa_zz_42791',
            }
            command('show_workspace',{'route':'search'})
            initial=wait_tools()
            saved_page=None
            for item in initial['tools']:
                name=item['id']
                if not item['available'] or name=='evidence_get':continue
                if item.get('sensitive'):
                    # Native confirmation must be handled interactively, never
                    # click Yes from a script. This case is left as a visible
                    # untested limitation until a manual authorized run occurs.
                    report['tools'].append({'tool':name,'executed':False,'reason':'requires native confirmation; no automatic approval'})
                    continue
                action('tool_run',{'tool':name,'query':targets[name],'limit':2})
                if name=='blockchain_gansar':snapshot('02-running-tool')
                wait(lambda row:not desktop().get('search',{}).get('busy'),40)
                value=desktop('tool-'+name)
                activity=value['activity'][-1]
                report['tools'].append({'tool':name,'executed':True,'status':activity['status'],
                    'result_count':activity.get('resultCount'),'error':activity.get('error','')})
                save()
                if name=='web_read':
                    snapshot('02-read-page')
                    saved_page=next((row for row in value['search']['results'] if row['kind']=='page'),None)
            evidence=saved_page
            if evidence:
                action('tool_run',{'tool':'evidence_get','query':evidence['evidence_id'],'limit':1})
                wait(lambda row:not desktop().get('search',{}).get('busy'),10)
                retrieved=desktop()
                check('manual_saved_evidence_retrieved',any(row['evidence_id']==evidence['evidence_id'] for row in retrieved['search']['results']))
                report['tools'].append({'tool':'evidence_get','executed':True,'status':retrieved['activity'][-1]['status'],
                    'result_count':retrieved['activity'][-1].get('resultCount')})
            check('permitted_tool_requests_dispatched',sum(row.get('executed',False) for row in report['tools'])>=9)
            check('manual_results_and_sources_visible',bool(desktop()['evidence']))
        elif args.phase=='chat':
            command('show_workspace',{'route':'chat'})
            action('chat_send',{'text':'Гермиона, проверь только https://example.org/ с web_read. Коротко опиши назначение этой страницы по-русски, со ссылкой. Это разрешённый документационный домен; не ищи людей и не вызывай другие внешние источники.'})
            wait(lambda row:row['ai_busy'],5)
            wait(lambda row:not row['ai_busy'],120)
            value=desktop('agent-result');investigation=value['investigation']
            check('real_gateway_answer',state()['ai_request'].get('code')=='ok')
            check('agent_actually_called_reader','web_read' in state().get('agent',{}).get('tools',[]))
            check('actual_sources_retained',any(row['kind']=='page' for row in value['messages'][-1].get('sources',[])))
            check('agent_respects_explicit_reader_only',set(state().get('agent',{}).get('tools',[]))<={'web_read','evidence_get'})
            check('actual_usage_returned',bool(value['usage']['request']['usage'].get('total_tokens')))
            report['investigation']={key:investigation.get(key) for key in ('id','status','steps','tool_calls','usage')}
            report['usage']=value['usage']['conversation'];snapshot('03-chat-with-sources')
            action('route',{'route':'settings','category':'ai'});snapshot('04-settings-top')
        elif args.phase=='reply':
            command('show_workspace',{'route':'chat'})
            action('chat_send',{'text':'Коротко, одним предложением: совпадение никнейма само по себе доказывает, что у профилей один владелец? Без инструментов.'})
            wait(lambda row:row['ai_busy'],5)
            action('window',{'mode':'minimize'})
            wait(lambda row:not row['ai_busy'],75)
            row=wait(lambda row:row['notification']['visible'],5)
            check('actual_unread_reply_envelope',row['notification']['unread_count']>=1)
            report['notification']=row['notification'];snapshot('05-unread-envelope')
        elif args.phase=='finish':
            value=desktop('final-state')
            report['final_usage']=value['usage']['conversation']
            command('stop');time.sleep(.8)
            check('own_exe_stopped',not send_command('pet','status',timeout=250))
        save();print(json.dumps({'phase':args.phase,'checks':len(report['checks']),'failures':[row for row in report['checks'] if not row['passed']]},ensure_ascii=False))
    except Exception as error:
        report['failure']={'phase':args.phase,'type':type(error).__name__,'message':str(error)};save();raise


if __name__=='__main__':main()
