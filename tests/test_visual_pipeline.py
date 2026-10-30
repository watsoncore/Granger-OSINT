"""Sequential adapter orchestration with real geometry and bounded fixtures.

These tests do not claim live ML inference. Optional model QA is separate.
"""
import copy
import io
import math
import threading
import time
from types import SimpleNamespace

from PIL import Image
import pytest

from grangerpet.geoint import AttachmentStore
from grangerpet.visual_models import pipeline

IDENTIFIER = 'img_'+'a'*64


def record(capability, **data):
    return {'id': capability, 'type': 'image_analysis', 'status': 'metadata' if capability == 'image_metadata' else 'hypothesis',
            'details': {'tool': capability, 'capability': capability, **data}}


def envelope(*records, status='complete', **values):
    return {'status': status, 'results': list(records), **values}


@pytest.fixture
def adapters(monkeypatch):
    called = []
    metadata = record('image_metadata', metadata={'gps': {'latitude': 0, 'longitude': 0, 'authenticity_verified': False}})
    def geo(name, value, **kwargs):
        called.append((name, value, kwargs))
        return envelope(copy.deepcopy(metadata) if name == 'image_metadata' else record('image_ocr', text='Тест: Москва'))
    def model(name, args, **kwargs):
        called.append((name, args, kwargs))
        return envelope(record(name, predictions=[{'lat': 0, 'lon': 1 if name == 'geoclip_predict' else 2, 'raw_score': 90}]))
    monkeypatch.setattr(pipeline.geoint_tools, 'execute', geo)
    monkeypatch.setattr(pipeline.geoint_tools, 'readiness', lambda *args: {'available': True})
    monkeypatch.setattr(pipeline.visual_tools, 'execute', model)
    return called, metadata


def run(**args):
    return pipeline.execute({'attachment_id': IDENTIFIER, 'include_scene':False, **args}, SimpleNamespace(), object(),
                            deadline=time.monotonic()+5)


def test_order_shared_deadline_options_and_records_emitted_before_next_stage(adapters):
    called, _ = adapters
    received = []
    deadline = time.monotonic()+5
    result = pipeline.execute({'attachment_id': IDENTIFIER, 'include_scene':False, 'top_k': 3, 'seed': 7, 'samples': 16},
        settings='settings', store='store', deadline=deadline, on_result=lambda row: received.append((row, len(called))))
    assert result['status'] == 'complete'
    assert [name for name, *_ in called] == ['image_metadata', 'image_ocr', 'geoclip_predict', 'waypoint_predict']
    assert [count for _, count in received] == [1, 2, 3, 4, 4]
    assert all(kwargs['deadline'] == deadline and kwargs['store'] == 'store' for _, _, kwargs in called)
    assert called[2][1] == {'attachment_id': IDENTIFIER, 'top_k': 3, 'seed': 7, 'samples': 16}
    assert received[-1][0]['status'] == 'computed'
    assert received[-1][0]['details']['capability'] == 'visual_geoint_comparison'
    assert result['results'][1]['details']['text'] == 'Тест: Москва'


def test_selected_model_and_disabled_ocr_do_not_run_unrequested_stages(adapters):
    called, _ = adapters
    result = run(include_ocr=False, methods=['waypoint_predict'])
    assert result['status'] == 'complete'
    assert [name for name, *_ in called] == ['image_metadata', 'waypoint_predict']
    assert len(result['comparison']['distances']) == 1


def test_missing_ocr_is_honest_partial_but_models_and_metadata_survive(adapters, monkeypatch):
    monkeypatch.setattr(pipeline.geoint_tools, 'readiness', lambda *args: {'available': False})
    result = run()
    assert result['status'] == 'partial'
    assert result['stages'][1] == {'tool': 'image_ocr', 'status': 'unavailable', 'error_code': 'ocr_not_installed'}
    assert [row['details']['tool'] for row in result['results'][:3]] == ['image_metadata', *pipeline.METHODS]


