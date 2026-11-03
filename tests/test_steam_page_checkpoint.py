import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from grangerpet import steam_public


def test_real_child_cancel_keeps_completed_encrypted_page_and_cursor(tmp_path,monkeypatch):
    """Actual process/DPAPI/job cancellation; the source page is a fixture."""
    helper=tmp_path/'checkpoint_child.py';ready=tmp_path/'ready'
    root=Path(__file__).resolve().parents[1]
    helper.write_text("""import json,sys,time
from pathlib import Path
sys.path.insert(0,ROOT)
from grangerpet.credentials import WindowsLegacyStore
from grangerpet.portable_vault import atomic_write
payload=json.load(sys.stdin)
value={'tool':'steam_inventory','status':'partial','results':[{'id':'fixture-inventory','type':'steam_inventory','details':{'coverage':{'next_cursor':'123','observed_assets':1}}}],'limitations':['Fixture source page; not live Steam']}
atomic_write(Path(payload['checkpoint']),WindowsLegacyStore._protect(json.dumps(value).encode()))
Path(READY).write_text('ready')
time.sleep(30)
""".replace('ROOT',repr(str(root))).replace('READY',repr(str(ready))),encoding='utf-8')
    actual=subprocess.Popen
    def launch(argv,**kwargs):
        kwargs['env']={**kwargs['env'],'APPDATA':str(tmp_path/'appdata')}
        return actual([sys.executable,str(helper)],**kwargs)
    monkeypatch.setattr(steam_public.subprocess,'Popen',launch)
    monkeypatch.setattr(steam_public,'_CACHE',{});monkeypatch.setattr(steam_public,'_COOLDOWN',{})
    cancelled=threading.Event()
    def cancel_after_page():
        end=time.monotonic()+12
        while not ready.exists() and time.monotonic()<end:time.sleep(.02)
        cancelled.set()
    watcher=threading.Thread(target=cancel_after_page);watcher.start()
    result=steam_public.execute('steam_inventory',{'profile':'76561198045277210','price_limit':0},cancel_event=cancelled,deadline=time.monotonic()+16)
    watcher.join(timeout=1)
    assert ready.exists()
    assert result['status']=='cancelled' and result['from_page_checkpoint']
    assert result['results'][0]['details']['coverage']['next_cursor']=='123'
    assert 'Fixture source page; not live Steam' in result['limitations']


def test_registry_keeps_valid_inventory_observations_after_cancel_signal(monkeypatch):
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    stopped=threading.Event()
    def execute(*args,**kwargs):
        stopped.set()
        return {'tool':'steam_inventory','status':'cancelled','from_page_checkpoint':True,'results':[
            {'id':'fixture-page','type':'steam_inventory','platform':'Steam','title':'Fixture partial page',
             'url':'https://steamcommunity.com/profiles/76561198045277210/inventory/',
             'details':{'steamid64':'76561198045277210','appid':730,'contextid':'2','coverage':{'next_cursor':'123'}}}],
            'limitations':['Fixture, not live']}
    monkeypatch.setattr(steam_public,'execute',execute)
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    outcome=registry.execute('steam_inventory',{'profile':'76561198045277210'},cancel_event=stopped)
    assert outcome['status']=='cancelled' and len(outcome['results'])==1
    assert registry.evidence.records()[0]['details']['coverage']['next_cursor']=='123'
