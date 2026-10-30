"""Reuse exact completed local observations within the current investigation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

TOOLS = frozenset(('image_understand', 'geoclip_predict', 'waypoint_predict', 'waypoint_match'))


def parameters(tool, args):
    result = {'attachment_id': args['attachment_id']}
    if tool in ('geoclip_predict', 'waypoint_predict'):
        result['top_k'] = args.get('top_k', 5)
    if tool == 'waypoint_predict':
        result.update(samples=args.get('samples', 32), seed=args.get('seed', 0))
    if tool == 'waypoint_match':
        result['reference_id'] = args['reference_id']
    return result


def signature(tool, args):
    path = Path(__file__).with_name('scene_manifest.json' if tool == 'image_understand' else 'manifest.json')
    manifest_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    value = [tool, parameters(tool, args), manifest_hash]
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def cached(tool, args, records):
    if tool not in TOOLS:
        return None
    key = signature(tool, args)
    for row in reversed(list(records)):
        details = row.get('details') or {}
        if details.get('local_inference_signature') == key and details.get('status') == 'completed':
            return {'tool': tool, 'status': 'complete', 'query': args['attachment_id'],
                'results': [deepcopy(row)], 'from_saved_data': True, 'inference_calls': 0,
                'limitations': ['Использовано сохранённое локальное наблюдение с теми же параметрами и версией модели; новый inference не выполнялся.']}
    return None
