"""One reusable, disposable CPU inference child; the Qt process imports no ML."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from . import installation


def default_runtime_root():
    if getattr(sys,'frozen',False):
        base=Path(sys.executable).resolve().parent
        # A developer build can reuse the explicitly installed adjacent workspace
        # runtime. A copied standalone EXE installs under its own runtime/ folder.
        development=base.parent/'.toolenvs/visual-cpu'
        return development if (development/'receipt.json').is_file() else base/'runtime/visual-cpu'
    return Path(__file__).resolve().parents[2]/'.toolenvs/visual-cpu'


class VisualModelManager:
    def __init__(self,runtime_root=None):
        self.root=Path(runtime_root or default_runtime_root()).resolve()
        self._process=None;self._job=None;self._replies=None;self._lock=threading.Lock();self._state='not_installed'
        self._last_error='';self._idle_timer=None;self._probe=None
        self._component=None
        try:
            receipt=json.loads((self.root/'receipt.json').read_text(encoding='utf-8'))
            expected=hashlib.sha256(Path(__file__).with_name('manifest.json').read_bytes()).hexdigest()
            if receipt.get('manifest_sha256')==expected:self._probe=receipt.get('runtime_probe')
        except (OSError,ValueError):pass

    def status(self):
        lock=installation.manifest();receipt=self.root/'receipt.json'
        installed=False
        try:
            r=json.loads(receipt.read_text(encoding='utf-8'))
            installed=r.get('manifest_sha256')==hashlib.sha256(Path(__file__).with_name('manifest.json').read_bytes()).hexdigest() and (self.root/'site-packages/torch').is_dir()
            installed=installed and all((self.root/a['relative_path']).is_file() and (self.root/a['relative_path']).stat().st_size==a['bytes'] for a in lock['artifacts'])
        except (OSError,ValueError,KeyError):pass
        state=self._state if installed and self._state in ('loading','running','ready','error') else 'installed' if installed else 'not_installed'
        verified=installed and isinstance(self._probe,dict) and self._probe.get('status')=='completed'
        if verified and state=='installed':state='ready'
        return {'state':state,'installed':installed,'available':verified,'runtime_verified':verified,'download_bytes':lock['total_download_bytes'],
            'disk_recommended_bytes':8_000_000_000,'ram_recommended_bytes':6_000_000_000,'device':'cpu','cuda_required':False,
            'components':['geoclip','waypoint','waypoint_match'],'error':self._last_error,'probe':self._probe,
            'automatic_download':False,'manifest_id':lock['id']}

    def close(self):
        timer=self._idle_timer
        if timer:timer.cancel();self._idle_timer=None
        job,self._job=self._job,None
        process,self._process=self._process,None
        if job:job.close()
        if process:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
            for pipe in (process.stdin,process.stdout):
                if pipe:pipe.close()
        self._state='installed' if (self.root/'receipt.json').is_file() else 'not_installed'
        self._component=None

    def _start(self):
        if self._process and self._process.poll() is None:return
        self.close();root=Path(__file__).resolve().parents[2]
        command=[sys.executable,'--visual-model-worker'] if getattr(sys,'frozen',False) else [sys.executable,str(root/'main.py'),'--visual-model-worker']
        allowed=('SystemRoot','WINDIR','TEMP','TMP','COMSPEC','NUMBER_OF_PROCESSORS')
        env={key:os.environ[key] for key in allowed if key in os.environ}
        env.update(GRANGERPET_VISUAL_ROOT=str(self.root),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
            DO_NOT_TRACK='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1',
            PATH=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'))
        self._process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,cwd=self.root,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if os.name=='nt':
            from ..engine.runtime import _WindowsJob
            self._job=_WindowsJob(self._process,memory_limit=6_000_000_000)
            if not self._job.handle:self.close();raise RuntimeError('worker_job_unavailable')
        self._replies=queue.Queue(maxsize=2)
        replies=self._replies;process=self._process
        def read():
            try:
                while line:=process.stdout.readline(2_000_001):
                    if len(line)>2_000_000:break
                    try:replies.put_nowait(json.loads(line))
                    except (ValueError,queue.Full):break
            finally:
                try:replies.put_nowait({'status':'error','error_code':'worker_exited'})
                except queue.Full:pass
        threading.Thread(target=read,daemon=True,name='GrangerVisualReply').start()

    def _call(self,payload,cancel_event=None,deadline=None):
        end=deadline if deadline is not None else time.monotonic()+240
        while not self._lock.acquire(timeout=.05):
            if cancel_event and cancel_event.is_set():return {'status':'cancelled','predictions':[]}
            if time.monotonic()>=end:return {'status':'timeout','predictions':[]}
        try:
            if cancel_event and cancel_event.is_set():return {'status':'cancelled','predictions':[]}
            if not self.status()['installed']:return {'status':'not_installed','predictions':[],'error_code':'optional_runtime_not_installed'}
            if self._idle_timer:self._idle_timer.cancel()
            operation=payload.get('operation')
            if operation!='probe' and self._component not in (None,operation):
                # Native allocators can retain freed arenas across frameworks.
                # Restart on component changes to actually return that RAM.
                self.close()
            self._state='loading';self._start()
            if operation!='probe':self._component=operation
            process=self._process;replies=self._replies
            def write_request():
                try:
                    process.stdin.write(json.dumps(payload,separators=(',',':')).encode('utf-8')+b'\n');process.stdin.flush()
                except (OSError,ValueError):
                    try:replies.put_nowait({'status':'error','error_code':'worker_input_failed','predictions':[]})
                    except queue.Full:pass
            # A frozen bootloader may spend seconds extracting before it reads
            # stdin. Keep cancellation responsive while a large image pipe fills.
            threading.Thread(target=write_request,daemon=True,name='GrangerVisualInput').start()
            self._state='running'
            while True:
                if cancel_event and cancel_event.is_set():self.close();return {'status':'cancelled','predictions':[]}
                if time.monotonic()>=end:self.close();return {'status':'timeout','predictions':[]}
                try:result=self._replies.get(timeout=.05);break
                except queue.Empty:continue
            if not isinstance(result,dict):raise ValueError('invalid_worker_result')
            self._state='ready' if result.get('status')=='completed' else 'error';self._last_error=str(result.get('error_code',''))[:80]
            if payload['operation']=='probe':
                self._probe=result
                try:
                    path=self.root/'receipt.json';receipt=json.loads(path.read_text(encoding='utf-8'))
                    receipt['runtime_probe']=result
                    temp=self.root/'receipt.probe.pending.json';temp.write_text(json.dumps(receipt,ensure_ascii=True,indent=2)+'\n',encoding='utf-8');temp.replace(path)
                except (OSError,ValueError):pass
            self._idle_timer=threading.Timer(20,self.close);self._idle_timer.daemon=True;self._idle_timer.start()
            return result
        except (OSError,ValueError,RuntimeError):
            self.close();self._state='error';self._last_error='worker_unavailable'
            return {'status':'error','error_code':'worker_unavailable','predictions':[]}
        finally:self._lock.release()

    def probe(self,**kwargs):return self._call({'operation':'probe'},**kwargs)

    def infer(self,component,image_bytes,*,top_k=5,samples=32,seed=0,cancel_event=None,deadline=None):
        if component not in ('geoclip','waypoint') or type(top_k) is not int or not 1<=top_k<=10 or type(samples) is not int or not 8<=samples<=256 or type(seed) is not int or not 0<=seed<=2**31-1 or not isinstance(image_bytes,bytes) or len(image_bytes)>20*1024*1024:
            raise ValueError('Invalid visual model input')
        return self._call({'operation':component,'image':base64.b64encode(image_bytes).decode('ascii'),'top_k':top_k,'samples':samples,'seed':seed},cancel_event,deadline)

    def match(self,image_bytes,reference_bytes,*,cancel_event=None,deadline=None):
        if any(not isinstance(x,bytes) or not 0<len(x)<=20*1024*1024 for x in (image_bytes,reference_bytes)):raise ValueError('Invalid matching input')
        return self._call({'operation':'waypoint_match','image':base64.b64encode(image_bytes).decode('ascii'),'reference':base64.b64encode(reference_bytes).decode('ascii')},cancel_event,deadline)


_default_manager=None
_default_lock=threading.Lock()


def get_manager():
    global _default_manager
    with _default_lock:
        if _default_manager is None:_default_manager=VisualModelManager()
        return _default_manager
