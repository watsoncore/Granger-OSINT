"""Actual final EXE scenarios A-F, using saved key and native application paths.

Fresh local profile, no fake answers/credentials. Optional keep-open leaves only
this script's verified process available for final native F11 input inspection.
"""
from datetime import datetime,timezone
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
    from grangerpet.ai_keys import resolve_deepseek_key
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    from smoke_exe import _terminate_spawned_binary_tree
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--keep-open',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'output/master-qa/exe-live')
    args=parser.parse_args()
    app=QCoreApplication([]);exe=ROOT/'dist/GrangerPet.exe';out=args.output.resolve()
    if out.exists():raise SystemExit('Prior EXE evidence preserved')
    if send_command('pet','status') or send_command('launcher','status'):raise SystemExit('Close existing GrangerPet before isolated QA')
    out.mkdir(parents=True);profile=out/'appdata/GrangerPet';profile.mkdir(parents=True)
    settings=Settings(ai_provider='deepseek',source_root=str(ROOT),size=195,x=100,y=320,request_limit=3,
        agent_steps=6,agent_calls=7,agent_timeout=180,agent_tokens=42000,agent_page_limit=4)
    (profile/'settings.json').write_text(json.dumps(settings.to_dict()),encoding='utf-8')
    env=os.environ.copy()
    for name in ('QT_QPA_PLATFORM','GRANGERPET_QA_VAULT','GRANGERPET_QA_INPUT_KEY','GEMINI_API_KEY','DEEPSEEK_API_KEY'):
        env.pop(name,None)
    env.update(APPDATA=str(out/'appdata'),GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    key=resolve_deepseek_key();process=None;pid=None
    report={'tested_at_utc':datetime.now(timezone.utc).isoformat(),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
        'method':'Final Windows EXE, actual Qt chat/DeepSeek/SSE/registered tools, real pages; no fake responses',
        'checks':[],'screenshots':[],'mock':False,'key_available':bool(key)}
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    def status():
        value=send_command('pet','status',timeout=700)
        if not value or pid and value['pid']!=pid:raise RuntimeError('Owned EXE unavailable')
        return value
    def command(name,payload=None):
        status();value=send_command('pet',name,payload,timeout=700)
        if not value or not value.get('ok'):raise RuntimeError('QA command rejected: '+name)
    def wait(predicate,seconds=10):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=status()
            if predicate(value):return value
            time.sleep(.1)
        raise TimeoutError('Bounded QA timeout')
    def snapshot(name):
        time.sleep(.25);command('qa_snapshot',{'name':name});time.sleep(.1)
        report['screenshots'].append(name)
    def start():
        nonlocal process,pid
        process=subprocess.Popen([str(exe),'--pet','--interaction-qa'],cwd=ROOT,env=env,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        end=time.monotonic()+25;value=None
        while time.monotonic()<end:
            value=send_command('pet','status',timeout=200)
            if value:break
            time.sleep(.1)
        check('fresh_exe_started',bool(value));pid=value['pid']
        check('exact_executable',Path(process_image(pid)).resolve()==exe.resolve())
    def stop():
        nonlocal process,pid
        value=send_command('pet','status')
        if value and value['pid']==pid:send_command('pet','stop')
        if process:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:_terminate_spawned_binary_tree(exe,process.pid)
        pid=None
    try:
        check('saved_key_available',bool(key));start()
        check('configured_without_autoprobes',status()['chat_can_send'] and not status()['ai_request'])
        command('panel');command('qa_show_chat')
        # Exercise the native state sequence before spending any API balance.
        original=status()['window']
        command('qa_window_mode',{'mode':'maximized'});time.sleep(.5)
        command('qa_window_mode',{'mode':'fullscreen'});time.sleep(.5)
        command('qa_window_mode',{'mode':'fullscreen'});time.sleep(.6)
        check('D_preflight_restores_maximized',status()['window']['maximized'] and not status()['window']['fullscreen'])
        command('qa_window_mode',{'mode':'windowed'});time.sleep(.6)
        check('D_preflight_restores_windowed',not status()['window']['maximized'] and abs(status()['window']['width']-original['width'])<5)
        command('qa_chat',{'text':'Найди публичные упоминания никнейма torvalds. Выбери релевантную страницу и прочитай её web_read; при необходимости прочитай связанную страницу. Не связывай личности только по нику. Ограничься шестью инструментами и limit=3; без авторизованных сервисов/email. Итог с заголовками, источниками и таблицей.'})
        wait(lambda s:s['ai_busy'],4);snapshot('A-investigating')
        result=wait(lambda s:not s['ai_busy'],195)
        report['agent']=result.get('agent',{});report['agent_request']=result['ai_request']
        check('A_real_agent_answer',result['ai_request'].get('code')=='ok')
        check('A_direct_page_content',result.get('agent',{}).get('direct_pages',0)>0)
        check('A_multistep',result['agent']['steps']>=3 and result['agent']['tool_calls']>=2)
        check('A_existing_search_has_evidence',result['result_count']>0)
        snapshot('A-real-deep-report')
        journals=list((profile/'investigations').glob('*.json'))
        check('A_evidence_journal',bool(journals))
        journal=next(p for p in journals if p.stem==result['agent']['id']);evidence_before=hashlib.sha256(journal.read_bytes()).hexdigest()
        (out/'evidence.json').write_bytes(journal.read_bytes())
        command('qa_chat',{'text':'Без инструментов составь учебный Markdown-документ о критическом мышлении. Около 450 слов. Обязательно: # заголовок, ## два раздела, **жирный**, *курсив*, вложенный маркированный и нумерованный списки, цитата, разделитель, кликабельная ссылка https://example.org/, inline-code, блок ```python с print("Привет") и таблица из пяти колонок и четырёх строк. Это учебный текст, не результаты нового расследования.'})
        wait(lambda s:s['ai_busy'],4);snapshot('B-real-streaming')
        formatted=wait(lambda s:not s['ai_busy'],55)
        check('B_real_stream_answer',formatted['ai_request'].get('code')=='ok')
        time.sleep(.2);formatted=status();report['markdown']=formatted.get('markdown')
        check('B_real_markdown_headings',formatted.get('markdown',{}).get('headings',0)>=2)
        check('B_real_markdown_table',formatted.get('markdown',{}).get('tables',0)>=1)
        snapshot('B-real-markdown')
        command('qa_canvas',{'action':'open_last'});wait(lambda s:s['window']['canvas_visible'])
        report['canvas_before']=status()['canvas'];check('C_outline',status()['canvas']['headings']>=2);snapshot('C-canvas-view')
        command('qa_canvas',{'action':'edit_save'});time.sleep(.4);snapshot('C-canvas-edited')
        check('C_export_created',(out/'canvas-export.md').is_file())
        exported=(out/'canvas-export.md').read_text(encoding='utf-8')
        check('C_edit_in_export','Заметка проверки' in exported)
        check('C_evidence_immutable',hashlib.sha256(journal.read_bytes()).hexdigest()==evidence_before)
        command('qa_canvas',{'action':'back'});wait(lambda s:not s['window']['canvas_visible'])
        check('C_chat_retained',status()['ai_model_messages']==2)
        command('qa_chat',{'text':'Без инструментов: Гермиона, одинаковые никнеймы ведь доказывают одного владельца? Поговори со мной естественно и возрази, если я неправ. Достаточно двух-трёх предложений.'})
        wait(lambda s:s['ai_busy'],4)
        ordinary=wait(lambda s:not s['ai_busy'],40)
        check('E_real_ordinary_answer',ordinary['ai_request'].get('code')=='ok')
        time.sleep(.7)
        from grangerpet.chat_archive import ChatArchive
        restored=ChatArchive(profile/'chat-history.dpapi').load()
        report['ordinary_answer']=next(row['text'] for row in reversed(restored['messages']) if row['role']=='model')
        check('E_no_additional_investigation',status().get('agent',{}).get('id')==result['agent']['id'])
        snapshot('E-ordinary-dialogue')
        original=status()['window'];command('qa_window_mode',{'mode':'maximized'});wait(lambda s:s['window']['maximized']);snapshot('D-maximized')
        command('qa_window_mode',{'mode':'fullscreen'});wait(lambda s:s['window']['fullscreen']);snapshot('D-fullscreen')
        check('D_pet_alive_fullscreen',status()['running'])
        command('qa_window_mode',{'mode':'fullscreen'});wait(lambda s:s['window']['maximized'] and not s['window']['fullscreen'])
        check('D_restores_maximized',True)
        command('qa_window_mode',{'mode':'windowed'});wait(lambda s:not s['window']['maximized'])
        check('D_window_size_restored',abs(status()['window']['width']-original['width'])<5)
        command('panel');wait(lambda s:not s['panel_visible'])
        wait(lambda s:s['state']=='idle' and not s['near'],10)
        life=[]
        for action in ('reading','cast','avada','yawn','sleep','leave'):
            before=status()['position'];command('qa_life',{'action':action});time.sleep(.85)
            active=status();snapshot('F-'+action)
            check('F_'+action+'_visible_action',active['life']['active'])
            if action=='leave':check('F_leave_actual_motion',active['position']!=before)
            life.append({'action':action,'active_action':active['life']['action'],'position':active['position']})
            command('qa_life',{'action':'interrupt'});time.sleep(1.1)
            check('F_'+action+'_interrupts',not status()['life']['active'])
        report['life']=life
        models=status()['ai_model_messages'];stop();start()
        check('history_restored_without_network',status()['ai_model_messages']==models and not status()['ai_request'])
        command('panel');command('qa_show_chat');snapshot('history-reopened')
        report['pid']=pid;report['passed']=True
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error_action=str(error)[:150])
    finally:
        if not(args.keep_open and report.get('passed')):stop()
        report['key_absent_from_text_files']=all(key.encode() not in p.read_bytes() for p in out.rglob('*')
            if p.is_file() and p.suffix in ('.json','.jsonl','.log','.md')) if key else True
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report.get('passed'),'checks':len(report['checks']),'error_action':report.get('error_action'),'pid':pid}))
    return 0 if report.get('passed') else 1


if __name__=='__main__':raise SystemExit(main())
