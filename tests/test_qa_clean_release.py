"""Lifecycle safety of the native QA entrypoint; these are not native claims."""
from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from scripts import qa_clean_release as qa


def test_isolation_restores_environment_and_removes_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', 'original-profile')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only-no-key')
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    with qa.isolated_environment(tmp_path):
        assert Path(qa.os.environ['APPDATA']) == tmp_path/'appdata'
        assert 'DEEPSEEK_API_KEY' not in qa.os.environ
        assert 'QT_QPA_PLATFORM' not in qa.os.environ
        assert len(qa.os.environ['GRANGERPET_QA_NAMESPACE']) == 32
        assert qa.os.environ['GRANGERPET_QA_VAULT'].startswith('GrangerPet/QA/clean_')
    assert qa.os.environ['APPDATA'] == 'original-profile'
    assert qa.os.environ['DEEPSEEK_API_KEY'] == 'test-only-no-key'
    assert qa.os.environ['QT_QPA_PLATFORM'] == 'offscreen'


def test_isolation_restores_environment_on_interrupt(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', 'original-profile')
    with pytest.raises(KeyboardInterrupt):
        with qa.isolated_environment(tmp_path):
            raise KeyboardInterrupt()
    assert qa.os.environ['APPDATA'] == 'original-profile'


def test_report_cannot_be_left_in_dist(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='outside dist'):
        qa.validate_report_path(tmp_path/'dist'/'nested'/'report.json')
    qa.validate_report_path(tmp_path/'small-report.json')
    qa.validate_report_path(None)


@pytest.mark.parametrize('pid,path,owned,code', [
    (99, 'unrelated.exe', None, 'ipc_process_image_mismatch'),
    (100, 'expected.exe', 99, 'ipc_owned_pid_changed'),
    (None, 'expected.exe', None, 'ipc_process_image_mismatch'),
])
def test_ipc_rejects_unowned_process_without_sending_an_action(tmp_path, monkeypatch, pid, path, owned, code):
    import grangerpet.ipc
    calls=[]
    def send(role, command, **kwargs):
        calls.append(command)
        return {'ok': True, 'pid': pid}
    monkeypatch.setattr(grangerpet.ipc, 'send_command', send)
    monkeypatch.setattr(qa, 'process_image', lambda _pid:(tmp_path/path).resolve())
    session=qa.NativeSession(tmp_path/'expected.exe',tmp_path)
    session.process=SimpleNamespace(poll=lambda:None)
    session.owned_pid=owned
    with pytest.raises(qa.QaFailure, match=code):
        session.command('stop')
    assert calls == ['status']


def mock_smoke(monkeypatch):
    def execute(argv, **kwargs):
        destination=Path(argv[argv.index('--output')+1])
        destination.write_text(json.dumps({'status':'passed'}),encoding='utf-8')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(qa.subprocess,'run',execute)


@pytest.mark.parametrize('failure',[None,qa.QaFailure('controlled_failure'),KeyboardInterrupt()])
def test_owned_temp_profiles_removed_on_success_failure_and_interrupt(tmp_path,monkeypatch,failure):
    monkeypatch.setattr(qa,'ROOT',tmp_path)
    monkeypatch.setattr(qa.sys,'platform','win32')
    mock_smoke(monkeypatch)
    executable=tmp_path/'candidate.exe';executable.write_bytes(b'MZ-fixture')
    owned=[]
    def acceptance(exe,directory,check,**policy):
        owned.append(directory)
        (directory/'appdata').mkdir()
        (directory/'appdata'/'test-profile.dpapi').write_bytes(b'fixture-only')
        if failure is not None:raise failure
        check('mocked_lifecycle_only',True)
    monkeypatch.setattr(qa,'acceptance',acceptance)
    result=qa.run(executable)
    assert result['passed'] == (failure is None)
    assert result['temporary_data_removed'] is True
    assert not owned[0].exists()
    assert not list(tmp_path.glob('.granger-qa-*'))
    assert str(tmp_path) not in json.dumps(result)
    assert result['network_calls_requested']==0 and result['gateway_calls']==0


def test_failed_smoke_does_not_enter_native_acceptance_and_cleans_temp(tmp_path,monkeypatch):
    monkeypatch.setattr(qa,'ROOT',tmp_path)
    monkeypatch.setattr(qa.sys,'platform','win32')
    executable=tmp_path/'candidate.exe';executable.write_bytes(b'MZ-fixture')
    monkeypatch.setattr(qa.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=1))
    monkeypatch.setattr(qa,'acceptance',lambda *args:pytest.fail('Should not run after failed smoke'))
    result=qa.run(executable)
    assert result['passed'] is False and result['temporary_data_removed'] is True
    assert result['failure_code']=='fresh_launcher_and_pet_restricted_path_smoke'
    assert not list(tmp_path.glob('.granger-qa-*'))