def test_model_failure_does_not_fabricate_prediction_or_abort_other_model(adapters, monkeypatch):
    original = pipeline.visual_tools.execute
    monkeypatch.setattr(pipeline.visual_tools, 'execute', lambda name, *args, **kwargs:
        envelope(status='unavailable', error_code='not_installed') if name == 'geoclip_predict' else original(name, *args, **kwargs))
    result = run(include_ocr=False)
    assert result['status'] == 'partial'
    assert result['stages'][1]['error_code'] == 'not_installed'
    assert not any(row['details'].get('capability') == 'geoclip_predict' for row in result['results'])
    assert len(result['comparison']['distances']) == 1


def test_unexpected_stage_error_is_fixed_code_without_exception_secret(adapters, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('Bearer private-example-secret C:\\private\\image')
    monkeypatch.setattr(pipeline.visual_tools, 'execute', fail)
    result = run(include_ocr=False)
    assert result['status'] == 'partial'
    assert result['stages'][1]['error_code'] == 'local_stage_failed'
    assert 'private-example' not in str(result)


@pytest.mark.parametrize('stop', ['cancelled', 'timeout'])
def test_cancel_or_deadline_after_metadata_emits_and_retains_metadata(adapters, stop):
    called, _ = adapters
    event, received = threading.Event(), []
    deadline = time.monotonic()+1
    def collect(row):
        received.append(row)
        if stop == 'cancelled':
            event.set()
        else:
            # No sleep: consume the shared deadline deterministically in a fixture.
            monkey_time[0] = deadline+1
    monkey_time = [time.monotonic()]
    from unittest.mock import patch
    with patch('grangerpet.integrations19.solar.time.monotonic', side_effect=lambda: monkey_time[0]):
        result = pipeline.execute({'attachment_id': IDENTIFIER}, None, object(), event, deadline, collect)
    assert result['status'] == stop and result['error_code'] == stop
    assert result['results'] == received and len(received) == 1
    assert called[0][0] == 'image_metadata' and len(called) == 1
    assert 'comparison' not in result


def test_cancelled_adapter_retains_any_returned_stage_records(adapters, monkeypatch):
    monkeypatch.setattr(pipeline.visual_tools, 'execute', lambda *args, **kwargs:
        envelope(record('geoclip_predict', predictions=[]), status='cancelled'))
    result = run(include_ocr=False)
    assert result['status'] == 'cancelled'
    assert len(result['results']) == 2


def test_cancel_before_first_stage_does_no_work(adapters):
    event = threading.Event(); event.set()
    result = pipeline.execute({'attachment_id': IDENTIFIER}, None, object(), event)
    assert result['status'] == 'cancelled' and not result['results'] and not adapters[0]


@pytest.mark.parametrize('values', [None, {}, {'attachment_id': 'C:/photo.jpg'}, {'attachment_id': IDENTIFIER, 'methods': []},
    {'attachment_id': IDENTIFIER, 'methods': ['waypoint_predict', 'waypoint_predict']},
    {'attachment_id': IDENTIFIER, 'methods': ['unknown']}, {'attachment_id': IDENTIFIER, 'top_k': True},
    {'attachment_id': IDENTIFIER, 'samples': 7}, {'attachment_id': IDENTIFIER, 'seed': -1},
    {'attachment_id': IDENTIFIER, 'include_ocr': 'yes'}, {'attachment_id': IDENTIFIER, 'shadow': []},
    {'attachment_id': IDENTIFIER, 'api_key': 'never-use'}])
def test_invalid_pipeline_arguments_do_no_stage_work(adapters, values):
    result = pipeline.execute(values, None, object())
    assert result['status'] == 'error' and result['error_code'] == 'invalid_arguments'
    assert not adapters[0]


def test_haversine_known_axis_dateline_and_antipodes():
    assert pipeline.haversine_km([0, 0], [0, 1]) == pytest.approx(111.19508, abs=.0001)
    assert pipeline.haversine_km([0, 179.9], [0, -179.9]) == pytest.approx(22.239, abs=.001)
    assert pipeline.haversine_km([0, 0], [0, 180]) == pytest.approx(math.pi*6371.0088)
    assert pipeline.haversine_km([90, 0], [90, 180]) < 1e-9


def test_comparison_preserves_zero_gps_compares_all_candidates_and_only_top_models(adapters):
    result = run(include_ocr=False)
    comparison = result['comparison']
    assert comparison['gps_metadata_coordinate'] == [0, 0]
    assert [row['distance_km'] for row in comparison['distances']] == [111.195, 222.39, 111.195]
    assert len(comparison['conflicts']) == 3
    assert comparison['threshold_semantics'] == 'screening_distance_only'
    assert comparison['models_independent'] is False and comparison['metadata_authenticity_verified'] is False
    assert 'probability' not in str(comparison)


def test_missing_invalid_gps_and_invalid_predictions_are_not_zero_coordinates():
    no_gps = record('image_metadata', metadata={'gps': None})
    first = record('geoclip_predict', predictions=[{'lat': math.nan, 'lon': 0}, {'lat': 0, 'lon': 0}, {'lat': True, 'lon': 1}])
    second = record('waypoint_predict', predictions=[{'lat': 0, 'lon': 1}, {'lat': 99, 'lon': 0}])
    comparison = pipeline.compare_coordinates([no_gps, first, second])
    assert comparison['gps_metadata_coordinate'] is None and comparison['distances'] == []
    first['details']['predictions'][0] = {'lat': 0, 'lon': 1}
    comparison = pipeline.compare_coordinates([no_gps, first, second])
    assert len(comparison['distances']) == 1
    assert comparison['distances'][0]['distance_km'] == 0 and not comparison['conflicts']


def test_shadow_uses_real_local_math_only_for_explicit_measurements(adapters):
    result = run(include_ocr=False, methods=['geoclip_predict'], shadow={
        'datetime_utc': '2024-02-29T13:59:59Z', 'object_height': 10, 'shadow_length': 5,
        'grid_step_deg': 10, 'max_cells': 5})
    shadow = next(row for row in result['results'] if row['details'].get('capability') == 'shadow_regions')
    assert shadow['status'] == 'computed'
    assert shadow['details']['observed_sun_altitude_deg'] == pytest.approx(math.degrees(math.atan(2)))
    assert shadow['details']['regions']['type'] == 'FeatureCollection'
    assert len(shadow['details']['regions']['features']) <= 5
    assert result['status'] == 'complete'
    failed = run(include_ocr=False, shadow={'datetime_utc': '2024-02-29T13:59:59Z'})
    assert failed['status'] == 'partial'
    assert failed['stages'][-1]['error_code'] == 'invalid_arguments'


def test_real_attachment_metadata_without_gps_remains_separate_from_fixture_model(tmp_path, monkeypatch):
    store = AttachmentStore(tmp_path, seal=lambda data: b'test-sealed'+data, open_sealed=lambda data: data[len(b'test-sealed'):])
    encoded = io.BytesIO(); Image.new('RGB', (40, 20), (30, 70, 120)).save(encoded, 'PNG')
    attachment = store.import_bytes(encoded.getvalue(), 'Локальный кадр.png')
    monkeypatch.setattr(pipeline.visual_tools, 'execute', lambda *args, **kwargs:
        envelope(record('geoclip_predict', predictions=[{'lat': 0, 'lon': 1}])))
    result = pipeline.execute({'attachment_id': attachment['id'], 'include_scene':False, 'include_ocr': False, 'methods': ['geoclip_predict']}, None, store)
    assert result['status'] == 'complete'
    metadata, model = result['results']
    assert metadata['status'] == 'metadata' and metadata['details']['image']['width'] == 40
    assert metadata['details']['metadata']['gps'] is None and model['status'] == 'hypothesis'
    assert result['comparison']['distances'] == []
