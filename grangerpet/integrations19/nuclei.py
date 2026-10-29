"""Optional pinned Nuclei CLI: one approved origin, one harmless HEAD template.

This is a header observation, not a vulnerability scan. Neither caller-supplied
templates/CLI flags nor the user's Nuclei config, credentials or proxy are used.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from ..agent_browser import PageReadError, public_url, resolve_public, public_address
from ..agent_web import _FetchError, _run, _record, _envelope
from ..engine.runtime import _external_spawn, _WindowsJob, _PROCESS_SLOTS

VERSION = '3.11.1'
ZIP_SHA256 = 'bb6cb9ff8939b753f6fcab06fd30a15f5bc61d8382a597871334c007a85ff9d2'
EXE_SHA256 = '73d5e5b0dde9ea5d5fc15dcc34c756148ccae20dc431a21e611af11b8649b480'
RELEASE = 'https://github.com/projectdiscovery/nuclei/releases/download/v'+VERSION+'/'
TEMPLATE_ID = 'granger-approved-head-observation'
INPUT_SCHEMA = {'type':'object','properties':{
    'target':{'type':'string','maxLength':300,'description':'Public http(s) origin only; no path, credentials or parameters.'},
    'authorized_scope':{'type':'string','maxLength':300,'description':'The exact origin for which the user explicitly confirmed testing rights.'}},
    'required':['target','authorized_scope'],'additionalProperties':False}
# Authored for Granger; not imported from the public CVE template collection.
_TEMPLATE = '''id: granger-approved-head-observation
info:
  name: Explicitly approved single HEAD header observation
  author: granger-osint
  severity: info
  description: Observes one HTTP response; does not establish a vulnerability.
  metadata:
    max-request: 1
http:
  - method: HEAD
    path:
      - "{{BaseURL}}/"
    redirects: false
    max-redirects: 0
    matchers:
      - type: dsl
        dsl:
          - 'status_code >= 100 && status_code <= 599'
    extractors:
      - type: dsl
        name: status
        dsl:
          - 'status_code'
      - type: dsl
        name: hsts_present
        dsl:
          - 'contains(tolower(all_headers), "strict-transport-security:")'
      - type: dsl
        name: csp_present
        dsl:
          - 'contains(tolower(all_headers), "content-security-policy:")'
'''


def validate(args):
    if not isinstance(args,dict) or set(args)!=set(INPUT_SCHEMA['required']):raise ValueError('Exact scope required')
    normalized=[]
    for key in ('target','authorized_scope'):
        value=args[key]
        if not isinstance(value,str) or len(value)>300:raise ValueError('Invalid scope')
        value=public_url(value);p=urlsplit(value)
        if p.path!='/' or p.query:raise ValueError('Only origin allowed')
        normalized.append(value)
    if normalized[0]!=normalized[1]:raise ValueError('Target outside approved scope')
    return {'target':normalized[0],'authorized_scope':normalized[1]}


def runtime_path():
    roots=[Path(sys.executable).parent,Path(__file__).resolve().parents[2]]
    for root in roots:
        for folder in (root/'tools'/'nuclei'/VERSION,root/'.toolenvs'/'nuclei'/VERSION):
            candidate=folder/'nuclei.exe'
            if candidate.is_file():return candidate.resolve()
    return None


def readiness(settings=None):
    if getattr(settings,'nuclei_enabled',False) is not True:
        return {'available':False,'state':'disabled','reason':'Nuclei отключён по умолчанию; требуется явное включение и подтверждение права на конкретную цель.'}
    binary=runtime_path()
    if binary is None:return {'available':False,'state':'unavailable','reason':'Не установлен optional Nuclei '+VERSION+'; используйте scripts/setup_nuclei.py.'}
    return {'available':True,'state':'ready_local','reason':'Optional CLI присутствует. Перед каждым запуском проверяются pinned SHA256, точный scope и отдельное подтверждение.'}


def _verified(binary):
    with binary.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    if digest!=EXE_SHA256:raise _FetchError('nuclei_integrity_failed',status='blocked')


def _check(cancel,deadline):
    if cancel is not None and cancel.is_set():raise _FetchError('cancelled',status='cancelled')
    if time.monotonic()>=deadline:raise _FetchError('timeout',status='timeout')


def _environment(folder):
    # Do not inherit tokens, proxy variables, custom repositories or PDCP config.
    env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','COMSPEC','PATHEXT')}
    env.update({k:str(folder) for k in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME')})
    env['PATH']=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32')
    for kind in ('PUBLIC','GITHUB','GITLAB','AWS','AZURE'):env['DISABLE_NUCLEI_TEMPLATES_'+kind+'_DOWNLOAD']='true'
    return env


def _command(binary,folder,pinned,hostname):
    template=folder/'approved-head.yaml';template.write_text(_TEMPLATE,encoding='utf-8')
    config=folder/'isolated.yaml';config.write_text('{}\n',encoding='utf-8')
    return [str(binary),'-u',pinned,'-t',str(template),'-config',str(config),'-duc','-ni','-dr','-no-stdin',
        '-jsonl','-omit-raw','-omit-template','-silent','-nc','-pt','http','-c','1','-bs','1','-rl','1',
        '-retries','0','-timeout','4','-mp','0','-H','Host: '+hostname,
        '-H','User-Agent: Granger-OSINT/3.1 approved-header-observation','-sni',hostname]


def _run_target(binary,target,pinned,hostname,*,cancel,deadline):
    """Internal worker. Production callers must use execute's pinned DNS/scope gate."""
    _check(cancel,deadline);_verified(binary)
    while not _PROCESS_SLOTS.acquire(timeout=.03):_check(cancel,deadline)
    process=None;job=None
    try:
        with tempfile.TemporaryDirectory(prefix='granger-nuclei-') as temp:
            folder=Path(temp);command=_command(binary,folder,pinned,hostname)
            _check(cancel,deadline)
            process=_external_spawn(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                env=_environment(folder),cwd=str(folder),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=os.name!='nt')
            try:job=_WindowsJob(process,memory_limit=768*1024*1024)
            except Exception:
                process.kill();process.wait(timeout=2);process.stdout.close()
                raise _FetchError('nuclei_job_initialization_failed') from None
            output=queue.Queue(maxsize=8)
            def reader():
                total=0
                try:
                    while True:
                        line=process.stdout.readline(131073)
                        if not line:break
                        total+=len(line)
                        if len(line)>131072 or total>262144:
                            output.put_nowait({'_error':'nuclei_output_limit'});break
                        try:value=json.loads(line)
                        except (ValueError,UnicodeError):
                            if line.strip():output.put_nowait({'_error':'invalid_nuclei_json'})
                            continue
                        if isinstance(value,dict):output.put_nowait(value)
                except (OSError,ValueError,queue.Full):pass
                finally:
                    try:output.put_nowait(None)
                    except queue.Full:pass
            thread=threading.Thread(target=reader,daemon=True,name='GrangerNucleiReader');thread.start()
            items={}
            try:
                while True:
                    _check(cancel,deadline)
                    try:item=output.get(timeout=.05)
                    except queue.Empty:
                        if process.poll() is not None and not thread.is_alive():break
                        continue
                    if item is None:break
                    if item.get('_error'):raise _FetchError(item['_error'])
                    if item.get('template-id')!=TEMPLATE_ID or item.get('type')!='http' or item.get('matched-at')!=pinned:raise _FetchError('unexpected_nuclei_template',status='blocked')
                    values=item.get('extracted-results')
                    name=item.get('extractor-name')
                    if name not in ('status','hsts_present','csp_present') or name in items or not isinstance(values,list) or len(values)!=1 or not isinstance(values[0],str):raise _FetchError('invalid_nuclei_json')
                    if name=='status':
                        if not values[0].isdigit() or not 100<=int(values[0])<=599:raise _FetchError('invalid_nuclei_json')
                        items[name]=int(values[0])
                    else:
                        if values[0] not in ('true','false'):raise _FetchError('invalid_nuclei_json')
                        items[name]=values[0]=='true'
                try:code=process.wait(timeout=max(.01,min(1,deadline-time.monotonic())))
                except subprocess.TimeoutExpired:raise _FetchError('nuclei_shutdown_timeout',status='timeout') from None
                if code:raise _FetchError('nuclei_exit_'+str(code))
                if set(items)!=set(('status','hsts_present','csp_present')):raise _FetchError('nuclei_no_observation')
                details={'target':target,'authorized_scope':target,'cli_version':VERSION,'template_id':TEMPLATE_ID,
                    'observations':items,'method':'HEAD','request_budget':1,'redirects_followed':False,
                    'vulnerability_scan':False,'execution_mode':'LOCAL_CLI','capability':'nuclei_check','source_record':True,
                    'verification':'Один HTTP HEAD-ответ в явно подтверждённом scope. Отсутствие заголовка не устанавливает уязвимость; CVE-проверки не выполнялись.'}
                row=_record('nuclei_check',target,'Подтверждённое наблюдение HTTP-заголовков',target,details['verification'],kind='http_observation',details=details)
                return _envelope('nuclei_check',target,status='complete',results=[row],limitations=[details['verification']])
            finally:
                if process.poll() is None:
                    if job and job.handle:job.close()
                    else:process.kill()
                process.wait(timeout=2);process.stdout.close();thread.join(timeout=.5)
    except (OSError,subprocess.SubprocessError):raise _FetchError('nuclei_process_failed') from None
    finally:
        if job:job.close()
        _PROCESS_SLOTS.release()


