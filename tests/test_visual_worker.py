"""Offline protocol/math checks; these do not claim model accuracy/inference.

Reference constants and NMS cases are from pinned Waypoint plonk.rs/onnx.rs.
Optional NumPy/Pillow checks run only when their real CPU runtime is installed.
"""
import base64
import importlib.util
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

import pytest

from grangerpet.visual_models import worker


def request(operation='waypoint', **values):
    return json.dumps({'operation': operation, 'image': base64.b64encode(b'pixels').decode(), **values}).encode()


def test_protocol_decodes_images_and_keeps_utf8_out_of_model_paths():
    parsed = worker.parse_request(request(seed=7, samples=64, top_k=3))
    assert parsed == {'operation': 'waypoint', 'image': b'pixels', 'seed': 7, 'samples': 64, 'top_k': 3}
    pair = worker.parse_request(request('waypoint_match', reference=base64.b64encode(b'reference').decode()))
    assert pair['reference'] == b'reference'
    assert worker.parse_request(b'{"operation":"probe"}') == {'operation': 'probe'}


@pytest.mark.parametrize('payload', [b'', b'[]', b'null', b'{', b'\xff', b'{"operation":"download"}',
    request(image=''), request(image='not base64!!!'), request(image='https://example.org/photo.png'),
    request(top_k=True), request(top_k=0), request(top_k=11), request(samples=7), request(samples=257),
    request(seed=-1), request(seed=2**31), request('waypoint_match')])
def test_invalid_protocol_is_rejected_with_fixed_code(payload):
    with pytest.raises(worker.WorkerError, match='^invalid_request$'):
        worker.parse_request(payload)


def test_models_are_not_imported_by_the_main_app_math_module():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c',
        "import sys; from grangerpet.visual_models import worker; "
        "assert not any(x in sys.modules for x in ('torch','torchvision','transformers','onnxruntime','numpy','PySide6'))"],
        cwd=root, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')


def test_sigmoid_schedule_matches_pinned_rust_reference():
    values = worker.schedule()
    assert len(values) == 251
    assert values[0] == worker.f32(1e-9)
    assert values[1] == pytest.approx(0.0019336405, abs=1e-8)
    assert values[-1] == 1
    assert all(right >= left for left, right in zip(values, values[1:]))
    assert worker.confidence_threshold(0) == pytest.approx(.9, abs=1e-6)
    assert worker.confidence_threshold(1) == pytest.approx(.86411804, abs=1e-6)


def test_splitmix_box_muller_is_gaussian_and_repeatable_like_upstream():
    values = worker.gaussian_noise(200001, 7)
    assert values == worker.gaussian_noise(200001, 7)
    assert values[:10] != worker.gaussian_noise(10, 8)
    assert abs(statistics.mean(values)) < .01
    assert abs(statistics.pvariance(values) - 1) < .01


def test_unit_axes_are_mapped_to_lat_lon_without_swapping():
    assert worker.to_lat_lon([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, -1, 0]]) == [[0, 0], [0, 90], [90, 0], [0, -90]]
    with pytest.raises(worker.WorkerError, match='numerical_output_invalid'):
        worker.to_lat_lon([[math.nan, 0, 1]])


def test_haversine_dbscan_preserves_noise_fraction_and_sample_counts():
    # A Moscow cluster, a Paris cluster, and two isolated model samples.
    coordinates = [[55.75, 37.61], [55.8, 37.5], [55.7, 37.7], [55.77, 37.65],
        [48.85, 2.35], [48.87, 2.32], [48.9, 2.3], [0, 0], [-30, 100]]
    clusters, noise = worker.cluster_samples(coordinates)
    assert [item['count'] for item in clusters] == [4, 3]
    assert clusters[0]['lat'] == pytest.approx(55.755)
    assert clusters[0]['raw_score'] == pytest.approx(4/9)
    assert all(item['score_type'] == 'sample_fraction_uncalibrated' for item in clusters)
    assert noise == .222


def test_no_clues_dispersed_samples_do_not_fabricate_a_location():
    coordinates = [[-70 + i*20, -150 + i*40] for i in range(8)]
    assert worker.cluster_samples(coordinates) == ([], 1.0)
    clusters, _ = worker.cluster_samples([[0, 179.9], [0.01, -179.9], [-.01, 179.8]])
    assert clusters[0]['dateline_warning'] is True


def _optional_arrays():
    # Install discovery here does not initialize the worker or run .pth scripts.
    root = Path(__file__).resolve().parents[1] / '.toolenvs/visual-cpu/site-packages'
    if importlib.util.find_spec('numpy') is None and (root / 'numpy').is_dir():
        sys.path.insert(0, str(root))
    np = pytest.importorskip('numpy')
    return np


