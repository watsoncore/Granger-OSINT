"""Explicit, keyless live acceptance of registered public source adapters.

Not part of pytest. This makes real requests, sequentially, to the fixed
reviewed APIs using public test identifiers. It never reads user credentials
or the normal application profile. A successful receipt proves the backend
pipeline and encrypted reopen; it does not replace native preview/EXE QA.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def implementation_digest():
    files=['source_adapters.py','source_definitions.py','agent_tools.py',
           'evidence_graph.py','canvas_capabilities.py','tool_manifest.py']
    return {name:hashlib.sha256((ROOT/'grangerpet'/name).read_bytes()).hexdigest() for name in files}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New isolated QA directory')
    parser.add_argument('--providers',nargs='*',help='Provider IDs; defaults to every new V11 adapter')
    args=parser.parse_args()
    if args.output.exists():parser.error('Use a new output directory; existing evidence is never overwritten.')
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.config import Settings
    from grangerpet.research_canvas import new_document, merge_evidence, CanvasStore
    from grangerpet.source_adapters import CONTRACTS
    queries=json.loads((ROOT/'tests/fixtures/public_source_queries_v11.json').read_text(encoding='utf-8'))
    selected=args.providers or list(queries)
    if any(provider not in queries for provider in selected):parser.error('Unknown provider ID')
    args.output.mkdir(parents=True)
    private=args.output/'private-outcomes';private.mkdir()
    store=CanvasStore(InvestigationJournal(args.output/'isolated-investigations'))
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    report={'at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'live ToolRegistry → normalized evidence → typed graph → encrypted save/reopen; not native UI or EXE',
        'implementation_sha256':implementation_digest(),'passed':False,'cases':[]}
    try:
        for provider in selected:
            name='source_'+provider;started=time.monotonic()
            outcome=registry.execute(name,{'query':queries[provider],'limit':3},deadline=time.monotonic()+25)
            (private/(provider+'.json')).write_text(json.dumps(outcome,ensure_ascii=False),encoding='utf-8')
            records=outcome.get('results',[])
            document=new_document('Public provider acceptance '+provider)
            persistence=False;deduplicated=False
            if records:
                merge_evidence(document,records)
                saved=store.save(document,0);reopened=store.load(saved['id'])
                persistence=all(reopened[key]==saved[key] for key in ('entities','relations','evidence'))
                before={key:json.dumps(reopened[key],sort_keys=True) for key in ('entities','relations')}
                merge_evidence(reopened,records)
                deduplicated=all(json.dumps(reopened[key],sort_keys=True)==value for key,value in before.items())
            row={'provider_id':provider,'counting_unit':CONTRACTS[name].provider_id,'adapter_id':name,
                'status':outcome['status'],'error_code':outcome.get('error_code'),
                'observations':len(records),'graph_entities':len(document['entities']),
                'graph_relations':len(document['relations']),'persistence':persistence,'deduplicated':deduplicated,
                'from_saved_data':outcome.get('from_saved_data') is True,
                'seconds':round(time.monotonic()-started,3),'source_diagnostics':outcome.get('source_diagnostics')}
            row['live_execution_passed']=outcome['status']=='complete' and bool(records) and persistence and deduplicated and not row['from_saved_data']
            report['cases'].append(row)
            report['passed']=len(report['cases'])==len(selected) and all(r['live_execution_passed'] for r in report['cases'])
            report['independent_nonempty_live_providers']=len({r['counting_unit'] for r in report['cases'] if r['live_execution_passed']})
            (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(row),flush=True)
    finally:registry.close()
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
