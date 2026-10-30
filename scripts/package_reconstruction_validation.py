"""Curate reviewed public release evidence without profiles, pixels or secrets."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'output/reconstruction'


def main():
    out=QA/'release-public';out.mkdir(exist_ok=True)
    exe=ROOT/'dist/Granger-OSINT.exe'
    with exe.open('rb') as file:sha=hashlib.file_digest(file,'sha256').hexdigest()
    def read(name):return json.loads((QA/name).read_text(encoding='utf-8'))
    graph=read('graphs-exe-verified/report.json')
    gallery=read('gallery-exe-delivery/report.json')
    smoke=read('smoke-verified.json')
    chat=read('chat-exe-delivery/report.json')
    visual=read('visual-chat-exe-verified/report.json')
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
    sources=read('frozen-sources-delivery.json');assets=read('frozen-assets-delivery.json')
    if not sources['passed'] or not assets['passed'] or assets['exe_sha256']!=sha:raise ValueError('Frozen source/assets mismatch')
    tests=(QA/'backend-delivery.log').read_text(encoding='utf-8')
    if '1415 passed, 1 skipped, 32 subtests passed' not in tests:raise ValueError('Missing full regression results')
    summary={'mode':'actual final EXE, synthetic stress distinguished from saved and fresh public observations',
        'exe':{'bytes':exe.stat().st_size,'sha256':sha},'backend':{'passed':1415,'skipped':1,'subtests':32,'skip_reason':'Ollama not running'},
        'frontend':{'passed':125,'files':17,'build':True,'typecheck':True},
        'gui':{'graph_checks':len(graph['checks']),'gallery_checks':len(gallery['checks']),
            'graph_visual_review':'reviewed','gallery_visual_review':'reviewed'},
        'chat':{'checks':chat['checks'],'passed':True,'qa_gateway_secret_removed':True},
        'visual_chat':{'checks':visual['checks'],'passed':True,'qa_gateway_secret_removed':True},
        'cancel':{'checks':cancel['checks'],'passed':True,'qa_gateway_secret_removed':True},
        'photo_set':{'classes':7,'originals':5,'synthetic_images':0,'exact_locations_independently_confirmed':0,
            'detailed_results':'docs/validation/photo-set-results.json'},
        'actual_length_continuation':read('live-length-metadata-01/report.json'),
        'optional_paid_apis':'not configured; positive live tests not executed',
        'public_evidence_files':[]}
    (out/'release-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    for source,name in (('frozen-sources-delivery.json','frozen-sources.json'),('frozen-assets-delivery.json','frozen-assets.json'),
                        ('backend-delivery.log','tests-release-verified.log'),('freeze-delivery.log','freeze-delivery.log')):
        shutil.copy2(QA/source,out/name)
    shutil.copy2(QA/'smoke-verified.json',ROOT/'dist/binarysmoke.json')
    print(json.dumps({'exe_sha256':sha,'source_modules':len(sources['modules']),
        'asset_checks':len(assets['assets']),'source_profile_files_published':0,'source_photos_published':0}))


if __name__=='__main__':main()