def test_strict_disk_nms_matches_upstream_reference():
    np = _optional_arrays()
    heat = np.full((20, 20), -1, dtype=np.float32)
    for x, y, value in ((10, 10, 3), (12, 10, 2), (5, 5, 1), (1, 1, 9)):
        heat[y, x] = value
    descriptors = np.zeros((128, 20, 20), dtype=np.float32)
    descriptors[0] = np.arange(400).reshape(20, 20) + 1
    xy, desc = worker.select_keypoints(heat, descriptors, 2048)
    assert xy.tolist() == [[10, 10]]
    assert desc.shape == (1, 128) and desc[0, 0] == 1
    assert np.count_nonzero(desc) == 1


def test_disk_top_n_keeps_raster_order_above_n_plus_one_score():
    np = _optional_arrays()
    heat = np.full((12, 50), -1, dtype=np.float32)
    for index in range(6):
        heat[5, 3+index*6] = 1+index
    points, _ = worker.select_keypoints(heat, np.ones((128, 12, 50), dtype=np.float32), 3)
    assert points[:, 0].tolist() == [21, 27, 33]


def test_dinov2_and_disk_preprocessing_follow_pinned_dimensions_and_normalization():
    np = _optional_arrays()
    Image = pytest.importorskip('PIL.Image')
    image = Image.new('RGB', (1201, 601), (255, 128, 0))
    dino = worker.dinov2_input(image)
    assert dino.shape == (1, 3, 336, 336) and dino.dtype == np.float32
    assert dino[0, :, 0, 0] == pytest.approx((np.array([1, 128/255, 0]) - [.485, .456, .406]) / [.229, .224, .225], abs=1e-6)
    tensor, width, height = worker.disk_input(image)
    assert (width, height) == (1024, 512)
    assert tensor.shape == (1, 3, height, width)
    assert tensor[0, :, 0, 0] == pytest.approx([1, 128/255, 0], abs=1e-6)
    tiny, width, height = worker.disk_input(Image.new('RGB', (1, 1)))
    assert tiny.shape == (1, 3, 16, 16)


def test_pixel_input_strips_exif_gps_metadata_and_rejects_corrupt_images():
    _optional_arrays()
    Image = pytest.importorskip('PIL.Image')
    import io
    source = Image.new('RGB', (32, 16), (15, 20, 30))
    exif = Image.Exif()
    exif[274] = 6
    exif[37510] = b'fake GPS and private metadata'
    encoded = io.BytesIO()
    source.save(encoded, format='JPEG', exif=exif)
    image = worker.open_image(encoded.getvalue())
    assert image.size == (16, 32) and image.info == {} and not image.getexif()
    with pytest.raises(worker.WorkerError, match='invalid_image'):
        worker.open_image(b'not an image')


def test_eight_point_geometry_recovers_epipolar_inliers_with_outliers():
    np = _optional_arrays()
    rng = np.random.default_rng(42)
    world = rng.uniform([-2, -1, 4], [2, 1, 10], size=(70, 3))
    angle = .1
    rotation = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
    second = world @ rotation.T + [.8, .1, .05]
    points0 = world[:, :2] / world[:, 2:3] * 500 + [320, 240]
    points1 = second[:, :2] / second[:, 2:3] * 500 + [320, 240]
    points1 += rng.normal(0, .1, points1.shape)
    points1[-15:] = rng.uniform([0, 0], [640, 480], size=(15, 2))
    result = worker.geometric_verification(points0, points1)
    assert result['state'] == 'estimated' and result['inliers'] >= 53
    assert sum(index >= 55 for index in result['inlier_indices']) <= 3
    assert worker.geometric_verification(points0[:5], points1[:5])['state'] == 'insufficient_matches'


def test_network_is_denied_in_disposable_process_without_affecting_test_host():
    result = subprocess.run([sys.executable, '-c',
        "import socket; from grangerpet.visual_models.worker import _deny_network, WorkerError; _deny_network(); "
        "\ntry: socket.getaddrinfo('example.com',443)\nexcept WorkerError as e: assert str(e)=='network_disabled'\nelse: raise AssertionError('network permitted')"],
        capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')


def test_windows_memory_measurement_is_real_or_explicitly_unavailable():
    result = worker.process_memory()
    if sys.platform == 'win32':
        assert 0 < result['process_rss_bytes'] <= result['process_peak_rss_bytes']
        assert result['process_private_bytes'] > 0
    else:
        assert result['process_rss_bytes'] is None
