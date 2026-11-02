"""Evaluate saved, licensed camera-geotagged controls with both installed CPU models."""
import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from PIL import Image, ImageOps
    from grangerpet.geoint.skyline import extract, fit_dem
    from grangerpet.visual_models.manager import get_manager
    from grangerpet.visual_models.pipeline import haversine_km

    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--terrain', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    manager = get_manager()
    try:
        for case in manifest['cases']:
            if case['status'] != 'downloaded':
                continue
            raw = (args.manifest.parent / case['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != case['sha256']:
                raise ValueError('Input SHA mismatch')
            with Image.open(io.BytesIO(raw)) as image:
                converted = ImageOps.exif_transpose(image).convert('RGB')
                converted.info.clear()
                buffer = io.BytesIO()
                converted.save(buffer, format='PNG')
            blind = buffer.getvalue()
            truth = case['annotated_coordinate']
            result = {'id':case['case_id'],'class':case['class'],'source':case['source']['source_url'],
                'license':case['source']['license'],'ground_truth_kind':case['ground_truth_kind'],
                'archive_camera_lat_lon':truth,'original_sha256':case['sha256'],
                'pixel_input_sha256':hashlib.sha256(blind).hexdigest(),'seed':0,'samples':32,'models':{}}
            for model in ('geoclip','waypoint'):
                start = time.monotonic()
                value = manager.infer(model, blind, top_k=5, samples=32, seed=0, deadline=start+120)
                metrics = []
                for prediction in value.get('predictions',[]):
                    coordinate = [prediction.get('lat',prediction.get('latitude')),prediction.get('lon',prediction.get('longitude'))]
                    metrics.append({'candidate':coordinate,'distance_to_archive_camera_m':round(haversine_km(coordinate, truth)*1000)})
                result['models'][model] = {'status':value.get('status'),'error_code':value.get('error_code'),
                    'seconds':round(time.monotonic()-start,2),'predictions':metrics}
            if case['class']=='natural_landscape':
                trace=extract(blind)
                result['pixel_trace_status']=trace['status']
                result['alternative_regions']={}
                for name in ('Medeu','Dolomites'):
                    terrain=json.loads((args.terrain/f'terrain-{name}.json').read_text(encoding='utf-8'))
                    result['alternative_regions'][name]=fit_dem(trace,terrain)
            (args.output/(case['case_id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(case['case_id'],{key:row['status'] for key,row in result['models'].items()},flush=True)
    finally:
        manager.close()


if __name__=='__main__':
    main()
