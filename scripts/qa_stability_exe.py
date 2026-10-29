"""Real Qt/WebEngine restart checks with corrupt synthetic state only.

Both IPC and encrypted profile namespaces are isolated from the owner's app.
The same script accepts a staged or final executable; it never imports keys.
"""
from __future__ import annotations
import argparse
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('Choose a new output directory; earlier evidence retained')
    out.mkdir(parents=True)
    namespace = uuid.uuid4().hex
    os.environ.update(APPDATA=str(out / 'appdata'), GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_INTERACTION_TRACE=str(out / 'interaction.jsonl'),
        GRANGERPET_QA_VAULT='GrangerPet/QA/stability_' + namespace)
    for name in ('QT_QPA_PLATFORM', 'DEEPSEEK_API_KEY', 'GEMINI_API_KEY'):
        os.environ.pop(name, None)
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    from grangerpet import credentials
    from grangerpet.config import Settings
    from grangerpet.chat_archive import ChatArchive
    from grangerpet.conversations import ConversationLibrary
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.ipc import send_command
    credentials._STORE = credentials.CredentialsStore(prefix=os.environ['GRANGERPET_QA_VAULT'])
    profile = out / 'appdata/GrangerPet'
    profile.mkdir(parents=True)
    (profile / 'settings.json').write_text(json.dumps(Settings(cursor_reaction=False, reduced_motion=True, source_root=str(ROOT)).to_dict()), encoding='utf-8')
    archive = ChatArchive(profile / 'chat-history.dpapi')
    library = ConversationLibrary(archive)
    inv_id = uuid.uuid4().hex
    row = normalize_evidence({'id': 'synthetic', 'title': 'Сохранённое доказательство', 'type': 'observation', 'platform': 'Synthetic', 'details': {}}, 'fixture', 'synthetic')
    bad = dict(row, provenance='[ограничено]')
    journal = profile / 'investigations'
    journal.mkdir()
    report_path = journal / (inv_id + '.json')
    report_path.write_text(json.dumps({'id': inv_id, 'status': 'running', 'context_compactions': '[ограничено]',
        'evidence': [row, bad], 'executions': [{'tool': 'fixture', 'status': 'complete'}]}, ensure_ascii=False), encoding='utf-8')
    checkpoint_path = journal / (inv_id + '.checkpoint.dpapi')
    checkpoint_path.write_bytes(credentials.CredentialsStore._protect(json.dumps({'version': 1, 'id': inv_id,
        'record': {'id': inv_id, 'status': 'running'}, 'executions': ['corrupt synthetic row']}).encode()))
    originals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (report_path, checkpoint_path)}
    archive.save([{'id': uuid.uuid4().hex, 'role': 'user', 'text': 'Синтетическое сохранённое расследование'},
        {'id': uuid.uuid4().hex, 'role': 'model', 'text': 'Сохранённый результат', 'investigation_id': inv_id, 'evidence_ids': [row['evidence_id']]}], [])
    library.seal()
    report = {'mode': 'actual_frozen_Qt_WebEngine', 'user_data_read': False, 'gateway_calls': 0,
              'exe_sha256': hashlib.sha256(args.exe.read_bytes()).hexdigest(), 'checks': []}
    def save():
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        save()
        if not condition:
            raise AssertionError(name)
    def wait(fn, timeout=50):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = fn()
            if value:
                return value
            time.sleep(.12)
        raise TimeoutError('Bounded own-GUI wait expired')
    process = None
    owned = None
    def state():
        value = send_command('pet', 'status', timeout=1500)
        if value and owned and value.get('pid') != owned:
            raise RuntimeError('Own isolated IPC PID mismatch')
        return value
    def command(name, payload=None):
        if not state():
            raise RuntimeError('Own isolated app unavailable')
        value = send_command('pet', name, payload, timeout=3000)
        if not value or not value.get('ok'):
            raise RuntimeError('Own action rejected: ' + name)
        return value
    def action(name, payload=None):
        command('qa_desktop', {'action': name, 'payload': payload or {}})
        time.sleep(.2)
    def snapshot(label):
        command('qa_desktop', {'action': 'save_state', 'name': label})
        path = out / (label + '.json')
        wait(path.exists)
        return json.loads(path.read_text(encoding='utf-8'))
    try:
        for run in range(2):
            with (out / f'process-{run}.log').open('wb') as log:
                process = subprocess.Popen([str(args.exe.resolve()), '--pet', '--interaction-qa'], cwd=ROOT,
                    env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
            owned = wait(state)['pid']
            wait(lambda: (s := state()) and s.get('desktop', {}).get('ready'))
            command('show_workspace', {'route': 'chat'})
            current = snapshot(f'restored-{run}')
            check(f'opened_after_corrupt_state_{run}', bool(current['messages']))
            check(f'no_automatic_resume_{run}', not current['busy'] and current['investigation'].get('status') != 'running')
            check(f'intact_neighbor_evidence_visible_{run}', len(current['evidence']) == 1)
            check(f'one_recovery_notice_{run}', len(current.get('errors', [])) == 1)
            command('qa_desktop', {'action': 'dom'})
            wait(lambda: (s := state()) and 'Сохранённый результат' in s['desktop'].get('dom', {}).get('text', ''))
            check(f'real_renderer_responsive_{run}', True)
            action('investigation_continue', {'id': inv_id})
            wait(lambda: state()['desktop'].get('last_response', {}).get('ok') is False)
            check(f'bad_checkpoint_rejected_without_gui_crash_{run}', not snapshot(f'after-bad-resume-{run}')['busy'])
            command('qa_snapshot', {'name': f'stability-recovery-{run}'})
            if run == 1:
                action('chat_new')
                current = snapshot('new-conversation')
                check('new_conversation_opens_after_failure', not current['messages'] and not current['busy'])
            command('stop')
            process.wait(timeout=25)
            check(f'exit_zero_{run}', process.returncode == 0)
            owned = None
        check('damaged_originals_never_rewritten', originals == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (report_path, checkpoint_path)})
        report['passed'] = True
        save()
    except Exception as error:
        report.update(passed=False, error_type=type(error).__name__, error=str(error)[:200])
        save()
        raise
    finally:
        if process is not None and process.poll() is None:
            command('stop')
            process.wait(timeout=25)
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
