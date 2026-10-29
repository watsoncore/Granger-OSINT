"""Offline CPU inference in a disposable child, never in the Qt process.

Waypoint's MIT Rust sampler/preprocessing/adaptive LightGlue loop are translated
from commit 502318a7da42bdc38af2ad2f87152492dbf9d671. Published ONNX graphs are
loaded unchanged. The optional eight-point geometric check is our own estimator,
not the upstream seven-point RANSAC. All scores are explicitly uncalibrated.
"""
from __future__ import annotations

import base64
import binascii
import gc
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import sys
import time

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_INPUT = 56_000_000  # two 20 MiB images, base64, plus bounded JSON metadata
MAX_OUTPUT = 1_900_000
MAX_KEYPOINTS = 1024  # explicit CPU budget; upstream defaults to 2048
EARTH_RADIUS_KM = 6371.0
NUM_STEPS = 250
_DLL_HANDLES = []


class WorkerError(Exception):
    """Only fixed codes leave this process; exception details stay private."""


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def schedule(num_steps=NUM_STEPS):
    """Float32 SigmoidScheduler(-7, 3, tau=1), as in upstream plonk.rs."""
    if type(num_steps) is not int or not 1 <= num_steps <= 1000:
        raise ValueError('Invalid schedule length')
    sigmoid = lambda value: f32(1.0 / f32(1.0 + f32(math.exp(-value))))
    start, end = sigmoid(-7.0), sigmoid(3.0)
    denominator = f32(end - start)
    result = []
    for index in range(num_steps + 1):
        t = f32(1.0 - f32(index / num_steps))
        argument = f32(f32(t * 10.0) - 7.0)
        gamma = f32(f32(end - sigmoid(argument)) / denominator)
        result.append(max(f32(1e-9), min(1.0, gamma)))
    return result


def gaussian_noise(count, seed):
    """Upstream SplitMix64 + Box-Muller, including f32 output rounding."""
    if type(count) is not int or not 0 <= count <= 1_000_000 or type(seed) is not int:
        raise ValueError('Invalid noise request')
    mask = (1 << 64) - 1
    state = seed & mask
    def next_value():
        nonlocal state
        state = (state + 0x9E3779B97F4A7C15) & mask
        value = state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        return value ^ (value >> 31)
    output = []
    while len(output) < count:
        u1 = ((next_value() >> 11) + 1.0) / (1 << 53)
        u2 = (next_value() >> 11) / (1 << 53)
        radius, theta = math.sqrt(-2.0 * math.log(u1)), 2.0 * math.pi * u2
        output.extend((f32(radius * math.cos(theta)), f32(radius * math.sin(theta))))
    return output[:count]


def to_lat_lon(vectors):
    result = []
    for vector in vectors:
        if len(vector) != 3 or any(not math.isfinite(float(x)) for x in vector):
            raise WorkerError('numerical_output_invalid')
        x, y, z = (float(value) for value in vector)
        result.append([math.degrees(math.asin(max(-1.0, min(1.0, z)))), math.degrees(math.atan2(y, x))])
    return result