def test_shutdown_after_ipc_mismatch_targets_only_spawned_binary_tree(tmp_path,monkeypatch):
    import scripts.smoke_exe
    calls=[]
    session=qa.NativeSession(tmp_path/'expected.exe',tmp_path)
    session.process=SimpleNamespace(pid=40,poll=lambda:None,wait=lambda timeout:calls.append(('wait',timeout)))
    monkeypatch.setattr(session,'command',lambda *args:(_ for _ in ()).throw(qa.QaFailure('ipc_process_image_mismatch')))
    monkeypatch.setattr(scripts.smoke_exe,'_terminate_spawned_binary_tree',lambda path,pid:calls.append((path,pid)))
    with pytest.raises(qa.QaFailure,match='ipc_process_image_mismatch'):
        session.stop()
    assert calls == [(session.executable,40),('wait',10)]


@pytest.mark.parametrize('workspace', [False, True])
def test_start_can_check_desktop_pet_before_showing_its_host(tmp_path, monkeypatch, workspace):
    session=qa.NativeSession(tmp_path/'expected.exe',tmp_path)
    calls=[]
    monkeypatch.setattr(qa.subprocess,'Popen',lambda *args,**kwargs:SimpleNamespace(poll=lambda:None))
    monkeypatch.setattr(session,'status',lambda:{'pid':55,'desktop':{'ready':True}})
    monkeypatch.setattr(session,'command',lambda name,payload:calls.append((name,payload)))
    monkeypatch.setattr(session,'action',lambda name,payload:calls.append((name,payload)))
    session.start(0,workspace=workspace)
    assert session.owned_pid==55
    assert calls==([('show_workspace',{'route':'chat'}),('window',{'mode':'maximize'})] if workspace else [])


def tool_check_recorder():
    checks=[]
    def check(name,condition):
        checks.append((name,bool(condition)))
        if not condition:raise qa.QaFailure(name)
    return checks,check


@pytest.mark.parametrize('allow_missing',[False,True])
def test_external_tool_policy_records_real_absence_without_fake_availability_pass(allow_missing):
    tools=[{'id':'blockchain_gansar','available':False},{'id':'username_maigret','available':True},
           {'id':'image_metadata','available':True}]
    checks,check=tool_check_recorder();report={}
    if allow_missing:
        qa.check_tool_catalog(tools,check,allow_missing_external_tools=True,report=report)
        assert checks==[('gansar_maigret_and_image_tool_registered',True)]
    else:
        with pytest.raises(qa.QaFailure,match='gansar_and_maigret_locally_available'):
            qa.check_tool_catalog(tools,check,report=report)
        assert checks[-1]==('gansar_and_maigret_locally_available',False)
    assert report['availability']=={'blockchain_gansar':False,'username_maigret':True}
    assert report['missing_external_tools']==['blockchain_gansar']
    assert report['availability_required'] is not allow_missing
    assert report['external_execution_requested'] is False


def test_explicit_ci_policy_still_requires_all_registry_ids():
    checks,check=tool_check_recorder()
    with pytest.raises(qa.QaFailure,match='gansar_maigret_and_image_tool_registered'):
        qa.check_tool_catalog([{'id':'image_metadata','available':True}],check,allow_missing_external_tools=True)
    assert checks==[('gansar_maigret_and_image_tool_registered',False)]


def test_default_tool_policy_remains_strict_with_original_availability_check():
    checks,check=tool_check_recorder();report={}
    qa.check_tool_catalog([{'id':name,'available':True} for name in
        ('blockchain_gansar','username_maigret','image_metadata')],check,report=report)
    assert checks==[('gansar_maigret_and_image_tool_registered',True),('gansar_and_maigret_locally_available',True)]
    assert report['policy']=='strict-local-availability' and report['missing_external_tools']==[]


def test_explicit_ci_policy_propagates_to_native_scope_and_summary(tmp_path,monkeypatch):
    monkeypatch.setattr(qa,'ROOT',tmp_path);monkeypatch.setattr(qa.sys,'platform','win32')
    mock_smoke(monkeypatch)
    executable=tmp_path/'candidate.exe';executable.write_bytes(b'MZ-fixture')
    def acceptance(exe,directory,check,*,allow_missing_external_tools,tool_report):
        assert allow_missing_external_tools is True
        qa.check_tool_catalog([{'id':name,'available':name=='image_metadata'} for name in
            ('blockchain_gansar','username_maigret','image_metadata')],check,
            allow_missing_external_tools=allow_missing_external_tools,report=tool_report)
    monkeypatch.setattr(qa,'acceptance',acceptance)
    result=qa.run(executable,allow_missing_external_tools=True)
    assert result['passed'] and result['temporary_data_removed']
    assert result['external_tools']['availability']=={'blockchain_gansar':False,'username_maigret':False}
    assert not any(row['name']=='gansar_and_maigret_locally_available' for row in result['checks'])
