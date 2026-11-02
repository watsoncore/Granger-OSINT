"""Actual passive network controls. No user profile, source key or caller-IP lookup."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.network_report import profiles,markdown
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--only-prefix',action='store_true');args=p.parse_args()
    if args.output.exists():raise SystemExit('Prior receipts preserved')
    args.output.mkdir(parents=True);registry=ToolRegistry(Settings(),secret_getter=lambda _: '');summary=[]
    cases=[('network_geoip','66.249.67.41'),('network_geoip','87.199.131.94'),('network_rdap','31.0.0.0/16'),('network_rdap','87.199.131.94')]
    if args.only_prefix:cases=[('network_rdap','31.0.0.0/16')]
    try:
        for index,(tool,value) in enumerate(cases):
            start=time.monotonic();field='address' if tool=='network_geoip' else 'resource'
            result=registry.execute(tool,{field:value},deadline=start+45)
            (args.output/f'{index+1}-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            rows=result.get('results',[])
            summary.append({'timestamp':datetime.now(timezone.utc).isoformat(),'tool':tool,'target':value,'status':result.get('status'),
                'evidence_count':len(rows),'seconds':round(time.monotonic()-start,3),'source_diagnostics':result.get('source_diagnostics'),
                'observations':[{key:row.get('details',{}).get(key) for key in ('source_observed_at','body_sha256','geoip','registration_match','registry_entities')} for row in rows]})
            (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'tool':tool,'target':value,'status':result.get('status'),'count':len(rows)},ensure_ascii=False),flush=True)
        (args.output/'report.md').write_text(markdown(profiles(registry.evidence.records())),encoding='utf-8')
    finally:registry.close()


if __name__=='__main__':main()
