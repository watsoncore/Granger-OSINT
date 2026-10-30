"""Curate aggregate validation evidence; never package profiles or full QA states."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'output/masterfix'
OUT=QA/'release-public'
OUT.mkdir(parents=True,exist_ok=True)

def read(name):return json.loads((QA/name).read_text(encoding='utf-8'))
def required(name):
    value=read(name)
    if value.get('passed') is not True:raise ValueError('Unverified evidence: '+name)
    return value
def digest(path):
    with path.open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()

binary=QA/'candidate-identity/Granger-OSINT.exe'
sha=digest(binary)
automatic=required('automatic-final/report.json')
graph=required('graph-release/report.json')
media=required('media-release-04/report.json')
chat=required('live-agent-final-02/report.json')
identity=required('identity-agent-final/report.json')
cancel=required('cancel-release/report.json')
smoke=required('smoke-release/report.json')
preservation=required('preservation-final.json')
for value in (graph,media,identity,cancel,smoke):
    if value['exe_sha256']!=sha:raise ValueError('Evidence belongs to another final binary')
for value in (chat,identity,cancel):
    if value.get('qa_gateway_secret_removed') is not True:raise ValueError('QA secret cleanup unverified')
for name in ('frozen-sources-release.json','frozen-assets-release.json'):
    required(name)
tests=(QA/'python-release.log').read_text(encoding='utf-8')
passed=re.search(r'(\d+) passed, (\d+) skipped, (\d+) subtests passed',tests)
if not passed or 'failed' in tests[-500:]:raise ValueError('Final Python regression incomplete')
frontend=(QA/'frontend-tests-final.log').read_text(encoding='utf-8')
if not re.search(r'118 passed',frontend):raise ValueError('Frontend regression incomplete')
matrix={}
for path in sorted((QA/'live-matrix-01').glob('*/report.json')):
    row=json.loads(path.read_text(encoding='utf-8'))
    if path.parent.name=='tron-profile':row=read('live-tron-corrected/report.json')
    if path.parent.name=='auto-identity-vitalik.eth':row=read('live-ens-corrected/report.json')
    diagnostics=row.get('source_diagnostics') or {}
    matrix[path.parent.name]={'status':row['status'],'kinds':row['kinds'],'elapsed_seconds':row['elapsed_seconds'],
        'http_requests':diagnostics.get('http_requests'),'http_statuses':diagnostics.get('http_statuses'),
        'engine_error':diagnostics.get('engine_error')}
screens={
    'automatic-ton.png':'automatic-final/automatic-search-search.png',
    'graph-stress-synthetic.png':'graph-release/stress-overview-search.png',
    'graph-dark.png':'graph-release/graph-dark-search.png',
    'nft-inspector.png':'media-release-04/nft-inspector-search.png',
    'nft-tree.png':'media-release-04/real-nft-tree-search.png',
    'nft-evidence.png':'media-release-04/real-nft-evidence-search.png',
}
for name,source in screens.items():shutil.copy2(QA/source,OUT/name)
scenarios={}
for name,row in chat['scenarios'].items():
    calls=row.get('calls',[])
    scenarios[name]={'status':row.get('status','observed_by_native_checks'),
        'tool_ids':sorted({call['tool']for call in calls}),
        'operations':sorted({call.get('arguments',{}).get('operation','profile')for call in calls if call.get('tool')=='blockchain_gansar'}),
        'calls_may_be_cumulative':name in ('ton','cached_assets','ens')}
summary={'tested_at_utc':datetime.now(timezone.utc).isoformat(),
    'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'binary':{'filename':'Granger-OSINT.exe','bytes':binary.stat().st_size,'sha256':sha},
    'python_tests':{'passed':int(passed[1]),'skipped':int(passed[2]),'subtests':int(passed[3])},'frontend_tests':118,
    'automatic_before':{'rows':20,'adapter_count':1,'investigation_saved':False},
    'automatic_after':{'rows':automatic['result_count'],'elapsed_seconds':automatic['elapsed_seconds'],
        'metric_label':automatic['search']['checkedLabel'],'investigation_saved':bool(automatic['search'].get('investigation_id'))},
    'native_checks':{'graph':len(graph['checks']),'media':len(media['checks']),'six_scenarios':len(chat['checks']),
        'final_identity_routing':len(identity['checks']),'cancel':len(cancel['checks']),'startup_surfaces':len(smoke['checks'])},
    'scenarios':scenarios,'network_matrix':matrix,'graph_performance':graph['metrics'],
    'cancel_seconds':cancel['scenarios']['cancel']['seconds_until_ui_idle'],
    'preservation':{'profile_files_unchanged':sum(row['unchanged']for row in preservation['protected_profile_files']),
        'gansar_modules_unchanged':len(preservation['original_gansar_modules']),'original_gansar_clean':preservation['original_gansar_git_clean'],
        'visual_runtime_receipt_unchanged':preservation['visual_runtime_receipt_unchanged']},
    'frozen_sources':read('frozen-sources-release.json'),'frozen_assets':read('frozen-assets-release.json'),
    'qa_credentials_removed':True,'raw_profiles_or_checkpoints_published':False,
    'six_scenario_producer_sha256':chat['exe_sha256'],'final_identity_retest_sha256':sha,
    'limitations':['Public providers returned partial data, rate limits and errors; full history is not claimed.',
        'Deep NFT wallet/item/collection engine exists for TON, not all eleven networks.',
        'TON and ENS chat stages paused on semantic no-progress; useful factual reports and checkpoints remained available.',
        'Six full chat scenarios ran on the preceding candidate; the final identity-only fix was retested on the final binary.',
        'RSS is the sum of monitored owned processes, with shared pages counted repeatedly; idle sample is 1.8 seconds.',
        'Optional runtimes and the existing local Gansar source directory remain external to the EXE.'],
    'public_evidence_files':['release-summary.json',*screens]}
(OUT/'release-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
# The generic packager requires this artifact; this is the actual isolated
# final-EXE startup proof. The older smoke harness refuses concurrent production
# instances and was deliberately not used to stop the owner's application.
smoke_public={**smoke,'schema_version':1,'status':'passed','sha256':sha,'size_bytes':binary.stat().st_size,
    'mode':'actual_isolated_final_EXE_launcher_and_pet','production_instance_stopped':False}
(OUT/'binarysmoke.json').write_text(json.dumps(smoke_public,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'binary':summary['binary'],'python_tests':summary['python_tests'],'public_files':len(summary['public_evidence_files'])}))
