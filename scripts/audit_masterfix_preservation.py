"""Compare hashes only; never load original investigations or Gansar databases."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
baseline=json.loads((ROOT/'output/masterfix/baseline.json').read_text(encoding='utf-8'))
profile=Path(os.environ['APPDATA'])/'GrangerPet'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
files=[{'path':row['path'],'unchanged':sha(profile/row['path'])==row['sha256']}for row in baseline['profile_files']]
original=ROOT.parent/'crypto_osint'
modules=[{'path':row['path'],'unchanged':sha(original/row['path'])==row['sha256']}for row in baseline['gansar']['files']]
clean=not subprocess.check_output(['git','-C',str(original),'status','--porcelain'],text=True).strip()
receipt=sha(ROOT/'.toolenvs/visual-cpu/receipt.json')==baseline['runtime_receipt_sha256']
report={'passed':all(row['unchanged']for row in files+modules) and clean and receipt,
    'protected_profile_files':files,'original_gansar_modules':modules,'original_gansar_git_clean':clean,'visual_runtime_receipt_unchanged':receipt}
(ROOT/'output/masterfix/preservation-final.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'profile_files':len(files),'unchanged_profile_files':sum(r['unchanged']for r in files),'original_modules':len(modules),'original_gansar_clean':clean,'visual_runtime_receipt_unchanged':receipt}))
