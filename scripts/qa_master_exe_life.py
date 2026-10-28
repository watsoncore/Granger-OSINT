"""Continue final EXE idle-action/history checks, without repeating paid A-E.

Actions are triggered through the explicitly enabled test hook. Their rendering,
motion and interruption run through production PetWindow/Controller handlers.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from PySide6.QtCore import QCoreApplication
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    from smoke_exe import _terminate_spawned_binary_tree
    app = QCoreApplication([])
    out = ROOT/'output/master-qa/exe-life'
    previous = ROOT/'output/master-qa/exe-release'
    exe = ROOT/'dist/GrangerPet.exe'
    previous_report = json.loads((previous/'report.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    if digest != previous_report['exe_sha256']:
        raise SystemExit('A-E evidence belongs to a different executable')
    if out.exists():
        raise SystemExit('Prior life evidence preserved')
    if send_command('pet', 'status') or send_command('launcher', 'status'):
        raise SystemExit('Close existing GrangerPet before isolated QA')
    profile = out/'appdata/GrangerPet'
    profile.mkdir(parents=True)
    for filename in ('settings.json', 'chat-history.dpapi'):
        shutil.copy2(previous/'appdata/GrangerPet'/filename, profile/filename)
    env = os.environ.copy()
    for key in ('QT_QPA_PLATFORM', 'QT_SCALE_FACTOR', 'QT_SCREEN_SCALE_FACTORS', 'GRANGERPET_QA_VAULT',
                'GRANGERPET_QA_INPUT_KEY', 'GEMINI_API_KEY', 'DEEPSEEK_API_KEY'):
        env.pop(key, None)
    env.update(APPDATA=str(out/'appdata'), GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(), 'exe_sha256': digest,
              'prior_live_report': 'exe-release/report.json', 'real_api_called': False,
              'method': 'Final native EXE; actual saved conversation, forced local actions, production activity hook, actual window movement',
              'checks': [], 'actions': []}
    process = None
    pid = None
    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)
    def state():
        current = send_command('pet', 'status')
        if not current or current['pid'] != pid:
            raise RuntimeError('Verified QA instance exited')
        return current
    def command(name, payload=None):
        state()
        answer = send_command('pet', name, payload, timeout=700)
        if not answer or not answer.get('ok'):
            raise RuntimeError('QA command rejected: '+name)
    def wait(predicate, seconds=10):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            current = state()
            if predicate(current):
                return current
            time.sleep(.1)
        raise TimeoutError('Bounded life/history QA timeout')
    def start():
        nonlocal process, pid
        process = subprocess.Popen([str(exe), '--pet', '--interaction-qa'], cwd=ROOT, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        end = time.monotonic()+25
        while time.monotonic()<end:
            current = send_command('pet', 'status', timeout=200)
            if current:
                pid = current['pid']
                break
            time.sleep(.1)
        check('verified_final_exe', pid is not None and Path(process_image(pid)).resolve()==exe.resolve())
    def stop():
        nonlocal process, pid
        current = send_command('pet', 'status')
        if current and current['pid']==pid:
            send_command('pet', 'stop')
        if process:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _terminate_spawned_binary_tree(exe, process.pid)
        process = None
        pid = None
    try:
        start()
        check('real_history_restored', state()['ai_model_messages']==3 and not state()['ai_request'])
        wait(lambda s:s['state']=='idle' and not s['near'],12)
        report['initial_idle_state'] = {name: state()[name] for name in ('state', 'near', 'position', 'panel_visible')}
        for action in ('reading', 'cast', 'avada', 'yawn', 'sleep', 'leave'):
            before = state()['position']
            command('qa_life', {'action': action})
            time.sleep(.85)
            active = state()
            check('F_'+action+'_rendered_action', active['life']['action']==action)
            command('qa_snapshot', {'name': 'F-'+action})
            if action=='leave':
                check('F_leave_actual_window_motion', active['position']!=before)
            row = {'action': action, 'actual_action': active['life']['action'], 'position': active['position']}
            report['actions'].append(row)
            command('qa_life', {'action': 'interrupt'})
            time.sleep(.12)
            row['transition_after_activity'] = state()['life']['action']
            wait(lambda s:not s['life']['active'],3)
            check('F_'+action+'_interrupted', True)
            check('F_'+action+'_home_restored', state()['position']==before)
        home = state()['position']
        command('qa_life', {'action': 'leave'})
        away = wait(lambda s:s['life']['action']=='away',6)
        check('F_natural_leave_to_away', away['position']!=home)
        returned = wait(lambda s:s['life']['action']=='return',12)
        command('qa_snapshot', {'name': 'F-return'})
        wait(lambda s:not s['life']['active'],4)
        check('F_natural_return_home', state()['position']==home)
        models = state()['ai_model_messages']
        stop()
        start()
        check('history_restored_without_network', state()['ai_model_messages']==models and not state()['ai_request'])
        command('panel')
        command('qa_show_chat')
        time.sleep(.4)
        command('qa_snapshot', {'name': 'history-reopened'})
        report.update(passed=True, pid=pid)
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error)[:160])
        if pid:
            try:
                report['failure_state']=state()
            except Exception:
                pass
    finally:
        if not report.get('passed'):
            stop()
        (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report.get('passed'), 'checks': len(report['checks']), 'pid': pid, 'error': report.get('error')}))
    return 0 if report.get('passed') else 1


if __name__=='__main__':
    raise SystemExit(main())
