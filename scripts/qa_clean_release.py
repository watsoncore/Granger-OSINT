"""Actual frozen Qt acceptance with automatically removed isolated QA data.

No previous output directory, user profile, API key or network result is used.
Only a small allowlisted summary may outlive this run. Call with --exe for the
staged executable, then again for dist/Granger-OSINT.exe after promotion.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def research_labels(label):
    words={'полотно':'граф','полотна':'графа','полотну':'графу','полотном':'графом','полотне':'графе','полотен':'графов'}
    modern=label.replace('Моё полотно','Мой граф').replace('Рабочее полотно','Рабочий граф')
    modern=re.sub(r'\b[Пп]олотн[а-я]*\b',
        lambda match:words.get(match[0].lower(),match[0]).capitalize() if match[0][0].isupper() else words.get(match[0],match[0]),modern)
    return (label,modern)


class QaFailure(RuntimeError):
    """Static failure code only; raw runtime data does not enter the report."""


@contextmanager
def isolated_environment(directory: Path):
    """Restore the caller's environment even after an interrupted QA run."""
    before = os.environ.copy()
    namespace = uuid.uuid4().hex
    temporary = directory / 'tmp'
    temporary.mkdir()
    for name in list(os.environ):
        if (name in {'QT_QPA_PLATFORM', 'DEEPSEEK_API_KEY', 'GEMINI_API_KEY',
                     'GRANGERPET_QA_INPUT_KEY', 'PYTHONHOME', 'PYTHONPATH'}
                or name.startswith(('_PYI_', 'PYINSTALLER_'))):
            os.environ.pop(name, None)
    os.environ.update(APPDATA=str(directory / 'appdata'), TEMP=str(temporary), TMP=str(temporary),
        GRANGERPET_QA_NAMESPACE=namespace, GRANGERPET_QA_VAULT='GrangerPet/QA/clean_' + namespace,
        GRANGERPET_INTERACTION_TRACE=str(directory / 'interaction.jsonl'))
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def process_image(pid: int) -> Path:
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise QaFailure('owned_process_not_readable')
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise QaFailure('owned_process_image_unavailable')
        return Path(buffer.value).resolve()
    finally:
        kernel.CloseHandle(handle)


