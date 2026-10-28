"""Observe the user-authorized primary-profile setup; never makes API requests.

Key entry and Save are performed in the actual EXE's settings UI. This helper
starts/stops only its recorded process and records safe configuration metadata.
It never copies the user's profile or credentials into a release report.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QCoreApplication
from grangerpet.config import SettingsStore
from grangerpet.credentials import CredentialsStore
from grangerpet.ipc import send_command

OUT = ROOT / 'output/deepseek-qa/primary-profile'
EXE = ROOT / 'dist/GrangerPet.exe'


def other_fields(settings):
    data = settings.to_dict()
    for name in ('ai_provider', 'deepseek_model', 'x', 'y'):
        data.pop(name, None)
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def main():
    app = QCoreApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'report.json'
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'tested_at_utc': datetime.now(timezone.utc).isoformat(),
        'exe_sha256': hashlib.sha256(EXE.read_bytes()).hexdigest(),
        'method': 'Actual EXE primary-profile UI Save; no additional API call',
        'checks': [],
    }
    store = SettingsStore()
    if action == 'start':
        assert not send_command('pet', 'status') and not send_command('launcher', 'status')
        if 'before' not in report:
            settings = store.load()
            report['before'] = {'provider': settings.ai_provider, 'model': settings.deepseek_model,
                                'credential_available': bool(CredentialsStore().get('deepseek_api_key')),
                                'other_fields_sha256': other_fields(settings)}
        environment = os.environ.copy()
        for name in ('QT_QPA_PLATFORM', 'DEEPSEEK_API_KEY', 'GOOGLE_API_KEY',
                     'GRANGERPET_QA_VAULT', 'GRANGERPET_QA_INPUT_KEY'):
            environment.pop(name, None)
        environment['GRANGERPET_INTERACTION_TRACE'] = str(OUT / 'interaction.jsonl')
        process = subprocess.Popen([str(EXE), '--pet', '--interaction-qa'], cwd=ROOT, env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        end = time.monotonic() + 30
        current = None
        while time.monotonic() < end:
            current = send_command('pet', 'status', timeout=200)
            if current and current.get('running'):
                break
            time.sleep(.1)
        assert current and current.get('running')
        report['pid'] = current['pid']
        report.setdefault('initial_state', current['ai_connection'])
        report['last_start_state'] = current['ai_connection']
        send_command('pet', 'panel')
        time.sleep(.2)
        send_command('pet', 'qa_settings', {'page': 2})
    elif action == 'verify_saved':
        expected = CredentialsStore().get('deepseek_api_key')
        current = send_command('pet', 'status')
        assert current and current['pid'] == report['pid']
        settings = store.load()
        tests = {
            'provider_model_saved': settings.ai_provider == 'deepseek' and settings.deepseek_model == 'deepseek-v4-flash',
            'windows_credential_available': bool(expected) and CredentialsStore().get('deepseek_api_key') == expected,
            'chat_enabled_immediately_without_restart': bool(current['chat_can_send']),
            'honest_unverified_status': current['ai_connection']['connection_status'] == 'configured_unverified',
            'other_preferences_preserved': other_fields(settings) == report['before']['other_fields_sha256'],
            'key_absent_from_settings_json': bool(expected) and expected not in store.path.read_text(encoding='utf-8'),
            'no_generation_performed': current['ai_model_messages'] == 0 and not current['ai_request'],
        }
        for name, passed in tests.items():
            report['checks'].append({'name': name, 'passed': bool(passed)})
        report['after_save'] = current['ai_connection']
        report['settings_status'] = current['settings_ai_status']
        send_command('pet', 'qa_snapshot', {'name': 'primary-saved'})
        assert all(tests.values()), [name for name, passed in tests.items() if not passed]
    elif action == 'restart_verified':
        current = send_command('pet', 'status')
        assert current and current['pid'] == report['pid']
        checks = {
            'restart_restores_configuration_and_credential': current['ai_connection']['provider'] == 'deepseek' and current['ai_connection']['model_id'] == 'deepseek-v4-flash' and current['ai_connection']['credential_available'],
            'restart_enables_chat_without_api_probe': bool(current['chat_can_send']) and not current['ai_request'] and not current['ai_busy'],
            'restart_still_reports_unverified': current['ai_connection']['connection_status'] == 'configured_unverified',
        }
        report['restart_state'] = current['ai_connection']
        report['checks'].extend({'name': name, 'passed': bool(passed)} for name, passed in checks.items())
        report['passed'] = all(item['passed'] for item in report['checks'])
        assert all(checks.values())
    elif action == 'chat':
        current = send_command('pet', 'status')
        assert current and current['pid'] == report['pid']
        send_command('pet', 'qa_ai_close')
        send_command('pet', 'qa_show_chat')
        time.sleep(.4)
        send_command('pet', 'qa_snapshot', {'name': 'primary-configured-chat'})
    elif action == 'stop':
        current = send_command('pet', 'status')
        assert current and current['pid'] == report['pid']
        send_command('pet', 'stop', timeout=600)
    elif action == 'status':
        current = send_command('pet', 'status')
        print(json.dumps(current, ensure_ascii=False))
    else:
        raise ValueError(action)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Primary-profile step:', action)


if __name__ == '__main__':
    main()
