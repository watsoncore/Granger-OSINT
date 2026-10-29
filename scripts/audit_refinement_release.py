"""Audit the 3.1 release, checking vault values without ever printing them."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.credentials import NAMES,get_secret,CredentialError
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',action='store_true')
    parser.add_argument('--git-history',action='store_true')
    args=parser.parse_args()
    out=ROOT/'output/refinement-qa';out.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((ROOT/'output/upgrade-qa/baseline.json').read_text(encoding='utf-8'))
    assets=[{'path':name,'unchanged':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected} for name,expected in baseline.items()]
    (out/'preservation.json').write_text(json.dumps({'passed':all(row['unchanged'] for row in assets),'files':assets},indent=2),encoding='utf-8')
    secrets=[]
    for name in NAMES:
        try:value=get_secret(name)
        except CredentialError:value=''
        if len(value)>=8:secrets.append(value.encode('utf-8'))
    patterns=[re.compile(rb'AIza[0-9A-Za-z_-]{30,}'),re.compile(rb'sk-[A-Za-z0-9_-]{25,}'),re.compile(rb'vk1\.[A-Za-z0-9_-]{60,}')]
    failures=[];checked=0
    def inspect(name,raw):
        nonlocal checked
        checked+=1
        if any(secret in raw for secret in secrets) or any(pattern.search(raw) for pattern in patterns):failures.append(name)
    tracked=subprocess.check_output(['git','ls-files','-c','-o','--exclude-standard','-z'],cwd=ROOT)
    for name in tracked.split(b'\0'):
        if name:
            path=ROOT/name.decode('utf-8')
            if path.is_file():inspect(path.relative_to(ROOT).as_posix(),path.read_bytes())
    for path in out.rglob('*'):
        if path.is_file() and path.suffix in ('.json','.jsonl','.log','.md'):
            inspect(path.relative_to(ROOT).as_posix(),path.read_bytes())
    inspect('dist/Granger-OSINT.exe',(ROOT/'dist/Granger-OSINT.exe').read_bytes())
    if args.git_history:
        rows=[row.split(b' ',1) for row in subprocess.check_output(['git','rev-list','--objects','--all'],cwd=ROOT).splitlines()]
        raw=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,input=b'\n'.join(row[0] for row in rows)+b'\n')
        offset=0
        for row in rows:
            end=raw.index(b'\n',offset);header=raw[offset:end].split();size=int(header[2]);offset=end+1
            if header[1]==b'blob':inspect('git/'+(row[1].decode('utf-8','replace') if len(row)>1 else row[0].decode()),raw[offset:offset+size])
            offset+=size+1
    if args.archive:
        with zipfile.ZipFile(ROOT/'dist/Granger-OSINT-source.zip') as archive:
            for name in archive.namelist():
                if any(part in name.split('/') for part in ('appdata','node_modules','.toolenvs','vault')) or name.endswith(('.dpapi','.sqlite3','.sqlite3-wal','.v1-backup')):
                    failures.append('private-or-runtime-file:'+name)
                inspect('zip/'+name,archive.read(name))
    report={'tested_at':datetime.now(timezone.utc).isoformat(),'passed':not failures and all(row['unchanged'] for row in assets),
        'payloads_checked':checked,'protected_assets':len(assets),'failures':failures,
        'archive_checked':args.archive,'git_history_checked':args.git_history,
        'method':'Exact saved vault values + credential patterns; source/Git/QA/EXE/decompressed source ZIP; no secret values in report'}
    (out/'secret-scan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