def cluster_samples(coordinates, radius_km=100.0, top_k=5):
    """Bounded DBSCAN, same haversine/min-samples parameters as upstream.

    Arithmetic coordinate means/stds deliberately preserve upstream behavior.
    Dateline-spanning clusters are flagged because arithmetic longitude is then
    misleading. A cluster's sample fraction is not a correctness probability.
    """
    count = len(coordinates)
    if not 1 <= count <= 256 or not 1 <= top_k <= 10 or not 0 < radius_km <= 1000:
        raise ValueError('Invalid cluster request')
    for point in coordinates:
        if len(point) != 2 or any(not math.isfinite(float(x)) for x in point) or not -90 <= point[0] <= 90 or not -180 <= point[1] <= 180:
            raise WorkerError('numerical_output_invalid')
    radians = [(math.radians(lat), math.radians(lon)) for lat, lon in coordinates]
    minimum = max(3, int(count * 0.03))
    neighbors = []
    for lat, lon in radians:
        nearby = []
        for index, (other_lat, other_lon) in enumerate(radians):
            hav = math.sin((lat - other_lat) / 2) ** 2 + math.cos(lat) * math.cos(other_lat) * math.sin((lon - other_lon) / 2) ** 2
            distance = 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(max(0.0, min(1.0, hav))))
            if distance <= radius_km:
                nearby.append(index)
        neighbors.append(nearby)
    labels = [-2] * count  # unvisited, noise=-1
    next_label = 0
    for index in range(count):
        if labels[index] != -2:
            continue
        if len(neighbors[index]) < minimum:
            labels[index] = -1
            continue
        labels[index] = next_label
        pending = list(neighbors[index])
        queued = set(pending)
        cursor = 0
        while cursor < len(pending):
            current = pending[cursor]
            cursor += 1
            if labels[current] == -1:
                labels[current] = next_label
            if labels[current] != -2:
                continue
            labels[current] = next_label
            if len(neighbors[current]) >= minimum:
                for neighbor in neighbors[current]:
                    if neighbor not in queued:
                        pending.append(neighbor)
                        queued.add(neighbor)
        next_label += 1
    clusters = []
    for label in range(next_label):
        points = [point for point, group in zip(coordinates, labels) if group == label]
        lat = sum(point[0] for point in points) / len(points)
        lon = sum(point[1] for point in points) / len(points)
        dateline = max(point[1] for point in points) - min(point[1] for point in points) > 180
        clusters.append({'lat': lat, 'lon': lon,
            'lat_std': math.sqrt(sum((p[0] - lat) ** 2 for p in points) / len(points)),
            'lon_std': math.sqrt(sum((p[1] - lon) ** 2 for p in points) / len(points)),
            'count': len(points), 'raw_score': len(points) / count,
            'weight': round(len(points) / count, 3), 'score_type': 'sample_fraction_uncalibrated',
            'dateline_warning': dateline})
    clusters.sort(key=lambda item: item['count'], reverse=True)
    return clusters[:top_k], round(labels.count(-1) / count, 3)


def parse_request(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_INPUT:
        raise WorkerError('invalid_request')
    try:
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError()
        operation = request.get('operation')
        if operation == 'probe':
            return {'operation': operation}
        if operation not in ('geoclip', 'waypoint', 'waypoint_match'):
            raise ValueError()
        result = {'operation': operation}
        for name in ('image', 'reference') if operation == 'waypoint_match' else ('image',):
            encoded = request.get(name)
            if not isinstance(encoded, str) or not 0 < len(encoded) <= 4 * ((MAX_IMAGE_BYTES + 2) // 3):
                raise ValueError()
            decoded = base64.b64decode(encoded, validate=True)
            if not 0 < len(decoded) <= MAX_IMAGE_BYTES:
                raise ValueError()
            result[name] = decoded
        if operation != 'waypoint_match':
            for key, default, minimum, maximum in (('top_k', 5, 1, 10), ('samples', 32, 8, 256), ('seed', 0, 0, 2**31 - 1)):
                value = request.get(key, default)
                if type(value) is not int or not minimum <= value <= maximum:
                    raise ValueError()
                result[key] = value
        return result
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise WorkerError('invalid_request') from None


def _deny_network():
    """Fail closed even if a library ignores HF/Transformers offline settings."""
    def audit(event, arguments):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.bind', 'socket.sendto'):
            raise WorkerError('network_disabled')
    sys.addaudithook(audit)


def configure_runtime(root):
    """Only the child adds installed wheels/DLL paths; the parent stays clean."""
    root = Path(root).resolve()
    site = root / 'site-packages'
    if not site.is_dir() or not (site / 'numpy').is_dir():
        raise WorkerError('runtime_not_installed')
    sys.path.insert(0, str(site))  # .pth files are deliberately not executed
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
        DO_NOT_TRACK='1', TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2',
        OPENBLAS_NUM_THREADS='2', NUMEXPR_NUM_THREADS='2', CUDA_VISIBLE_DEVICES='',
        PYTHONDONTWRITEBYTECODE='1', HF_HOME=str(root / 'offline-cache'))
    if os.name == 'nt':
        import ctypes
        # PyInstaller's inherited extraction directory must not override the
        # optional wheels' native libraries. Python itself is already loaded.
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        for relative in ('torch/lib', 'numpy.libs', 'pandas.libs', 'torchvision', 'onnxruntime/capi', 'PIL'):
            path = site / relative
            if path.is_dir():
                _DLL_HANDLES.append(os.add_dll_directory(str(path)))
    _deny_network()
    return root


def open_image(data):
    from PIL import Image, ImageOps, UnidentifiedImageError
    import warnings
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > MAX_IMAGE_PIXELS or getattr(source, 'n_frames', 1) != 1:
                    raise WorkerError('invalid_image')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGB')
                # Inference receives pixels only, never EXIF/GPS metadata.
                image.info.clear()
                return image
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise WorkerError('invalid_image') from None


def dinov2_input(image):
    import numpy as np
    from PIL import Image
    width, height = image.size
    side = min(width, height)
    left, top = round((width - side) / 2), round((height - side) / 2)
    resized = image.crop((left, top, left + side, top + side)).resize((336, 336), Image.Resampling.BICUBIC)
    pixels = np.asarray(resized, dtype=np.float32) / np.float32(255.0)
    pixels = (pixels - np.asarray([.485, .456, .406], dtype=np.float32)) / np.asarray([.229, .224, .225], dtype=np.float32)
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[None])


