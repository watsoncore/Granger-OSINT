"""Read-only new-source inventory; optional existing registry readiness probes.

The newly supplied projects are never imported or executed by this script.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PATTERNS = {
    'shell_or_process': r'\b(?:subprocess|os\.system|os\.popen|child_process)\b',
    'dynamic_execution': r'\b(?:exec|eval)\s*\(',
    'credentials_or_session': r'(?i)\b(?:password|cookies?|sessionid|api_key|access_token|authorization)\b',
    'proxy_or_challenge': r'(?i)\b(?:proxy|proxies|captcha|camoufox|undetected)\b',
    'network': r'(?i)https?://|\b(?:requests|httpx|aiohttp|socket)\b',
    'insecure_tls': r'verify\s*=\s*False|ssl\s*=\s*False',
}
CODE_SUFFIXES = {'.py', '.js', '.ts', '.tsx', '.sh', '.ps1', '.bat'}


def summarize(name, files, archive_hash=None):
    """Only names/locations of indicators are emitted, never raw secret text."""
    result = {'name': name, 'files': len(files), 'bytes': sum(len(v) for v in files.values()),
              'archive_sha256': archive_hash, 'origins': [], 'license_files': [],
              'manifests': [], 'security_indicators': {}, 'executed': False,
              'assessment': 'Static inventory only; indicators require source review, not a safety certification.'}
    for path, raw in files.items():
        leaf = Path(path).name.lower()
        if leaf.startswith(('license', 'copying')):
            result['license_files'].append({'path': path, 'sha256': hashlib.sha256(raw).hexdigest()})
        if leaf in ('pyproject.toml', 'package.json', 'requirements.txt', 'setup.py', 'cargo.toml'):
            result['manifests'].append(path)
        if leaf.startswith('readme') and len(raw) < 500_000:
            result['origins'].extend(re.findall(r'https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', raw.decode('utf-8', 'replace')))
        if Path(path).suffix.lower() not in CODE_SUFFIXES or len(raw) > 2_000_000:
            continue
        for number, line in enumerate(raw.decode('utf-8', 'replace').splitlines(), 1):
            for category, pattern in PATTERNS.items():
                if re.search(pattern, line):
                    result['security_indicators'].setdefault(category, []).append({'path': path, 'line': number})
    result['origins'] = sorted(set(result['origins']))
    return result


def inventory():
    rows = []
    for archive in sorted(ROOT.glob('*.zip')):
        with zipfile.ZipFile(archive) as bundle:
            files = {}
            for entry in bundle.infolist():
                path = Path(entry.filename)
                if (entry.is_dir() or entry.file_size > 2_000_000 or path.is_absolute()
                        or '..' in path.parts or set(path.parts) & {'.git', 'node_modules', '__pycache__'}):
                    continue
                if path.suffix.lower() in CODE_SUFFIXES | {'.md', '.txt', '.toml', '.json', '.cfg'} or path.name.lower().startswith(('license', 'copying')):
                    files[entry.filename] = bundle.read(entry)
            row = summarize(archive.name, files, hashlib.sha256(archive.read_bytes()).hexdigest())
            row['expanded_bytes'] = sum(e.file_size for e in bundle.infolist())
            rows.append(row)
    folder = ROOT / 'SteamRecon'
    if folder.is_dir():
        files = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*')
                 if p.is_file() and not set(p.relative_to(folder).parts) & {'.git', '.venv', '__pycache__', 'output', 'reports', 'data'}
                 and p.stat().st_size <= 2_000_000 and (p.suffix.lower() in CODE_SUFFIXES | {'.md', '.txt', '.toml', '.json'} or p.name.lower().startswith('license'))}
        rows.append(summarize('SteamRecon', files))
    return rows


def disk_sizes():
    totals = {}
    for entry in os.scandir(ROOT):
        if entry.is_symlink():
            continue
        total = count = 0
        if entry.is_file(follow_symlinks=False):
            total = entry.stat(follow_symlinks=False).st_size; count = 1
        elif entry.is_dir(follow_symlinks=False):
            pending = [entry.path]
            while pending:
                try:
                    with os.scandir(pending.pop()) as children:
                        for child in children:
                            if child.is_symlink(): continue
                            if child.is_dir(follow_symlinks=False): pending.append(child.path)
                            elif child.is_file(follow_symlinks=False):
                                total += child.stat(follow_symlinks=False).st_size; count += 1
                except (PermissionError, FileNotFoundError):
                    continue
        totals[entry.name] = {'bytes': total, 'files': count}
    return {'logical_bytes': sum(r['bytes'] for r in totals.values()), 'entries': totals,
            'method': 'Logical file sizes; no file content read or deleted; symlinks excluded. Not allocated disk space.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--disk', action='store_true'); parser.add_argument('--catalog', action='store_true')
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    def save(name, data):
        (args.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    sources = inventory(); save('source-audit.json', {'at': datetime.now(timezone.utc).isoformat(), 'projects': sources})
    if args.disk: save('disk-audit.json', disk_sizes())
    if args.catalog:
        from grangerpet.agent_tools import ToolRegistry
        from grangerpet.config import Settings
        registry = ToolRegistry(Settings(), options={'source_root': str(ROOT)}, secret_getter=lambda name: '')
        rows = registry.catalog()
        # Only public capability fields; never serialize settings or credentials.
        save('capabilities.json', [{k: row[k] for k in ('name', 'source', 'kind', 'available', 'state', 'requires_approval', 'manifest', 'reason')} for row in rows])
    print(json.dumps({'static_projects': len(sources), 'executed_new_vendor_code': False, 'output': str(args.output)}))


if __name__ == '__main__': main()
