"""Read actual previously observed CDX snapshots; never treat CDX as profile data."""
import argparse
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.socmint_targets import vk
    from grangerpet.socmint_public import vk_observation
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise SystemExit('Prior receipts preserved')
    if args.input.stat().st_size>2_000_000:raise SystemExit('Input too large')
    saved=json.loads(args.input.read_text(encoding='utf-8-sig'))
    if saved.get('tool')!='web_archive':raise SystemExit('Expected an actual archive tool receipt')
    args.output.mkdir(parents=True);registry=ToolRegistry(Settings(),secret_getter=lambda _: '');summary=[]
    try:
        for index,record in enumerate(saved.get('results',[])[:2]):
            url=record['url']
            if urlsplit(url).hostname!='web.archive.org':raise ValueError('Unexpected archive origin')
            original=record['details']['original_url'];target=vk(original)
            registry.web_reader.allow_url(url)
            page=registry.execute('web_read',{'url':url},deadline=time.monotonic()+35)
            observed=vk_observation(target,page)
            (args.output/f'{index+1}-page.json').write_text(json.dumps(page,ensure_ascii=False,indent=2),encoding='utf-8')
            summary.append({'url':url,'original_url':original,'snapshot_timestamp':record['details'].get('timestamp'),
                'page_status':page.get('status'),'page_error':page.get('error_code') or page.get('error'),
                'verified_profile_content':bool(observed.get('results')),'profile_status':observed.get('status'),
                'profile_error':observed.get('error_code'),'limitations':page.get('limitations',[])})
            (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(summary[-1],ensure_ascii=False),flush=True)
    finally:registry.close()


if __name__=='__main__':main()
