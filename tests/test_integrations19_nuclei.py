"""Fixtures for the restricted optional runner; no real target is contacted."""
import io
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from grangerpet.agent_web import _FetchError
from grangerpet.integrations19 import nuclei


ARGS={'target':'https://example.org/','authorized_scope':'https://example.org/'}


@pytest.mark.parametrize('changes',[
    {'target':'https://example.org/private'}, {'authorized_scope':'https://example.com/'},
    {'target':'http://127.0.0.1/'}, {'target':'https://example.org:8443/'},
    {'target':'https://user:password@example.org/'}, {'template':'not-allowed'},
    {'target':'https://example.org/?q=x'}, {'authorized_scope':'https://example.org.evil.com/'},
])
def test_scope_and_arbitrary_flags_rejected(changes,monkeypatch):
    monkeypatch.setattr(nuclei,'_external_spawn',lambda *a,**kw:pytest.fail('Invalid input spawned a process'))
    result=nuclei.execute({**ARGS,**changes},approved=True,settings=SimpleNamespace(nuclei_enabled=True))
    assert result['status']=='invalid_arguments' and not result['results']


def test_default_disabled_and_separate_scope_approval(monkeypatch):
    monkeypatch.setattr(nuclei,'runtime_path',lambda:Path('fixture/nuclei.exe'))
    assert nuclei.readiness()['state']=='disabled'
    assert nuclei.execute(ARGS,approved=False,settings=SimpleNamespace(nuclei_enabled=True))['status']=='approval_required'
    assert nuclei.execute(ARGS,approved=True)['status']=='unavailable'


def test_private_resolved_address_never_reaches_cli(monkeypatch):
    monkeypatch.setattr(nuclei,'runtime_path',lambda:Path('fixture/nuclei.exe'))
    async def private(*args):return ['127.0.0.1']
    monkeypatch.setattr(nuclei,'resolve_public',private)
    monkeypatch.setattr(nuclei,'_run_target',lambda *a,**kw:pytest.fail('Private DNS reached CLI'))
    result=nuclei.execute(ARGS,approved=True,settings=SimpleNamespace(nuclei_enabled=True))
    assert result['status']=='blocked' and not result['results']


def test_exact_pinned_ip_and_original_host_preserved(monkeypatch):
    monkeypatch.setattr(nuclei,'runtime_path',lambda:Path('fixture/nuclei.exe'))
    async def addresses(*args):return ['93.184.216.34']
    monkeypatch.setattr(nuclei,'resolve_public',addresses)
    seen=[]
    def run(*args,**kwargs):seen.append(args);return {'status':'complete'}
    monkeypatch.setattr(nuclei,'_run_target',run)
    assert nuclei.execute(ARGS,approved=True,settings=SimpleNamespace(nuclei_enabled=True))['status']=='complete'
    assert seen[0][1:] == ('https://example.org/','https://93.184.216.34/','example.org')


def test_environment_does_not_inherit_tokens_proxy_or_user_config(monkeypatch,tmp_path):
    monkeypatch.setenv('GITHUB_TOKEN','fixture-secret');monkeypatch.setenv('HTTPS_PROXY','https://example.org/')
    monkeypatch.setenv('NUCLEI_SIGNATURE_PRIVATE_KEY','fixture-key');monkeypatch.setenv('PDCP_API_KEY','fixture-secret')
    env=nuclei._environment(tmp_path)
    assert not any(k in env for k in ('GITHUB_TOKEN','HTTPS_PROXY','NUCLEI_SIGNATURE_PRIVATE_KEY','PDCP_API_KEY'))
    assert env['APPDATA']==str(tmp_path) and env['HOME']==str(tmp_path)
    assert all(env['DISABLE_NUCLEI_TEMPLATES_'+kind+'_DOWNLOAD']=='true' for kind in ('PUBLIC','GITHUB','GITLAB','AWS','AZURE'))
    command=nuclei._command(Path('fixture.exe'),tmp_path,'https://93.184.216.34/','example.org')
    assert all(flag in command for flag in ('-duc','-ni','-dr','-no-stdin','-omit-raw','-omit-template'))
    assert '-ut' not in command and '-code' not in command and '-headless' not in command
    assert 'HEAD' in (tmp_path/'approved-head.yaml').read_text(encoding='utf-8')


def test_binary_integrity_mismatch_fails_closed(tmp_path):
    binary=tmp_path/'nuclei.exe';binary.write_bytes(b'explicit nonexecutable fixture')
    with pytest.raises(_FetchError,match='integrity_failed'):nuclei._verified(binary)


def fixture_line(name,value,**updates):
    return {'template-id':nuclei.TEMPLATE_ID,'type':'http','matched-at':'https://93.184.216.34/',
            'extractor-name':name,'extracted-results':[value],**updates}


class Process:
    def __init__(self,values):
        self.stdout=io.BytesIO(b''.join(json.dumps(v).encode()+b'\n' for v in values));self.killed=False
    def poll(self):return 0
    def wait(self,timeout):return 0
    def kill(self):self.killed=True


def run_fixture(monkeypatch,values):
    process=Process(values)
    monkeypatch.setattr(nuclei,'_verified',lambda binary:None)
    monkeypatch.setattr(nuclei,'_external_spawn',lambda *a,**kw:process)
    monkeypatch.setattr(nuclei,'_WindowsJob',lambda *a,**kw:SimpleNamespace(handle=None,close=lambda:None))
    return nuclei._run_target(Path('fixture.exe'),'https://example.org/','https://93.184.216.34/','example.org',cancel=threading.Event(),deadline=time.monotonic()+5)


def test_cli_json_only_exports_reviewed_fields(monkeypatch):
    values=[fixture_line('status','200',request='raw fixture secret',response='do not export'),fixture_line('hsts_present','true'),fixture_line('csp_present','false')]
    result=run_fixture(monkeypatch,values)
    assert result['status']=='complete'
    details=result['results'][0]['details']
    assert details['observations']=={'status':200,'hsts_present':True,'csp_present':False}
    assert details['vulnerability_scan'] is False and details['request_budget']==1
    assert 'raw fixture secret' not in json.dumps(result)


@pytest.mark.parametrize('lines',[
    [fixture_line('status','200',**{'template-id':'unexpected-cve-template'})],
    [fixture_line('status','200',**{'matched-at':'http://127.0.0.1/'})],
    [fixture_line('status','200'),fixture_line('status','200')],
    [fixture_line('status','200')],
    [fixture_line('status','200'),fixture_line('hsts_present','false'),fixture_line('csp_present','unsafe')],
])
def test_unexpected_or_partial_cli_json_never_becomes_success(monkeypatch,lines):
    with pytest.raises(_FetchError):run_fixture(monkeypatch,lines)


def test_cancel_before_cli_spawn(monkeypatch):
    event=threading.Event();event.set()
    monkeypatch.setattr(nuclei,'_verified',lambda binary:pytest.fail('Cancelled work must not hash/spawn'))
    with pytest.raises(_FetchError,match='cancelled'):
        nuclei._run_target(Path('fixture.exe'),'https://example.org/','https://93.184.216.34/','example.org',cancel=event,deadline=time.monotonic()+5)
