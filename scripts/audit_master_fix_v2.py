"""Read-only preservation baseline and bounded new-project discovery. Never executes vendors."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','.venv','.toolenvs','node_modules','build','dist','output','test-output','__pycache__','.pytest_cache','frontend','grangerpet','docs','resources','tests','scripts','.codex'}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def snapshot(base):
    rows={};total=0
    if not base.is_dir():return rows,0
    for folder,dirs,files in os.walk(base,followlinks=False):
        dirs[:]=[name for name in dirs if not Path(folder,name).is_symlink() and not Path(folder,name).is_junction()]
        for name in sorted(files):
            path=Path(folder,name)
            if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):continue
            try:
                before=path.stat();checksum=digest(path);after=path.stat();total+=after.st_size
                rows[path.relative_to(base).as_posix()]={'sha256':checksum,'bytes':after.st_size,
                    'stable':(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)}
            except OSError as error:rows[path.relative_to(base).as_posix()]={'error':type(error).__name__}
    return rows,total


def discover():
    result=[]
    for folder,dirs,files in os.walk(ROOT,followlinks=False):
        relative=Path(folder).relative_to(ROOT);depth=len(relative.parts)
        dirs[:]=[d for d in dirs if d not in SKIP and not Path(folder,d).is_symlink() and not Path(folder,d).is_junction() and depth<3]
        if depth and any(n in files for n in ('pyproject.toml','setup.py','package.json','requirements.txt','Cargo.toml','go.mod')):
            result.append({'kind':'directory','path':relative.as_posix(),'manifests':[n for n in files if n in ('pyproject.toml','setup.py','package.json','requirements.txt','Cargo.toml','go.mod')],
                'licenses':[n for n in files if n.lower().startswith(('license','copying'))],'executed':False})
        for name in files:
            p=Path(folder,name)
            if p.suffix.lower()!='.zip':continue
            row={'kind':'archive','path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p),'executed':False}
            try:
                with zipfile.ZipFile(p) as archive:
                    entries=archive.infolist();row.update(files=len(entries),expanded_bytes=sum(e.file_size for e in entries),
                        unsafe_paths=sum(e.filename.startswith(('/','\\')) or '..' in Path(e.filename).parts for e in entries),
                        manifests=[e.filename for e in entries if Path(e.filename).name in ('pyproject.toml','setup.py','package.json','requirements.txt','Cargo.toml','go.mod')][:20],
                        licenses=[e.filename for e in entries if Path(e.filename).name.lower().startswith(('license','copying'))][:15])
            except (OSError,zipfile.BadZipFile) as error:row['error']=type(error).__name__
            result.append(row)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--compare',type=Path)
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    tracked=subprocess.check_output(['git','ls-files','grangerpet'],cwd=ROOT,text=True).splitlines()
    locked=[name for name in tracked if Path(name).parent==Path('grangerpet') and
        (Path(name).name.startswith(('pet','original','scene_','chibi','cameo')) or Path(name).name in
         ('animation.py','motion.py','sprite.py','sprites.py','painted_arms.py','key_poses.py','solo_sequence.py','prop_choreography.py'))]
    groups={'profile':Path(os.environ.get('APPDATA',Path.home()))/'GrangerPet','assets':ROOT/'grangerpet/assets',
        'resources':ROOT/'resources','gansar':ROOT/'Gansar-main','visual_cpu':ROOT/'.toolenvs/visual-cpu','scene_vision':ROOT/'.toolenvs/scene-vision'}
    report={'at':datetime.now(timezone.utc).isoformat(),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),'groups':{},'pet_runtime':{name:digest(ROOT/name) for name in locked}}
    summary={}
    for name,path in groups.items():
        started=time.monotonic();rows,size=snapshot(path);report['groups'][name]=rows
        summary[name]={'files':len(rows),'bytes':size,'unstable':sum(not row.get('stable',False) for row in rows.values())}
        print(json.dumps({'group':name,**summary[name],'seconds':round(time.monotonic()-started,2)}),flush=True)
    exe=ROOT/'dist/Granger-OSINT.exe';report['exe']={'sha256':digest(exe),'bytes':exe.stat().st_size}
    (out/'private-preservation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.compare:
        previous=json.loads(args.compare.read_text(encoding='utf-8'));changes={}
        for name,rows in previous['groups'].items():
            now=report['groups'][name];changes[name]={'original_files':len(rows),'changed':sum(now.get(k,{}).get('sha256')!=v.get('sha256') for k,v in rows.items())}
        changes['pet_runtime']={'original_files':len(previous['pet_runtime']),'changed':sum(report['pet_runtime'].get(k)!=v for k,v in previous['pet_runtime'].items())}
        (out/'preservation-summary.json').write_text(json.dumps({'passed':all(not v['changed'] for v in changes.values()),'groups':changes},indent=2),encoding='utf-8')
    else:
        (out/'baseline-summary.json').write_text(json.dumps({'at':report['at'],'head':report['head'],'groups':summary,'protected_pet_modules':len(locked),'exe':report['exe']},indent=2),encoding='utf-8')
        (out/'new-project-inventory.json').write_text(json.dumps(discover(),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
