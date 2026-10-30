"""Sequential local image observations; importing never initializes ML models.

Metadata, OCR, model hypotheses and measured shadow geometry remain separate
records. A 100 km distance is only a screening threshold, never a truth test.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
import time

from .. import geoint_tools
from ..integrations19 import local_tools
from ..integrations19.solar import LocalToolError, check
from . import tools as visual_tools
from . import scene

METHODS = ('geoclip_predict', 'waypoint_predict')
INPUT_SCHEMA = {'type': 'object', 'properties': {
    **deepcopy(visual_tools._BASE),
    'methods': {'type': 'array', 'minItems': 1, 'maxItems': 2, 'uniqueItems': True,
                'items': {'type': 'string', 'enum': list(METHODS)}},
    'include_ocr': {'type': 'boolean'},
    'include_scene': {'type': 'boolean'},
    'shadow': deepcopy(local_tools.INPUT_SCHEMAS['shadow_regions']),
}, 'required': ['attachment_id'], 'additionalProperties': False}
LIMITATIONS = [
    'GPS из EXIF может быть изменён: метаданные не проверяют подлинность или место съёмки.',
    'Координаты моделей — некалиброванные гипотезы; модели не являются независимыми подтверждениями.',
    'Расстояние свыше 100 км — screening_distance_only для ручной проверки, не установленная ошибка источника.',
]


def _arguments(args):
    if not isinstance(args, dict) or set(args) - set(INPUT_SCHEMA['properties']):
        raise LocalToolError('invalid_arguments', 'Неизвестные параметры visual_geoint.')
    if not isinstance(args.get('attachment_id'), str) or not re.fullmatch(r'img_[a-f0-9]{64}', args['attachment_id']):
        raise LocalToolError('invalid_arguments', 'Нужен идентификатор выбранного изображения.')
    for name, default, minimum, maximum in (('top_k', 5, 1, 10), ('samples', 32, 8, 256), ('seed', 0, 0, 2**31-1)):
        value = args.get(name, default)
        if type(value) is not int or not minimum <= value <= maximum:
            raise LocalToolError('invalid_arguments', f'Некорректный параметр {name}.')
    methods = args.get('methods', list(METHODS))
    if (not isinstance(methods, list) or not 1 <= len(methods) <= 2
            or any(value not in METHODS for value in methods) or len(set(methods)) != len(methods)):
        raise LocalToolError('invalid_arguments', 'Выберите одну или обе поддерживаемые модели без повторов.')
    if (type(args.get('include_ocr', True)) is not bool or type(args.get('include_scene', True)) is not bool
            or 'shadow' in args and not isinstance(args['shadow'], dict)):
        raise LocalToolError('invalid_arguments', 'Некорректные параметры OCR или солнечной геометрии.')
    return methods


def _coordinate(value):
    if not isinstance(value, dict):
        return None
    lat, lon = value.get('latitude', value.get('lat')), value.get('longitude', value.get('lon'))
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (lat, lon)):
        return None
    return [float(lat), float(lon)] if abs(lat) <= 90 and abs(lon) <= 180 else None


def haversine_km(first, second):
    """Great-circle distance using mean Earth radius; handles the dateline."""
    lat1, lat2 = math.radians(first[0]), math.radians(second[0])
    dlat, dlon = lat2-lat1, math.radians(second[1]-first[1])
    arc = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(max(0.0, min(1.0, arc))))


def _computed(capability, data, args, title):
    digest = hashlib.sha256(json.dumps(args, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:24]
    return {'id': capability+':'+digest, 'type': 'local_computation', 'platform': 'Local GEOINT',
        'title': title, 'url': '', 'description': title, 'status': 'computed', 'sources': [capability],
        'details': {**data, 'tool':capability, 'capability': capability, 'attachment_id': args['attachment_id'],
                    'acquisition': 'local_tool', 'execution_mode': 'LOCAL_PYTHON', 'source_record': True}}


def compare_coordinates(records):
    """Compare actual returned coordinates, not invented place names or scores."""
    gps, models = None, {}
    for row in records:
        details = row.get('details', {})
        if not isinstance(details, dict):
            continue
        if details.get('tool') == 'image_metadata':
            metadata = details.get('metadata', {})
            if isinstance(metadata, dict):
                gps = _coordinate(metadata.get('gps'))
        method = details.get('capability')
        if method in METHODS and isinstance(details.get('predictions'), list):
            models[method] = [(index+1, coordinate) for index, item in enumerate(details['predictions'][:10])
                             if (coordinate := _coordinate(item)) is not None]
    distances = []
    def add(kind, left, right, first, second):
        distance = haversine_km(first, second)
        distances.append({'kind': kind, 'from_label': left, 'to_label': right,
            'from_coordinate': first, 'to_coordinate': second, 'distance_km': round(distance, 3),
            'screening_distance_only': distance > 100})
    if gps is not None:
        for method, points in models.items():
            for rank, point in points:
                add('metadata_to_model', 'EXIF GPS (не проверен)', f'{method} #{rank}', gps, point)
    if all(models.get(method) and models[method][0][0] == 1 for method in METHODS):
        add('model_to_model', METHODS[0]+' #1', METHODS[1]+' #1', models[METHODS[0]][0][1], models[METHODS[1]][0][1])
    return {'distances': distances, 'gps_metadata_coordinate': gps, 'metadata_authenticity_verified': False,
        'models_independent': False, 'review_threshold_km': 100, 'threshold_semantics': 'screening_distance_only',
        'conflicts': [item for item in distances if item['screening_distance_only']], 'warnings': list(LIMITATIONS)}


def execute(args, settings, store, cancel_event=None, deadline=None, on_result=None):
    """Run repository adapters in order, emitting records before checking cancel.

    The caller scopes attachment IDs and persists each callback in its existing
    evidence store. A cancellation retains completed rows and reports cancelled.
    """
    started, records, stages, limitations = time.monotonic(), [], [], list(LIMITATIONS)
    envelope = {'tool': 'visual_geoint', 'query': args.get('attachment_id', '') if isinstance(args, dict) else '',
                'results': records, 'stages': stages, 'limitations': limitations}
    def emit(row):
        records.append(row)
        if on_result is not None:
            on_result(row)
    def stage(name, operation):
        check(cancel_event, deadline)
        try:
            outcome = operation()
        except (LocalToolError, geoint_tools.GeointError) as error:
            outcome = {'status': error.code if error.code in ('cancelled', 'timeout') else 'error',
                       'error_code': error.code, 'results': [], 'limitations': [str(error)]}
        except Exception:
            # Neither exception text nor a private path/credential is returned.
            outcome = {'status': 'error', 'error_code': 'local_stage_failed', 'results': []}
        if not isinstance(outcome, dict):
            outcome = {'status': 'error', 'error_code': 'invalid_stage_response', 'results': []}
        stages.append({'tool': name, 'status': outcome.get('status', 'error'), 'error_code': outcome.get('error_code')})
        limitations.extend(str(item) for item in outcome.get('limitations', []) if isinstance(item, str))
        for row in outcome.get('results', []):
            if isinstance(row, dict):
                emit(row)
        if outcome.get('status') in ('cancelled', 'timeout'):
            raise LocalToolError(outcome['status'], 'Последовательный GEOINT-анализ остановлен.')
        check(cancel_event, deadline)
    try:
        methods = _arguments(args)
        stage('image_metadata', lambda: geoint_tools.execute('image_metadata', args['attachment_id'], settings=settings,
                store=store, cancel_event=cancel_event, deadline=deadline))
        if args.get('include_ocr', True):
            check(cancel_event, deadline)
            if geoint_tools.readiness('image_ocr', settings, store).get('available'):
                stage('image_ocr', lambda: geoint_tools.execute('image_ocr', args['attachment_id'], settings=settings,
                        store=store, cancel_event=cancel_event, deadline=deadline))
            else:
                stages.append({'tool': 'image_ocr', 'status': 'unavailable', 'error_code': 'ocr_not_installed'})
                limitations.append('Локальный OCR недоступен; текст изображения не распознан.')
        if args.get('include_scene', True):
            stage('image_understand', lambda: scene.execute({'attachment_id':args['attachment_id']}, store=store,
                cancel_event=cancel_event, deadline=deadline))
        values = {key: args[key] for key in ('attachment_id', 'top_k', 'samples', 'seed') if key in args}
        for method in methods:
            stage(method, lambda name=method: visual_tools.execute(name, values, store=store,
                  cancel_event=cancel_event, deadline=deadline))
        if 'shadow' in args:
            def shadow():
                data = local_tools.execute('shadow_regions', args['shadow'], settings=settings,
                                           cancel_event=cancel_event, deadline=deadline)
                data = local_tools.bound_shadow_evidence(data)
                return {'status': 'complete', 'results': [_computed('shadow_regions', data, args, 'ShadowFinder · солнечная геометрия')],
                        'limitations': data.get('warnings', [])}
            stage('shadow_regions', shadow)
        comparison = compare_coordinates(records)
        envelope['comparison'] = comparison
        if comparison['distances']:
            emit(_computed('visual_geoint_comparison', comparison, args, 'Сравнение географических наблюдений'))
        check(cancel_event, deadline)
        failed = any(item['status'] != 'complete' for item in stages)
        envelope['status'] = 'partial' if failed and records else 'error' if failed else 'complete'
    except LocalToolError as error:
        envelope.update(status=error.code if error.code in ('cancelled', 'timeout') else 'error', error_code=error.code)
        limitations.append(str(error))
    envelope['elapsed_seconds'] = round(time.monotonic()-started, 3)
    return envelope
