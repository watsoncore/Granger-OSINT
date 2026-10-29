"""Actual no-personal-source-key requests; public fixtures, no private profile."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise SystemExit('Existing evidence preserved')
    registry=ToolRegistry(Settings(ai_provider='none'),secret_getter=lambda name:'')
    cases=[('github_profile',{'username':'octocat'}),('github_users',{'query':'octocat','limit':2}),
        ('github_repositories',{'query':'repo:octocat/Hello-World','limit':2}),('hn_search',{'query':'Python','limit':2}),
        ('hn_profile',{'username':'pg'}),('openlibrary_search',{'query':'python programming','limit':2}),
        ('archive_search',{'query':'title:(The Adventures of Sherlock Holmes) AND mediatype:texts','limit':2}),
        ('wikipedia_search',{'query':'London','limit':2}),('web_search',{'query':'octocat','limit':5})]
    report={'tested_at_utc':datetime.now(timezone.utc).isoformat(),'mock':False,'personal_source_keys_used':False,
        'user_history_or_photos_read':False,'executions':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for tool,arguments in cases:
        outcome=registry.execute(tool,arguments,deadline=time.monotonic()+25)
        report['executions'].append({'tool':tool,'arguments':arguments,'outcome':outcome})
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'tool':tool,'status':outcome['status'],'records':len(outcome['results'])},ensure_ascii=True),flush=True)
    report['live_successes']=[r['tool'] for r in report['executions'] if r['outcome']['status'] in ('complete','empty')]
    report['real_public_records']=len(registry.evidence.records())
    report['basic_keyfree_search_has_evidence']=bool(report['executions'][-1]['outcome']['results'])
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if report['basic_keyfree_search_has_evidence'] else 1


if __name__=='__main__':raise SystemExit(main())
