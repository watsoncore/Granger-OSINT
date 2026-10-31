"""Curate public pet-release checks; exclude profiles, logs and gateway state."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'output/pet-scenes'


def main():
    def read(name):return json.loads((QA/name).read_text(encoding='utf-8'))
    exe=ROOT/'dist/Granger-OSINT.exe';sha=hashlib.sha256(exe.read_bytes()).hexdigest()
    native=read('exe-verified-final/report.json');smoke=read('smoke-position-final.json')
    sources=read('frozen-position-sources.json');assets=read('frozen-position-assets.json')
    before=read('idle-before/report.json');after=read('idle-position-after/report.json')
    if not native.get('passed') or native.get('exe_sha256')!=sha or native.get('manual_visual_review')!='reviewed':
        raise ValueError('Final actual EXE and screenshot review required')
    if not all(c['passed'] for c in native['checks']):raise ValueError('A native scenario failed')
    soak=native.get('soak',{})
    if soak.get('elapsed_seconds',0)<300 or not soak.get('natural_actions_during_130s_typing'):
        raise ValueError('Actual five-minute soak and natural typing scenario required')
    if smoke.get('status')!='passed' or smoke['sha256']!=sha:raise ValueError('Final EXE smoke mismatch')
    if not sources['passed'] or not assets['passed'] or assets['exe_sha256']!=sha:raise ValueError('Frozen source/asset mismatch')
    if not before['passed'] or not after['passed'] or after['exe_sha256']!=sha:raise ValueError('Native idle measurements required')
    full=(QA/'backend-full.log').read_text(encoding='utf-8');target=(QA/'targeted-position-final.log').read_text(encoding='utf-8')
    counts=re.search(r'(\d+) passed, (\d+) skipped, (\d+) subtests passed',full)
    focused=re.search(r'(\d+) passed',target)
    scale=(QA/'scale-regression.log').read_text(encoding='utf-8')
    if not re.search(r'1 passed',scale) or 'failed' in scale:raise ValueError('Actual cameo scale regression required')
    if not counts or not focused or 'failed' in full[-1000:] or 'failed' in target[-1000:]:raise ValueError('Passing regressions required')
    if subprocess.check_output(['git','diff','9f3430c','--','frontend'],cwd=ROOT):raise ValueError('Frontend changed; do not reuse previous UI validation')
    values=[s.get('private_commit_bytes_sum') for s in soak['samples'] if s.get('private_commit_bytes_sum') is not None]
    allocation=read('renderer-allocation.json');preservation=read('profile-preservation.json')
    summary={'mode':'actual frozen EXE and native Windows/Qt; no application API calls',
        'exe':{'bytes':exe.stat().st_size,'sha256':sha},
        'backend_full':{'passed':int(counts[1]),'skipped':int(counts[2]),'subtests':int(counts[3]),'skip':'Ollama not running'},
        'latest_pet_regressions':int(focused[1]),'additional_scale_regression':1,'native_checks':native['checks'],
        'source_modules':len(sources['modules']),'resource_checks':len(assets['assets']),
        'frontend':'Source unchanged from 9f3430c; existing production bundle verified byte-for-byte in EXE',
        'idle_before':before['summary'],'idle_after':after['summary'],
        'idle_measurement_limits':'Three five-second samples, same size/FPS/cursor settings, hidden workspace. No broad performance guarantee.',
        'soak':{'elapsed_seconds':soak['elapsed_seconds'],'samples':len(soak['samples']),
            'natural_actions_during_typing':soak['natural_actions_during_130s_typing'],
            'distinct_render_signatures':soak['distinct_render_signatures'],
            'adjacent_visible_pairs':soak['adjacent_visible_pairs'],'adjacent_render_changes':soak['adjacent_render_changes'],
            'timer_count_min':min(soak['owned_timer_counts']),'timer_count_max':max(soak['owned_timer_counts']),
            'private_commit_first':values[0],'private_commit_last':values[-1],
            'limit':'Five actual minutes plus deterministic three-day scheduler simulation; no multi-hour Windows run claimed'},
        'raster_allocation_profile':allocation,'profile_preservation':preservation,
        'retained_failures':['Early QA ran with the existing dock collapsed and correctly suppressed the figure.',
            'First cameo fitting used transparent square bounds and was too conservative for a 241px dock; fixed using opaque bounds.',
            'Native drag trace exposed duplicate presses replacing collar identity; fixed and regression tested.',
            'An intermediate natural-start QA followed a forced preview of every scene and encountered their valid cooldowns; final natural-start QA uses an actual restart with no shortened clocks.',
            'A later five-minute run observed natural reading/wand scenes but its unique-frame-cardinality assertion was invalid for looping atlases; final QA compares adjacent visible render observations.',
            'Harry ImageGen output was blocked twice; deterministic native derivation is documented instead of claiming generated success.'],
        'original_character_assets':'12 original protected files unchanged; only a new scenes subdirectory was added',
        'public_evidence_files':['pet-regressions.log','scale-regression.log']}
    out=QA/'release-public';out.mkdir(exist_ok=True)
    (out/'release-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    for source,dest in (('frozen-position-sources.json','frozen-sources.json'),('frozen-position-assets.json','frozen-assets.json'),
        ('backend-full.log','tests-release-verified.log'),('targeted-position-final.log','pet-regressions.log'),
        ('scale-regression.log','scale-regression.log'),('freeze-position.log','freeze-delivery.log')):
        shutil.copy2(QA/source,out/dest)
    shutil.copy2(QA/'smoke-position-final.json',ROOT/'dist/binarysmoke.json')
    print(json.dumps({'native_checks':len(native['checks']),'exe_sha256':sha,'source_profiles_published':0}))


if __name__=='__main__':main()
