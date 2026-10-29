"""Explicit live reads through the existing ToolRegistry, no credentials.

Run with --live. Only fixed documentation examples are queried. Raw reports are
saved under ignored output/; failed and partial results remain visible.
"""
from pathlib import Path
import argparse
from datetime import datetime,timezone
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings

CASES=[('mail_dns',{'email':'info@example.org'}),
       ('x_post',{'url':'https://x.com/jack/status/20'}),
       ('x_profile',{'username':'jack'}),
       ('arctic_posts',{'subreddit':'announcements','after':'2020-01-01','before':'2021-01-01','limit':2}),
       ('arctic_comments',{'author':'PresidentObama','after':'2012-01-01','before':'2013-01-01','limit':2}),
       ('historical_contacts',{'domain':'example.org','max_snapshots':1})]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live:parser.error('Use --live to authorize the fixed bounded public API reads')
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    destination=ROOT/'output'/'integrations19'/'registry-live';destination.mkdir(parents=True,exist_ok=True)
    summary={'fixture':False,'started_at':datetime.now(timezone.utc).isoformat(),'operations':[]}
    for name,arguments in CASES:
        result=registry.execute(name,arguments,deadline=time.monotonic()+25)
        (destination/(name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        summary['operations'].append({'tool':name,'status':result['status'],'evidence_count':len(result.get('evidence_ids',[])),
            'result_count':len(result.get('results',[])),'error_code':result.get('error_code',''),'report':name+'.json'})
        print(name,result['status'],len(result.get('results',[])),flush=True)
    summary['saved_evidence_count']=len(registry.evidence.records())
    (destination/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':main()
