"""Serial V9/V10 native measurements with shared generated bitmap fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]


def run(exe,baseline,output,observed_result,observed_profiles,photo_fixture=None):
    from PIL import Image,ImageOps
    output.mkdir(parents=True,exist_ok=False)
    fixtures={}
    for label,size in (('1080p',(1920,1080)),('4k',(3840,2160))):
        path=output/(label+'.jpg')
        if photo_fixture:
            with Image.open(photo_fixture) as source:
                with ImageOps.fit(source.convert('RGB'),size,method=Image.Resampling.LANCZOS) as image:
                    image.save(path,'JPEG',quality=90)
        else:
            with Image.effect_noise(size,40).convert('RGB') as image:image.save(path,'JPEG',quality=90)
        fixtures[label]=path
    variants=[('no-image',[]),('1080p-auto',['--wallpaper',str(fixtures['1080p'])]),
              ('4k-auto',['--wallpaper',str(fixtures['4k'])]),
              ('4k-original-blur-glow',['--wallpaper',str(fixtures['4k']),'--wallpaper-quality','original','--wallpaper-fit','original','--wallpaper-blur','12','--glow','18']),
              ('effects-off',['--effects','off'])]
    report={'schema':'graph-performance-v10/1','passed':False,'cases':[],
            'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
            'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
            'fixtures':{label:{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'kind':'resampled user-supplied reference photograph; tests decoded dimensions, not native photographic detail' if photo_fixture else 'generated textured raster, not user photograph'} for label,path in fixtures.items()},
            'method':'Serial runs; same machine, input gestures, saved datasets and bitmap bytes. No whole-session FPS claim.'}
    def save():(output/'matrix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    for version,binary,styles in (('V10',exe,('glass','minimal')),('V9',baseline,('glass',))):
        for style in styles:
            for name,args in variants:
                target=output/(version.lower()+'-'+style+'-'+name)
                command=[sys.executable,str(ROOT/'scripts/qa_canvas_stress.py'),'--exe',str(binary),'--output',str(target),'--graph-style',style,'--verify-edge-gestures',*args]
                if name=='no-image':
                    command+=['--observed-result',str(observed_result),'--observed-profiles',str(observed_profiles)]
                else:command+=['--counts','500']
                with target.with_suffix('.log').open('wb') as stream:
                    result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
                receipt=json.loads((target/'report.json').read_text(encoding='utf-8')) if (target/'report.json').is_file() else {}
                item={'version':version,'style':style,'variant':name,'passed':result.returncode==0 and receipt.get('passed') is True,'receipt':str(target/'report.json')}
                report['cases'].append(item);save();print(json.dumps(item),flush=True)
                if not item['passed']:raise RuntimeError('Native performance run failed: '+target.name)
    report['passed']=True;save()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--observed-result',type=Path,required=True);p.add_argument('--observed-profiles',type=Path,required=True)
    p.add_argument('--photo-fixture',type=Path,help='Optional supplied photograph; resampled copies remain in the private QA directory')
    a=p.parse_args()
    run(a.exe.resolve(),a.baseline.resolve(),a.output.resolve(),a.observed_result.resolve(),a.observed_profiles.resolve(),a.photo_fixture.resolve() if a.photo_fixture else None)