def execute(args,*,cancel_event=None,deadline=None,approved=False,settings=None):
    try:values=validate(args)
    except (TypeError,ValueError,PageReadError):return _envelope('nuclei_check','',status='invalid_arguments',error_code='invalid_scope')
    if approved is not True:return _envelope('nuclei_check',values['target'],status='approval_required',error_code='explicit_scope_confirmation_required')
    if not readiness(settings)['available']:return _envelope('nuclei_check',values['target'],status='unavailable',error_code='nuclei_disabled_or_missing')
    end=min(deadline,time.monotonic()+20) if deadline is not None else time.monotonic()+20
    try:
        _check(cancel_event,end);p=urlsplit(values['target']);port=443 if p.scheme=='https' else 80
        async def resolve():return await resolve_public(p.hostname,port)
        addresses=_run(resolve,cancel_event=cancel_event,deadline=end,timeout=4)
        if not addresses or any(not public_address(v) for v in addresses):raise _FetchError('private_or_service_address',status='blocked')
        address=addresses[0];authority='['+address+']' if ':' in address else address
        pinned=p.scheme+'://'+authority+'/'
        return _run_target(runtime_path(),values['target'],pinned,p.hostname,cancel=cancel_event,deadline=end)
    except PageReadError as exc:return _envelope('nuclei_check',values['target'],status=exc.status,error_code=exc.code)
    except _FetchError as exc:return _envelope('nuclei_check',values['target'],status=exc.status,error_code=exc.code)