def disk_input(image):
    import numpy as np
    from PIL import Image
    width, height = image.size
    scale = 1024 / max(width, height)
    if scale < 1:
        image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.BILINEAR)
    width, height = image.size
    width, height = max(16, width // 16 * 16), max(16, height // 16 * 16)
    image = image.resize((width, height), Image.Resampling.BILINEAR)
    pixels = np.asarray(image, dtype=np.float32) / np.float32(255.0)
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[None]), width, height


def select_keypoints(heat, descriptors, maximum=MAX_KEYPOINTS):
    """Strict 5x5 NMS and kornia's >kth threshold, preserving raster order."""
    import numpy as np
    height, width = heat.shape
    if height < 5 or width < 5:
        return np.empty((0, 2), dtype=np.float32), np.empty((0, 128), dtype=np.float32)
    center = heat[2:-2, 2:-2]
    maxima = center > 0
    for dy in range(5):
        for dx in range(5):
            if dy != 2 or dx != 2:
                maxima &= center > heat[dy:height - 4 + dy, dx:width - 4 + dx]
    yy, xx = np.nonzero(maxima)
    yy, xx = yy + 2, xx + 2
    if len(xx):
        scores = heat[yy, xx]
        rank = min(maximum + 1, len(scores))
        threshold = np.partition(scores, len(scores) - rank)[len(scores) - rank]
        selected = np.flatnonzero(scores > threshold)[:maximum]
        xx, yy = xx[selected], yy[selected]
    xy = np.stack((xx, yy), axis=1).astype(np.float32)
    desc = descriptors[:, yy, xx].T.copy()
    norms = np.sqrt(np.sum(desc * desc, axis=1, keepdims=True, dtype=np.float32))
    desc /= np.maximum(norms, np.float32(1e-12))
    return xy, desc


def normalize_keypoints(points):
    import numpy as np
    size = np.max(points, axis=0)
    scale = np.max(size) / np.float32(2)
    if not np.isfinite(scale) or scale <= 0:
        raise WorkerError('numerical_output_invalid')
    return np.ascontiguousarray(((points - size / np.float32(2)) / scale)[None], dtype=np.float32)


def confidence_threshold(layer):
    return f32(.8 + .1 * math.exp(-4.0 * layer / 9.0))


def _identity_onnx():
    """Build a 1-element Identity test graph with stdlib protobuf wire format."""
    def varint(value):
        result = bytearray()
        while value > 127:
            result.append((value & 127) | 128)
            value >>= 7
        result.append(value)
        return bytes(result)
    def number(field, value):
        return varint(field << 3) + varint(value)
    def message(field, value):
        return varint((field << 3) | 2) + varint(len(value)) + value
    def info(name):
        dimension = number(1, 1)
        shape = message(1, dimension)
        tensor = number(1, 1) + message(2, shape)  # TensorProto.FLOAT
        return message(1, name) + message(2, message(1, tensor))
    node = message(1, b'x') + message(2, b'y') + message(4, b'Identity')
    graph = message(1, node) + message(2, b'GrangerCPUProbe') + message(11, info(b'x')) + message(12, info(b'y'))
    return number(1, 9) + message(7, graph) + message(8, number(2, 17))


