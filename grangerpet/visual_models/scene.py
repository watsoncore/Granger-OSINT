"""Optional local scene understanding; ML imports live only in a child process."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from .manager import default_runtime_root

_LOCK = threading.Lock()


def manifest():
    return json.loads(Path(__file__).with_name('scene_manifest.json').read_text(encoding='utf-8'))


def model_root():
    return default_runtime_root().parent/'scene-vision'


def readiness():
    root = model_root()
    lock = manifest()
    try:
        receipt = json.loads((root/'receipt.json').read_text(encoding='utf-8'))
        installed = receipt.get('manifest_sha256') == hashlib.sha256(Path(__file__).with_name('scene_manifest.json').read_bytes()).hexdigest()
        installed = installed and all((root/'model'/row['relative_path']).is_file()
            and (root/'model'/row['relative_path']).stat().st_size == row['bytes'] for row in lock['artifacts'])
    except (OSError, ValueError):
        installed = False
    dependencies = (default_runtime_root()/'site-packages/transformers/models/florence2').is_dir()
    available = bool(installed and dependencies)
    return {'available':available, 'state':'ready_local' if available else 'not_installed',
        'reason':'Локальный Florence-2-base-ft: описание пикселей и областей; изображения не покидают компьютер.' if available
            else 'Нужны отдельные MIT-веса Florence-2-base-ft (~469 МБ) и optional visual CPU runtime.',
        'model':lock['model'], 'revision':lock['revision'], 'download_bytes':lock['download_bytes'],
        'device':'cpu', 'automatic_download':False}


def understand(image, *, cancel_event=None, deadline=None):
    if not isinstance(image, bytes) or not 0 < len(image) <= 20*1024*1024:
        return {'status':'error', 'error_code':'invalid_image'}
    if not readiness()['available']:
        return {'status':'unavailable', 'error_code':'scene_runtime_not_installed'}
    end = min(deadline, time.monotonic()+180) if deadline else time.monotonic()+180
    while not _LOCK.acquire(timeout=.05):
        if cancel_event and cancel_event.is_set():
            return {'status':'cancelled', 'error_code':'cancelled'}
        if time.monotonic() >= end:
            return {'status':'timeout', 'error_code':'timeout'}
    process, job = None, None
    try:
        if cancel_event and cancel_event.is_set():
            return {'status':'cancelled', 'error_code':'cancelled'}
        root = Path(__file__).resolve().parents[2]
        command = [sys.executable, '--scene-vision-worker'] if getattr(sys, 'frozen', False) else [sys.executable, str(root/'main.py'), '--scene-vision-worker']
        env = {key:os.environ[key] for key in ('SystemRoot','WINDIR','TEMP','TMP','COMSPEC','NUMBER_OF_PROCESSORS') if key in os.environ}
        env.update(GRANGERPET_VISUAL_ROOT=str(default_runtime_root()), GRANGERPET_SCENE_ROOT=str(model_root()),
            HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1',
            PATH=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'))
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=model_root(), env=env, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if os.name == 'nt':
            from ..engine.runtime import _WindowsJob
            job = _WindowsJob(process, memory_limit=5_000_000_000)
            if not job.handle:
                return {'status':'error','error_code':'worker_job_unavailable'}
        payload = json.dumps({'image':base64.b64encode(image).decode('ascii')}).encode('ascii')+b'\n'
        first = True
        while True:
            if cancel_event and cancel_event.is_set():
                return {'status':'cancelled','error_code':'cancelled'}
            if time.monotonic() >= end:
                return {'status':'timeout','error_code':'timeout'}
            try:
                output, _ = process.communicate(payload if first else None, timeout=.05)
                if len(output) > 1_000_000:
                    return {'status':'error','error_code':'scene_output_limit'}
                value = json.loads(output.decode('utf-8'))
                if not isinstance(value, dict):
                    raise ValueError()
                from ..geoint.scene_language import russian_scene
                return russian_scene(value)
            except subprocess.TimeoutExpired:
                first = False
            except (ValueError, UnicodeError):
                return {'status':'error','error_code':'scene_worker_failed'}
    finally:
        if job:
            job.close()
        if process:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
        _LOCK.release()


def execute(args, *, store, cancel_event=None, deadline=None):
    from ..geoint import GeointError
    try:
        result = understand(store.read_bytes(args['attachment_id'], cancel_event), cancel_event=cancel_event, deadline=deadline)
    except GeointError as error:
        return {'status':'cancelled' if error.code == 'cancelled' else 'error', 'error_code':error.code, 'results':[]}
    if result.get('status') != 'completed':
        return {**result, 'results':[], 'limitations':['Семантическое описание пикселей не получено; содержимое сцены не угадано.']}
    from ..geoint.scene_language import russian_scene
    result=russian_scene(result)
    from .observations import signature, parameters
    details = {**result, 'local_inference_signature':signature('image_understand',args),
        'inference_parameters':parameters('image_understand',args), 'tool':'image_understand', 'capability':'image_understand', 'attachment_id':args['attachment_id'],
        'source_record':True, 'acquisition':'local_model', 'execution_mode':'LOCAL_MODEL'}
    return {'status':'complete', 'results':[{'id':'image_understand:'+details['local_inference_signature'], 'type':'image_analysis',
        'platform':'Florence-2-base-ft', 'title':'Видимая сцена и области изображения', 'url':'',
        'description':result['description'], 'status':'hypothesis', 'details':details, 'sources':['image_understand']}],
        'limitations':result['limitations']}
