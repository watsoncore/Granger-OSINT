"""Bounded lifecycle for the application's own offline Qt render worker."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

_SLOTS=threading.BoundedSemaphore(1)


def render_html(html,*,cancel_event=None,deadline=None,ready_selector='',minimum_text=80):
    end=min(deadline or float('inf'),time.monotonic()+15)
    while not _SLOTS.acquire(timeout=.04):
        if cancel_event and cancel_event.is_set():return {'status':'cancelled','html':''}
        if time.monotonic()>=end:return {'status':'render_timeout','html':''}
    process=job=None
    try:
        if cancel_event and cancel_event.is_set():return {'status':'cancelled','html':''}
        if time.monotonic()>=end:return {'status':'render_timeout','html':''}
        payload=json.dumps({'html':html,'seconds':max(1,end-time.monotonic()-1),
            'ready_selector':ready_selector,'minimum_text':minimum_text},ensure_ascii=True).encode('utf-8')
        if len(payload)>2_500_000:return {'status':'render_input_too_large','html':''}
        root=Path(__file__).resolve().parents[1]
        line=[sys.executable,'--public-render-worker'] if getattr(sys,'frozen',False) else [sys.executable,str(root/'main.py'),'--public-render-worker']
        env={k:v for k,v in os.environ.items() if not re.search(r'KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|GRANGERPET_QA',k,re.I)}
        env['QT_QPA_PLATFORM']='offscreen'
        env.pop('QTWEBENGINE_REMOTE_DEBUGGING',None)
        env.pop('QTWEBENGINE_DISABLE_SANDBOX',None)
        # Worker-local switches, never process-global application or OS flags.
        env['QTWEBENGINE_CHROMIUM_FLAGS']='--force-webrtc-ip-handling-policy=disable_non_proxied_udp --disable-background-networking --js-flags=--max-old-space-size=128'
        options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
        process=subprocess.Popen(line,cwd=root,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,**options)
        if os.name=='nt':
            from .engine.runtime import _WindowsJob
            job=_WindowsJob(process,memory_limit=1024*1024*1024)
            if not job.handle:return {'status':'browser_job_unavailable','html':''}
        sent=False
        while True:
            if cancel_event and cancel_event.is_set():return {'status':'cancelled','html':''}
            if time.monotonic()>=end:return {'status':'render_timeout','html':''}
            try:
                output,_=process.communicate(input=None if sent else payload,timeout=.05)
                break
            except subprocess.TimeoutExpired:sent=True
        if process.returncode or len(output)>2_500_000:return {'status':'browser_unavailable','html':''}
        try:result=json.loads(output)
        except (ValueError,UnicodeError):return {'status':'invalid_browser_response','html':''}
        if not isinstance(result,dict) or not isinstance(result.get('html'),str):return {'status':'invalid_browser_response','html':''}
        return result
    except (OSError,ValueError):return {'status':'browser_unavailable','html':''}
    finally:
        if job:job.close()
        if process:
            if process.poll() is None:
                if os.name!='nt':
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                else:process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=3)
            for pipe in (process.stdin,process.stdout):
                if pipe:pipe.close()
        _SLOTS.release()
