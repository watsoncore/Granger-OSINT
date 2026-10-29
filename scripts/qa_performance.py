"""Controlled Granger-only Windows performance and lifecycle measurements.

No other application windows, settings, command lines or processes are touched.
All application launches use a disposable APPDATA. Live requests, when explicitly
enabled, contain only documentation-domain tasks; reports retain aggregate usage,
not conversation text, gateway balance or credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from perf_process_metrics import ProcessSampler, summarize


def main():
    from PySide6.QtCore import QCoreApplication
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('exe', 'source-probe'), default='exe')
    parser.add_argument('--project-root', type=Path, default=ROOT)
    parser.add_argument('--group', choices=('app', 'long', 'cycles'), default='app')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exe', type=Path, default=ROOT/'dist/Granger-OSINT.exe')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--seconds', type=int, default=6)
    args = parser.parse_args()
    app = QCoreApplication.instance() or QCoreApplication([])
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('Existing performance evidence preserved; choose a new directory')
    if send_command('pet', 'status') or send_command('launcher', 'status'):
        raise SystemExit('An existing Granger instance is active; it will not be touched')
    out.mkdir(parents=True)
    exe = args.exe.resolve()
    monitor = ProcessSampler(exe)
    processes = []
    owned = {}
    roots = []
    source_roots = []
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(),
        'mode':args.mode,'group':args.group,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
        'source_project':str(args.project_root.resolve()) if args.mode=='source-probe' else None,
        'method':'Only image-verified Granger process trees; steady-state trials after warmup; no global GPU flags or system changes',
        'memory_notes':'RSS sums include shared pages; private commit is not private working set',
        'cpu_notes':'100% one-core means one logical CPU; machine percentage also provided',
        'repeats':args.repeats,'seconds_per_trial':args.seconds,'scenarios':[],'checks':[]}

    def save():
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name, value):
        report['checks'].append({'name':name,'passed':bool(value)});save()
        if not value:raise AssertionError(name)
    def state(role='pet'):
        value = None
        for _ in range(3):
            value = send_command(role,'status',timeout=2500)
            if value:break
        if value and role in owned and value['pid']!=owned[role]:
            raise RuntimeError('Unexpected instance; stopping benchmark without controlling it')
        return value
    def command(name,payload=None,role='pet'):
        if not state(role):raise RuntimeError('Owned instance is unavailable')
        answer=send_command(role,name,payload,timeout=3000)
        if not answer or not answer.get('ok'):raise RuntimeError('Benchmark action rejected: '+name)
    def action(name,payload=None):
        command('qa_desktop',{'action':name,'payload':payload or {}})
        time.sleep(.35)
    def wait(predicate,seconds=35):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            result=predicate()
            if result:return result
            time.sleep(.2)
        raise TimeoutError('Bounded performance scenario timed out')
    def launch(role,folder):
        profile=folder/'appdata/GrangerPet';profile.mkdir(parents=True,exist_ok=True)
        if not (profile/'settings.json').exists():
            settings=Settings(ai_provider='none',source_root=str(ROOT),agent_steps=3,agent_calls=4,
                agent_tokens=30000,agent_page_limit=2,request_limit=5)
            (profile/'settings.json').write_text(json.dumps(settings.to_dict()),encoding='utf-8')
        env=os.environ.copy()
        for key in ('QT_QPA_PLATFORM','QT_SCALE_FACTOR','QTWEBENGINE_CHROMIUM_FLAGS',
                    'GRANGERPET_QA_VAULT','GRANGERPET_QA_INPUT_KEY','DEEPSEEK_API_KEY','GEMINI_API_KEY'):
            env.pop(key,None)
        env.update(APPDATA=str(folder/'appdata'),GRANGERPET_INTERACTION_TRACE=str(folder/'interaction.jsonl'))
        if args.mode=='exe':
            line=[str(exe)]
        else:
            line=[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/perf_source_probe.py'),
                '--project-root',str(args.project_root.resolve())]
            env['GRANGERPET_PERF_OUTPUT']=str(folder/'numeric-probe.json')
        if role=='pet':line.append('--pet')
        line.append('--interaction-qa')
        with (folder/'process.log').open('ab') as log:
            process=subprocess.Popen(line,cwd=args.project_root,env=env,stdin=subprocess.DEVNULL,
                stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(process)
        (roots if args.mode=='exe' else source_roots).append(process.pid)
        value=wait(lambda:send_command(role,'status',timeout=500),40)
        if args.mode=='exe' and Path(process_image(value['pid'])).resolve()!=exe.resolve():
            raise RuntimeError('Unexpected executable')
        owned[role]=value['pid']
        wait(lambda:(s.get('desktop',{}).get('ready') if role=='pet' else s.get('desktop_ready'))
            if (s:=state(role)) else None,35)
        # Readiness may briefly start local workers; do not count startup as idle.
        time.sleep(10 if role=='pet' else 3)
        return process
    def sample():return monitor.sample(roots,source_main_pids=source_roots)
    def probe(folder):
        path=folder/'numeric-probe.json'
        return json.loads(path.read_text()) if args.mode=='source-probe' and path.is_file() else None
    def measure(name,folder=None,repeats=None):
        row={'name':name,'trials':[]}
        if 'pet' in owned:
            current=state()
            row['application_state']={key:current.get(key) for key in ('state','near','hovered','panel_visible','ai_busy')}
            row['application_state']['desktop']={key:current.get('desktop',{}).get(key) for key in
                ('visible','page_visible','lifecycle_state','recommended_state','render_process_pid')}
        report['scenarios'].append(row)
        for repeat in range(repeats or args.repeats):
            before=probe(folder) if folder else None
            sample();samples=[]
            for _ in range(args.seconds):
                time.sleep(1);samples.append(sample())
            trial={'samples':samples,'summary':summarize(samples)}
            after=probe(folder) if folder else None
            if before and after:
                seconds=(after['elapsed_ns']-before['elapsed_ns'])/1e9
                trial['source_probe']={'seconds':seconds,'operations':{
                    key:{'calls':value['calls']-before['operations'].get(key,{}).get('calls',0),
                        'total_ns':value['total_ns']-before['operations'].get(key,{}).get('total_ns',0)}
                    for key,value in after['operations'].items()},'active_ui_jobs_end':after['active_ui_jobs']}
            row['trials'].append(trial);save()
        keys=row['trials'][0]['summary']['medians']
        row['median_of_trials']={key:statistics.median([t['summary']['medians'][key] for t in row['trials'] if t['summary']['medians'][key] is not None])
            if any(t['summary']['medians'][key] is not None for t in row['trials']) else None for key in keys}
        save();print(json.dumps({'scenario':name,'medians':row['median_of_trials']}),flush=True)
        return row
    def stop(role):
        value=state(role)
        if value:
            if role=='pet':command('stop')
            else:command('qa_launcher',{'name':'perf-close','action':'window','payload':{'mode':'close'}},role='launcher')
            wait(lambda:not state(role),20)
        owned.pop(role,None)
        time.sleep(2)
    def live(name,text,minimized=False,folder=None):
        if minimized:command('show_workspace',{'route':'chat'})
        action('chat_send',{'text':text});wait(lambda:state()['ai_busy'],5)
        if minimized:action('window',{'mode':'minimize'})
        row=measure(name,folder or out/'pet',repeats=1)
        end=wait(lambda:s if (s:=state()) and not s['ai_busy'] else None,110)
        request=end.get('ai_request') or {}
        row['live_result']={'code':request.get('code'),'usage':request.get('usage'),
            'tool_names':end.get('agent',{}).get('tools',[]) if 'investigation' in name else [],
            'unread':end.get('notification',{}).get('unread_count'),'completed_after_minimize':minimized}
        check(name+'_api_succeeded',request.get('code')=='ok')
        if minimized:check(name+'_notification',end.get('notification',{}).get('unread_count',0)>0)
        save()

    try:
        if args.group=='app':
            measure('closed')
            launch('launcher',out/'launcher');measure('launcher_only',out/'launcher');stop('launcher')
            launch('pet',out/'pet');measure('desktop_pet_only',out/'pet')
            command('show_workspace',{'route':'chat'});time.sleep(2);measure('main_visible_idle',out/'pet')
            action('window',{'mode':'minimize'});time.sleep(2);measure('main_minimized_idle',out/'pet')
            command('show_workspace',{'route':'chat'});time.sleep(1)
            launch('launcher',out/'launcher-inactive');measure('main_inactive_own_launcher',out/'pet');stop('launcher')
            command('show_workspace',{'route':'chat'});time.sleep(1)
            if args.live:
                action('settings_save',{'values':{'ai_provider':'deepseek'}});time.sleep(1)
                live('ordinary_reply','Без инструментов: объясни в четырёх коротких предложениях, почему совпадение никнейма не доказывает общего владельца профилей. Это проверка производительности Granger-OSINT.')
                live('investigation_minimized','Проверь только https://example.org/ через web_read. По-русски кратко объясни назначение этой страницы и укажи источник. Другие внешние инструменты не вызывай.',True)
            command('show_workspace',{'route':'chat'});action('window',{'mode':'close'});measure('main_closed_pet_alive',out/'pet')
            stop('pet');measure('after_full_exit',repeats=1)
        elif args.group=='long':
            from grangerpet.chat_archive import ChatArchive
            folder=out/'long';profile=folder/'appdata/GrangerPet';profile.mkdir(parents=True)
            messages=[{'id':f'perf-{i:05}','role':'user' if i%2==0 else 'model',
                'text':f'Синтетическое сообщение {i}. Только проверка длинного списка. '+('Открытые сведения требуют проверки. '*5)} for i in range(1000)]
            ChatArchive(profile/'chat-history.dpapi').save(messages,[])
            launch('pet',folder);command('show_workspace',{'route':'chat'});time.sleep(4)
            loaded=wait(lambda:s if (s:=state()) and s.get('ai_model_messages')==500 else None,60)
            check('all_500_model_fixture_messages_loaded',loaded['ai_model_messages']==500)
            measure('long_1000_visible',folder)
            if args.live:
                action('settings_save',{'values':{'ai_provider':'deepseek'}});time.sleep(1)
                live('long_history_streaming','Без инструментов: перечисли двадцать кратких причин, почему совпадение никнейма не доказывает общего владельца. Это синтетический тест длинной переписки Granger-OSINT.',folder=folder)
            action('window',{'mode':'minimize'});time.sleep(2)
            measure('long_1000_minimized',folder);stop('pet');measure('after_long_exit',repeats=1)
        else:
            for index in range(3):
                folder=out/str(index);launch('pet',folder);command('show_workspace',{'route':'search'})
                command('show_workspace',{'route':'search'});check(f'reopen_{index}_same_pid',state()['pid']==owned['pet'])
                action('tool_run',{'tool':'username_maigret','query':'granger_osint_perf_qa_zz42791','limit':2});time.sleep(.5)
                action('search_stop');time.sleep(3);sample()
                action('window',{'mode':'close'});check(f'close_{index}_keeps_pet',bool(state()))
                command('show_workspace',{'route':'chat'});stop('pet')
                row=measure(f'after_cycle_{index}',repeats=1)
                check(f'cycle_{index}_no_remaining_owned_processes',row['median_of_trials']['process_count']==0)
        check('all_observed_owned_processes_exited',sample()['process_count']==0)
        report['passed']=True
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error)[:300]);save();raise
    finally:
        for role in ('launcher','pet'):
            if role in owned:
                try:stop(role)
                except (RuntimeError,TimeoutError):pass
        for process in processes:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:report.setdefault('unexited_owned_parents',[]).append(process.pid)
        monitor.close();save()
    return 0


if __name__=='__main__':raise SystemExit(main())
