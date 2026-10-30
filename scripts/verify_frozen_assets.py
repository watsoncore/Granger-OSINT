"""Compare real frozen frontend/resources with the files delivered in the source ZIP."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,default=ROOT/'dist/Granger-OSINT.exe')
    parser.add_argument('--output',type=Path,default=ROOT/'output/refinement-qa/frozen-assets.json')
    args=parser.parse_args()
    from PyInstaller.archive.readers import CArchiveReader
    exe=args.exe
    archive=CArchiveReader(str(exe))
    rows=[]
    for path in sorted((ROOT/'frontend/dist').rglob('*')):
        if path.is_file():
            name='frontend\\'+str(path.relative_to(ROOT/'frontend/dist')).replace('/','\\')
            rows.append({'path':name,'matches':name in archive.toc and archive.extract(name)==path.read_bytes()})
    for path in sorted((ROOT/'grangerpet/assets').rglob('*')):
        if path.is_file():
            name=str(path.relative_to(ROOT)).replace('/','\\')
            rows.append({'path':name,'matches':name in archive.toc and archive.extract(name)==path.read_bytes()})
    for directory in ('resources/ocr','resources/third-party/Python-geoint-security'):
        for path in sorted((ROOT/directory).rglob('*')):
            if path.is_file():
                name=str(path.relative_to(ROOT)).replace('/','\\')
                rows.append({'path':name,'matches':name in archive.toc and archive.extract(name)==path.read_bytes()})
    required=('PySide6\\QtWebEngineProcess.exe','PySide6\\resources\\icudtl.dat',
        'PySide6\\resources\\qtwebengine_resources.pak','PySide6\\translations\\qtwebengine_locales\\ru.pak',
        'frontend\\THIRD_PARTY_NOTICES.txt','resources\\Granger-OSINT.ico','resources\\THIRD_PARTY_NOTICES.md')
    for name in required: rows.append({'path':name,'present':name in archive.toc})
    report={'tested_at_utc':datetime.now(timezone.utc).isoformat(),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
        'method':'Read actual PyInstaller CArchive; compare all frontend and character asset bytes, verify runtime resources',
        'passed':all(row.get('matches',row.get('present',False)) for row in rows),'assets':rows}
    out=args.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(rows),'failures':[r['path'] for r in rows if not r.get('matches',r.get('present',False))]}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
