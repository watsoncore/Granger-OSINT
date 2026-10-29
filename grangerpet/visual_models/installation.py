"""Pinned, consent-gated artifact installation without executing package setup."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import re
from urllib.parse import urlsplit
import zipfile
import time
import uuid
from contextlib import contextmanager

import httpx


def manifest():
    return json.loads(Path(__file__).with_name('manifest.json').read_text(encoding='utf-8'))


def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):sha.update(block)
    return sha.hexdigest()


def _check(cancel):
    if cancel is not None and cancel.is_set():raise InterruptedError('Installation cancelled')


def _inside(root,path):
    root=Path(root).resolve();target=(root/path).resolve()
    if not target.is_relative_to(root) or target==root:raise ValueError('Unsafe runtime artifact path')
    return target


def _trusted_url(url):
    parsed=urlsplit(url)
    allowed=('files.pythonhosted.org','huggingface.co','hf.co','xethub.hf.co')
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or not any(parsed.hostname==host or parsed.hostname.endswith('.'+host) for host in allowed):
        raise ValueError('Unexpected artifact host')


@contextmanager
def _artifact_lock(target,cancel_event):
    """Different app/install processes must never append to the same partial."""
    lock=Path(str(target)+'.lock');lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+b') as handle:
        handle.seek(0);handle.write(b'0');handle.flush()
        while True:
            _check(cancel_event)
            try:
                handle.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except (OSError,BlockingIOError):time.sleep(.1)
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def download(artifact,target,*,cancel_event=None,progress=None,client_factory=None):
    with _artifact_lock(target,cancel_event):
        for attempt in range(5):
            try:
                return _download_once(artifact,target,cancel_event=cancel_event,progress=progress,client_factory=client_factory)
            except (httpx.TransportError,httpx.HTTPStatusError) as exc:
                if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code not in (408,429,500,502,503,504):raise
                if attempt==4:raise RuntimeError('Artifact download interrupted after five attempts; verified partial is retained') from None
                if progress:progress({'artifact':Path(target).name,'phase':'retrying','attempt':attempt+2})
                until=time.monotonic()+min(8,2**attempt)
                while time.monotonic()<until:_check(cancel_event);time.sleep(.1)


def _download_once(artifact,target,*,cancel_event=None,progress=None,client_factory=None):
    """Resume only a known app-owned .part; hash authenticates completed bytes."""
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    expected=artifact['bytes'];wanted=artifact['sha256']
    if target.is_file() and target.stat().st_size==expected and digest(target)==wanted:
        if progress:progress({'artifact':target.name,'bytes':expected,'total_bytes':expected,'cached':True})
        return
    partial=target.with_name(target.name+'.part')
    if partial.exists() and partial.stat().st_size>expected:raise ValueError('Partial artifact exceeds pinned size')
    start=partial.stat().st_size if partial.exists() else 0
    if start==expected:
        if digest(partial)==wanted:
            _check(cancel_event);partial.replace(target)
            if progress:progress({'artifact':target.name,'bytes':expected,'total_bytes':expected,'cached':True})
            return
        # A full but corrupt partial cannot be resumed with bytes=size- (416).
        # Restart from byte zero; only a verified response can replace target.
        start=0
    _check(cancel_event);_trusted_url(artifact['url'])
    def redirect_check(response):
        _trusted_url(str(response.url))
        if response.is_redirect:
            from urllib.parse import urljoin
            _trusted_url(urljoin(str(response.url),response.headers.get('location','')))
    with (client_factory or httpx.Client)(follow_redirects=True,max_redirects=8,trust_env=False,
        timeout=httpx.Timeout(60,connect=15),headers={'User-Agent':'Granger-OSINT/3.1 optional-visual-runtime'},
        event_hooks={'response':[redirect_check]}) as client:
        with client.stream('GET',artifact['url'],headers={'Range':f'bytes={start}-'} if start else {}) as response:
            response.raise_for_status()
            if response.status_code not in (200,206):raise ValueError('Unexpected artifact status')
            if response.status_code==206 and not response.headers.get('content-range','').startswith(f'bytes {start}-'):
                raise ValueError('Unexpected artifact range')
            if response.status_code==200:start=0
            count=start
            with partial.open('ab' if start else 'wb') as output:
                for block in response.iter_bytes(1024*1024):
                    _check(cancel_event);count+=len(block)
                    if count>expected:raise ValueError('Artifact exceeds pinned size')
                    output.write(block)
                    if progress:progress({'artifact':target.name,'bytes':count,'total_bytes':expected,'cached':False})
                output.flush();os.fsync(output.fileno())
    if partial.stat().st_size!=expected or digest(partial)!=wanted:raise ValueError('Pinned artifact hash/size mismatch')
    partial.replace(target)


def extract_wheel(wheel,site,*,cancel_event=None):
    """Extract hashed wheels, including purelib/platlib, without install hooks."""
    site=Path(site);site.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        total=0
        for info in archive.infolist():
            _check(cancel_event)
            if info.is_dir():continue
            mode=info.external_attr>>16
            if stat.S_ISLNK(mode):raise ValueError('Wheel contains a symbolic link')
            name=info.filename.replace('\\','/')
            parts=name.split('/')
            if any(p in ('..','') for p in parts) or name.startswith('/') or ':' in name:raise ValueError('Unsafe wheel member')
            if len(parts)>2 and parts[0].endswith('.data'):
                if parts[1] not in ('purelib','platlib'):continue
                parts=parts[2:]
            total+=info.file_size
            if total>3_000_000_000 or info.file_size>1_500_000_000:raise ValueError('Wheel expansion exceeds limit')
            target=_inside(site,Path(*parts));target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(info) as source,target.open('wb') as dest:
                while block:=source.read(1024*1024):_check(cancel_event);dest.write(block)


def _no_reparse(path):
    """Reject symlinks and Windows junctions, including any existing ancestor."""
    for current in (path,*path.parents):
        try:
            attributes=current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(attributes.st_mode) or getattr(attributes,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):
            raise ValueError('Runtime path contains a symbolic link or junction')


def _wheel_owned_files(wheel):
    """File names installed by our extractor, without executing wheel code."""
    names=set()
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if entry.is_dir():continue
            if stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Wheel contains a symbolic link')
            name=entry.filename.replace('\\','/');parts=name.split('/')
            if any(part in ('..','') for part in parts) or name.startswith('/') or ':' in name:
                raise ValueError('Unsafe wheel member')
            if len(parts)>2 and parts[0].endswith('.data'):
                if parts[1] not in ('purelib','platlib'):continue
                parts=parts[2:]
            names.add('/'.join(parts))
    return names


def remove_runtime(root,*,_allowed_root=None):
    """Remove only a verified app-owned optional runtime, never a general tree.

    The caller closes its worker and obtains the user's native confirmation.
    ``_allowed_root`` is a private test seam; production callers must omit it.
    All names/ownership/reparse checks finish before any file is removed. This
    intentionally refuses unknown files instead of deleting user-added data.
    """
    from .manager import default_runtime_root
    supplied=Path(root)
    if not supplied.is_absolute():raise ValueError('Runtime removal requires an absolute path')
    allowed=Path(default_runtime_root() if _allowed_root is None else _allowed_root)
    if not allowed.is_absolute():raise ValueError('Allowed runtime path must be absolute')
    _no_reparse(supplied);_no_reparse(allowed)
    root=supplied.resolve();allowed=allowed.resolve()
    if root!=allowed or len(root.parts)<4:raise ValueError('Only the exact app-owned visual runtime can be removed')
    if not root.exists():return {'status':'not_installed','removed_files':0,'removed_bytes':0}
    if not root.is_dir():raise ValueError('Runtime path is not a directory')
    receipt_path=root/'receipt.json'
    try:
        _no_reparse(receipt_path)
        if receipt_path.stat().st_size>1_000_000:raise ValueError('Runtime receipt exceeds limit')
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    except (OSError,ValueError,TypeError):
        raise ValueError('A known installation receipt is required for removal') from None
    lock=manifest()
    expected_hash=hashlib.sha256(Path(__file__).with_name('manifest.json').read_bytes()).hexdigest()
    expected_packages={row['name']:row['version'] for row in lock['runtime_packages']}
    expected_artifacts=[{'path':row['relative_path'],'bytes':row['bytes'],'sha256':row['sha256']} for row in lock['artifacts']]
    if not isinstance(receipt,dict) or receipt.get('schema_version')!=1 or receipt.get('manifest_sha256')!=expected_hash or receipt.get('packages')!=expected_packages or receipt.get('artifacts')!=expected_artifacts:
        raise ValueError('Runtime receipt does not match the reviewed manifest')
    top_files={'receipt.json','receipt.pending.json','receipt.probe.pending.json'}
    known_files=set(top_files)
    known_directories={'downloads','models','site-packages','offline-cache'}
    for row in lock['artifacts']:
        relative=Path(row['relative_path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe manifest artifact path')
        name=relative.as_posix()
        known_files.update((name,name+'.part',name+'.lock'))
        known_directories.update(parent.as_posix() for parent in relative.parents if parent!=Path('.'))
    wheel_files=set()
    for row in lock['runtime_packages']:
        filename=row['filename']
        if Path(filename).name!=filename or '/' in filename or '\\' in filename:raise ValueError('Unsafe manifest wheel path')
        name='downloads/'+filename
        known_files.update((name,name+'.part',name+'.lock'))
        wheel=root/name
        _no_reparse(wheel)
        # Full original wheel names, authenticated by the reviewed manifest,
        # establish which site-packages files belong to this installation.
        if not wheel.is_file() or wheel.stat().st_size!=row['bytes'] or digest(wheel)!=row['sha256']:
            raise ValueError('Verified wheel cache is required for safe runtime removal')
        wheel_files.update(_wheel_owned_files(wheel))
    wheel_directories={parent.as_posix() for name in wheel_files for parent in Path(name).parents if parent!=Path('.')}
    site_roots=set()
    for entry in root.iterdir():
        if entry.name=='site-packages' or re.fullmatch(r'site-packages\.(?:pending|previous)-[0-9a-f]{32}',entry.name):
            _no_reparse(entry)
            if not entry.is_dir():raise ValueError('Unexpected runtime staging entry')
            site_roots.add(entry.name)
            known_directories.add(entry.name)
    files=[];directories=[]
    pending=[root]
    while pending:
        directory=pending.pop();_no_reparse(directory)
        for entry in directory.iterdir():
            _no_reparse(entry)
            if not entry.resolve().is_relative_to(root):raise ValueError('Runtime entry leaves the owned directory')
            relative=entry.relative_to(root);name=relative.as_posix();parts=relative.parts
            is_directory=entry.is_dir()
            recognized=False
            if parts[0] in site_roots:
                inner=Path(*parts[1:]).as_posix()
                if is_directory:
                    recognized=not parts[1:] or inner in wheel_directories
                    if not recognized and parts[-1]=='__pycache__':
                        parent=Path(*parts[1:-1])
                        recognized=any(Path(item).parent==parent and item.endswith('.py') for item in wheel_files)
                else:
                    recognized=inner in wheel_files
                    if not recognized and len(parts)>2 and parts[-2]=='__pycache__':
                        match=re.fullmatch(r'(.+)\.cpython-314(?:\.opt-[12])?\.pyc',parts[-1])
                        if match:
                            source=Path(*parts[1:-2],match.group(1)+'.py').as_posix()
                            recognized=source in wheel_files
            else:
                recognized=name in (known_directories if is_directory else known_files)
            if not recognized:raise ValueError('Unknown file or directory in optional runtime; nothing removed')
            if is_directory:
                directories.append(entry);pending.append(entry)
            else:
                files.append(entry)
    # No rmtree/followed links. Recheck immediately before each operation; an
    # unexpected concurrent addition is preserved and makes rmdir fail closed.
    removed_bytes=0
    for path in files:
        _no_reparse(path)
        if not path.resolve().is_relative_to(root):raise ValueError('Runtime path changed during removal')
        removed_bytes+=path.stat().st_size
        path.unlink()
    for path in sorted(directories,key=lambda item:len(item.parts),reverse=True):
        _no_reparse(path);path.rmdir()
    _no_reparse(root);root.rmdir()
    return {'status':'removed','removed_files':len(files),'removed_bytes':removed_bytes}


def install(root,*,consent=False,cancel_event=None,progress=None):
    if consent is not True:raise PermissionError('Explicit consent required for the optional visual model download')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True);lock=manifest()
    downloads=root/'downloads';jobs=[]
    for row in lock['runtime_packages']:
        jobs.append(({'url':row['url'],'bytes':row['bytes'],'sha256':row['sha256']},_inside(downloads,row['filename'])))
    for row in lock['artifacts']:jobs.append((row,_inside(root,row['relative_path'])))
    _check(cancel_event)
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix='GrangerVisualDownload') as pool:
        pending=[pool.submit(download,row,target,cancel_event=cancel_event,progress=progress) for row,target in jobs]
        for future in as_completed(pending):future.result()
    site=root/('site-packages.pending-'+uuid.uuid4().hex)
    for row in lock['runtime_packages']:
        extract_wheel(downloads/row['filename'],site,cancel_event=cancel_event)
        if progress:progress({'phase':'extracting','package':row['name'],'version':row['version']})
    _check(cancel_event)
    active=root/'site-packages'
    previous=None
    if active.exists():
        previous=root/('site-packages.previous-'+uuid.uuid4().hex)
        active.replace(previous)
    try:site.replace(active)
    except OSError:
        if previous is not None and not active.exists():previous.replace(active)
        raise
    receipt={'schema_version':1,'manifest_sha256':hashlib.sha256(Path(__file__).with_name('manifest.json').read_bytes()).hexdigest(),
        'installed_at_utc':datetime.now(timezone.utc).isoformat(),'status':'files_verified_probe_pending',
        'packages':{row['name']:row['version'] for row in lock['runtime_packages']},'artifacts':[{'path':r['relative_path'],'bytes':r['bytes'],'sha256':r['sha256']} for r in lock['artifacts']]}
    temporary=root/'receipt.pending.json';temporary.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');temporary.replace(root/'receipt.json')
    return receipt
