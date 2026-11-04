"""Read-only hash comparison with the V3 private baseline; never decrypts data.

The private report contains relative protected filenames and ciphertext hashes.
The printed/public summary contains aggregate counts and protected-group hashes.
No baseline, runtime, original release, profile or archived copy is overwritten.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'output/master-fix-v3/baseline/private-manifest.json'


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def paths(root):
    values = []
    if not root.is_dir():
        return values
    for folder, directories, names in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if not Path(folder, name).is_symlink() and not Path(folder, name).is_junction()]
        values.extend(Path(folder, name) for name in names if not Path(folder, name).is_symlink())
    return values


def inspect(path, root):
    name = path.relative_to(root).as_posix()
    try:
        before = path.stat()
        checksum = digest(path)
        after = path.stat()
        return name, {'sha256': checksum, 'bytes': after.st_size,
            'stable': (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)}
    except OSError:
        return name, {'readable': False}


def tree_digest(rows):
    canonical = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def compare(expected, actual):
    changed, unchanged = {}, 0
    for name, before in expected.items():
        versions = before.get('versions')
        original = next((row for row in reversed(versions or []) if row.get('stable')), before)
        now = actual.get(name)
        if now and now.get('sha256') == original.get('sha256') and now.get('bytes') == original.get('bytes'):
            unchanged += 1
        else:
            changed[name] = {'before': {key: original.get(key) for key in ('sha256', 'bytes')}, 'after': now}
    added = {name: row for name, row in actual.items() if name not in expected}
    return {'expected': len(expected), 'actual': len(actual), 'unchanged': unchanged,
        'changed_or_missing': changed, 'added': added,
        'unstable': sum(row.get('stable') is False for row in actual.values()),
        'unreadable': sum(row.get('readable') is False for row in actual.values())}


def main():
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    roots = {'profile': Path(os.environ['APPDATA']) / 'GrangerPet', 'assets': ROOT / 'grangerpet/assets',
        'resources': ROOT / 'resources', 'gansar': ROOT / 'Gansar-main', 'maigret': ROOT / 'maigret-main',
        'visual_cpu': ROOT / '.toolenvs/visual-cpu', 'scene_vision': ROOT / '.toolenvs/scene-vision',
        'maigret_runtime': ROOT / '.toolenvs/maigret'}
    report = {'at_utc': datetime.now(timezone.utc).isoformat(), 'baseline_head': baseline['head'], 'groups': {}}
    public = {'at_utc': report['at_utc'], 'baseline_head': baseline['head'], 'groups': {},
              'profile_decrypted': False, 'source_files_written': False, 'restored_files': 0}
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, root in roots.items():
            expected = baseline['groups'][name]
            actual = dict(pool.map(lambda path: inspect(path, root), paths(root)))
            comparison = compare(expected, actual)
            report['groups'][name] = comparison
            summary = {key: comparison[key] for key in ('expected', 'actual', 'unchanged', 'unstable', 'unreadable')}
            summary.update(changed_or_missing=len(comparison['changed_or_missing']), added=len(comparison['added']))
            if name != 'profile':
                summary['current_tree_sha256'] = tree_digest({k: {a: v.get(a) for a in ('sha256', 'bytes')} for k, v in actual.items()})
            public['groups'][name] = summary
            print(json.dumps({'group': name, **summary}), flush=True)
    report['pet_runtime'] = {}
    for name, checksum in baseline['pet_runtime'].items():
        path = ROOT / name
        report['pet_runtime'][name] = {'baseline_sha256': checksum, 'current_sha256': digest(path) if path.is_file() else None}
    public['pet_runtime'] = {'expected': len(report['pet_runtime']),
        'unchanged': sum(row['baseline_sha256'] == row['current_sha256'] for row in report['pet_runtime'].values())}
    report['release'] = {}
    for name, row in baseline['release'].items():
        checks = {}
        for kind, path in (('current', ROOT / 'dist' / name), ('archive', ROOT / 'dist/archive/before-master-fix-v3' / name)):
            checks[kind] = {'sha256': digest(path), 'bytes': path.stat().st_size} if path.is_file() else None
        checks['baseline'] = row
        report['release'][name] = checks
    public['release'] = {name: {'baseline_sha256': rows['baseline']['sha256'],
        'current_matches_baseline': rows['current'] == rows['baseline'], 'archive_matches_baseline': rows['archive'] == rows['baseline']}
        for name, rows in report['release'].items()}
    public['seconds'] = round(time.monotonic() - started, 2)
    destination = ROOT / 'output/master-fix-v3' / ('preservation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'private-comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (destination / 'preservation-summary.json').write_text(json.dumps(public, indent=2), encoding='utf-8')
    print(json.dumps({'summary': public, 'private_output_folder': destination.name}), flush=True)


if __name__ == '__main__':
    main()
