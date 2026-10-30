"""Read-only code inventory; never loads Gansar databases, sessions or datasets."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True,encoding='utf-8').strip()


def inventory(root):
    files=[];objects=[]
    for path in sorted((root/'app').rglob('*.py')):
        raw=path.read_bytes();tree=ast.parse(raw.decode('utf-8-sig'))
        relative=path.relative_to(root).as_posix()
        files.append({'path':relative,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        for node in tree.body:
            if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
                entry={'path':relative,'name':node.name,'line':node.lineno,'kind':type(node).__name__}
                if isinstance(node,ast.ClassDef):
                    entry['methods']=[child.name for child in node.body if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef))]
                    entry['fields']=[child.target.id for child in node.body if isinstance(child,ast.AnnAssign) and isinstance(child.target,ast.Name)]
                objects.append(entry)
    return {'files':files,'objects':objects,'python_modules':len(files)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gansar',type=Path,default=ROOT.parent/'crypto_osint')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise SystemExit('Preserve prior baseline; choose a new file')
    from grangerpet.config import SettingsStore,data_directory
    settings=SettingsStore().load();binary=ROOT/'dist/Granger-OSINT.exe'
    originals=[];profile=data_directory()
    for directory in ('investigations','conversations','attachments','canvas','vault'):
        for path in sorted((profile/directory).rglob('*')):
            if path.is_file():originals.append({'path':path.relative_to(profile).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    for name in ('settings.json','chat-history.dpapi'):
        path=profile/name
        if path.is_file():originals.append({'path':name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    vendor=inventory(args.gansar)
    report={'head':git(ROOT,'rev-parse','HEAD'),'branch':git(ROOT,'branch','--show-current'),
        'exe':{'bytes':binary.stat().st_size,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()},
        'settings':{name:getattr(settings,name) for name in ('source_root','runtime_python','request_limit','search_timeout','agent_tool_timeout','agent_calls','agent_steps','agent_timeout')},
        'gansar':{'head':git(args.gansar,'rev-parse','HEAD'),'working_tree_clean':not git(args.gansar,'status','--porcelain'),**vendor},
        'legacy_gansar':inventory(ROOT/'Gansar-main'),'profile_files':originals,
        'runtime_receipt_sha256':hashlib.sha256((ROOT/'.toolenvs/visual-cpu/receipt.json').read_bytes()).hexdigest(),
        'no_database_contents_read':True,'no_original_files_modified':True}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'granger_head':report['head'],'gansar_head':report['gansar']['head'],
        'gansar_modules':vendor['python_modules'],'legacy_modules':report['legacy_gansar']['python_modules'],
        'gansar_clean':report['gansar']['working_tree_clean'],'protected_profile_files':len(originals)}))


if __name__=='__main__':main()
