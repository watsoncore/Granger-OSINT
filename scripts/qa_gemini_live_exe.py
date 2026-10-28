"""One explicitly requested live Gemini message through the final EXE's actual chat.

No credential is copied to disk, a report, command-line arguments or WinCred.
The optional existing development file is read only into the spawned process's
environment. An unavailable quota/model/key is reported without retry or fallback.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=ROOT / 'dist/GrangerPet.exe')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/ui-gemini-qa/live-exe')
    parser.add_argument('--key-file', type=Path, help='Existing local dotenv file; never created or modified')
    args = parser.parse_args()
    from PySide6.QtCore import QCoreApplication
    from dotenv import dotenv_values
    from grangerpet.ai_keys import DEFAULT_GEMINI_MODEL, gemini_credentials
    from grangerpet.config import Settings
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    app = QCoreApplication([])
    if send_command('pet', 'status', timeout=200) or send_command('launcher', 'status', timeout=200):
        raise SystemExit('Close GrangerPet first; no existing instance will be touched')
    output, executable = args.output.resolve(), args.exe.resolve()
    if (output / 'report.json').exists():
        raise SystemExit('Use a new output folder to preserve previous API attempts')
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    source = 'configured'
    if args.key_file:
        values = dotenv_values(args.key_file.resolve(), interpolate=False, encoding='utf-8-sig')
        if values.get('GEMINI_API_KEY') and not environment.get('GEMINI_API_KEY'):
            environment['GEMINI_API_KEY'] = values['GEMINI_API_KEY']
            source = 'explicit-existing-development-file'
    credential = gemini_credentials(environ=environment)
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(),
        'model': DEFAULT_GEMINI_MODEL, 'thinking_level': 'medium', 'sdk': 'google-genai',
        'sdk_version': version('google-genai'), 'live_generation_attempts': 0,
        'method': 'Final EXE ChatWidget → official SDK → real Gemini API, one short user message; no mocks',
        'key_source': source if credential.source == 'environment' else credential.source,
        'exe_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(), 'checks': []}
    if not credential.available:
        report.update(live_test='not_executed', reason='No available Gemini API key')
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('No key available; live request not made')
        return 0
    environment['GEMINI_API_KEY'] = credential.key
    environment['GEMINI_MODEL'] = DEFAULT_GEMINI_MODEL
    environment['APPDATA'] = str(output / 'appdata')
    environment['GRANGERPET_INTERACTION_TRACE'] = str(output / 'interaction.jsonl')
    environment.pop('QT_QPA_PLATFORM', None)
    profile = output / 'appdata/GrangerPet'
    profile.mkdir(parents=True, exist_ok=True)
    settings = Settings(size=195, x=600, y=320, ai_provider='gemini', gemini_model=DEFAULT_GEMINI_MODEL,
                        source_root=str(ROOT))
    (profile / 'settings.json').write_text(json.dumps(settings.to_dict()), encoding='utf-8')
    child = subprocess.Popen([str(executable), '--pet', '--interaction-qa'], env=environment,
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW)
    pid = None
    started = time.monotonic()

    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    def status():
        value = send_command('pet', 'status', timeout=600)
        if not value or not value.get('running') or (pid is not None and value.get('pid') != pid):
            raise RuntimeError('Owned EXE no longer answers; no other process will be targeted')
        return value

    def command(name, payload=None):
        status()
        response = send_command('pet', name, payload, timeout=600)
        if not response or not response.get('ok'):
            raise RuntimeError('Application QA command rejected: ' + name)

    def capture(name, suffix='search'):
        command('qa_snapshot', {'name': name})
        path = output / (name + '-' + suffix + '.png')
        end = time.monotonic() + 4
        while not path.is_file() and time.monotonic() < end:
            time.sleep(.05)
        check('actual_screenshot_' + name, path.is_file())

    try:
        end = time.monotonic() + 25
        initial = None
        while time.monotonic() < end:
            initial = send_command('pet', 'status', timeout=150)
            if initial and initial.get('running'):
                break
            time.sleep(.05)
        check('fresh_exe_running', bool(initial and initial.get('running')))
        pid = int(initial['pid'])
        check('exact_owned_executable', os.path.normcase(str(process_image(pid))) == os.path.normcase(str(executable)))
        command('panel')
        time.sleep(.25)
        capture('empty')
        before = status().get('ai_model_messages', 0)
        request_started = time.monotonic()
        command('qa_chat', {'text': 'Гермиона, кратко объясни назначение OSINT в одном предложении.'})
        report['live_generation_attempts'] = 1
        observed_busy = False
        states, phases = [], []
        end = time.monotonic() + 65
        while time.monotonic() < end:
            time.sleep(.1)
            current = status()
            observed_busy |= bool(current.get('ai_busy'))
            if current.get('state') not in states:
                states.append(current.get('state'))
            if current.get('ai_status') not in phases:
                phases.append(current.get('ai_status'))
            if not current.get('ai_busy') and (observed_busy or current.get('ai_model_messages', 0) > before or current.get('ai_status') not in ('Введите сообщение', None)):
                break
        report['request_elapsed_seconds'] = round(time.monotonic() - request_started, 3)
        report['animation_states_observed'] = states
        report['ui_statuses'] = phases
        report['text_received'] = current.get('ai_model_messages', 0) > before
        report['live_test'] = 'success' if report['text_received'] else 'rejected_or_unavailable'
        report['final_ui_status'] = current.get('ai_status', '')
        report['request_metadata'] = current.get('ai_request', {})
        check('request_finished_without_blocking_app', not current.get('ai_busy'))
        check('search_remains_independent', not current.get('searching') and current.get('result_count') == 0)
        capture('gemini-reply' if report['text_received'] else 'gemini-error')
        command('qa_settings', {'page': 2})
        time.sleep(.2)
        capture('gemini-settings', 'settings')
        check('no_plaintext_key_in_settings', credential.key not in (profile / 'settings.json').read_text(encoding='utf-8'))
        for path in (profile / 'logs').glob('*.log'):
            check('no_key_in_' + path.name, credential.key not in path.read_text(encoding='utf-8'))
        report['app_checks_passed'] = True
    except Exception as exc:
        # Never stringify an arbitrary SDK error or the environment.
        report['app_checks_passed'] = False
        report['harness_error_type'] = type(exc).__name__
    finally:
        if pid is not None:
            existing = send_command('pet', 'status', timeout=300)
            if existing and existing.get('pid') == pid:
                send_command('pet', 'stop', timeout=600)
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
        report['process_closed'] = child.poll() is not None
        report['total_elapsed_seconds'] = round(time.monotonic() - started, 3)
        payload = json.dumps(report, ensure_ascii=False, indent=2).replace(credential.key, '[redacted]')
        (output / 'report.json').write_text(payload + '\n', encoding='utf-8')
        print(json.dumps({name: report.get(name) for name in ('model', 'live_generation_attempts', 'live_test', 'text_received', 'request_elapsed_seconds', 'app_checks_passed')}, ensure_ascii=False))
    return 0 if report.get('app_checks_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
