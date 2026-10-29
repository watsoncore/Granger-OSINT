"""Read-only Windows resource measurements for explicitly identified Granger trees.

No process control, window/content capture, registry writes or third-party command
lines. Toolhelp supplies PID ancestry only; image paths/counters are opened only
for supplied Granger roots, verified descendants and previously verified PIDs.

CPU percentages expose both 100%=one logical core and machine-normalized units.
PrivateUsage is PRIVATE COMMIT, never mislabeled private working set. Summed RSS
double-counts shared pages across processes. GPU engine sums are not total GPU
utilization; driver/PDH unavailability remains null with a diagnostic code.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes as W
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import statistics
import time

ROOT = Path(__file__).resolve().parents[1]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),
        ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',W.DWORD),
        ('cntThreads',W.DWORD),('th32ParentProcessID',W.DWORD),
        ('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]


class _Memory(ctypes.Structure):
    _fields_ = [('cb',W.DWORD),('PageFaultCount',W.DWORD)] + [(name,ctypes.c_size_t) for name in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]


def _ticks(value):
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


class _WindowsProcesses:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Windows resource sampler requires Windows')
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.psapi=ctypes.WinDLL('psapi',use_last_error=True)
        k=self.kernel
        k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD]; k.CreateToolhelp32Snapshot.restype=W.HANDLE
        for name in ('Process32FirstW','Process32NextW'):
            fn=getattr(k,name);fn.argtypes=[W.HANDLE,ctypes.POINTER(_ProcessEntry)];fn.restype=W.BOOL
        k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD]; k.OpenProcess.restype=W.HANDLE
        k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
        k.QueryFullProcessImageNameW.restype=W.BOOL
        k.GetProcessTimes.argtypes=[W.HANDLE]+[ctypes.POINTER(W.FILETIME)]*4;k.GetProcessTimes.restype=W.BOOL
        k.CloseHandle.argtypes=[W.HANDLE];k.CloseHandle.restype=W.BOOL
        self.psapi.GetProcessMemoryInfo.argtypes=[W.HANDLE,ctypes.POINTER(_Memory),W.DWORD]
        self.psapi.GetProcessMemoryInfo.restype=W.BOOL

    def ancestry(self):
        handle=self.kernel.CreateToolhelp32Snapshot(2,0)
        if handle==ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(),'Toolhelp snapshot unavailable')
        rows={}
        try:
            entry=_ProcessEntry();entry.dwSize=ctypes.sizeof(entry)
            valid=self.kernel.Process32FirstW(handle,ctypes.byref(entry))
            while valid:
                # Do not retain names or inspect command lines of other apps.
                rows[entry.th32ProcessID]={'parent_pid':entry.th32ParentProcessID,'threads':entry.cntThreads}
                valid=self.kernel.Process32NextW(handle,ctypes.byref(entry))
        finally:
            self.kernel.CloseHandle(handle)
        return rows

    def counters(self,pid):
        handle=self.kernel.OpenProcess(0x1000|0x10,False,pid)
        access='query_limited_and_vm_read'
        if not handle:
            # Sandboxed WebEngine children may deny VM_READ. Their CPU/image
            # counters still permit limited-query access on current Windows.
            handle=self.kernel.OpenProcess(0x1000,False,pid)
            access='query_limited'
        if not handle:return None
        try:
            size=W.DWORD(32768);image=ctypes.create_unicode_buffer(size.value)
            if not self.kernel.QueryFullProcessImageNameW(handle,0,image,ctypes.byref(size)):
                return None
            birth,exit,kernel,user=(W.FILETIME() for _ in range(4))
            if not self.kernel.GetProcessTimes(handle,ctypes.byref(birth),ctypes.byref(exit),ctypes.byref(kernel),ctypes.byref(user)):
                return None
            memory=_Memory();memory.cb=ctypes.sizeof(memory)
            memory_ok=self.psapi.GetProcessMemoryInfo(handle,ctypes.byref(memory),memory.cb)
            return {'pid':pid,'image':str(Path(image.value).resolve()),'creation_ticks':_ticks(birth),
                'cpu_seconds':(_ticks(kernel)+_ticks(user))/10_000_000,
                'query_access':access,
                'rss_bytes':int(memory.WorkingSetSize) if memory_ok else None,
                'private_commit_bytes':int(memory.PrivateUsage) if memory_ok else None}
        finally:
            self.kernel.CloseHandle(handle)


class _PdhValueUnion(ctypes.Union):
    _fields_=[('longValue',W.LONG),('doubleValue',ctypes.c_double),('largeValue',ctypes.c_int64),('AnsiStringValue',ctypes.c_char_p),('WideStringValue',W.LPWSTR)]


class _PdhValue(ctypes.Structure):
    _fields_=[('CStatus',W.DWORD),('value',_PdhValueUnion)]


class _PdhItem(ctypes.Structure):
    _fields_=[('szName',W.LPWSTR),('FmtValue',_PdhValue)]


class _GpuPdh:
    """Optional WDDM counters; emits only values belonging to verified own PIDs."""
    PATHS={'engines':r'\GPU Engine(*)\Utilization Percentage',
        'dedicated':r'\GPU Process Memory(*)\Dedicated Usage',
        'shared':r'\GPU Process Memory(*)\Shared Usage'}

    def __init__(self):
        self.query=W.HANDLE();self.counters={};self.errors={};self.dll=None
        try:
            self.dll=ctypes.WinDLL('pdh',use_last_error=True);d=self.dll
            d.PdhOpenQueryW.argtypes=[W.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(W.HANDLE)]
            d.PdhAddEnglishCounterW.argtypes=[W.HANDLE,W.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(W.HANDLE)]
            d.PdhCollectQueryData.argtypes=[W.HANDLE]
            d.PdhGetFormattedCounterArrayW.argtypes=[W.HANDLE,W.DWORD,ctypes.POINTER(W.DWORD),ctypes.POINTER(W.DWORD),ctypes.c_void_p]
            d.PdhCloseQuery.argtypes=[W.HANDLE]
            if d.PdhOpenQueryW(None,0,ctypes.byref(self.query)):
                self.errors['query']='pdh_open_failed';return
            for name,path in self.PATHS.items():
                handle=W.HANDLE();code=d.PdhAddEnglishCounterW(self.query,path,0,ctypes.byref(handle))
                if code:self.errors[name]='pdh_counter_unavailable_'+hex(code&0xffffffff)
                else:self.counters[name]=handle
            d.PdhCollectQueryData(self.query)
        except (OSError,AttributeError):
            self.errors['provider']='pdh_unavailable'

    def sample(self,pids):
        result={'gpu_engine_percent_sum':None,'gpu_engine_percent_max':None,
            'gpu_dedicated_bytes':None,'gpu_shared_bytes':None,'diagnostics':dict(self.errors)}
        if not pids:
            result.update(gpu_engine_percent_sum=0.0,gpu_engine_percent_max=0.0,gpu_dedicated_bytes=0,gpu_shared_bytes=0)
            return result
        if not self.dll or not self.query or not self.counters:
            return result
        code=self.dll.PdhCollectQueryData(self.query)
        if code:
            result['diagnostics']['collect']='pdh_collect_failed_'+hex(code&0xffffffff);return result
        values={}
        for name,handle in self.counters.items():
            size,count=W.DWORD(),W.DWORD()
            code=self.dll.PdhGetFormattedCounterArrayW(handle,0x200|0x8000,ctypes.byref(size),ctypes.byref(count),None)
            if (code&0xffffffff)!=0x800007d2 or not 0<size.value<64_000_000:
                result['diagnostics'][name]='pdh_no_samples_'+hex(code&0xffffffff);continue
            buffer=ctypes.create_string_buffer(size.value)
            code=self.dll.PdhGetFormattedCounterArrayW(handle,0x200|0x8000,ctypes.byref(size),ctypes.byref(count),buffer)
            if code:
                result['diagnostics'][name]='pdh_read_failed_'+hex(code&0xffffffff);continue
            rows=ctypes.cast(buffer,ctypes.POINTER(_PdhItem));own=[]
            for i in range(count.value):
                # Instance strings and values of other apps are never retained.
                match=re.match(r'^pid_(\d+)_',rows[i].szName or '')
                if match and int(match[1]) in pids and rows[i].FmtValue.CStatus in (0,1):
                    value=rows[i].FmtValue.value.doubleValue
                    if math.isfinite(value) and value>=0:own.append(value)
            values[name]=own
        if 'engines' in values:
            result.update(gpu_engine_percent_sum=sum(values['engines']),gpu_engine_percent_max=max(values['engines'],default=0.0))
        for name,key in (('dedicated','gpu_dedicated_bytes'),('shared','gpu_shared_bytes')):
            if name in values:result[key]=int(sum(values[name]))
        return result

    def close(self):
        if self.dll and self.query:
            self.dll.PdhCloseQuery(self.query);self.query=W.HANDLE()


class ProcessSampler:
    def __init__(self,exe=None,*,gpu=True):
        self.exe=Path(exe or ROOT/'dist/Granger-OSINT.exe').resolve()
        self.source_images={str((ROOT/'.venv/Scripts'/name).resolve()).casefold() for name in ('python.exe','pythonw.exe')}
        self.api=_WindowsProcesses();self.gpu=_GpuPdh() if gpu else None
        self._known={};self._previous={};self._last_time=None;self._last_wall_ticks=None

    def sample(self,root_pids=(),*,source_main_pids=()):
        """source_main_pids must be caller-owned PIDs launched with ROOT/main.py.

        Source command lines are deliberately not harvested. Only explicit source
        roots with an exact project venv interpreter path are accepted. Detached
        Pet should be supplied as its own root; observed descendants remain
        tracked after a parent exits, enabling orphan checks without killing any.
        """
        started=time.monotonic();tree=self.api.ancestry();roots=set(map(int,root_pids));source=set(map(int,source_main_pids))
        rows={};rejected=[]
        for pid in roots|source:
            row=self.api.counters(pid) if pid in tree else None
            if row and ((pid in roots and Path(row['image'])==self.exe) or (pid in source and row['image'].casefold() in self.source_images)):
                rows[pid]=row
            elif pid in tree:rejected.append(pid)
        for pid,identity in list(self._known.items()):
            if pid in rows or pid not in tree:continue
            row=self.api.counters(pid)
            if row and (row['creation_ticks'],row['image'])==identity:rows[pid]=row
        changed=True
        while changed:
            changed=False
            for pid,item in tree.items():
                if pid in rows or item['parent_pid'] not in rows:continue
                row=self.api.counters(pid)
                parent_birth=rows[item['parent_pid']]['creation_ticks']
                if row and (parent_birth is None or row['creation_ticks']>=parent_birth):
                    rows[pid]=row;changed=True
                elif row is None:
                    # Count ancestry-verified inaccessible children too. Do not
                    # invent zero CPU/memory or retain an unverified PID after
                    # its parent exits: creation identity is unavailable.
                    rows[pid]={'pid':pid,'image':None,'creation_ticks':None,'cpu_seconds':None,
                        'rss_bytes':None,'private_commit_bytes':None,'query_access':'unavailable'}
                    changed=True
        now=time.monotonic();wall_ticks=time.time_ns()//100+116444736000000000
        elapsed=now-self._last_time if self._last_time is not None else None
        total_cpu=0.0
        for pid,row in rows.items():
            identity=(pid,row['creation_ticks']);previous=self._previous.get(identity)
            if previous is None and self._last_wall_ticks is not None and row['creation_ticks'] is not None and row['creation_ticks']>=self._last_wall_ticks:
                previous=0.0  # A child born inside this interval has no earlier CPU.
            row['cpu_percent_one_core']=max(0.0,(row['cpu_seconds']-previous)/elapsed*100) if previous is not None and row['cpu_seconds'] is not None and elapsed else None
            if row['cpu_percent_one_core'] is not None:total_cpu+=row['cpu_percent_one_core']
            row.update(parent_pid=tree[pid]['parent_pid'],threads=tree[pid]['threads'])
        self._known={pid:(r['creation_ticks'],r['image']) for pid,r in rows.items() if r['creation_ticks'] is not None}
        self._previous={(pid,r['creation_ticks']):r['cpu_seconds'] for pid,r in rows.items() if r['cpu_seconds'] is not None};self._last_time=now;self._last_wall_ticks=wall_ticks
        def total(field):return sum(r[field] for r in rows.values()) if all(r[field] is not None for r in rows.values()) else None
        result={'sampled_at_utc':datetime.now(timezone.utc).isoformat(),'process_count':len(rows),
            'thread_count':sum(r['threads'] for r in rows.values()),'rss_bytes_sum':total('rss_bytes'),
            'private_commit_bytes_sum':total('private_commit_bytes'),'private_working_set_bytes':None,
            'cpu_percent_one_core':total_cpu if elapsed and all(r['cpu_percent_one_core'] is not None for r in rows.values()) else None,
            'cpu_percent_machine':total_cpu/(os.cpu_count() or 1) if elapsed and all(r['cpu_percent_one_core'] is not None for r in rows.values()) else None,
            'cpu_percent_one_core_available':total_cpu if elapsed else None,
            'resource_coverage_process_count':sum(r['rss_bytes'] is not None for r in rows.values()),
            'cpu_coverage_process_count':sum(r['cpu_percent_one_core'] is not None for r in rows.values()),
            'unreadable_process_count':sum(r.get('query_access')=='unavailable' for r in rows.values()),
            'logical_processors':os.cpu_count(),'interval_seconds':elapsed,
            'rejected_root_pids':rejected,'processes':sorted(rows.values(),key=lambda r:r['pid']),
            'gpu':self.gpu.sample(set(rows)) if self.gpu else {'diagnostics':{'provider':'disabled_for_measurement'}},
            'monitor_seconds':time.monotonic()-started}
        return result

    def close(self):
        if self.gpu:self.gpu.close()


def summarize(samples):
    """Medians preserve missing values rather than treating unavailable as zero."""
    fields=('process_count','thread_count','rss_bytes_sum','private_commit_bytes_sum',
        'cpu_percent_one_core','cpu_percent_machine','monitor_seconds')
    result={'samples':len(samples),'medians':{},'gpu_medians':{}}
    for name in fields:
        values=[row[name] for row in samples if isinstance(row.get(name),(int,float))]
        result['medians'][name]=statistics.median(values) if values else None
    for name in ('gpu_engine_percent_sum','gpu_engine_percent_max','gpu_dedicated_bytes','gpu_shared_bytes'):
        values=[row['gpu'][name] for row in samples if isinstance(row.get('gpu',{}).get(name),(int,float))]
        result['gpu_medians'][name]=statistics.median(values) if values else None
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-pid',type=int,action='append',default=[])
    parser.add_argument('--source-main-pid',type=int,action='append',default=[])
    parser.add_argument('--exe',type=Path)
    parser.add_argument('--samples',type=int,default=5)
    parser.add_argument('--interval',type=float,default=1)
    parser.add_argument('--no-gpu',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 2<=args.samples<=600 or not .25<=args.interval<=30:parser.error('Use 2..600 samples and 0.25..30 second interval')
    monitor=ProcessSampler(args.exe,gpu=not args.no_gpu);samples=[]
    try:
        for index in range(args.samples):
            if index:time.sleep(args.interval)
            samples.append(monitor.sample(args.root_pid,source_main_pids=args.source_main_pid))
    finally:monitor.close()
    report={'method':'Explicit image-verified Granger trees; read-only Windows Toolhelp/GetProcessTimes/GetProcessMemoryInfo/optional PDH',
        'memory_notes':'RSS includes shared pages; private_commit is committed private memory, not private working set',
        'gpu_notes':'Only owned PIDs retained; engine sum/max are not whole-GPU utilization; unavailable data is null',
        'sampling_limits':'CPU of a process that starts and exits wholly between samples is not captured; warm steady-state comparisons avoid treating this as whole-task CPU accounting',
        'sources':['https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes',
            'https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex',
            'https://learn.microsoft.com/en-us/windows/win32/api/pdh/nf-pdh-pdhgetformattedcounterarrayw'],
        'samples':samples,'summary':summarize(samples)}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report['summary']))


if __name__=='__main__':main()
