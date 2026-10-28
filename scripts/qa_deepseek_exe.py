"""No-key final EXE regression in a fresh profile and isolated Windows vault.

No credential (real or fake) is supplied. This verifies migration, the actual
settings/check/save callbacks, honest missing-key status and restart behavior.
It does not claim a live API/tool_calls test. Existing instances are untouched.
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
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if sys.platform != 'win32':
        raise SystemExit('Packaged Windows EXE verification requires Windows')
    from PySide6.QtCore import QCoreApplication
    from grangerpet.credentials import CredentialsStore, NAMES
    from grangerpet.ipc import send_command
    from qa_packaged_search import process_image
    from smoke_exe import _terminate_spawned_binary_tree
    app = QCoreApplication.instance() or QCoreApplication([])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=ROOT / 'dist/GrangerPet.exe')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/deepseek-qa/exe-no-key')
    args = parser.parse_args()
    if send_command('pet', 'status', timeout=200) or send_command('launcher', 'status', timeout=200):
        raise SystemExit('Close GrangerPet first; existing instances are never touched')
    exe, output = args.exe.resolve(), args.output.resolve()
    if not exe.is_file():
        raise SystemExit('EXE is missing')
    if output.exists():
        raise SystemExit('Use a fresh output folder; previous evidence is preserved')
    profile = output / 'appdata/GrangerPet'
    profile.mkdir(parents=True)
    config = profile / 'settings.json'
    legacy = {'ai_provider': 'gemini', 'gemini_model': 'gemini-3.8-flash',
              'size': 195, 'fps': 24, 'cursor_reaction': True, 'x': 100, 'y': 320,
              'source_root': str(ROOT)}
    config.write_text(json.dumps(legacy, ensure_ascii=False, indent=2), encoding='utf-8')
    prefix = 'GrangerPet/QA/' + uuid.uuid4().hex
    vault = CredentialsStore(prefix=prefix, directory=profile / 'vault')
    environment = os.environ.copy()
    for name in ('QT_QPA_PLATFORM', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'DEEPSEEK_API_KEY',
                 'GEMINI_MODEL', 'DEEPSEEK_MODEL', 'GRANGERPET_QA_INPUT_KEY'):
        environment.pop(name, None)
    environment.update(APPDATA=str(output / 'appdata'),
        GRANGERPET_INTERACTION_TRACE=str(output / 'interaction.jsonl'),
        GRANGERPET_QA_VAULT=prefix, GRANGERPET_QA_INPUT_KEY='')
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(),
        'exe_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
        'method': 'Actual EXE SettingsDialog/ConnectionsPane/ChatWidget callbacks and Windows vault namespace; no credential, no API response substitution',
        'credential_scope': 'Fresh random GrangerPet/QA namespace only; production secrets are not read or changed',
        'live_api_test': 'not_executed_no_key', 'tool_calls_test': 'not_executed_no_key',
        'checks': [], 'screenshots': []}
    process = None
    owned_pid = None

    def check(name, condition, detail=None):
        report['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            raise AssertionError(name)

    def status():
        value = send_command('pet', 'status', timeout=600)
        if not value or value.get('pid') != owned_pid:
            raise RuntimeError('Owned EXE no longer answers; no other instance will be touched')
        return value

    def command(name, payload=None):
        status()
        value = send_command('pet', name, payload, timeout=700)
        if not value or not value.get('ok'):
            raise RuntimeError('QA command rejected: ' + name)

    def wait(predicate, seconds=8):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            value = status()
            if predicate(value):
                return value
            time.sleep(.06)
        raise TimeoutError('Bounded packaged UI verification timed out')

    def snapshot(name, suffix):
        time.sleep(.35)
        command('qa_snapshot', {'name': name})
        path = output / f'{name}-{suffix}.png'
        end = time.monotonic() + 4
        while not path.is_file() and time.monotonic() < end:
            time.sleep(.05)
        check('actual_snapshot_' + name, path.is_file())
        report['screenshots'].append(path.name)

    def start():
        nonlocal process, owned_pid
        assert not send_command('pet', 'status', timeout=200)
        process = subprocess.Popen([str(exe), '--pet', '--interaction-qa'], cwd=ROOT, env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        end = time.monotonic() + 30
        value = None
        while time.monotonic() < end:
            value = send_command('pet', 'status', timeout=200)
            if value and value.get('running'):
                break
            time.sleep(.08)
        check('fresh_exe_started', bool(value and value.get('running')))
        owned_pid = value['pid']
        check('exact_executable_image', os.path.normcase(str(process_image(owned_pid))) == os.path.normcase(str(exe)))
        report.setdefault('pids', []).append(owned_pid)

    def stop():
        nonlocal process, owned_pid
        current = send_command('pet', 'status', timeout=300)
        if owned_pid is not None and current and current.get('pid') == owned_pid:
            send_command('pet', 'stop', timeout=700)
        if process is not None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _terminate_spawned_binary_tree(exe, process.pid)
                process.wait(timeout=5)
        process, owned_pid = None, None

    try:
        check('fresh_vault_contains_no_credentials', all(not vault.get(name) for name in NAMES))
        start()
        initial = status()
        report['initial_state'] = initial['ai_connection']
        check('legacy_provider_migrates_to_deepseek', initial['ai_connection']['provider'] == 'deepseek')
        check('legacy_model_not_reused', initial['ai_connection']['model_id'] == 'deepseek-v4-flash')
        check('no_key_means_not_configured', initial['ai_connection']['connection_status'] == 'not_configured' and not initial['ai_connection']['credential_available'])
        check('chat_disabled_without_key', not initial['chat_can_send'])
        command('panel')
        command('qa_show_chat')
        snapshot('initial-empty-chat', 'search')
        command('qa_settings', {'page': 2})
        snapshot('deepseek-settings', 'settings')
        command('qa_ai_draft')
        time.sleep(.1)
        command('qa_ai_check')
        checked = wait(lambda value: value['ai_connection']['connection_status'] == 'not_configured' and bool(value['ai_connection']['last_error']))
        report['after_missing_key_check'] = checked['ai_connection']
        check('missing_key_check_is_honest', not checked['chat_can_send'] and checked['ai_connection']['last_verified_at'] is None)
        check('missing_key_has_visible_error', 'API-ключ' in checked['settings_ai_status'])
        check('settings_chat_same_missing_key_status', checked['settings_ai_status'] == checked['ai_provider_status'])
        check('no_message_generation_without_key', not checked['ai_request'] and not checked['ai_busy'] and checked['ai_model_messages'] == 0)
        snapshot('missing-key-settings', 'settings')
        command('qa_ai_save')
        saved = wait(lambda value: value['ai_connection']['configuration_saved'] and not value['ai_connection']['last_error'])
        saved_config = json.loads(config.read_text(encoding='utf-8'))
        check('save_persists_provider_and_model', saved_config['ai_provider'] == 'deepseek' and saved_config['deepseek_model'] == 'deepseek-v4-flash')
        check('save_drops_legacy_model_field', 'gemini_model' not in saved_config)
        check('save_without_key_does_not_claim_connected', saved['ai_connection']['connection_status'] == 'not_configured' and not saved['chat_can_send'])
        check('no_key_written_to_profile', 'deepseek_api_key' not in saved_config and not vault.get('deepseek_api_key'))
        snapshot('saved-without-key', 'settings')
        command('qa_ai_close')
        command('qa_show_chat')
        snapshot('saved-empty-chat', 'search')
        stop()
        start()
        restarted = status()
        report['restart_state'] = restarted['ai_connection']
        check('restart_restores_selected_provider_model', restarted['ai_connection']['provider'] == 'deepseek' and restarted['ai_connection']['model_id'] == 'deepseek-v4-flash')
        check('restart_without_key_remains_not_configured', restarted['ai_connection']['connection_status'] == 'not_configured' and not restarted['chat_can_send'])
        check('restart_does_not_autogenerate_or_verify', not restarted['ai_request'] and not restarted['ai_busy'] and restarted['ai_model_messages'] == 0 and restarted['ai_connection']['last_verified_at'] is None)
        command('panel')
        command('qa_show_chat')
        snapshot('restarted-empty-chat', 'search')
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['error_type'] = type(error).__name__
        # Error messages from this harness contain no provider body or key.
        report['error'] = str(error)
    finally:
        stop()
        removed = []
        for name in NAMES:
            if vault.get(name):
                vault.delete(name)
                removed.append(name)
        report['isolated_namespace_entries_created'] = len(removed)
        report['isolated_namespace_empty_after_test'] = all(not vault.get(name) for name in NAMES)
        report['logs_have_no_http_request_records'] = not any('HTTP Request:' in path.read_text(encoding='utf-8', errors='replace')
            for path in (profile / 'logs').glob('*.log'))
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(output / 'report.json'), 'passed': report['passed'],
                      'checks': len(report['checks']), 'live_api': report['live_api_test'],
                      'tool_calls': report['tool_calls_test']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
