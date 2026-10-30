"""Offline diagnostics distinguish packaging, dependencies and account state."""
import sys
import threading
from pathlib import Path

from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings
from grangerpet.engine import readiness, runtime


def test_explicit_wrong_source_path_is_not_silently_replaced_with_another_checkout(tmp_path, monkeypatch):
    wrong = tmp_path / 'wrong';valid=tmp_path/'valid';(valid/'maigret-main').mkdir(parents=True)
    monkeypatch.chdir(valid)
    assert runtime.tool_root({'source_root':str(wrong)}) == wrong
    row=readiness.runtime_readiness('maigret',{'source_root':str(wrong)})
    assert not row['runtime_ready'] and row['state']=='configuration_error'
    assert row['diagnostic']['code']=='missing_sources' and row['diagnostic']['remedy']


def test_frozen_runtime_discovers_sibling_toolenv_instead_of_packaged_executable(tmp_path,monkeypatch):
    root=tmp_path/'workspace';(root/'dist').mkdir(parents=True);(root/'maigret-main').mkdir()
    executable=root/'.toolenvs/maigret/Scripts/python.exe';executable.parent.mkdir(parents=True);executable.write_bytes(b'fixture')
    monkeypatch.setattr(runtime.sys,'executable',str(root/'dist/Granger-OSINT.exe'))
    monkeypatch.setattr(runtime.sys,'frozen',True,raising=False)
    assert runtime.tool_root()==root
    assert runtime.python_runtime('maigret')==executable
    executable.unlink()
    assert runtime.python_runtime('maigret') is None
    assert runtime.runtime_diagnostic('maigret')['code']=='missing_runtime'


def test_missing_dependency_name_and_remedy_survive_registry_catalog(tmp_path,monkeypatch):
    (tmp_path/'maigret-main').mkdir()
    readiness.clear_readiness_cache()
    monkeypatch.setattr(readiness,'run_worker',lambda *args,**kwargs:{'status':'unavailable','error_code':'missing_dependency',
        'missing_module':'aiohttp','message':'Не установлена зависимость (aiohttp).'})
    settings=Settings(source_root=str(tmp_path),runtime_python=sys.executable)
    registry=ToolRegistry(settings,secret_getter=lambda name:'')
    updates=[];catalog=registry.catalog(on_update=updates.append)
    row=next(row for row in catalog if row['source']=='maigret')
    assert row['state']=='missing_dependency' and 'aiohttp' in row['reason']
    assert row['diagnostic']['missing_module']=='aiohttp' and '--groups maigret' in row['diagnostic']['remedy']
    assert not row['available'] and not row['diagnostic']['execution_verified']
    from grangerpet.agent_tools import _SPECS
    assert len(updates)==len(catalog)==len(_SPECS)
    assert {row['name'] for row in updates}=={spec.name for spec in _SPECS}


def test_force_refresh_really_reprobes_and_cancelled_probe_is_not_cached(monkeypatch):
    count=[]
    registry=ToolRegistry(Settings(),secret_getter=lambda name:'',readiness=lambda *args,**kwargs:
        count.append(args[0]) or {'runtime_ready':True,'message':'Imported'})
    registry.catalog();first=len(count);registry.catalog();assert len(count)==first
    registry.catalog(force_refresh=True);assert len(count)==first*2
    event=threading.Event();event.set()
    assert all(row['state']=='cancelled' for row in registry.catalog(cancel_event=event,force_refresh=True))


def test_account_credentials_do_not_manufacture_verified_external_service():
    registry=ToolRegistry(Settings(telegram_api_id='12345'),secret_getter=lambda name:'fixture' if name in
        ('telegram_api_hash','telegram_session','vk_token')else'',readiness=lambda *args,**kwargs:{'runtime_ready':True})
    rows={row['name']:row for row in registry.catalog()}
    # Public preview no longer requires or verifies an account session.
    assert rows['telegram_public']['state']=='ready' and rows['telegram_public']['available']
    assert not rows['telegram_public']['diagnostic']['execution_verified']
    assert rows['vk_public']['available']
    assert not rows['vk_public']['diagnostic']['execution_verified']
