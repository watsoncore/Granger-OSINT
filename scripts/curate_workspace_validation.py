"""Publish an explicit aggregate subset; never profiles, renderer state or findings."""
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'output/investigation-workspace-v1'
PUBLIC=QA/'public'
DOCS=ROOT/'docs/validation/investigation-workspace-v1'


def read(relative):return json.loads((QA/relative).read_text(encoding='utf-8'))


def main():
    PUBLIC.mkdir(exist_ok=True);DOCS.mkdir(parents=True,exist_ok=True)
    published=[]
    def publish(name,value):
        raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
        for location,label in ((ROOT,'<workspace>'),(Path.home(),'<user-profile>')):
            for token in (str(location),location.as_posix(),json.dumps(str(location))[1:-1]):raw=raw.replace(token,label)
        (PUBLIC/name).write_text(raw,encoding='utf-8');(DOCS/name).write_text(raw,encoding='utf-8')
        if name not in published:published.append(name)
    for name in ('delivery-candidate.json','delivery-frozen-sources.json','delivery-frozen-assets.json','regression-equivalence.json'):
        shutil.copy2(PUBLIC/name,DOCS/name);published.append(name)
    for name,relative,keys in (
        ('manual-canvas.json','frozen-canvas-06/report.json',('origin','mocked','isolated_profile','gateway_calls','gateway_generation_checks','ai_reply_characters','ai_immutable_comparison_excludes','checks','live_tools','cached_scope','interrupted_operation','exe_sha256','passed')),
        ('native-dialogs.json','frozen-canvas-04/native-dialogs.json',('origin','exe_sha256','checks','passed')),
        ('gansar-directions.json','frozen-canvas-04/typed-gansar.json',('origin','checked_sender_receiver_relations','directions_match_typed_source_fields','relation_types','all_tool_relations_have_evidence','wallet_owner_not_attested')),
        ('graph-stress.json','frozen-stress-02/report.json',('origin','data_origin','exe_sha256','cases','checks','metric_semantics','passed','owned_processes_left','parent_exit_code')),
        ('layout-algorithm.json','layout-benchmark-01/benchmark.json',('origin','native','fps_measured','cases')),
        ('automatic-graphs.json','frozen-automatic-graphs-01/report.json',('mode','exe_sha256','gateway_calls','inference_calls','checks','manual_visual_review','passed')),
        ('local-models.json','frozen-local-models-01/report.json',('mode','mock','user_data_read','gateway_calls','exe_sha256','checks','metrics','geographic_benchmark','empty_waypoint_control','unavailable_external_sources','passed')),
        ('provider-context.json','frozen-provider-context-02/report.json',('test_kind','exe_sha256','isolated_profile_and_ipc','user_history_read','gateway_available','checks','operations','turns','passed')),
        ('phone-regression.json','frozen-phone-01/report.json',('exe_sha256','checks','isolated_profile','api_requests','passed')),
        ('steam-fresh.json','frozen-steam-01/corrected-report.json',('origin','exe_sha256','gateway_calls','cookies_or_keys','operations','live_item_data_verified','fresh_prices_verified','passed','owned_processes_left','error_type','error','receipt_correction')),
    ):
        if not (QA/relative).is_file():continue
        value=read(relative);publish(name,{k:value[k] for k in keys if k in value})
    previous=read('preservation-delivery-private.json')
    comparison=read('dialog-comparison-nov04-private.json')
    publish('preservation.json',{'protected_groups':{k:v for k,v in previous['groups'].items() if k!='profile'},
        'protected_resources_all_unchanged':all(v['changed']==0 for k,v in previous['groups'].items() if k!='profile'),
        'profile_baseline_files':87,'profile_identical_bytes':85,'missing_transient_lock_files':1,
        'changed_encrypted_dialogs':1,'changed_dialog_plaintext_bytes_equal':comparison.get('plaintext_bytes_equal'),
        'baseline_and_current_ciphertext_copies_retained':True,'user_reports_no_manual_app_changes':True,
        'write_initiator_proven':False,'historical_v2_exception_resolved':False,'plaintext_contents_exported':False})
    logs={
        'python_full':'python-all-03.log',
        'python_latest_focused':'final-group-regression.log',
        'frontend_final':'frontend-tests-all-04.log',
        'frontend_production_build':'frontend-build-06.log',
    }
    counts={}
    for name,relative in logs.items():
        text=(QA/relative).read_text(encoding='utf-8-sig',errors='replace')
        if name.startswith('python'):counts[name]=re.findall(r'\d+ passed[^\r\n]*',text)[-1:]
        elif name=='frontend_final':counts[name]=re.findall(r'Tests\s+\d+ passed[^\r\n]*',text)[-1:]
        else:counts[name]={'passed':'built in' in text and 'error TS' not in text,'warning':'bundle chunk exceeds 500 kB' if '500 kB' in text else None}
    publish('source-tests.json',{'origin':'source','counts':counts,'full_suite_precedes_final_canvas_fixes':True,
        'final_canvas_fixes_verified_in_focused_suite':True,'skips':['Ollama service not running','Second owner pet instance already running at time of full suite']})
    changed=subprocess.check_output(['git','diff','--name-only','54f3f7f','--','grangerpet','frontend/src','tests','scripts'],cwd=ROOT,text=True).splitlines()
    added=subprocess.check_output(['git','ls-files','--others','--exclude-standard','--','grangerpet','frontend/src','tests','scripts'],cwd=ROOT,text=True).splitlines()
    publish('changed-files.json',{'baseline_commit':'54f3f7f','scope':'Application sources, tests and validation scripts; artwork and vendor/runtime trees excluded','files':sorted(set(changed+added))})
    # Fixed own QA screenshots, reviewed separately; no directory-wide exports.
    for relative,name in (
        ('frozen-canvas-06/canvas-after-restart-search.png','manual-canvas-reopened.png'),
        ('frozen-automatic-graphs-01/actual-geoint-graph-search.png','geoint-graph-saved-observations.png'),
        ('frozen-automatic-graphs-01/actual-steam-v2-tree-search.png','steam-tree-saved-observations.png'),
    ):
        shutil.copy2(QA/relative,PUBLIC/name);shutil.copy2(QA/relative,DOCS/name)
        published.append(name)
    for source,name in (('public/secret-scan-delivery.json','secret-scan.json'),('candidate-smoke.json','candidate-smoke.json'),('public/canonical-smoke.json','canonical-smoke.json'),('public/build-environment.json','build-environment.json')):
        publish(name,read(source))
    summary={'curated_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Explicit aggregate acceptance receipts only. Saved/live/fixture origins are separate.',
        'public_evidence_files':sorted([*published,'release-summary.json']),
        'production_commit':'20f035a','all_requested_capabilities_fully_verified':False,
        'limitations':['5000-node native interaction is below the 60 FPS target; see qualified metrics.',
            'Historical dialog write initiator remains unknown; current compared plaintext is unchanged.',
            'Original local-image bytes are not included in portable canvas JSON export.',
            'Fresh Steam complete inventory/prices and all Gansar networks are not established by saved-data controls.']}
    publish('release-summary.json',summary)
    print(json.dumps({'public_files':len(summary['public_evidence_files']),'scope':'explicit aggregate subset'}))


if __name__=='__main__':main()
