"""Bounded hidden subprocess transport. Credentials only travel over stdin."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time

VENDOR_DIRS = {"maigret": "maigret-main", "blackbird": "blackbird-main", "snoop": "snoop-master",
               "holehe": "holehe-master", "phoneinfoga": "phoneinfoga-master", "social_analyzer": "social-analyzer-main",
               "telegram": "Telethon-1", "vk": "vk_api-master", "instagram": "instaloader-master",
               "wayback": "waybackpy-master", "blockchain": "Gansar-main"}
GROUPS = {"telegram": "platforms", "vk": "platforms", "instagram": "platforms", "wayback": "platforms"}
_SPAWN_LOCK = threading.Lock()
_PROCESS_SLOTS = threading.BoundedSemaphore(2)


def _external_spawn(command, **kwargs):
    # PyInstaller sets a process-global DLL search directory. External Python
    # must resolve its own version's DLLs, not those of the packaged Qt runtime.
    with _SPAWN_LOCK:
        kernel = None
        frozen_path = getattr(sys, "_MEIPASS", None)
        if os.name == "nt" and frozen_path:
            import ctypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
            kernel.SetDllDirectoryW.restype = ctypes.c_int
            kernel.SetDllDirectoryW(None)
        try:
            return subprocess.Popen(command, **kwargs)
        finally:
            if kernel:
                kernel.SetDllDirectoryW(str(frozen_path))


def tool_root(options=None):
    options = options or {}
    supplied = options.get("source_root") or options.get("tools_root")
    # An explicit path is authoritative: silently falling back to another
    # checkout masks bad settings and can run the wrong vendor version.
    if supplied:
        return Path(supplied).expanduser().resolve()
    candidates = []
    candidates.extend([Path(sys.executable).parent, Path(sys.executable).parent.parent,
                       Path(__file__).resolve().parents[2], Path.cwd()])
    for candidate in candidates:
        if any((candidate / folder).is_dir() for folder in VENDOR_DIRS.values()):
            return candidate.resolve()
    return candidates[0].resolve()


def runtime_diagnostic(source, options=None):
    """Local filesystem facts only; no import, account or network request."""
    options = options or {}
    root = tool_root(options)
    source_path = root / VENDOR_DIRS.get(source, '')
    python = python_runtime(source, options) if source in VENDOR_DIRS and source != 'phoneinfoga' else None
    bridge = Path(options.get('phoneinfoga_bridge') or root / '.toolenvs/phoneinfoga/phoneinfoga-bridge.exe')
    worker = Path(__file__).resolve().with_name('worker.py')
    code, remedy = 'probe_required', 'Запустите безопасную проверку готовности.'
    if source not in VENDOR_DIRS:
        code, remedy = 'unknown_source', 'Выберите зарегистрированный источник.'
    elif not source_path.is_dir():
        code, remedy = 'missing_sources', 'Укажите папку, содержащую локальные исходники этого инструмента.'
    elif source == 'phoneinfoga' and not bridge.is_file():
        code, remedy = 'missing_bridge', 'Соберите PhoneInfoga bridge через scripts/setup_sources.py с установленным Go.'
    elif source != 'phoneinfoga' and python is None:
        code = 'invalid_interpreter' if options.get('runtime_python') else 'missing_runtime'
        remedy = 'Исправьте путь к Python или подготовьте изолированное окружение scripts/setup_sources.py.'
    elif source != 'phoneinfoga' and not worker.is_file():
        code, remedy = 'missing_worker', 'Восстановите комплект приложения: отсутствует engine/worker.py.'
    return {'code': code, 'remedy': remedy, 'source_root': str(root), 'source_path': str(source_path),
            'runtime_path': str(bridge if source == 'phoneinfoga' else python or ''),
            'worker_path': str(worker), 'frozen': bool(getattr(sys, 'frozen', False)),
            'source_present': source_path.is_dir()}


def python_runtime(source, options=None):
    options = options or {}
    root = tool_root(options)
    configured = options.get("runtime_python")
    if configured:
        candidate = Path(configured).expanduser()
        return candidate.resolve() if candidate.is_file() else None
    group = GROUPS.get(source, source)
    for candidate in (root / ".toolenvs" / group / "Scripts/python.exe", root / ".toolenvs" / group / "bin/python",
                      root / ".toolenv/Scripts/python.exe", root / ".toolenv/bin/python",
                      root / VENDOR_DIRS.get(source, "") / ".venv/Scripts/python.exe"):
        if candidate.is_file():
            return candidate.resolve()
    if not getattr(sys, "frozen", False):
        return Path(sys.executable)
    return None


class _WindowsJob:
    def __init__(self, process, *, memory_limit=None):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes
        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(field, ctypes.c_uint64) for field in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateJobObjectW(None, None)
        limits = EXTENDED()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE, includes descendants.
        if memory_limit is not None:
            if type(memory_limit) is not int or not 64*1024*1024<=memory_limit<=8*1024*1024*1024:
                if handle:kernel.CloseHandle(handle)
                raise ValueError('Invalid own worker memory budget')
            limits.BasicLimitInformation.LimitFlags |= 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY.
            limits.JobMemoryLimit=memory_limit
        if handle and kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) and kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(process._handle)):
            self.handle, self.kernel = handle, kernel
        elif handle:
            kernel.CloseHandle(handle)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def run_worker(source, query, options, cancelled, event=None):
    # Readiness probes share the same global child-process budget as searches.
    # A cold cancelled/replaced query cannot leave an uncancellable import probe
    # running or start more processes on every press of Enter.
    while not cancelled.is_set():
        if _PROCESS_SLOTS.acquire(timeout=.05):
            try:
                if cancelled.is_set():
                    break
                return _run_worker(source, query, options, cancelled, event)
            finally:
                _PROCESS_SLOTS.release()
    return {"source": source, "status": "cancelled", "results": [], "message": "Поиск отменён."}


def _run_worker(source, query, options, cancelled, event=None):
    root = tool_root(options)
    if source not in VENDOR_DIRS or not (root / VENDOR_DIRS[source]).is_dir():
        return {"source": source, "status": "unavailable", "results": [], "message": "Локальные исходники источника не найдены. Укажите папку подключений."}
    if source == "phoneinfoga":
        bridge = Path(options.get("phoneinfoga_bridge") or root / ".toolenvs/phoneinfoga/phoneinfoga-bridge.exe")
        if not bridge.is_file():
            return {"source": source, "status": "unavailable", "results": [], "message": "Нужно собрать локальный PhoneInfoga bridge с Go через scripts/setup_sources.py."}
        command = [str(bridge.resolve())]
        if options.get("operation") == "probe":
            # Exercise the real local number parser with a reserved example.
            query = {"text": "+12025550123", "kind": "phone", "timeout": 5}
    else:
        python = python_runtime(source, options)
        if python is None:
            return {"source": source, "status": "unavailable", "results": [], "message": "Нужно установить изолированное окружение источника через scripts/setup_sources.py."}
        worker = Path(__file__).resolve().with_name("worker.py")
        if not worker.is_file():
            return {"source": source, "status": "unavailable", "results": [], "message": "Не найден мост локальных источников; проверьте комплект поставки."}
        command = [str(python), "-X", "utf8", "-I", str(worker)]
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1",'PYTHONDONTWRITEBYTECODE':'1'})
    if source=='blockchain':
        for key in tuple(environment):
            if key.startswith(('GANSAR_','TONAPI_','TON_API_','TONCENTER_','TONCONSOLE_','ETHEREUM_','ETHERSCAN_','WEB3_')):
                environment.pop(key,None)
        environment.update(GANSAR_TRUST_ENV='0',GANSAR_VERIFY_TLS='1')
    # No inherited source search paths; legacy dependency resolution is isolated.
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    for key in tuple(environment):
        if key.startswith(("_PYI_", "PYINSTALLER_")):
            environment.pop(key, None)
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        environment["PATH"] = os.pathsep.join(value for value in environment.get("PATH", "").split(os.pathsep)
            if value and not Path(value).resolve().is_relative_to(Path(frozen_root).resolve()))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = _external_spawn(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=environment, cwd=str(root),
                               creationflags=flags, start_new_session=os.name != "nt")
    job = _WindowsJob(process)
    lines = queue.Queue()
    def read_output():
        try:
            total = 0
            for line in iter(lambda: process.stdout.readline(16_000_001 if source in ('blockchain','maigret') else 1_000_001), b""):
                total += len(line)
                if len(line) > (16_000_000 if source in ('blockchain','maigret') else 1_000_000) or total > (128_000_000 if source=='maigret' else 64_000_000 if source=='blockchain' else 4_000_000):
                    lines.put({"event": "transport_error"})
                    return
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        lines.put(item)
                except (ValueError, UnicodeError):
                    # The larger Maigret frame allowance is for structured
                    # findings/final diagnostics, never oversized vendor noise.
                    if source=='maigret' and len(line)>1_000_000:
                        lines.put({"event":"transport_error"})
                        return
                    continue
        finally:
            lines.put(None)
    reader = threading.Thread(target=read_output, daemon=True, name="GrangerPetSourceReader")
    reader.start()
    stderr_count = [0]
    def drain_stderr():
        # Drain to prevent a full pipe blocking a tool. Never return raw stderr:
        # vendor diagnostics can contain the query or credentials. Only a bounded
        # byte count accompanies the exit code for technical diagnosis.
        try:
            for chunk in iter(lambda: process.stderr.read(4096), b""):
                stderr_count[0] = min(1_000_000, stderr_count[0] + len(chunk))
        except (OSError, ValueError):
            pass
    stderr_reader = threading.Thread(target=drain_stderr, daemon=True, name="GrangerPetSourceStderr")
    stderr_reader.start()
    deadline = time.monotonic() + float(query.get("timeout", 25))
    outcome = None
    partial = []
    partial_ids={}
    gansar_state={}
    maigret_state={}
    maigret_checks={}
    maigret_sites=[]
    def retained_state(status=None):
        if source != 'maigret':
            return gansar_state
        diagnostics=dict(maigret_state)
        coverage=dict(diagnostics.get('coverage',{}))
        if status:
            coverage.update(phase=status,complete=False,cancelled=status=='cancelled')
        diagnostics.update(coverage=coverage,site_checks=list(maigret_checks.values()),
            resumption={'native_durable_resume':False,
                        'remaining_sites':[name for name in maigret_sites if name not in maigret_checks],
                        'method':'Explicit Custom sites filter; remaining checks are rerun.'})
        return {'source_diagnostics':diagnostics}
    try:
        payload_options = dict(options)
        payload_options["tools_root"] = str(root)
        process.stdin.write((json.dumps({"source": source, "query": query, "options": payload_options}, ensure_ascii=False) + "\n").encode("utf-8"))
        process.stdin.close()
        while True:
            if cancelled.is_set():
                return {"source": source, "status": "cancelled", "results": partial, **retained_state('cancelled'),"error_code":"source_cancelled","message": "Поиск отменён. Полученные наблюдения сохранены."}
            if time.monotonic() >= deadline:
                return {"source": source, "status": "timeout", "results": partial, **retained_state('timeout'),"error_code":"worker_time_budget","message": "Источник превысил время ожидания. Полученные наблюдения сохранены."}
            try:
                item = lines.get(timeout=0.06)
            except queue.Empty:
                if process.poll() is not None and not reader.is_alive():
                    break
                continue
            if item is None:
                break
            if item.get("event") == "result":
                result = item.get("result")
                if isinstance(result, dict):
                    identifier=result.get('id') if source in ('blockchain','maigret') else None
                    if identifier and identifier in partial_ids:partial[partial_ids[identifier]]=result
                    else:
                        if identifier:partial_ids[identifier]=len(partial)
                        partial.append(result)
                    if event:
                        event(item)
            elif item.get("event") == "final":
                outcome = item.get("outcome")
            elif source=='blockchain' and item.get('event')=='gansar_snapshot' and isinstance(item.get('report'),dict):
                gansar_state={'gansar_report':item['report'],'source_diagnostics':item.get('source_diagnostics',{})}
            elif source=='maigret' and item.get('event')=='maigret_progress' and isinstance(item.get('progress'),dict):
                maigret_state['coverage']=item['progress']
                if event:event(item)
            elif source=='maigret' and item.get('event')=='maigret_plan':
                maigret_sites=[name for name in item.get('scheduled_sites',[]) if isinstance(name,str)]
                maigret_state['configuration']=item.get('configuration',{})
            elif source=='maigret' and item.get('event')=='maigret_checks':
                for check in item.get('checks',[]):
                    if isinstance(check,dict) and isinstance(check.get('site'),str):
                        maigret_checks[check['site']]=check
            elif item.get("event") == "transport_error":
                return {"source": source, "status": "partial" if partial else "error", "results": partial, **retained_state('transport_error'),"error_code":"worker_response_limit","message": "Источник превысил допустимый объём ответа. Полученные наблюдения сохранены."}
            elif event:
                event(item)
        if not isinstance(outcome, dict):
            code = process.poll()
            return {"source": source, "status": "partial" if source=='maigret' and partial else "error", "results": partial, **retained_state('error'),
                    "error_code":"worker_missing_final",
                    "exit_code": code, "stderr_bytes": stderr_count[0],
                    "message": "Локальный источник завершился без структурированного ответа; проверьте его зависимости." + (f" Код: {code}." if code is not None else "")}
        try:
            code = process.wait(timeout=.2)
        except subprocess.TimeoutExpired:
            code = None
        outcome["exit_code"] = code
        if source=='blockchain':
            outcome={**gansar_state,**outcome}
            if partial and not outcome.get('results'):
                outcome['results']=partial
                if outcome.get('status')=='error':outcome['status']='partial'
        if source=='maigret':
            diagnostics={**retained_state().get('source_diagnostics',{}),**outcome.get('source_diagnostics',{})}
            outcome['source_diagnostics']=diagnostics
            if 'streamed_result_count' in outcome:
                expected=outcome.pop('streamed_result_count')
                outcome['results']=partial
                if expected != len(partial):
                    outcome['status']='partial'
                    outcome['error_code']='maigret_incomplete_stream'
                    outcome['message']='Получен неполный поток Maigret; сохранены все принятые наблюдения.'
            elif partial:
                # Worker-level exceptions can produce an empty final frame after
                # legitimate finding frames. Never let that frame erase them.
                by_id={row.get('id',str(index)):row for index,row in enumerate(partial)}
                for index,row in enumerate(outcome.get('results',[])):
                    by_id[row.get('id',str(len(partial)+index))]=row
                outcome['results']=list(by_id.values())
                if outcome.get('status')=='error':outcome['status']='partial'
            coverage=diagnostics.get('coverage')
            if isinstance(coverage,dict) and coverage.get('phase')=='running':
                coverage.update(phase=outcome.get('status','error'),complete=False)
        outcome["stderr_bytes"] = stderr_count[0]
        if code not in (0, None) and outcome.get("status") in {"complete", "ready", "empty"}:
            outcome["status"] = "partial" if outcome.get("results") else "error"
            outcome["error_code"] = 'worker_process_exit'
            outcome["message"] = "Источник завершился с ошибкой процесса. Полученные наблюдения сохранены." if outcome.get("results") else "Источник завершился с ошибкой процесса. Проверьте его зависимости."
        return outcome
    finally:
        job.close()
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream and not stream.closed:
                stream.close()
