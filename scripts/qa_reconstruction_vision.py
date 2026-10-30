"""Actual production image pipeline in isolated encrypted attachment storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scene-only', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('QA output already exists; do not rerun inference implicitly.')
    out = args.output.resolve()
    out.mkdir(parents=True)
    os.environ['APPDATA'] = str(out/'appdata')
    from grangerpet.geoint_tools import attachment_store
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.visual_models.manager import get_manager
    store = attachment_store()
    attachment = store.import_bytes(args.image.read_bytes(), args.image.name)
    registry = ToolRegistry(Settings(source_root=str(ROOT)), attachment_ids=[attachment['id']], image_store=store,
        secret_getter=lambda _: '')
    started = time.monotonic()
    result = registry.execute('image_understand' if args.scene_only else 'visual_geoint', {'attachment_id':attachment['id']},
        deadline=time.monotonic()+300)
    get_manager().close()
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    scenes = [row['details'] for row in result.get('results', []) if row.get('details', {}).get('tool') == 'image_understand']
    report = {'mock':False, 'mode':'actual_cpu_production_registry', 'image_sha256':attachment['sha256'],
        'width':attachment['width'], 'height':attachment['height'], 'image_uploaded':False,
        'status':result['status'], 'error':result.get('error'), 'elapsed_seconds':round(time.monotonic()-started, 3),
        'scene_descriptions':[row['description'] for row in scenes],
        'regions':[row.get('observations') for row in scenes],
        'model_results':[{key:row['details'].get(key) for key in ('tool', 'model_version', 'predictions', 'status')}
            for row in result.get('results', []) if isinstance(row.get('details'), dict)]}
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('model_results', 'regions')}, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
