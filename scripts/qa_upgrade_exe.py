"""Real Granger-OSINT EXE / WebChannel / React / gateway integration checks.

Runs in explicit phases so native screenshot/input review can occur between
them. Every phase verifies the exact executable and keeps paid requests bounded.
"""
from datetime import datetime, timezone
import argparse
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
    from grangerpet.chat_archive import ChatArchive
    from grangerpet.usage import UsageLedger
    from qa_packaged_search import process_image
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('start','research','ui','ui-tail','finish'),required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'output/upgrade-qa/exe-live')
    args=parser.parse_args();app=QCoreApplication([]);out=args.output.resolve();exe=ROOT/'dist/Granger-OSINT.exe'
    destination=out/'report.json';profile=out/'appdata/GrangerPet'
    if args.phase=='start':
        if destination.exists():raise SystemExit('Previous actual evidence is preserved')
        if send_command('pet','status') or send_command('launcher','status'):raise SystemExit('Close existing app before isolated QA')
        profile.mkdir(parents=True)
        settings=Settings(ai_provider='deepseek',source_root=str(ROOT),request_limit=5,size=195,
            agent_steps=1,agent_calls=10,agent_tokens=60000,agent_page_limit=5)
        (profile/'settings.json').write_text(json.dumps(settings.to_dict()),encoding='utf-8')
        report={'tested_at_utc':datetime.now(timezone.utc).isoformat(),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
                'mock':False,'method':'Final native EXE, actual bundled React/WebChannel/controllers, saved gateway key, no fake responses',
                'checks':[],'phases':[],'pid':None}
    else:
        report=json.loads(destination.read_text(encoding='utf-8'))
        if report['exe_sha256']!=hashlib.sha256(exe.read_bytes()).hexdigest():raise SystemExit('EXE changed; use a fresh evidence directory')
    pid=report.get('pid');process=None
    env=os.environ.copy()
    for key in ('QT_QPA_PLATFORM','QT_SCALE_FACTOR','QT_SCREEN_SCALE_FACTORS','GRANGERPET_QA_VAULT','GRANGERPET_QA_INPUT_KEY','DEEPSEEK_API_KEY','GEMINI_API_KEY'):
        env.pop(key,None)
    env.update(APPDATA=str(out/'appdata'),GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    def save():destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    def state():
        current=send_command('pet','status',timeout=1000)
        if not current or current['pid']!=pid:raise RuntimeError('Verified QA instance is unavailable')
        if Path(process_image(pid)).resolve()!=exe.resolve():raise RuntimeError('Wrong executable')
        return current
    def command(name,payload=None):
        state();answer=send_command('pet',name,payload,timeout=1500)
        if not answer or not answer.get('ok'):raise RuntimeError('QA command rejected: '+name)
    def wait(predicate,seconds=15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=state()
            if predicate(value):return value
            time.sleep(.12)
        raise TimeoutError('Bounded '+args.phase+' phase timeout')
    def act(action,payload=None):
        command('qa_desktop',{'action':action,'payload':payload or {}});time.sleep(.18)
        answer=state().get('desktop',{}).get('last_response',{})
        if answer.get('ok') is False:raise RuntimeError(answer.get('error','Bridge action failed'))
    def snapshot(name):
        command('qa_snapshot',{'name':name});time.sleep(.2)
    def desktop(name='state'):
        command('qa_desktop',{'action':'save_state','name':name});time.sleep(.15)
        return json.loads((out/(name+'.json')).read_text(encoding='utf-8'))
    def dom():
        command('qa_desktop',{'action':'dom'});time.sleep(.2)
        return state()['desktop']['dom']
    def start():
        nonlocal pid,process
        process=subprocess.Popen([str(exe),'--pet','--interaction-qa'],cwd=ROOT,env=env,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        end=time.monotonic()+35;value=None
        while time.monotonic()<end:
            value=send_command('pet','status',timeout=250)
            if value:pid=value['pid'];break
            time.sleep(.1)
        check('verified_final_executable',bool(value) and Path(process_image(pid)).resolve()==exe.resolve())
        wait(lambda s:s.get('desktop',{}).get('ready'),20)
        report['pid']=pid
    def stop():
        nonlocal pid
        command('stop');end=time.monotonic()+15
        while time.monotonic()<end and send_command('pet','status',timeout=100):time.sleep(.15)
        check('own_instance_stopped',not send_command('pet','status',timeout=100));pid=None
    def send(text):
        act('chat_send',{'text':text});wait(lambda s:s['ai_busy'],4)
    def done(seconds=120):
        value=wait(lambda s:not s['ai_busy'],seconds)
        check('real_provider_response',value['ai_request'].get('code')=='ok')
        return value
    try:
        if args.phase=='start':
            start();command('show_workspace',{'route':'chat'});time.sleep(.5)
            initial=desktop('initial-state')
            check('connection_available_without_autoprobe',initial['connection']['canSend'] and not state()['ai_request'])
            check('new_public_identity',dom()['title']=='Granger-OSINT')
            check('real_react_controls',len(dom()['buttons'])>=15)
            snapshot('01-main-empty')
            send('Привет, Гермиона. Один и тот же никнейм на двух сайтах ведь доказывает одного владельца? Возрази, если я ошибаюсь, естественно и коротко — два предложения. Без инструментов.')
            act('window',{'mode':'minimize'})
            done(60)
            wait(lambda s:s.get('notification',{}).get('visible'),2)
            check('real_reply_notification_while_minimized',state()['notification']['kind']=='reply')
            snapshot('02-reply-notification')
            data=desktop('ordinary-reply')
            report['ordinary_answer']=data['messages'][-1]['text']
            report['reply_message_id']=data['messages'][-1]['id']
            check('real_usage_returned',data['usage']['request']['usage'].get('total_tokens',0)>0)
            check('unknown_balance_honest',data['connection']['balance'] is None and 'не предоставляет' in data['connection']['balanceMessage'])
        elif args.phase=='research':
            state();command('show_workspace',{'route':'chat'});time.sleep(.4)
            send('Исследуй публичные упоминания никнейма torvalds. Найди доступный профиль GitHub и прочитай найденную страницу через web_read. Разделяй сниппеты и прочитанный текст, не устанавливай личность одним ником. Не используй авторизованные сервисы. Для поиска limit=3. Короткий итог с понятными заголовками и реальными источниками.')
            done(180);time.sleep(.7)
            paused=desktop('research-paused')
            check('explicit_user_step_budget_pauses',paused['investigation'].get('canResume') and paused['investigation'].get('stop_reason_code')=='step_limit')
            identifier=paused['investigation']['id'];report['investigation_id']=identifier
            first_ids=[s['evidence_id'] for s in paused['evidence']]
            checkpoint=profile/'investigations'/(identifier+'.checkpoint.dpapi')
            check('actual_checkpoint_encrypted',checkpoint.is_file() and b'pending_calls' not in checkpoint.read_bytes())
            snapshot('03-budget-paused');stop();start();command('show_workspace',{'route':'chat'});time.sleep(.5)
            restored=desktop('research-restored')
            check('resume_survives_actual_exe_restart',restored['investigation'].get('id')==identifier and restored['investigation'].get('canResume'))
            check('history_restored_without_network',not state()['ai_request'])
            act('settings_save',{'values':{'agent_steps':8,'agent_calls':10,'agent_tokens':60000}})
            act('investigation_continue');wait(lambda s:s['ai_busy'],5);snapshot('04-real-tools-running')
            done(190);time.sleep(.5)
            final=desktop('research-completed')
            check('same_investigation_continued',final['investigation']['id']==identifier)
            check('original_evidence_retained',set(first_ids).issubset({s['evidence_id'] for s in final['evidence']}))
            check('actual_page_reading',any(s['kind']=='page' and s.get('excerpt') for s in final['evidence']))
            check('real_tool_activity',bool(final['activity']))
            check('compact_answer_without_ledger_dump','Проверяемые находки источников:' not in final['messages'][-1]['text'])
            report['investigation']=final['investigation'];report['research_usage']=final['usage'];snapshot('05-research-report')
        elif args.phase=='ui':
            state();command('show_workspace',{'route':'chat'});time.sleep(.3)
            send('Без инструментов составь учебную заметку по критическому мышлению, около 400 слов. Нужны # заголовок, ## два раздела, **жирный**, *курсив*, вложенные списки, цитата, разделитель, ссылка https://example.org/, inline-code, блок кода python print("Привет") и таблица 5 колонок на 4 строки. Это учебный текст, не результаты нового расследования.')
            snapshot('06-real-streaming');done(90);time.sleep(.6)
            data=desktop('markdown-state');report['markdown_message_id']=data['messages'][-1]['id'];markup=dom()
            check('react_markdown_actual_headings',len(markup['headings'])>=3)
            check('react_markdown_actual_table',markup['tables']>=1)
            check('no_root_overflow',not markup['overflow']);snapshot('07-real-markdown')
            journal=profile/'investigations'/(report['investigation_id']+'.json');original=hashlib.sha256(journal.read_bytes()).hexdigest()
            act('canvas_open',{'message_id':report['markdown_message_id']});time.sleep(.4);snapshot('08-canvas-real')
            canvas=desktop('canvas-open')['canvas'];edited=canvas['text']+'\n\n## Заметка пользователя\n\nПравка в настоящем Canvas.'
            act('canvas_edit',{'document_id':canvas['id'],'text':edited});act('canvas_save')
            check('canvas_saved_utf8',(profile/'canvas'/(canvas['id']+'.md')).read_text(encoding='utf-8')==edited)
            check('canvas_keeps_original_evidence',hashlib.sha256(journal.read_bytes()).hexdigest()==original)
            snapshot('09-canvas-edited')
            for route in ('history','search','settings','chat'):
                act('route',{'route':route});time.sleep(.2);snapshot('route-'+route);check('route_'+route,state()['desktop']['route']==route)
            act('tools_refresh');wait(lambda s:not desktop('tool-readiness')['search']['busy'],25)
            readiness=desktop('tool-readiness');check('real_tool_readiness',any(t['available'] for t in readiness['tools']))
            report['tools']=readiness['tools']
            act('route',{'route':'search'});act('tool_run',{'tool':'web_read','query':'https://example.org/','limit':1})
            wait(lambda s:not desktop('manual-tool')['search']['busy'],30)
            actual=desktop('manual-tool');check('manual_actual_http_result',any('example.org' in s['url'] and s['kind']=='page' for s in actual['search']['results']))
            snapshot('10-manual-public-page')
            act('tool_run',{'tool':'web_read','query':'http://127.0.0.1/','limit':1})
            wait(lambda s:not desktop('blocked-tool')['search']['busy'],10)
            blocked=desktop('blocked-tool');check('unsafe_url_rejected_before_network',any(a['status'] in ('blocked','invalid_arguments') for a in blocked['activity']))
        if args.phase in ('ui','ui-tail'):
            if args.phase=='ui-tail':
                blocked=desktop('blocked-tool-rechecked')
                check('unsafe_url_rejected_before_network',any(a['status'] in ('blocked','invalid_arguments') for a in blocked['activity']))
            act('route',{'route':'chat'});send('Без инструментов напиши большой учебный текст о проверке источников, двадцать абзацев.')
            act('chat_stop');wait(lambda s:not s['ai_busy'],4);check('cancel_actual_stream',state()['ai_request']['code']=='cancelled')
            report['usage_after_cancel']=desktop('usage-after-cancel')['usage']
            before=state()['ai_model_messages']
            act('chat_regenerate',{'message_id':report['markdown_message_id']});wait(lambda s:s['ai_busy'],4);done(90)
            check('regenerate_after_cancel',state()['ai_model_messages']>before)
            previous=desktop('history-before')['conversation_id'];act('chat_new');check('new_encrypted_conversation',desktop('history-new')['conversation_id']!=previous)
            act('history_load',{'id':previous});check('actual_history_switch',desktop('history-restored')['conversation_id']==previous)
            act('window',{'mode':'maximize'});wait(lambda s:s['window']['maximized']);snapshot('11-maximized')
            act('window',{'mode':'fullscreen'});wait(lambda s:s['window']['fullscreen']);snapshot('12-fullscreen')
            act('window',{'mode':'fullscreen'});wait(lambda s:not s['window']['fullscreen'] and s['window']['maximized'])
            check('fullscreen_restores_maximized',True)
            act('window',{'mode':'maximize'});wait(lambda s:not s['window']['maximized']);snapshot('13-restored-window')
        if args.phase=='finish':
            state();data=desktop('final-state');report['final_usage']=data['usage']
            check('all_usage_is_actual_or_missing',data['usage']['conversation']['usage_reported_requests']>0)
            models=state()['ai_model_messages'];stop();start();check('final_history_restored',state()['ai_model_messages']==models and not state()['ai_request'])
            command('show_workspace',{'route':'chat'});time.sleep(.3);snapshot('14-final-reopened')
        report['phases'].append(args.phase);report['phase_passed']=True;report['pid']=pid
    except Exception as error:
        report.update(phase_passed=False,error_phase=args.phase,error_type=type(error).__name__,error=str(error)[:250],pid=pid)
        try:report['failure_state']=state()
        except Exception:pass
    finally:save()
    print(json.dumps({'phase':args.phase,'passed':report.get('phase_passed'),'checks':len(report['checks']),'pid':pid,'error':report.get('error')}))
    return 0 if report.get('phase_passed') else 1


if __name__=='__main__':raise SystemExit(main())
