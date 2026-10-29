"""Native final-EXE DPI/window checks using the real, encrypted QA conversation.

No generation requests or new conversations. The configured gateway may receive
an automatic read-only balance GET. Qt's documented testing scale override
simulates 100/125/150% without modifying Windows display settings.
"""
from datetime import datetime, timezone
import argparse
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
    from PySide6.QtWidgets import QApplication
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    from smoke_exe import _terminate_spawned_binary_tree
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'output/upgrade-qa/exe-dpi-delivery')
    parser.add_argument('--profile', type=Path, default=ROOT/'output/upgrade-qa/exe-delivery/appdata/GrangerPet')
    args = parser.parse_args()
    app = QApplication([])
    native_scale = app.primaryScreen().devicePixelRatio()
    area = app.primaryScreen().availableGeometry()
    physical_area = (area.width()*native_scale, area.height()*native_scale)
    source = args.profile.resolve()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('Prior DPI evidence preserved')
    if send_command('pet', 'status') or send_command('launcher', 'status'):
        raise SystemExit('Close existing GrangerPet before isolated QA')
    out.mkdir(parents=True)
    exe = ROOT/'dist/Granger-OSINT.exe'
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(),
              'exe_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
              'method': 'Native Windows EXE; QT_SCALE_FACTOR relative to measured native DPR; real previous chat; no generation requests; automatic balance GET possible',
              'native_dpr': native_scale,
              'source': 'https://doc.qt.io/qt-6/highdpi.html', 'runs': []}
    process = None
    pid = None
    try:
        for scale in (1.0, 1.25, 1.5):
            name = str(round(scale*100))
            folder = out/name
            profile = folder/'appdata/GrangerPet'
            profile.mkdir(parents=True)
            shutil.copytree(source, profile, dirs_exist_ok=True)
            env = os.environ.copy()
            for key in ('QT_QPA_PLATFORM', 'QT_SCALE_FACTOR', 'QT_SCREEN_SCALE_FACTORS', 'GRANGERPET_QA_VAULT',
                        'GRANGERPET_QA_INPUT_KEY', 'GEMINI_API_KEY', 'DEEPSEEK_API_KEY'):
                env.pop(key, None)
            env.update(APPDATA=str(folder/'appdata'), QT_SCALE_FACTOR=str(scale/native_scale),
                       GRANGERPET_INTERACTION_TRACE=str(out/(name+'-interaction.jsonl')))
            process = subprocess.Popen([str(exe), '--pet', '--interaction-qa'], cwd=ROOT, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            end = time.monotonic()+25
            status = None
            while time.monotonic() < end:
                status = send_command('pet', 'status', timeout=200)
                if status:
                    break
                time.sleep(.1)
            if not status:
                raise TimeoutError('EXE did not start')
            pid = status['pid']
            if Path(process_image(pid)).resolve() != exe.resolve():
                raise RuntimeError('Unexpected executable')
            row = {'requested_scale': scale, 'actual_dpr': status['dpr'], 'checks': []}
            report['runs'].append(row)
            def check(name, value):
                row['checks'].append({'name': name, 'passed': bool(value)})
                if not value:
                    raise AssertionError(name)
            def state():
                current = send_command('pet', 'status')
                if not current or current['pid'] != pid:
                    raise RuntimeError('Verified QA instance exited')
                return current
            def command(name, payload=None):
                state()
                answer = send_command('pet', name, payload, timeout=2500)
                if not answer or not answer.get('ok'):
                    raise RuntimeError('QA command rejected: '+name)
                time.sleep(.35)
            check('effective_dpr', abs(status['dpr']-scale)<.02)
            check('real_history_loaded', status['ai_model_messages']>=2)
            command('panel')
            command('qa_show_chat')
            for mode in ('windowed', 'maximized', 'fullscreen'):
                command('qa_window_mode', {'mode': mode})
                current = state()
                check(mode+'_state', current['window']['fullscreen'] if mode=='fullscreen' else
                      current['window']['maximized'] if mode=='maximized' else
                      not current['window']['fullscreen'] and not current['window']['maximized'])
                check(mode+'_pet_alive', current['running'])
                command('qa_snapshot', {'name': name+'-'+mode})
                command('qa_desktop', {'action':'dom'})
                check(mode+'_react_ready', state()['desktop']['ready'])
                check(mode+'_no_overflow', not state()['desktop']['dom'].get('overflow', True))
                if mode=='windowed':
                    row['windowed_size']=[state()['window']['width'],state()['window']['height']]
                    row['available_size']=[round(v/scale) for v in physical_area]
                    check('windowed_fits_work_area', state()['window']['height'] <= physical_area[1]/scale + 2)
            command('qa_window_mode', {'mode': 'fullscreen'})
            check('restores_maximized', state()['window']['maximized'] and not state()['window']['fullscreen'])
            check('no_generation_on_restore', not state()['ai_request'])
            for route in ('settings','search','chat'):
                command('qa_desktop',{'action':'route','payload':{'route':route}})
                command('qa_desktop',{'action':'dom'})
                document=state()['desktop']['dom']
                check(route+'_manrope_loaded',document.get('font',{}).get('loaded'))
                check(route+'_no_horizontal_overflow',not document.get('overflow',True))
                check(route+'_dock_fit',document.get('dock',{}).get('width',0)>=219 and document.get('dock',{}).get('height',0)>=280)
                command('qa_snapshot',{'name':name+'-'+route})
            command('stop')
            process.wait(timeout=10)
            process = None
            pid = None
        report['passed'] = True
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error)[:150])
    finally:
        if process:
            current = send_command('pet', 'status')
            if current and current['pid']==pid:
                send_command('pet', 'stop')
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _terminate_spawned_binary_tree(exe, process.pid)
        (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report.get('passed'), 'scales': len(report['runs']), 'error': report.get('error')}))
    return 0 if report.get('passed') else 1


if __name__=='__main__':
    raise SystemExit(main())
