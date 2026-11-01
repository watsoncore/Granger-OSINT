"""Live public-source checks via the actual registry; never fixtures or saved keys."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Previous evidence preserved;choose a new output folder')
    args.output.mkdir(parents=True)
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.investigation_analysis import analyze,factual_report
    from grangerpet.evidence_graph import build
    registry=ToolRegistry(Settings(ai_provider='none'),secret_getter=lambda name:'')
    plan=[('ip_lookup',{'address':'66.249.67.41'}),('network_rdap',{'resource':'66.249.67.41'}),
        ('network_reverse_dns',{'address':'66.249.67.41'}),('network_routing',{'resource':'66.249.67.41'}),
        ('network_reputation',{'address':'66.249.67.41'}),('threat_feodo',{'address':'66.249.67.41'}),
        ('domain_dns',{'domain':'example.org'}),('domain_rdap',{'domain':'example.org'}),
        ('domain_certificates',{'domain':'example.org'})]
    rows=[]
    def save(name,data):(args.output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for tool,arguments in plan:
        started=time.monotonic();result=registry.execute(tool,arguments)
        save(tool+'.json',result)
        row={'tool':tool,'arguments':arguments,'status':result['status'],'observed_at':result['obtained_at'],
            'records':len(result['results']),'seconds':round(time.monotonic()-started,3),
            'error_code':result.get('error_code'),'limitations':result.get('limitations',[]),'test_type':'live HTTPS via production registry'}
        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    records=registry.evidence.records();ip_records=[r for r in records if (r.get('details') or {}).get('address')=='66.249.67.41' or (r.get('details') or {}).get('query')=='66.249.67.41']
    analysis=analyze({'goal':'Исследуй 66.249.67.41','evidence':ip_records})
    save('analysis.json',analysis);save('graph.json',build(ip_records,full=True,limit=5000,goal='Исследуй 66.249.67.41'))
    (args.output/'ip-profile.md').write_text(factual_report(analysis,language_unavailable=True),encoding='utf-8')
    mandatory=[r for r in rows if r['tool']!='domain_certificates']
    save('report.json',{'at':datetime.now(timezone.utc).isoformat(),'test_type':'live','llm_requests':0,
        'saved_user_keys_used':False,'checks':rows,'mandatory_passed':all(r['records']>0 and r['status'] in ('complete','partial') for r in mandatory),
        'live_sources_with_records':sorted({r.get('platform') for r in records}),
        'limitations':['External source availability is time-specific; CT timeout is not a negative certificate result.','This CLI is not a native EXE test or an LLM-led investigation.']})


if __name__=='__main__':main()