def wait_for(function, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = function()
        if value:
            return value
        time.sleep(.15)
    raise QaFailure('bounded_native_wait_expired')


def validate_report_path(path: Path | None):
    if path is not None and path.resolve().is_relative_to(ROOT / 'dist'):
        raise ValueError('The QA report must remain outside dist.')


class NativeSession:
    def __init__(self, executable: Path, directory: Path):
        self.executable = executable.resolve()
        self.directory = directory
        self.process = None
        self.owned_pid = None

    def status(self):
        from grangerpet.ipc import send_command
        started=time.monotonic()
        row = send_command('pet', 'status', timeout=1500)
        if not row and self.owned_pid is not None:
            # Read-only cold WebEngine status may overlap the first window
            # publication. Bound recovery and expose its duration; never retry
            # an unknown-outcome mutation or accept a different process.
            self.status_timeouts=getattr(self,'status_timeouts',0)+1
            row=send_command('pet','status',timeout=3000)
            if row:self.status_recovery_ms=max(getattr(self,'status_recovery_ms',0),(time.monotonic()-started)*1000)
        if row:
            pid = row.get('pid')
            if type(pid) is not int or pid <= 0 or process_image(pid) != self.executable:
                raise QaFailure('ipc_process_image_mismatch')
            if self.owned_pid is not None and pid != self.owned_pid:
                raise QaFailure('ipc_owned_pid_changed')
            if self.process is None or self.process.poll() is not None:
                raise QaFailure('spawned_executable_not_running')
        return row

    def command(self, name, payload=None):
        # Every action is preceded by an exact PID + full image-path check.
        if not self.status():
            raise QaFailure('owned_ipc_unavailable')
        from grangerpet.ipc import send_command
        value = send_command('pet', name, payload or {}, timeout=8000)
        if not value or not value.get('ok'):
            raise QaFailure('owned_command_rejected_' + name)
        return value

    def action(self, name, payload=None):
        self.command('qa_desktop', {'action': name, 'payload': payload or {}})
        time.sleep(.2)

    def snapshot(self):
        # Windows can keep a just-scanned large JSON file open without write
        # sharing. Never overwrite an earlier observation during live workers.
        name='state_'+uuid.uuid4().hex
        path=self.directory/(name+'.json')
        self.command('qa_desktop', {'action': 'save_state', 'name': name})
        try:return json.loads(path.read_text(encoding='utf-8'))
        finally:
            try:path.unlink(missing_ok=True)
            except PermissionError:pass  # The owned temporary directory cleans up.

    def dom(self):
        self.action('dom')
        return self.status()['desktop'].get('dom', {})

    def click(self, label):
        def control():
            dom = self.dom()
            return next((row for row in dom.get('elements', [])
                if any(value in (row.get('label'), row.get('text')) for value in research_labels(label)) and row['width'] > 0
                and 0 < row['y'] < dom['height'] - 25), None)
        row = wait_for(control)
        self.action('input', {'kind': 'click', 'at': [row['x'] + row['width'] / 2, row['y'] + min(16, row['height'] / 2)]})

    def start(self, number, *, workspace=True):
        if self.process and self.process.poll() is None:
            raise QaFailure('previous_owned_process_still_running')
        self.owned_pid = None
        with (self.directory / f'process-{number}.log').open('wb') as stream:
            self.process = subprocess.Popen([str(self.executable), '--pet', '--interaction-qa'],
                cwd=ROOT, env=os.environ.copy(), stdout=stream, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.owned_pid = wait_for(self.status, 90)['pid']
        wait_for(lambda: self.status().get('desktop', {}).get('ready'), 60)
        if workspace:
            self.show_workspace()

    def show_workspace(self):
        self.command('show_workspace', {'route': 'chat'})
        self.action('window', {'mode': 'maximize'})

    def stop(self):
        if not self.process or self.process.poll() is not None:
            return
        try:
            self.command('stop')
        except QaFailure:
            from scripts.smoke_exe import _terminate_spawned_binary_tree
            _terminate_spawned_binary_tree(self.executable, self.process.pid)
            self.process.wait(timeout=10)
            raise
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            # Only our exact spawned binary tree is eligible; never a process
            # name/global taskkill. This is an owned failed-test cleanup.
            from scripts.smoke_exe import _terminate_spawned_binary_tree
            _terminate_spawned_binary_tree(self.executable, self.process.pid)
            self.process.wait(timeout=10)
            raise QaFailure('owned_shutdown_timeout') from None
        if self.process.returncode != 0:
            raise QaFailure('owned_exit_nonzero')
        self.owned_pid = None


def check_tool_catalog(tools, check, *, allow_missing_external_tools=False, report=None):
    """CI may test registration while honestly reporting absent external runtimes."""
    by_id = {row['id']: row for row in tools}
    external = ('blockchain_gansar', 'username_maigret')
    availability = {name: by_id.get(name, {}).get('available') is True for name in external}
    scope = {'policy': 'registry-only-for-external-tools' if allow_missing_external_tools else 'strict-local-availability',
        'availability': availability, 'missing_external_tools': [name for name in external if not availability[name]],
        'external_execution_requested': False, 'availability_required': not allow_missing_external_tools}
    if report is not None:
        report.update(scope)
    check('gansar_maigret_and_image_tool_registered', {*external, 'image_metadata'} <= set(by_id))
    if not allow_missing_external_tools:
        check('gansar_and_maigret_locally_available', all(availability.values()))


def acceptance(executable: Path, directory: Path, check, *, allow_missing_external_tools=False, tool_report=None):
    from PySide6.QtCore import QCoreApplication
    from PIL import Image
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.chat_archive import ChatArchive
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.investigation import new_investigation
    from grangerpet.research_canvas import CanvasStore, add_node, new_document

    application = QCoreApplication.instance() or QCoreApplication([])
    SettingsStore().save(Settings(source_root=str(ROOT), cursor_reaction=False, reduced_motion=True, ai_provider='none'))
    profile = Path(os.environ['APPDATA']) / 'GrangerPet'
    model_id = uuid.uuid4().hex
    markdown = '# Синтетический документ QA\n\nПроверка UTF-8: Гермиона, Ёжик.'
    ChatArchive(profile / 'chat-history.dpapi').save([{'id': model_id, 'role': 'model', 'text': markdown}], [])
    journal = InvestigationJournal(profile / 'investigations')
    record, protocol = new_investigation('SYNTHETIC offline QA investigation https://cleanup.example/')
    record.update(status='completed', synthetic=True)
    rows = [normalize_evidence({'id': 'cleanup-fixture', 'type': 'web', 'platform': 'Synthetic QA fixture',
        'url': 'https://cleanup.example/', 'title': 'SYNTHETIC saved fixture',
        'description': 'Offline fixture, never a live search result.', 'details': {'synthetic': True}}, 'web_read', 'https://cleanup.example/')]
    journal.save_checkpoint({**protocol, 'version': 1, 'id': record['id'], 'record': record, 'evidence': rows, 'executions': []})
    document = new_document('SYNTHETIC saved analyst canvas')
    add_node(document, {'type': 'person', 'label': 'Синтетический объект QA'})
    document = CanvasStore(journal).save(document, 0)
    buffer = io.BytesIO()
    Image.new('RGB', (96, 64), '#31617b').save(buffer, 'PNG')
    (directory / 'fixture.png').write_bytes(buffer.getvalue())
    image_sha = hashlib.sha256(buffer.getvalue()).hexdigest()
    session = NativeSession(executable, directory)
    try:
        session.start(0, workspace=False)
        check('exact_spawned_pid_and_executable_path', True)
        state = session.status()
        check('native_frontend_ready_and_load_ok', state['desktop']['ready'] and state['desktop']['load_ok'])
        # Opening/maximizing a host before its CSS dock is delivered may
        # deliberately suppress the overlay. Test the actual desktop pet
        # before that separate host state, including its rendered pixels.
        visible = wait_for(lambda: s if (s := session.status()).get('pet_render', {}).get('visible')
            and s['pet_render'].get('frame_timer') and s['pet_render'].get('render_count', 0) > 0 else None, 10)
        session.command('qa_snapshot', {'name': 'native-pet-startup'})
        pixels = wait_for(lambda: directory/'native-pet-startup-pet.png' if (directory/'native-pet-startup-pet.png').is_file() else None)
        with Image.open(pixels) as rendered:
            alpha = rendered.convert('RGBA').getchannel('A')
            check('grangerpet_visible_and_initialized', visible['pet_render']['width'] > 0
                and visible['pet_render']['height'] > 0 and alpha.getextrema()[1] > 0)
        session.show_workspace()
        titles = {'search': 'Поиск и OSINT-инструменты', 'history': 'История', 'canvas': 'Canvas',
                  'chat': 'Диалог с Гермионой', 'settings': 'Настройки'}
        for route, label in [('search', 'Поиск'), ('history', 'История'), ('canvas', 'Canvas'), ('chat', 'Гермиона'), ('settings', 'Настройки')]:
            session.click(label)
            wait_for(lambda: session.status()['desktop']['route'] == route)
            wait_for(lambda: titles[route] in session.dom().get('headings', []), 15)
            check('native_navigation_' + route, True)
        session.action('canvas_open', {'message_id': model_id})
        wait_for(lambda: (session.snapshot().get('canvas') or {}).get('text') == markdown)
        wait_for(lambda: 'Canvas' in (d := session.dom()).get('headings', []) and 'Ёжик' in d.get('text', ''), 15)
        check('saved_utf8_text_canvas_opened', True)
        session.action('route', {'route': 'search'})
        session.action('tools_refresh')
        tools = wait_for(lambda: s['tools'] if not (s := session.snapshot()).get('toolsChecking') else None, 90)
        check_tool_catalog(tools, check, allow_missing_external_tools=allow_missing_external_tools, report=tool_report)
        session.action('investigation_graph_get', {'id': record['id']})
        wait_for(lambda: (g := session.snapshot().get('investigation_graph', {})).get('state') == 'ready' and g.get('investigation_id') == record['id'])
        session.action('graph_scroll')
        session.click('Граф')
        wait_for(lambda: int(((session.dom().get('graph') or {}).get('canvas') or {}).get('drawnNodes', '0')) > 0)
        check('saved_synthetic_investigation_graph_actually_drawn', True)
        session.click('Моё полотно')
        session.action('research_canvas_open', {'id': document['id']})
        wait_for(lambda: (session.snapshot().get('research_canvas', {}).get('document') or {}).get('id') == document['id'])
        session.action('research_canvas_metrics')
        metrics = wait_for(lambda: session.snapshot().get('research_canvas', {}).get('metrics', {}).get('canvas'))
        check('saved_manual_canvas_actually_drawn', int(metrics.get('drawnNodes', '0')) > 0)
        session.command('qa_desktop', {'action': 'attachment_file', 'payload': {'name': 'fixture.png'}})
        attachment = wait_for(lambda: s['attachments'][-1] if (s := session.snapshot()).get('attachments') else None)
        check('real_image_import_preserves_digest', attachment['sha256'] == image_sha and attachment['width'] == 96 and attachment['height'] == 64)
        old = session.snapshot()['research_canvas']['document']['revision']
        session.action('research_canvas_attach', {'id': document['id'], 'revision': old, 'attachment_id': attachment['id']})
        updated = wait_for(lambda: d if (d := session.snapshot()['research_canvas'].get('document', {})).get('revision', 0) > old else None)
        media = next(row for row in updated['entities'] if row['attributes'].get('attachment_id') == attachment['id'])
        position = updated['view']['positions'][media['id']]
        old = updated['revision']
        session.action('research_canvas_edit', {'id': document['id'], 'revision': old, 'operation': 'view',
            'arguments': {'view': {'viewport': {'x': 250-position['x'], 'y': 180-position['y'], 'scale': 1}}}})
        expected = wait_for(lambda: d if (d := session.snapshot()['research_canvas'].get('document', {})).get('revision', 0) > old else None)
        def visible_media():
            session.action('research_canvas_metrics')
            return int((session.snapshot()['research_canvas'].get('metrics', {}).get('canvas') or {}).get('drawnImages', '0')) > 0
        wait_for(visible_media)
        check('real_media_card_pixels_drawn', True)
        session.action('canvas_media_open', {'canvas_id': document['id'], 'entity_id': media['id']})
        time.sleep(.5)
        session.command('qa_snapshot', {'name': 'original-viewer'})
        wait_for(lambda: list(directory.glob('original-viewer-original-*.png')))
        check('actual_native_original_viewer_opened', True)
        session.action('tool_run', {'tool': 'image_metadata', 'query': attachment['id']})
        def metadata_result():
            state = session.snapshot()
            rows = [row for row in state['search']['results'] if row.get('details', {}).get('tool') == 'image_metadata']
            complete = any(row.get('id') == 'image_metadata' and row.get('status') in ('complete', 'completed') for row in state.get('activity', []))
            return rows[0] if complete and not state['search']['busy'] and rows else None
        result = wait_for(metadata_result, 60)
        # Search uses a deliberate compact presentation without details.image.
        # Fetch the actual full safe source through the existing bridge.
        session.action('source_open', {'evidence_id': result['evidence_id']})
        full = wait_for(lambda: d if (d := session.status()['desktop'].get('last_response', {}).get('result', {})).get('details', {}).get('image', {}).get('sha256') == image_sha else None)
        check('real_local_image_metadata_tool_completed', full['details']['image']['sha256'] == image_sha)
        session.stop()
        check('normal_first_exit_zero', True)
        session.start(1)
        session.action('route', {'route': 'search'})
        session.action('research_canvas_open', {'id': document['id']})
        reopened = wait_for(lambda: (session.snapshot().get('research_canvas', {}).get('document') or None))
        check('restart_preserves_saved_analyst_canvas', reopened['id'] == expected['id'] and reopened['entities'] == expected['entities'] and reopened['view'] == expected['view'])
        session.stop()
        check('normal_restart_exit_zero', True)
        logs = list((profile / 'logs').glob('*.log'))
        check('fresh_runtime_logs_without_python_traceback', bool(logs) and not any('Traceback (most recent call last)' in path.read_text(encoding='utf-8', errors='replace') for path in logs))
    finally:
        if tool_report is not None:tool_report['ipc_observations']={
            'status_timeouts':getattr(session,'status_timeouts',0),
            'max_status_recovery_ms':round(getattr(session,'status_recovery_ms',0),3)}
        session.stop()
    # Keep the Qt application alive until all IPC sockets have been destroyed.
    application.processEvents()


def run(executable: Path, *, allow_missing_external_tools=False):
    executable = executable.resolve(strict=True)
    report = {'schema': 'granger-clean-release-qa/1', 'origin': 'actual-frozen-Windows-Qt-WebEngine',
        'exe_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(), 'exe_bytes': executable.stat().st_size,
        'passed': False, 'checks': [], 'network_calls_requested': 0, 'gateway_calls': 0,
        'investigation_origin': 'new synthetic saved fixture; no user data', 'temporary_data_removed': False,
        'external_tools': {'policy': 'registry-only-for-external-tools' if allow_missing_external_tools else 'strict-local-availability',
            'availability_required': not allow_missing_external_tools, 'availability': {},
            'external_execution_requested': False}}
    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise QaFailure(name)
    temporary = None
    try:
        if sys.platform != 'win32':
            raise QaFailure('native_windows_required')
        with tempfile.TemporaryDirectory(prefix='.granger-qa-', dir=ROOT) as name:
            temporary = Path(name)
            with isolated_environment(temporary):
                smoke = temporary / 'smoke.json'
                with (temporary / 'smoke.log').open('wb') as stream:
                    result = subprocess.run([sys.executable, str(ROOT / 'scripts/smoke_exe.py'), '--exe', str(executable), '--output', str(smoke)],
                        cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                data = json.loads(smoke.read_text(encoding='utf-8')) if smoke.is_file() else {}
                check('fresh_launcher_and_pet_restricted_path_smoke', result.returncode == 0 and data.get('status') == 'passed')
                acceptance(executable, temporary, check, allow_missing_external_tools=allow_missing_external_tools,
                    tool_report=report['external_tools'])
        report['temporary_data_removed'] = not temporary.exists()
        report['passed'] = report['temporary_data_removed'] and all(row['passed'] for row in report['checks'])
    except BaseException as error:
        report['error_type'] = type(error).__name__
        report['failure_code'] = str(error) if isinstance(error, QaFailure) else 'native_acceptance_failed'
        report['temporary_data_removed'] = temporary is None or not temporary.exists()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--allow-missing-external-tools', action='store_true',
        help='Explicit source-only CI scope: require Gansar/Maigret registration, record their actual availability, and do not require absent external runtimes. Local metadata execution and all native UI checks remain required.')
    args = parser.parse_args()
    validate_report_path(args.report)
    result = run(args.exe, allow_missing_external_tools=args.allow_missing_external_tools)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding='utf-8')
    print(payload)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