def process_memory():
    """Working set/private usage of this disposable process, in bytes."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t), ('PrivateUsage', ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return {'process_rss_bytes': counters.WorkingSetSize, 'process_peak_rss_bytes': counters.PeakWorkingSetSize,
                'process_private_bytes': counters.PrivateUsage, 'process_peak_private_bytes': counters.PeakPagefileUsage}
    return {'process_rss_bytes': None, 'process_peak_rss_bytes': None,
        'process_private_bytes': None, 'process_peak_private_bytes': None}


def _normalized_eight_point(points0, points1):
    import numpy as np
    def normalize(points):
        center = points.mean(axis=0)
        radius = np.linalg.norm(points - center, axis=1).mean()
        if radius <= 1e-9:
            raise ValueError('Degenerate points')
        scale = math.sqrt(2) / radius
        transform = np.array([[scale, 0, -scale * center[0]], [0, scale, -scale * center[1]], [0, 0, 1]])
        homogeneous = np.column_stack((points, np.ones(len(points))))
        return (transform @ homogeneous.T).T, transform
    a, transform0 = normalize(points0)
    b, transform1 = normalize(points1)
    x, y, u, v = a[:, 0], a[:, 1], b[:, 0], b[:, 1]
    design = np.column_stack((u*x, u*y, u, v*x, v*y, v, x, y, np.ones(len(x))))
    if np.linalg.matrix_rank(design) < 8:
        raise ValueError('Degenerate points')
    _, _, vt = np.linalg.svd(design, full_matrices=len(points0) == 8)
    matrix = vt[-1].reshape(3, 3)
    left, singular, right = np.linalg.svd(matrix)
    singular[-1] = 0
    matrix = transform1.T @ (left @ np.diag(singular) @ right) @ transform0
    norm = np.linalg.norm(matrix)
    if norm <= 1e-15 or not np.isfinite(matrix).all():
        raise ValueError('Degenerate points')
    return matrix / norm


def geometric_verification(points0, points1, seed=0):
    """Bounded normalized eight-point RANSAC with 3px Sampson threshold.

    This checks geometric agreement only. It does not prove a shared location.
    """
    import numpy as np
    points0 = np.asarray(points0, dtype=np.float64)
    points1 = np.asarray(points1, dtype=np.float64)
    count = len(points0)
    if count < 8:
        return {'method': 'normalized_eight_point_ransac', 'state': 'insufficient_matches',
            'inliers': 0, 'inlier_ratio': 0.0, 'inlier_indices': [], 'threshold_px': 3.0}
    h0 = np.column_stack((points0, np.ones(count)))
    h1 = np.column_stack((points1, np.ones(count)))
    rng = np.random.default_rng(seed)
    best = np.zeros(count, dtype=bool)
    best_matrix = None
    def classify(matrix):
        f0, f1 = h0 @ matrix.T, h1 @ matrix
        error = np.sum(h1 * f0, axis=1) ** 2
        denominator = f0[:, 0]**2 + f0[:, 1]**2 + f1[:, 0]**2 + f1[:, 1]**2
        return error / np.maximum(denominator, 1e-15) <= 9.0
    for iteration in range(192):
        try:
            indices = np.arange(count) if iteration == 0 else rng.choice(count, 8, replace=False)
            matrix = _normalized_eight_point(points0[indices], points1[indices])
            inliers = classify(matrix)
            if inliers.sum() > best.sum():
                best, best_matrix = inliers, matrix
                if best.all():
                    break
        except (ValueError, np.linalg.LinAlgError):
            continue
    if best.sum() >= 8:
        try:
            refined = _normalized_eight_point(points0[best], points1[best])
            inliers = classify(refined)
            if inliers.sum() >= best.sum():
                best, best_matrix = inliers, refined
        except (ValueError, np.linalg.LinAlgError):
            pass
    return {'method': 'normalized_eight_point_ransac', 'state': 'estimated' if best_matrix is not None else 'degenerate',
        'inliers': int(best.sum()), 'inlier_ratio': float(best.mean()),
        'inlier_indices': np.flatnonzero(best).tolist(), 'threshold_px': 3.0}


class Runtime:
    """Exactly one component cache; swapping drops heavy sessions/model tensors."""
    def __init__(self, root):
        self.root = Path(root)
        self.component = None
        self.cache = None
        self.stage = 'dependency_import_failed'
        self._manifest = json.loads(Path(__file__).with_name('manifest.json').read_text(encoding='utf-8'))

    def clear(self):
        self.cache = None
        self.component = None
        gc.collect()

    def _switch(self, component):
        if self.component != component:
            self.clear()
        return self.cache

    def _torch(self):
        import torch
        torch.set_num_threads(2)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass  # already fixed during an earlier probe in this same child
        return torch

    def probe(self):
        self.stage = 'dependency_import_failed'
        import importlib.metadata
        import numpy
        import onnxruntime
        import PIL
        import safetensors
        import transformers
        import torchvision
        import geoclip
        torch = self._torch()
        packages = ('numpy', 'onnxruntime', 'Pillow', 'safetensors', 'transformers', 'torch', 'torchvision', 'geoclip')
        versions = {name: importlib.metadata.version(name) for name in packages}
        expected = {item['name'].lower(): item['version'] for item in self._manifest['runtime_packages']}
        if any(version != expected[name.lower()] for name, version in versions.items()):
            raise WorkerError('dependency_version_mismatch')
        if torch.version.cuda is not None:
            raise WorkerError('unexpected_cuda_runtime')
        # A tiny, literal Identity ONNX graph verifies the actual CPU provider,
        # including DLL loading/execution, without loading a pretrained model.
        import numpy as np
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        session = onnxruntime.InferenceSession(_identity_onnx(), sess_options=options, providers=['CPUExecutionProvider'])
        output = session.run(['y'], {'x': np.asarray([1.25], dtype=np.float32)})[0]
        if session.get_providers() != ['CPUExecutionProvider'] or output.tolist() != [1.25]:
            raise WorkerError('cpu_provider_probe_failed')
        return {'status': 'completed', 'operation': 'probe', 'device': 'cpu',
            'versions': versions, 'torch_cuda_runtime': None, 'network_enabled': False,
            'threads': 2, 'models_loaded': False, 'inference_verified': False,
            'onnx_cpu_probe': True, 'execution_providers': session.get_providers()}

    def _geoclip(self):
        if self._switch('geoclip') is not None:
            return self.cache
        self.stage = 'dependency_import_failed'
        torch = self._torch()
        from geoclip import GeoCLIP
        from torch.nn import functional as functional
        self.stage = 'model_load_failed'
        model = GeoCLIP(clip_path=str(self.root / 'models/geoclip/clip')).to('cpu').eval()
        # Exactly the published forward's location encoder + L2 normalization,
        # batched to bound temporary activations for the 100k reference gallery.
        with torch.inference_mode():
            gallery_features = torch.cat([functional.normalize(model.location_encoder(chunk), dim=1)
                for chunk in model.gps_gallery.split(1024)], dim=0)
        self.cache = (model, gallery_features)
        self.component = 'geoclip'
        return self.cache

    def geoclip(self, image, top_k):
        dependency_start = time.perf_counter()
        torch = self._torch()
        from torch.nn import functional as functional
        dependency_ms = round((time.perf_counter() - dependency_start) * 1000, 3)
        was_cached = self.component == 'geoclip' and self.cache is not None
        load_start = time.perf_counter()
        model, gallery = self._geoclip()
        load_ms = 0.0 if was_cached else round((time.perf_counter() - load_start) * 1000, 3)
        self.stage = 'inference_failed'
        inference_start = time.perf_counter()
        with torch.inference_mode():
            pixels = model.image_encoder.preprocess_image(image)
            feature = functional.normalize(model.image_encoder(pixels), dim=1)
            logits = (model.logit_scale.exp() * (feature @ gallery.T))[0]
            if not torch.isfinite(logits).all():
                raise WorkerError('numerical_output_invalid')
            values, indices = torch.topk(logits, top_k)
            probabilities = logits.softmax(dim=0).index_select(0, indices)
            coords = model.gps_gallery.index_select(0, indices)
            predictions = [{'lat': float(point[0]), 'lon': float(point[1]), 'raw_score': float(score),
                'score_type': 'uncalibrated_logit', 'gallery_softmax_uncalibrated': float(probability),
                'gallery_index': int(index)} for point, score, probability, index in zip(coords, values, probabilities, indices)]
        return {'status': 'completed', 'component': 'geoclip', 'predictions': predictions,
            'gallery_size': len(model.gps_gallery), 'device': 'cpu', 'score_calibrated': False,
            'dependency_load_ms': dependency_ms, 'model_load_ms': load_ms,
            'inference_ms': round((time.perf_counter() - inference_start) * 1000, 3),
            'model': 'GeoCLIP-1.3.0/OpenAI-CLIP-ViT-L-14', 'network_enabled': False}

    def _session(self, name):
        self.stage = 'dependency_import_failed'
        import onnxruntime as ort
        self.stage = 'model_load_failed'
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.log_severity_level = 3
        session = ort.InferenceSession(str(self.root / 'models/waypoint' / name),
            sess_options=options, providers=['CPUExecutionProvider'])
        if session.get_providers() != ['CPUExecutionProvider']:
            raise WorkerError('unexpected_execution_provider')
        return session

    def waypoint(self, image, top_k, samples, seed):
        self.stage = 'dependency_import_failed'
        dependency_start = time.perf_counter()
        import numpy as np
        dependency_ms = round((time.perf_counter() - dependency_start) * 1000, 3)
        dino_load_ms = plonk_load_ms = 0.0
        if self._switch('waypoint') is None:
            load_start = time.perf_counter()
            encoder = self._session('dinov2_vitl14_reg.onnx')
            dino_load_ms = round((time.perf_counter() - load_start) * 1000, 3)
            load_start = time.perf_counter()
            step = self._session('plonk_yfcc_step.onnx')
            plonk_load_ms = round((time.perf_counter() - load_start) * 1000, 3)
            self.cache = (encoder, step)
            self.component = 'waypoint'
        encoder, step = self.cache
        self.stage = 'inference_failed'
        embedding_start = time.perf_counter()
        embedding = encoder.run(['emb'], {'pixel_values': dinov2_input(image)})[0]
        embedding_ms = round((time.perf_counter() - embedding_start) * 1000, 3)
        if embedding.shape != (1, 1024) or not np.isfinite(embedding).all():
            raise WorkerError('numerical_output_invalid')
        x = np.asarray(gaussian_noise(samples * 3, seed), dtype=np.float32).reshape(samples, 3)
        times = np.asarray(schedule(), dtype=np.float32)
        sampling_start = time.perf_counter()
        for index in range(NUM_STEPS):
            x = step.run(['x_next'], {'x': x, 'gamma': times[index:index+1],
                'dt': np.asarray([times[index+1] - times[index]], dtype=np.float32), 'emb': embedding})[0]
        sampling_ms = round((time.perf_counter() - sampling_start) * 1000, 3)
        if x.shape != (samples, 3) or not np.isfinite(x).all():
            raise WorkerError('numerical_output_invalid')
        coordinates = to_lat_lon(x)
        clusters, noise = cluster_samples(coordinates, top_k=top_k)
        return {'status': 'completed', 'component': 'waypoint', 'predictions': clusters,
            'sample_coordinates': coordinates, 'sample_count': samples, 'seed': seed, 'steps': NUM_STEPS,
            'cluster_method': 'DBSCAN_haversine_100km', 'noise_frac': noise,
            'device': 'cpu', 'model': 'PLONK_YFCC/DINOv2-ViT-L-14-reg', 'score_calibrated': False,
            'dependency_load_ms': dependency_ms, 'dinov2_load_ms': dino_load_ms,
            'plonk_load_ms': plonk_load_ms, 'embedding_ms': embedding_ms, 'sampling_ms': sampling_ms,
            'network_enabled': False, 'limitations': ['coarse_model_hypotheses', 'sample_fraction_is_not_confidence']}

    def _match_models(self):
        if self._switch('waypoint_match') is None:
            names = ['disk_unet.onnx', 'lg_front.onnx', 'lg_post.onnx', 'lg_assign.onnx']
            names.extend(f'lg_layer{index}.onnx' for index in range(9))
            self.cache = {name: self._session(name) for name in names}
            self.component = 'waypoint_match'
        return self.cache

    def match(self, image, reference):
        self.stage = 'dependency_import_failed'
        import numpy as np
        was_cached = self.component == 'waypoint_match' and self.cache is not None
        load_start = time.perf_counter()
        models = self._match_models()
        load_ms = 0.0 if was_cached else round((time.perf_counter() - load_start) * 1000, 3)
        self.stage = 'inference_failed'
        matching_start = time.perf_counter()
        features, sizes = [], []
        for current in (image, reference):
            tensor, width, height = disk_input(current)
            output = models['disk_unet.onnx'].run(['out'], {'image': tensor})[0]
            if output.shape != (1, 129, height, width) or not np.isfinite(output).all():
                raise WorkerError('numerical_output_invalid')
            features.append(select_keypoints(output[0, 128], output[0, :128]))
            sizes.append([width, height])
            del output, tensor
        (points0, desc0), (points1, desc1) = features
        m, n = len(points0), len(points1)
        common = {'status': 'completed', 'component': 'waypoint_match', 'device': 'cpu',
            'model': 'DISK-depth/LightGlue-DISK', 'keypoints': [m, n], 'input_sizes': sizes,
            'max_keypoints': MAX_KEYPOINTS, 'network_enabled': False, 'score_calibrated': False, 'load_ms': load_ms}
        if not m or not n:
            return {**common, 'matches': [], 'match_count': 0, 'geometry': geometric_verification([], []),
                'feature_matching_ms': round((time.perf_counter() - matching_start) * 1000, 3)}
        d0, d1, e0, e1 = models['lg_front.onnx'].run(['desc0o', 'desc1o', 'enc0', 'enc1'], {
            'kpts0': normalize_keypoints(points0), 'desc0': desc0[None],
            'kpts1': normalize_keypoints(points1), 'desc1': desc1[None]})
        ind0, ind1 = np.arange(m), np.arange(n)
        last_layer = 0
        for layer in range(9):
            last_layer = layer
            d0, d1 = models[f'lg_layer{layer}.onnx'].run(['desc0o', 'desc1o'],
                {'desc0': d0, 'desc1': d1, 'enc0': e0, 'enc1': e1})
            if layer == 8:
                continue
            tok0, tok1, mat0, mat1 = models['lg_post.onnx'].run(['tok0', 'tok1', 'mat0', 'mat1'],
                {'desc0': d0, 'desc1': d1, 'layer': np.asarray(layer, dtype=np.int64)})
            threshold = confidence_threshold(layer)
            below = np.count_nonzero(tok0 < threshold) + np.count_nonzero(tok1 < threshold)
            if np.float32(1) - np.float32(below) / np.float32(m+n) > np.float32(.95):
                break
            for side in (0, 1):
                indices, descriptors, encoding = (ind0, d0, e0) if side == 0 else (ind1, d1, e1)
                if len(indices) <= 1536:
                    continue
                token, matchability = (tok0, mat0) if side == 0 else (tok1, mat1)
                keep = np.flatnonzero((matchability[0] > np.float32(.01)) | (token[0] <= threshold))
                indices, descriptors, encoding = indices[keep], descriptors[:, keep], encoding[:, :, :, keep]
                if side == 0:
                    ind0, d0, e0 = indices, np.ascontiguousarray(descriptors), np.ascontiguousarray(encoding)
                else:
                    ind1, d1, e1 = indices, np.ascontiguousarray(descriptors), np.ascontiguousarray(encoding)
        indices, scores = models['lg_assign.onnx'].run(['matches0', 'mscores0'],
            {'desc0': d0, 'desc1': d1, 'layer': np.asarray(last_layer, dtype=np.int64)})
        valid = np.flatnonzero(indices[0] >= 0)
        other = indices[0, valid]
        if np.any(other >= len(ind1)) or not np.isfinite(scores).all():
            raise WorkerError('numerical_output_invalid')
        a, b = points0[ind0[valid]], points1[ind1[other]]
        matches = [{'point0': left.tolist(), 'point1': right.tolist(), 'raw_score': float(score),
            'score_type': 'lightglue_assignment_uncalibrated'} for left, right, score in zip(a, b, scores[0, valid])]
        geometry = geometric_verification(a, b)
        return {**common, 'matches': matches, 'match_count': len(matches), 'last_layer': last_layer,
            'feature_matching_ms': round((time.perf_counter() - matching_start) * 1000, 3),
            'coordinate_frame': 'resized_disk_input_pixels', 'geometry': geometry,
            'limitations': ['geometric_agreement_does_not_prove_location', 'eight_point_geometry_differs_from_upstream_seven_point']}

    def dispatch(self, request):
        started = time.monotonic()
        operation = request['operation']
        cached = self.component == operation and self.cache is not None
        if operation == 'probe':
            response = self.probe()
        else:
            self.stage = 'invalid_image'
            image = open_image(request['image'])
            if operation == 'geoclip':
                response = self.geoclip(image, request['top_k'])
            elif operation == 'waypoint':
                response = self.waypoint(image, request['top_k'], request['samples'], request['seed'])
            else:
                reference = open_image(request['reference'])
                response = self.match(image, reference)
            response['input_sha256'] = hashlib.sha256(request['image']).hexdigest()
        response['elapsed_seconds'] = round(time.monotonic() - started, 3)
        response['duration_ms'] = round((time.monotonic() - started) * 1000)
        response['cached'] = cached
        response.update(process_memory())
        if operation != 'probe':
            upstream = self._manifest['upstream']['geoclip' if operation == 'geoclip' else 'waypoint']
            response['model_version'] = upstream.get('version', upstream.get('model_revision'))
            response['upstream_commit'] = upstream['commit']
            prefix = 'models/geoclip/' if operation == 'geoclip' else 'models/waypoint/'
            selected = {'dinov2_vitl14_reg.onnx', 'plonk_yfcc_step.onnx'} if operation == 'waypoint' else None
            artifacts = [item for item in self._manifest['artifacts'] if item['relative_path'].startswith(prefix)
                and (selected is None or Path(item['relative_path']).name in selected)
                and (operation != 'waypoint_match' or Path(item['relative_path']).name.startswith(('disk_', 'lg_')))]
            response['model_sha256'] = {Path(item['relative_path']).name: item['sha256'] for item in artifacts}
            if operation == 'geoclip':
                wheel = next(item for item in self._manifest['runtime_packages'] if item['name'] == 'geoclip')
                response['model_sha256'][wheel['filename']] = wheel['sha256']
        return response


def main():
    # Reuse only the pipe helper; importing this module does not import Qt.
    from grangerpet.web_render_worker import _binary_pipe
    incoming, outgoing = _binary_pipe('stdin'), _binary_pipe('stdout')
    # Dependencies sometimes print progress or advisories to stdout. Keep the
    # inherited protocol pipe separate before importing any optional package.
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    sys.stdout = sys.stderr
    try:
        root_value = os.environ.get('GRANGERPET_VISUAL_ROOT')
        if not root_value:
            raise WorkerError('runtime_not_installed')
        runtime = Runtime(configure_runtime(root_value))
    except Exception:
        outgoing.write(b'{"status":"error","error_code":"runtime_not_installed","predictions":[]}\n')
        outgoing.flush()
        return 2
    while True:
        raw = incoming.readline(MAX_INPUT + 1)
        if not raw:
            break
        try:
            if not raw.endswith(b'\n') or len(raw) > MAX_INPUT:
                raise WorkerError('invalid_request')
            request = parse_request(raw)
            result = runtime.dispatch(request)
        except WorkerError as exc:
            result = {'status': 'error', 'error_code': str(exc), 'predictions': []}
        except Exception as error:
            result = {'status': 'error', 'error_code': runtime.stage, 'predictions': [],'error_kind':type(error).__name__}
            if request.get('operation')=='probe':
                from grangerpet.agent_evidence import redact
                result['diagnostic']=redact(str(error))[:500]
        try:
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
            if len(encoded) > MAX_OUTPUT:
                raise ValueError()
        except (ValueError, TypeError):
            encoded = b'{"status":"error","error_code":"numerical_output_invalid","predictions":[]}'
        outgoing.write(encoded + b'\n')
        outgoing.flush()
        if len(raw) > MAX_INPUT or not raw.endswith(b'\n'):
            break
    runtime.clear()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
