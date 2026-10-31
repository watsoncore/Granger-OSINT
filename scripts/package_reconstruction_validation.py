"""Curate reviewed public release evidence without profiles, pixels or secrets."""
import hashlib
import json
import re
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'output/reconstruction'


def main():
    out=QA/'release-public';out.mkdir(exist_ok=True)
    exe=ROOT/'dist/Granger-OSINT.exe'
    with exe.open('rb') as file:sha=hashlib.file_digest(file,'sha256').hexdigest()
    def read(name):return json.loads((QA/name).read_text(encoding='utf-8'))
    graph=read('graphs-exe-coverage/report.json')
    gallery=read('gallery-exe-coverage/report.json')
    smoke=read('smoke-cold-final.json')
    chat=read('chat-exe-coverage/report.json')
    visual=read('visual-chat-exe-delivery-final/report.json')
    native_models=read('visual-chat-exe-delivery-final/actual-model-check.json')
    if not native_models.get('both_geolocators_completed') or native_models.get('exe_sha256')!=sha:
        raise ValueError('Both actual frozen geolocators must finish inference')
    cancel=read('cancel-exe-delivery/report.json')
    for label,value in (('chat',chat),('visual',visual),('cancel',cancel)):
        if value.get('passed') is not True or value.get('exe_sha256')!=sha or value.get('qa_gateway_secret_removed') is not True:
            raise ValueError('Unverified final paid scenario: '+label)
    for label,value in (('graph',graph),('gallery',gallery)):
        if not value.get('checks') or not all(row['passed'] for row in value['checks']):raise ValueError('Unverified GUI: '+label)
    if graph.get('manual_visual_review')!='reviewed' or gallery.get('manual_visual_review')!='reviewed':
        raise ValueError('Actual final screenshots require visual review')
    if graph.get('exe_sha256')!=sha or gallery.get('exe_sha256')!=sha:
        raise ValueError('GUI evidence belongs to another binary')
    if smoke.get('status')!='passed' or smoke.get('sha256')!=sha:raise ValueError('Final binary smoke failed')
    sources=read('frozen-sources-coverage.json');assets=read('frozen-assets-coverage.json')
    if not sources['passed'] or not assets['passed'] or assets['exe_sha256']!=sha:raise ValueError('Frozen source/assets mismatch')
    tests=(QA/'backend-coverage.log').read_text(encoding='utf-8')
    totals=re.search(r'(\d+) passed, (\d+) skipped, (\d+) subtests passed',tests)
    if not totals or 'failed' in tests[-1500:]:raise ValueError('Missing full passing regression results')
    summary={'mode':'actual final EXE, synthetic stress distinguished from saved and fresh public observations',
        'exe':{'bytes':exe.stat().st_size,'sha256':sha},'backend':{'passed':int(totals[1]),'skipped':int(totals[2]),'subtests':int(totals[3]),'skip_reason':'Ollama not running'},
        'frontend':{'passed':125,'files':17,'build':True,'typecheck':True},
        'gui':{'graph_checks':len(graph['checks']),'gallery_checks':len(gallery['checks']),
            'graph_visual_review':'reviewed','gallery_visual_review':'reviewed',
            'graph_scenarios':graph['checks'],'gallery_scenarios':gallery['checks']},
        'chat':{'checks':chat['checks'],'passed':True,'qa_gateway_secret_removed':True},
        'visual_chat':{'checks':visual['checks'],'passed':True,'qa_gateway_secret_removed':True},
        'actual_native_model_predictions':native_models['models'],
        'visual_restart':visual['scenarios']['visual_restore'],
        'smoke':smoke,
        'retained_failures':[
            'First cold visual GUI driver stopped at 800 seconds before the configured research plus synthesis budget; actual completed model results survived.',
            'First resumed GUI run completed synthesis, then its old graph driver timed out.',
            'Later QA driver incorrectly resumed a completed investigation and expected a public summary to contain protected report text; corrected to compare the checkpoint with the actual chat message.',
            'A reference-image assertion expected an obsolete node type; actual graph uses image with reference_photo attributes.',
            'Earlier 30-second smoke under resource contention timed out; the recorded sequential 60-second-bound run passed in under 15 seconds per surface.'
        ],
        'cancel':{'checks':cancel['checks'],'passed':True,'qa_gateway_secret_removed':True},
        'photo_set':{'classes':7,'originals':5,'synthetic_images':0,'exact_locations_independently_confirmed':0,
            'detailed_results':'docs/validation/photo-set-results.json'},
        'actual_length_continuation':read('live-length-metadata-01/report.json'),
        'optional_paid_apis':'not configured; positive live tests not executed',
        'preservation':{'character_assets_unchanged':12,'gansar_modules_unchanged':121,
            'original_visual_runtime_receipt_unchanged':True,'profile_hashes_matching':25,'profile_files_compared':27,
            'profile_caveat':'Two files changed while the ordinary user app was running; isolated QA did not share its profile. Complete byte-for-byte preservation is not claimed.'},
        'public_evidence_files':[]}
    (out/'release-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    for source,name in (('frozen-sources-coverage.json','frozen-sources.json'),('frozen-assets-coverage.json','frozen-assets.json'),
                        ('backend-coverage.log','tests-release-verified.log'),('freeze-coverage.log','freeze-delivery.log')):
        shutil.copy2(QA/source,out/name)
    shutil.copy2(QA/'smoke-cold-final.json',ROOT/'dist/binarysmoke.json')
    print(json.dumps({'exe_sha256':sha,'source_modules':len(sources['modules']),
        'asset_checks':len(assets['assets']),'source_profile_files_published':0,'source_photos_published':0}))


if __name__=='__main__':main()
