"""Run the final native acceptance groups sequentially in isolated QA profiles."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--groups',nargs='+',choices=['network-context','steam','graphs','site-social','browser','local-pixels'],help='Run only named groups in the same sequential order')
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('Choose a fresh batch directory')
    args.output.mkdir(parents=True)
    checks=[
        ('network-context','qa_intelligence_exe.py',['--v2-group','network-context']),
        ('steam','qa_intelligence_exe.py',['--v2-group','steam']),
        ('graphs','qa_reconstruction_graphs.py',['--master-fix-v2','--only','actual-geoint','actual-steam-v2','actual-network-v2','synthetic-1000']),
        ('site-social','qa_intelligence_exe.py',['--v2-group','site-social']),
        ('browser','qa_intelligence_exe.py',['--v2-group','browser']),
        ('local-pixels','qa_reconstruction_exe.py',['--integrations19']),
    ]
    results=[]
    for name,script,options in checks:
        if args.groups and name not in args.groups:
            continue
        folder=args.output/name
        command=[sys.executable,'-X','utf8',str(ROOT/'scripts'/script),'--exe',str(args.exe.resolve()),
                 '--output',str(folder.resolve()),*options]
        start=time.monotonic()
        with (args.output/(name+'.log')).open('wb') as log:
            process=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        results.append({'group':name,'exit_code':process.returncode,'seconds':round(time.monotonic()-start,2)})
        (args.output/'batch.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps(results[-1]),flush=True)
        if process.returncode:
            raise SystemExit(process.returncode)


if __name__=='__main__':
    main()
