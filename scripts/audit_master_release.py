"""Verify protected resources and absence of saved keys in the release payload."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from grangerpet.ai_keys import resolve_deepseek_key
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', action='store_true')
    parser.add_argument('--git-history', action='store_true')
    args = parser.parse_args()
    output = ROOT/'output/master-qa'
    baseline = json.loads((output/'baseline.json').read_text(encoding='utf-8'))
    preserved = []
    for name, original in baseline.items():
        current = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        preserved.append({'path': name, 'unchanged': current==original,
                          'expected_change': name=='grangerpet/engine/router.py'})
    protection = {'files': preserved, 'passed': all(row['unchanged'] or row['expected_change'] for row in preserved),
                  'reason_for_router_change': 'Independent bundled TON representation validator removes unlicensed vendor-file dependency; analytical adapters unchanged'}
    (output/'preservation.json').write_text(json.dumps(protection, indent=2)+'\n', encoding='utf-8')
    secret = resolve_deepseek_key()
    exact = [secret.encode('utf-8')] if secret else []
    patterns = [re.compile(rb'AIza[0-9A-Za-z_-]{30,}'), re.compile(rb'sk-[A-Za-z0-9_-]{25,}')]
    failures = []
    checked = 0
    def inspect(name, raw):
        nonlocal checked
        checked += 1
        if any(value in raw for value in exact) or any(pattern.search(raw) for pattern in patterns):
            failures.append(name)
    files = subprocess.check_output(['git', 'ls-files', '-c', '-o', '--exclude-standard', '-z'], cwd=ROOT).split(b'\0')
    for encoded in files:
        if not encoded:
            continue
        path = ROOT/encoded.decode('utf-8')
        if path.is_file():
            inspect(path.relative_to(ROOT).as_posix(), path.read_bytes())
    for path in output.rglob('*'):
        if path.is_file() and path.suffix in ('.json', '.jsonl', '.log', '.md'):
            inspect(path.relative_to(ROOT).as_posix(), path.read_bytes())
    inspect('dist/GrangerPet.exe', (ROOT/'dist/GrangerPet.exe').read_bytes())
    if args.git_history:
        objects = subprocess.check_output(['git', 'rev-list', '--objects', '--all'], cwd=ROOT).splitlines()
        rows = [row.split(b' ', 1) for row in objects]
        payload = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=ROOT,
            input=b'\n'.join(row[0] for row in rows)+b'\n')
        offset = 0
        for row in rows:
            end = payload.index(b'\n', offset)
            header = payload[offset:end].split()
            size = int(header[2])
            offset = end+1
            if header[1] == b'blob':
                name = row[1].decode('utf-8', errors='replace') if len(row)>1 else row[0].decode()
                inspect('git-history/'+name, payload[offset:offset+size])
            offset += size+1
    if args.archive:
        with zipfile.ZipFile(ROOT/'dist/GrangerPet-source.zip') as archive:
            for name in archive.namelist():
                if any(part in name.split('/') for part in ('appdata', '.git', '.venv', '.toolenvs')) or name.endswith(('.dpapi', '.session', '.env')):
                    failures.append('Forbidden archive path: '+name)
                inspect(name, archive.read(name))
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(), 'passed': not failures,
              'saved_key_available_for_exact_match': bool(secret), 'checked_payloads': checked,
              'archive_checked': args.archive, 'git_history_checked': args.git_history, 'failures': failures,
              'method': 'Saved Windows key exact bytes + credential-shaped strings; source payloads, QA text and EXE; optional decompressed source ZIP. No key value is recorded.'}
    (output/'secret-scan.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'preservation_passed': protection['passed'], 'secret_scan_passed': report['passed'],
                      'checked_payloads': checked, 'failures': failures}))
    return 0 if protection['passed'] and report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
