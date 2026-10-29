"""Install only the reviewed optional CPU runtime after explicit user consent."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.visual_models.installation import manifest,install,remove_runtime
    from grangerpet.visual_models.manager import default_runtime_root
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=default_runtime_root())
    group=p.add_mutually_exclusive_group()
    group.add_argument('--plan',action='store_true');group.add_argument('--remove',action='store_true')
    p.add_argument('--consent-download',action='store_true');p.add_argument('--confirm-remove',action='store_true');args=p.parse_args()
    if args.plan:print(json.dumps(manifest(),ensure_ascii=True,indent=2));return 0
    if args.remove:
        if not args.confirm_remove:raise SystemExit('Explicit --confirm-remove is required; only the app-owned optional runtime is removed')
        if args.consent_download:raise SystemExit('--remove cannot be combined with --consent-download')
        print(json.dumps(remove_runtime(args.root),ensure_ascii=True));return 0
    if args.confirm_remove:raise SystemExit('--confirm-remove requires --remove')
    if not args.consent_download:raise SystemExit('Explicit --consent-download is required')
    def progress(row):print(json.dumps(row,ensure_ascii=True),flush=True)
    receipt=install(args.root,consent=True,progress=progress)
    print(json.dumps({'status':receipt['status'],'root':str(args.root)}));return 0


if __name__=='__main__':raise SystemExit(main())
