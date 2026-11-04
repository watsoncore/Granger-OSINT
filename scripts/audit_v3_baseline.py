"""Private byte snapshot and read-only protected-resource audit for Master Fix V3."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/master-fix-v3/baseline'


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def files(root):
    if not root.is_dir():return []
    result=[]
    for folder,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=[n for n in dirs if not Path(folder,n).is_symlink() and not Path(folder,n).is_junction()]
        result.extend(Path(folder,n) for n in names if not Path(folder,n).is_symlink())
    return result


def main():
    raise SystemExit('Retired one-off V3 snapshot: it copied protected profiles and created dist/archive. Use the current cleanup/preservation workflow; do not recreate historical releases.')
    if OUT.exists():raise SystemExit('Preserve previous baseline; choose a new directory in code')
    OUT.mkdir(parents=True)
    roots={'profile':Path(os.environ['APPDATA'])/'GrangerPet','assets':ROOT/'grangerpet/assets',
        'resources':ROOT/'resources','gansar':ROOT/'Gansar-main','maigret':ROOT/'maigret-main',
        'visual_cpu':ROOT/'.toolenvs/visual-cpu','scene_vision':ROOT/'.toolenvs/scene-vision',
        'maigret_runtime':ROOT/'.toolenvs/maigret'}
    report={'at_utc':datetime.now(timezone.utc).isoformat(),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'groups':{}}
    # This copy contains actual original protected bytes, not a hash-only backup.
    # The application may still be running. Capture every version read stably;
    # never restore or rewrite its source files.
    root=roots['profile'];rows={}
    for path in files(root):
        name=path.relative_to(root).as_posix();attempts=[]
        for attempt in range(3):
            try:
                before=path.stat();data=path.read_bytes();after=path.stat()
            except OSError:attempts.append({'readable':False});break
            stable=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
            dest=OUT/'private-profile-copy'/f'attempt-{attempt+1}'/name
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            checksum=hashlib.sha256(data).hexdigest();assert sha(dest)==checksum
            attempts.append({'sha256':checksum,'bytes':len(data),'stable':stable,'backup':dest.relative_to(OUT).as_posix()})
            if stable:break
        rows[name]={'versions':attempts}
    report['groups']['profile']=rows
    print(json.dumps({'group':'profile','files':len(rows),'stable_copies':sum(any(v.get('stable') for v in row['versions']) for row in rows.values())}),flush=True)
    for name,root in roots.items():
        if name=='profile':continue
        start=time.monotonic()
        def inspect(path):
            before=path.stat();checksum=sha(path);after=path.stat()
            return path.relative_to(root).as_posix(),{'sha256':checksum,'bytes':after.st_size,'stable':(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)}
        with ThreadPoolExecutor(max_workers=8) as pool:rows=dict(pool.map(inspect,files(root)))
        report['groups'][name]=rows
        print(json.dumps({'group':name,'files':len(rows),'bytes':sum(r['bytes'] for r in rows.values()),'unstable':sum(not r['stable'] for r in rows.values()),'seconds':round(time.monotonic()-start,2)}),flush=True)
    tracked=subprocess.check_output(['git','ls-files','grangerpet'],cwd=ROOT,text=True).splitlines()
    protected=[n for n in tracked if Path(n).parent==Path('grangerpet') and (Path(n).name.startswith(('pet','original','scene_','chibi','cameo')) or Path(n).name in ('animation.py','motion.py','sprite.py','sprites.py','painted_arms.py','key_poses.py','solo_sequence.py','prop_choreography.py'))]
    report['pet_runtime']={n:sha(ROOT/n) for n in protected}
    report['release']={n:{'sha256':sha(ROOT/'dist'/n),'bytes':(ROOT/'dist'/n).stat().st_size} for n in ('Granger-OSINT.exe','Granger-OSINT-source.zip')}
    (OUT/'private-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    # Previous release remains at its normal path throughout development.
    archive=ROOT/'dist/archive/before-master-fix-v3';archive.mkdir(parents=True,exist_ok=True)
    for name,row in report['release'].items():
        dest=archive/name
        if dest.exists():assert sha(dest)==row['sha256']
        else:shutil.copy2(ROOT/'dist'/name,dest)
        assert sha(dest)==row['sha256']
    summary={'head':report['head'],'at_utc':report['at_utc'],'profile_files':len(report['groups']['profile']),
        'profile_copy_stable':all(any(v.get('stable') for v in r['versions']) for r in report['groups']['profile'].values()),
        'protected_groups':{n:{'files':len(rows),'bytes':sum(r['bytes'] for r in rows.values()),'unstable':sum(not r['stable'] for r in rows.values())} for n,rows in report['groups'].items() if n!='profile'},
        'protected_pet_modules':len(protected),'release':report['release'],'profile_plaintext_exported':False}
    (OUT/'baseline-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps({'baseline_complete':True,'profile_copy_stable':summary['profile_copy_stable']}),flush=True)


if __name__=='__main__':main()
