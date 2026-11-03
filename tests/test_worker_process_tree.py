"""Real bounded Windows worker trees, entirely owned by this test fixture.

No native app/IPC/network or unrelated process is touched. Cleanup uses retained
handles with verified image/creation time, never a name-based process kill.
"""
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from grangerpet.engine import runtime
from scripts.perf_process_metrics import _WindowsProcesses, _ticks


@pytest.mark.skipif(os.name!='nt',reason='Windows job-object process tree')
@pytest.mark.parametrize('mode,expected',[('normal','complete'),('cancel','cancelled'),('timeout','timeout')])
def test_owned_worker_and_grandchild_exit_after_terminal_state(tmp_path,monkeypatch,mode,expected):
    api=_WindowsProcesses();kernel=api.kernel
    kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.WaitForSingleObject.restype=W.DWORD
    kernel.TerminateProcess.argtypes=[W.HANDLE,W.UINT];kernel.TerminateProcess.restype=W.BOOL
    held=[];spawned=[];cancelled=threading.Event();observed=[]
    (tmp_path/'maigret-main').mkdir()
    ready=tmp_path/'child-ready.json';release=tmp_path/'release.flag'
    child=tmp_path/'child.py'
    child.write_text('import json,os,time\nfrom pathlib import Path\n'+
        f'Path({str(ready)!r}).write_text(json.dumps({{"pid":os.getpid()}}))\ntime.sleep(60)\n',encoding='utf-8')
    worker=tmp_path/'worker.py'
    worker.write_text('import json,os,subprocess,sys,time\nfrom pathlib import Path\n'+
        'request=json.loads(sys.stdin.readline())\n'+
        f'child=subprocess.Popen([sys.executable,{str(child)!r}],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)\n'+
        f'ready=Path({str(ready)!r});release=Path({str(release)!r})\n'+
        'end=time.monotonic()+4\nwhile not ready.exists() and time.monotonic()<end:time.sleep(.005)\n'+
        'value=json.loads(ready.read_text())\n'+
        'print(json.dumps({"event":"stage","worker_pid":os.getpid(),"child_pid":value["pid"]}),flush=True)\n'+
        'end=time.monotonic()+4\nwhile not release.exists() and time.monotonic()<end:time.sleep(.005)\n'+
        ('print(json.dumps({"event":"final","outcome":{"status":"complete","results":[]}}),flush=True)\n'
            if mode=='normal' else 'time.sleep(60)\n'),encoding='utf-8')
    original_spawn=runtime._external_spawn
    def spawn(command,**kwargs):
        process=original_spawn(command,**kwargs);spawned.append(process);return process
    monkeypatch.setattr(runtime,'_external_spawn',spawn)
    monkeypatch.setattr(runtime,'__file__',str(tmp_path/'runtime.py'))
    allowed={str(Path(path).resolve()).casefold() for path in (sys.executable,getattr(sys,'_base_executable',sys.executable),api.counters(os.getpid())['image'],
        Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/conhost.exe')}
    def observe(event):
        if event.get('event')!='stage':return
        ancestry=api.ancestry();owned={spawned[0].pid};changed=True
        # Toolhelp parent PIDs outlive their parent process and can refer to a
        # recycled PID. A browser born before our root is never our descendant.
        root_birth=api.counters(spawned[0].pid)['creation_ticks']
        identities={spawned[0].pid:api.counters(spawned[0].pid)}
        while changed:
            changed=False
            for pid,row in ancestry.items():
                if pid not in owned and row['parent_pid'] in owned:
                    candidate=api.counters(pid);parent=identities.get(row['parent_pid'])
                    if candidate and parent and candidate['creation_ticks']>=parent['creation_ticks']>=root_birth:
                        identities[pid]=candidate;owned.add(pid);changed=True
        assert {event['worker_pid'],event['child_pid']}<=owned
        for pid in owned:
            row=api.counters(pid)
            assert row and row['image'].casefold() in allowed and row['creation_ticks']>=root_birth
            handle=kernel.OpenProcess(0x100000|0x1000|1,False,pid)
            assert handle
            birth,exit,k,u=(W.FILETIME() for _ in range(4))
            assert kernel.GetProcessTimes(handle,ctypes.byref(birth),ctypes.byref(exit),ctypes.byref(k),ctypes.byref(u))
            assert _ticks(birth)==row['creation_ticks']
            held.append((handle,row['creation_ticks']))
        observed.append(event);release.write_text('owned handles retained')
        if mode=='cancel':cancelled.set()
    started=time.monotonic()
    try:
        result=runtime.run_worker('maigret',{'text':'fixture','timeout':2 if mode=='timeout' else 5},
            {'tools_root':str(tmp_path),'runtime_python':sys.executable},cancelled,observe)
        assert observed,'Worker did not establish its owned child tree'
        assert result['status']==expected
        assert time.monotonic()-started<7
        assert len(held)>=2
        assert all(kernel.WaitForSingleObject(handle,1500)==0 for handle,_ in held), 'Owned worker descendant survived terminal state'
        assert all(process.poll() is not None for process in spawned)
    finally:
        # Handles pin the original owned processes even if a PID is recycled.
        for handle,creation in held:
            if kernel.WaitForSingleObject(handle,0)==258:
                birth,exit,k,u=(W.FILETIME() for _ in range(4))
                if kernel.GetProcessTimes(handle,ctypes.byref(birth),ctypes.byref(exit),ctypes.byref(k),ctypes.byref(u)) and _ticks(birth)==creation:
                    kernel.TerminateProcess(handle,1);kernel.WaitForSingleObject(handle,1500)
            kernel.CloseHandle(handle)
        for process in spawned:
            if process.poll() is None:process.kill()
            process.wait(timeout=3)
