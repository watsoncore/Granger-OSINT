"""Public aggregation must neither leak private receipts nor bless stale builds."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

from scripts.curate_v3_validation import curate,test_log as summarize_log


def configuration(tmp_path):
    base=tmp_path/'private';base.mkdir()
    args=NS(input_root=base,exe=None,preservation=None,native_source=None,frozen_canvas=None,stress=None,
        frozen_maigret=None,frozen_sources=None,frozen_assets=None,backend_log=None,frontend_log=None)
    return args


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    return path


def test_allowlisted_public_projection_excludes_profiles_findings_renderer_and_log_data(tmp_path):
    args=configuration(tmp_path)
    forbidden='PRIVATE-CANARY-USER-DIALOG-API-KEY'
    args.preservation=write(args.input_root/'preservation-report.json',{
        'profile_decrypted':False,'groups':{'profile':{'expected':185,'actual':185,'unchanged':185,
            'filename':forbidden,'profile_path':'C:/Users/private/'+forbidden}},'private_raw':forbidden})
    args.native_source=write(args.input_root/'native.json',{'passed':True,'origin':forbidden,'isolated_profile':True,
        'checks':[{'name':forbidden,'passed':True}], 'screenshots':[{'name':forbidden,'sha256':'a'*64}],
        'renderer':{'chat':forbidden},'live_tools':[{'tool':forbidden,'status':'partial','records':3,'limitations':[forbidden]}]})
    for chain in ('btc','solana','tron'):
        write(args.input_root/'gansar-live'/chain/'report.json',{'status':'partial','count':3,
            'kinds':{'transaction':2,forbidden:1},'address':forbidden,
            'source_diagnostics':{'providers_attempted':2,'http_requests':7,'http_statuses':{'200':6,'429':1,forbidden:1},
                                  'headers':{'Authorization':forbidden},'provider_ids':[forbidden]}})
    args.backend_log=args.input_root/'backend.log'
    args.backend_log.write_text(forbidden+'\n205 passed in 14.95s\n',encoding='utf-8')
    before={p:p.read_bytes() for p in args.input_root.rglob('*') if p.is_file()}
    result=curate(args)
    serialized=json.dumps(result,ensure_ascii=False)
    assert forbidden not in serialized and 'C:/Users' not in serialized
    assert 'screenshots' not in result['receipts']['native_source']['summary']
    assert result['receipts']['native_source']['summary']['checks']=={'total':1,'passed':1,'failed':0,'unresolved':0}
    assert result['receipts']['live_btc']['summary']['source_diagnostics']['http_statuses']=={'200':6,'429':1}
    assert result['tests']['backend']['passed']==205
    assert result['final_release_certified'] is False
    assert all(path.read_bytes()==raw for path,raw in before.items())


def test_current_candidate_hash_marks_old_frozen_pass_receipt_stale(tmp_path):
    args=configuration(tmp_path)
    args.exe=tmp_path/'candidate.exe';args.exe.write_bytes(b'current candidate')
    args.frozen_canvas=write(args.input_root/'old-frozen.json',{'passed':True,'exe_sha256':'a'*64,'checks':[{'passed':True}]})
    result=curate(args)
    frozen=result['receipts']['frozen_canvas']
    assert frozen['summary']['passed'] is True
    assert frozen['receipt']['state']=='stale_binary' and frozen['receipt']['matches_candidate_binary'] is False
    assert 'frozen_canvas' in result['pending_receipts'] and result['status']=='awaiting_receipts'
    assert result['final_release_certified'] is False


def test_in_progress_and_failed_test_logs_are_not_promoted_to_passed(tmp_path):
    args=configuration(tmp_path)
    args.backend_log=tmp_path/'running.log'
    args.backend_log.write_text('................................................................ [72%]\n',encoding='utf-8')
    assert summarize_log(args.backend_log,'backend')['state']=='in_progress'
    args.frontend_log=tmp_path/'front.log'
    args.frontend_log.write_text('Tests  1 failed | 164 passed (165)\n',encoding='utf-8')
    result=curate(args)
    assert result['tests']['frontend']['state']=='failed'
    assert result['status']=='needs_attention'
    args.backend_log.write_text('1 failed, 1928 passed, 2 skipped, 32 subtests passed in 376.61s (0:06:16)\n',encoding='utf-8')
    summary=summarize_log(args.backend_log,'backend')
    assert summary['state']=='failed' and summary['failed']==1 and summary['passed']==1928 and summary['subtests_passed']==32


def test_failed_stress_receipt_stays_failed_and_exports_only_numeric_metrics(tmp_path):
    args=configuration(tmp_path)
    args.stress=write(tmp_path/'stress.json',{'passed':False,'error':'C:/private/original secret',
        'cases':[{'underlying_nodes':100,'edges':120,'renderer':{'private':'secret'},
            'event_to_paint_ms':{'p95':45.1,'private':'secret'}}]})
    result=curate(args)
    assert result['status']=='needs_attention' and result['failed_receipts']==['frozen_stress']
    stress=result['receipts']['frozen_stress']['summary']
    assert stress['synthetic_cases']==[{'underlying_nodes':100,'edges':120,'event_to_paint_ms':{'p95':45.1},'data_origin':'synthetic_fixture'}]
    assert 'error' not in stress and 'renderer' not in json.dumps(stress)
