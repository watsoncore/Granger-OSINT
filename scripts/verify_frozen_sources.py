"""Confirm packaged app bytecode matches the source being delivered."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import CodeType

ROOT = Path(__file__).resolve().parents[1]


def normalized(code):
    return code.replace(co_filename='<verified-source>', co_consts=tuple(
        normalized(value) if isinstance(value, CodeType) else value for value in code.co_consts))


def main():
    from PyInstaller.archive.readers import CArchiveReader
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=ROOT / 'dist/GrangerPet.exe')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/agent-qa/frozen-sources.json')
    args = parser.parse_args()
    archive = CArchiveReader(str(args.exe))
    name = next(name for name in archive.toc if name.endswith('.pyz'))
    pyz = archive.open_embedded_archive(name)
    results = []
    for path in sorted((ROOT / 'grangerpet').rglob('*.py')):
        module = '.'.join(path.relative_to(ROOT).with_suffix('').parts)
        if module.endswith('.__init__'):
            module = module[:-9]
        if module not in pyz.toc:
            continue
        frozen = pyz.extract(module)
        source = compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec', optimize=1, dont_inherit=True)
        match = normalized(frozen) == normalized(source)
        results.append({'module': module, 'source_matches': match})
    report = {'method': 'Compare actual PyInstaller embedded Python code objects with optimize=1 compiled delivered source; normalize filenames only',
              'passed': bool(results) and all(item['source_matches'] for item in results), 'modules': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'modules': len(results),
                      'mismatches': [item['module'] for item in results if not item['source_matches']]}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
