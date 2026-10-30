"""Bounded public Gansar calls through the production registry, isolated storage."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--address',default='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd')
    p.add_argument('--operation',default='profile')
    p.add_argument('--mode',default='quick')
    p.add_argument('--chain',default='auto')
    p.add_argument('--repeat',action='store_true',help='Test actual NFT/trace resume after registry reconstruction')
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['APPDATA']=str(out/'appdata')
    from grangerpet.config import Settings
    from grangerpet.agent_tools import ToolRegistry
    registry=ToolRegistry(Settings(source_root=str(ROOT)),secret_getter=lambda name:'')
    events=[];start=time.monotonic()
    result=registry.execute('blockchain_gansar',{'address':args.address,'operation':args.operation,'mode':args.mode,'chain':args.chain},on_event=events.append)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    state=registry.checkpoint_state()
    (out/'registry-state.json').write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
    report={'mock':False,'operation':args.operation,'chain':args.chain,'elapsed_seconds':round(time.monotonic()-start,3),
        'status':result['status'],'error':result.get('error'),'count':len(result['results']),
        'kinds':{},'streamed_evidence_events':len(events),'source_diagnostics':result.get('source_diagnostics'),
        'protected_datasets':len(state.get('blockchain_refs',{}))}
    for row in result['results']:
        kind=row.get('type','unknown');report['kinds'][kind]=report['kinds'].get(kind,0)+1
    if state.get('blockchain_refs'):
        restored=ToolRegistry(Settings(source_root=str(ROOT)),secret_getter=lambda name:'')
        restored.restore_investigation(result['results'],state)
        cached=restored.execute('blockchain_gansar',{'address':args.address,'operation':'cached','chain':args.chain})
        report['restored_cache']={'status':cached['status'],'count':len(cached['results']),'source_diagnostics':cached.get('source_diagnostics')}
        if args.repeat:
            repeated=restored.execute('blockchain_gansar',{'address':args.address,'operation':args.operation,'mode':args.mode,'chain':args.chain})
            report['resumed_operation']={'status':repeated['status'],'count':len(repeated['results']),'source_diagnostics':repeated.get('source_diagnostics')}
            (out/'resumed-result.json').write_text(json.dumps(repeated,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
