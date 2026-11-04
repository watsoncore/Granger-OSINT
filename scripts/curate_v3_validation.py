"""Publish allowlisted V3 receipt aggregates, never private reports or raw logs.

This does not execute tests, publish a release, copy screenshots, or certify a
final build. Missing/in-progress/stale receipts remain explicit. Existing local
receipts are never removed. Override receipt paths when a newer run finishes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
_HASH = re.compile(r'[a-fA-F0-9]{64}')
_STATES = {'complete','completed','partial','empty','error','timeout','cancelled','unavailable','blocked',
           'rate_limited','invalid_arguments','auth_required','interrupted','ready','passed','failed'}
_GROUPS = ('profile','assets','resources','gansar','maigret','visual_cpu','scene_vision','maigret_runtime')


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def integer(value):
    return value if type(value) is int and 0<=value<=10**12 else None


def number(value):
    import math
    return value if type(value) in (int,float) and math.isfinite(value) and 0<=value<=10**12 else None


def checksum(value):
    return value.lower() if isinstance(value,str) and _HASH.fullmatch(value) else None


def boolean(value):
    return value if type(value) is bool else None


def fields(value,names,convert):
    return {key:clean for key in names if key in value and (clean:=convert(value[key])) is not None}


def counts(rows):
    if not isinstance(rows,list):return {'total':0,'passed':0,'failed':0,'unresolved':0}
    return {'total':len(rows),'passed':sum(isinstance(row,dict) and row.get('passed') is True for row in rows),
            'failed':sum(isinstance(row,dict) and row.get('passed') is False for row in rows),
            'unresolved':sum(not isinstance(row,dict) or type(row.get('passed')) is not bool for row in rows)}


def receipt(path,kind,expected_exe=None):
    """Return only a fresh container and its receipt byte hash, never a path."""
    if path is None or not Path(path).is_file():return None,{'kind':kind,'state':'missing'}
    path=Path(path)
    if path.stat().st_size>8_000_000:return None,{'kind':kind,'state':'rejected_oversize'}
    provenance={'kind':kind,'sha256':sha(path),'bytes':path.stat().st_size}
    try:
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict):raise ValueError('Expected object')
    except (ValueError,UnicodeError,OSError):return None,{**provenance,'state':'invalid_receipt'}
    provenance['state']='available'
    if expected_exe and kind.startswith('frozen'):
        recorded=checksum(data.get('exe_sha256'))
        provenance['matches_candidate_binary']=recorded==expected_exe if recorded else None
        if recorded and recorded!=expected_exe:provenance['state']='stale_binary'
        if recorded is None:provenance['state']='unbound_binary'
    return data,provenance


def baseline(value):
    result=fields(value,('profile_files','protected_pet_modules'),integer)
    result.update(fields(value,('profile_copy_stable','profile_plaintext_exported'),boolean))
    groups=value.get('protected_groups',{})
    result['protected_groups']={name:fields(groups[name],('files','bytes','unstable'),integer)
        for name in _GROUPS if isinstance(groups.get(name),dict)}
    result['release']={name:fields(row,('sha256',),checksum)|fields(row,('bytes',),integer)
        for name in ('Granger-OSINT.exe','Granger-OSINT-source.zip') if isinstance((row:=value.get('release',{}).get(name)),dict)}
    return result


def preservation(value):
    result=fields(value,('profile_decrypted','source_files_written'),boolean)|fields(value,('restored_files',),integer)
    groups=value.get('groups',{})
    result['groups']={name:fields(groups[name],('expected','actual','unchanged','unstable','unreadable','changed_or_missing','added'),integer)
        |fields(groups[name],('current_tree_sha256',),checksum) for name in _GROUPS if isinstance(groups.get(name),dict)}
    result['pet_runtime']=fields(value.get('pet_runtime',{}),('expected','unchanged'),integer)
    result['release']={name:fields(row,('baseline_sha256',),checksum)|fields(row,('current_matches_baseline','archive_matches_baseline'),boolean)
        for name in ('Granger-OSINT.exe','Granger-OSINT-source.zip') if isinstance((row:=value.get('release',{}).get(name)),dict)}
    return result


def live_chain(value):
    result=fields(value,('mock',),boolean)|fields(value,('count','streamed_evidence_events','protected_datasets'),integer)|fields(value,('elapsed_seconds',),number)
    if value.get('status') in _STATES:result['status']=value['status']
    kinds=value.get('kinds',{})
    allowed=('blockchain_summary','blockchain_analysis','blockchain_analytics','balance','transaction','blockchain_counterparty',
             'blockchain_context','token_asset','nft_asset','contract_observation','web3_identity')
    result['kinds']=fields(kinds,allowed,integer) if isinstance(kinds,dict) else {}
    diagnostics=value.get('source_diagnostics',{})
    if isinstance(diagnostics,dict):
        result['source_diagnostics']=fields(diagnostics,('providers_attempted','http_requests','request_budget'),integer)|fields(diagnostics,('budget_exhausted','provider_count_complete'),boolean)
        statuses=diagnostics.get('http_statuses',{})
        result['source_diagnostics']['http_statuses']={str(code):n for code in range(100,600)
            if isinstance(statuses,dict) and (n:=integer(statuses.get(str(code)))) is not None}
    cached=value.get('restored_cache',{})
    if isinstance(cached,dict):
        result['restored_cache']=fields(cached,('count',),integer)
        if cached.get('status') in _STATES:result['restored_cache']['status']=cached['status']
        diagnostics=cached.get('source_diagnostics',{})
        if isinstance(diagnostics,dict):result['restored_cache']['source_diagnostics']=fields(diagnostics,('providers_attempted','http_requests'),integer)|fields(diagnostics,('from_saved_data',),boolean)
    return result


def native(value):
    result=fields(value,('mocked','isolated_profile','passed'),boolean)|fields(value,('gateway_calls','owned_processes_left','parent_exit_code'),integer)
    result.update(fields(value,('exe_sha256',),checksum))
    result['checks']=counts(value.get('checks'))
    if isinstance(value.get('coverage'),dict):
        result['coverage']=fields(value['coverage'],('database_total','enabled_username','selected','scheduled','checked','found','not_found','unknown','blocked','unavailable','errors','skipped','pending'),integer)|fields(value['coverage'],('complete','cancelled'),boolean)
    result.update(fields(value,('result_count','progress_snapshots'),integer))
    result['live_tool_runs']=[]
    for row in value.get('live_tools',[]) if isinstance(value.get('live_tools'),list) else []:
        if not isinstance(row,dict):continue
        clean=fields(row,('records',),integer)|fields(row,('seconds',),number)
        if row.get('status') in _STATES:clean['status']=row['status']
        result['live_tool_runs'].append(clean)
    return result


def stress(value):
    result=native(value)
    result['synthetic_cases']=[]
    result['observed_cases']=[]
    for row in value.get('cases',[]) if isinstance(value.get('cases'),list) else []:
        if not isinstance(row,dict):continue
        clean=fields(row,('underlying_nodes','edges'),integer)|fields(row,('encrypted_seed_write_ms','open_and_expand_seconds','active_interval_reciprocal_fps'),number)
        for metric in ('paint_ms','active_intervals_ms','event_to_paint_ms'):
            if isinstance(row.get(metric),dict):clean[metric]=fields(row[metric],('count','min','max','mean','median','p50','p90','p95','p99','total'),number)
        origin='provided_observed_result' if row.get('data_origin')=='provided_observed_result' else 'synthetic_fixture'
        clean['data_origin']=origin
        result['observed_cases' if origin=='provided_observed_result' else 'synthetic_cases'].append(clean)
    result['data_origin']='synthetic_fixture_and_separate_provided_observations' if result['observed_cases'] else 'synthetic_fixture'
    return result


def frozen_sources(value):
    rows=value.get('modules',[])
    return {'passed':boolean(value.get('passed')),'module_count':len(rows) if isinstance(rows,list) else 0,
            'mismatches':sum(isinstance(row,dict) and row.get('source_matches') is False for row in rows) if isinstance(rows,list) else 0}


def frozen_assets(value):
    rows=value.get('assets',[])
    return {'passed':boolean(value.get('passed')),'asset_count':len(rows) if isinstance(rows,list) else 0,
        'failures':sum(isinstance(row,dict) and row.get('matches',row.get('present')) is False for row in rows) if isinstance(rows,list) else 0,
        **fields(value,('exe_sha256',),checksum)}


def test_log(path,kind):
    if path is None or not Path(path).is_file():return {'kind':kind,'state':'missing'}
    path=Path(path)
    # Read bounded tail only; raw stdout/stderr is never copied to public docs.
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-32_000));tail=stream.read().decode('utf-8','replace')
    result={'kind':kind,'receipt_sha256':sha(path),'state':'in_progress'}
    if kind=='backend':
        summaries=re.findall(r'(?m)^([^\n]*\b\d+ (?:passed|failed)[^\n]* in [\d.]+s[^\n]*)$',tail)
        if summaries:
            summary=summaries[-1]
            for number_,status in re.findall(r'(\d+) (passed|failed|skipped|errors?|subtests passed)',summary):
                result[status.replace(' ','_')]=int(number_)
            result['state']='failed' if result.get('failed') or result.get('error') or result.get('errors') else 'passed'
    else:
        match=re.search(r'Tests\s+((?:\d+ (?:passed|failed|skipped)(?:\s*\([^)]*\))?\s*)+)',tail)
        if match:
            for number_,status in re.findall(r'(\d+) (passed|failed|skipped)',match.group(1)):result[status]=int(number_)
            result['state']='failed' if result.get('failed') else 'passed'
    return result


def curate(args):
    base=args.input_root
    binary_sha=sha(args.exe) if args.exe and args.exe.is_file() else None
    result={'schema':'granger-public-validation/1','generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'awaiting_receipts','candidate_exe_sha256':binary_sha,'final_release_certified':False,
        'privacy':{'raw_findings_exported':False,'renderer_state_exported':False,'profile_paths_exported':False,
                   'raw_logs_exported':False,'screenshots_copied':False},'receipts':{},'warnings':[]}
    selected={'baseline':(base/'baseline/baseline-summary.json',baseline),
        'preservation':(args.preservation,preservation),'native_source':(args.native_source,native),
        'frozen_canvas':(args.frozen_canvas,native),'frozen_stress':(args.stress,stress),
        'frozen_maigret':(args.frozen_maigret,native),'frozen_sources':(args.frozen_sources,frozen_sources),
        'frozen_assets':(args.frozen_assets,frozen_assets)}
    for chain in ('btc','solana','tron'):selected['live_'+chain]=(base/'gansar-live'/chain/'report.json',live_chain)
    for kind,(path,project) in selected.items():
        value,provenance=receipt(path,kind,binary_sha)
        result['receipts'][kind]={'receipt':provenance,**({'summary':project(value)} if value is not None else {})}
    result['tests']={'backend':test_log(args.backend_log,'backend'),'frontend':test_log(args.frontend_log,'frontend')}
    missing=[name for name,row in result['receipts'].items() if row['receipt']['state']!='available']
    failures=[name for name,row in result['receipts'].items() if row.get('summary',{}).get('passed') is False]
    unfinished=[name for name,row in result['tests'].items() if row['state']!='passed']
    if failures or any(row['state']=='failed' for row in result['tests'].values()):result['status']='needs_attention'
    elif not missing and not unfinished:result['status']='receipts_collected'
    result['pending_receipts']=missing
    result['failed_receipts']=failures
    result['unfinished_test_runs']=unfinished
    if any(row['receipt'].get('state')=='stale_binary' for row in result['receipts'].values()):result['warnings'].append('Some frozen receipts belong to another candidate binary.')
    result['warnings'].append('Aggregate receipts are not a final release declaration or an unbounded real-world coverage claim.')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',type=Path,default=ROOT/'output/master-fix-v3')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/validation/master-fix-v3')
    parser.add_argument('--exe',type=Path)
    for name in ('preservation','native-source','frozen-canvas','stress','frozen-maigret','frozen-sources','frozen-assets','backend-log','frontend-log'):
        parser.add_argument('--'+name,type=Path)
    args=parser.parse_args();base=args.input_root
    defaults={'native_source':base/'native-source-final/report.json','frozen_canvas':base/'frozen-canvas-final/report.json',
        'stress':base/'frozen-stress/report.json','frozen_maigret':base/'frozen-maigret-final/report.json',
        'frozen_sources':base/'frozen-sources-final.json','frozen_assets':base/'frozen-assets-final.json',
        'backend_log':base/'backend-delivery.log','frontend_log':base/'frontend-final.log'}
    for key,value in defaults.items():
        if getattr(args,key) is None:setattr(args,key,value)
    if args.preservation is None:
        available=sorted(base.glob('preservation-*/preservation-summary.json'))
        args.preservation=available[-1] if available else None
    summary=curate(args)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'validation-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # PNG review is deliberately separate; do not create, overwrite or infer a
    # screenshot manifest from private native receipts/renderer states.
    print(json.dumps({'status':summary['status'],'pending_receipts':summary['pending_receipts'],
        'failed_receipts':summary['failed_receipts'],'unfinished_test_runs':summary['unfinished_test_runs'],
        'final_release_certified':False},ensure_ascii=False))


if __name__=='__main__':main()
