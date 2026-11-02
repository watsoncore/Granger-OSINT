"""Read-only logical/allocated workspace audit and verified large duplicate candidates."""
from collections import defaultdict
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_DUPLICATE_BYTES = 16*1024*1024


def allocated_reader():
    if os.name != 'nt':
        return lambda path, stat: stat.st_blocks * 512
    from ctypes import wintypes
    class StandardInfo(ctypes.Structure):
        _fields_=[('AllocationSize', ctypes.c_int64), ('EndOfFile', ctypes.c_int64),
                  ('NumberOfLinks', wintypes.DWORD), ('DeletePending', ctypes.c_ubyte), ('Directory', ctypes.c_ubyte)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    create=kernel.CreateFileW
    create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    create.restype=wintypes.HANDLE
    query=kernel.GetFileInformationByHandleEx
    query.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    query.restype=wintypes.BOOL
    close=kernel.CloseHandle
    close.argtypes=[wintypes.HANDLE]
    def read(path, stat):
        handle=create(str(path),0x80,7,None,3,0,None)
        if handle==ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            info=StandardInfo()
            if not query(handle,1,ctypes.byref(info),ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            return info.AllocationSize
        finally:
            close(handle)
    return read


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('Choose a fresh receipt')
    allocated=allocated_reader()
    groups=defaultdict(lambda:dict(files=0,logical_bytes=0,allocated_bytes=0,allocation_unknown=0))
    candidates=defaultdict(list)
    seen=set()
    errors=0
    for directory,dirs,files in os.walk(ROOT,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink() and not (Path(directory)/d).is_junction()]
        for name in files:
            path=Path(directory)/name
            if path.is_symlink():
                continue
            group=groups[path.relative_to(ROOT).parts[0]]
            try:
                stat=path.stat()
                group['files']+=1
                group['logical_bytes']+=stat.st_size
                identity=(stat.st_dev,stat.st_ino) if stat.st_ino else str(path)
                if identity in seen:
                    continue
                seen.add(identity)
                group['allocated_bytes']+=allocated(path,stat)
                if stat.st_size>=MIN_DUPLICATE_BYTES:
                    candidates[stat.st_size].append(path)
            except OSError:
                errors+=1
                group['allocation_unknown']+=1
    duplicates=[]
    for length,paths in candidates.items():
        if len(paths)<2:continue
        checksums=defaultdict(list)
        for path in paths:
            try:
                with path.open('rb') as stream:
                    digest=hashlib.file_digest(stream,'sha256').hexdigest()
                checksums[digest].append(path.relative_to(ROOT).as_posix())
            except OSError:
                errors+=1
        duplicates.extend(dict(bytes_per_copy=length,sha256=digest,paths=sorted(matches))
            for digest,matches in checksums.items() if len(matches)>1)
    result={'at':datetime.now(timezone.utc).isoformat(),'groups':groups,'read_errors':errors,
        'logical_bytes':sum(v['logical_bytes'] for v in groups.values()),
        'allocated_bytes':sum(v['allocated_bytes'] for v in groups.values()),
        'duplicate_minimum_bytes':MIN_DUPLICATE_BYTES,'duplicate_groups':duplicates,
        'method':'Windows FileStandardInfo.AllocationSize for named files. Hardlinks counted once for allocation. Same-size independent files compared by full SHA-256. Reparse directory targets skipped.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('logical_bytes','allocated_bytes','read_errors')}))


if __name__=='__main__':
    main()
