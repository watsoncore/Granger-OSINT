"""Scan an explicit delivery without recording any credential value."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from grangerpet.credentials import CredentialsStore,NAMES,CredentialError
    store=CredentialsStore();exact=[];unavailable=0
    for name in NAMES:
        try:value=store.get(name)
        except CredentialError:unavailable+=1;continue
        if value:exact.append(value.encode('utf-8'))
    from scripts.audit_refinement_release import contains_credential_pattern
    import hashlib
    # Stock Qt resources contain a prose URL ending in "bitmask-improved..."
    # and Chromium's public Chrome UX Report client identifier. These exact
    # resources match both the installed Qt and the archived verified release.
    # Exact user-secret detection is ALWAYS applied, including these resources.
    stock_qt={
        'frozen/PySide6\\Qt6Quick3DHelpersImpl.dll':'0a367ab882b6e862cc68d3dc73489aeccfd77716c1a10b5452060a397d2afa33',
        'frozen/PySide6\\resources\\qtwebengine_devtools_resources.debug.pak':'1b51c9f34aa20f141ba8d60fce75e9228bf1e43a385d4b0011a586994f37073c',
    }
    checked=0;failures=[];stock_identifiers=[]
    def inspect(name,data):
        nonlocal checked
        checked+=1
        if any(secret in data for secret in exact):failures.append(name);return
        if contains_credential_pattern(data):
            if name in stock_qt and hashlib.sha256(data).hexdigest()==stock_qt[name]:
                stock_identifiers.append({'resource':name,'sha256':stock_qt[name],'classification':'unchanged stock Qt/Chromium public identifier or URL fragment'})
            else:failures.append(name)
    files=subprocess.check_output(['git','ls-files','-c','-o','--exclude-standard','-z'],cwd=ROOT).split(b'\0')
    for entry in files:
        if not entry:continue
        path=ROOT/entry.decode('utf-8')
        if path.is_file():inspect(path.relative_to(ROOT).as_posix(),path.read_bytes())
    inspect('candidate-EXE',args.exe.read_bytes())
    # Inspect uncompressed payloads too: scanning a compressed PE alone cannot
    # establish absence of strings inside PYZ/resources.
    from PyInstaller.archive.readers import CArchiveReader
    archive=CArchiveReader(str(args.exe))
    for name,row in archive.toc.items():
        if row[-1] in ('b','x','s','m','M'):
            data=archive.extract(name)
            if isinstance(data,bytes):inspect('frozen/'+name,data)
    pyz=archive.open_embedded_archive(next(n for n in archive.toc if n.endswith('.pyz')))
    import marshal
    for name in pyz.toc:
        if name.startswith('grangerpet'):inspect('frozen-bytecode/'+name,marshal.dumps(pyz.extract(name)))
    objects=subprocess.check_output(['git','rev-list','--objects','--all'],cwd=ROOT).splitlines()
    process=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        for entry in objects:
            oid=entry.split(b' ',1)[0];process.stdin.write(oid+b'\n');process.stdin.flush()
            header=process.stdout.readline().split();size=int(header[2]);data=process.stdout.read(size);process.stdout.read(1)
            if header[1]==b'blob':inspect('git-history/'+oid.decode(),data)
    finally:process.stdin.close();process.wait(timeout=30)
    if args.archive:
        with zipfile.ZipFile(args.archive) as bundle:
            for name in bundle.namelist():
                if any(p in name.split('/') for p in ('appdata','.git','.venv','.toolenvs','node_modules')) or name.endswith(('.dpapi','.session','.env','.sqlite3','.sqlite3-wal','.sqlite3-shm')):
                    failures.append('forbidden-archive-path/'+name)
                inspect('ZIP/'+name,bundle.read(name))
    report={'at_utc':datetime.now(timezone.utc).isoformat(),'passed':not failures,'checked_payloads':checked,
        'saved_credential_values_available':len(exact),'locked_or_unavailable_credentials':unavailable,
        'archive_checked':bool(args.archive),'git_history_checked':True,'failures':failures,
        'unchanged_stock_identifiers':stock_identifiers,
        'method':'Exact saved credentials + credential-shaped patterns; tracked source/public receipts, extracted PE resources/application PYZ, Git blobs and optional decompressed ZIP. Values are never printed or saved.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('passed','checked_payloads','archive_checked','failures')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
