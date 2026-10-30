"""Local scene contracts and actual subprocess cancellation, no accuracy claims."""
import json
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from grangerpet.agent import AgentRunner
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings
from grangerpet.visual_models import scene, pipeline

IMAGE = 'img_'+'a'*64


def test_unselected_scene_image_never_starts_model(monkeypatch):
    monkeypatch.setattr(scene, 'execute', lambda *a, **k: pytest.fail('unselected image'))
    result = ToolRegistry(Settings(), secret_getter=lambda _: '').execute('image_understand', {'attachment_id':IMAGE})
    assert result['status'] == 'invalid_arguments'


def test_unavailable_scene_does_not_invent_objects_or_stop_model_candidates(monkeypatch):
    monkeypatch.setattr(pipeline.geoint_tools, 'execute', lambda *a, **k: {'status':'complete', 'results':[]})
    monkeypatch.setattr(scene, 'execute', lambda *a, **k: {'status':'unavailable','error_code':'scene_runtime_not_installed','results':[]})
    monkeypatch.setattr(pipeline.visual_tools, 'execute', lambda name, *a, **k: {'status':'complete','results':[
        {'id':name,'details':{'capability':name,'predictions':[{'lat':1,'lon':2}]}}]})
    result = pipeline.execute({'attachment_id':IMAGE,'include_ocr':False}, SimpleNamespace(), object())
    assert result['status'] == 'partial'
    assert any(row['tool'] == 'image_understand' and row['status'] == 'unavailable' for row in result['stages'])
    assert not any('description' in row.get('details',{}) for row in result['results'])
    assert len(result['results']) == 3  # Two models plus actual coordinate comparison.


def test_scene_observations_are_given_to_model_without_encoded_pixels():
    from grangerpet.agent import _geoint_context
    value = _geoint_context({'tool':'image_understand', 'description':'A clock on a tower.',
        'observations':[{'description':'clock','region':[.1,.2,.3,.4],'confidence_kind':'model_estimate'}],
        'preview':'data:image/png;base64,PRIVATE'}, 5000)
    assert value['observations'][0]['region'] == [.1,.2,.3,.4]
    assert value['description'] == 'A clock on a tower.' and 'PRIVATE' not in json.dumps(value)


def test_scene_worker_deadline_closes_process_without_waiting_for_inference(monkeypatch, tmp_path):
    import subprocess
    actual = subprocess.Popen
    processes = []
    def child(*args, **kwargs):
        process = actual([sys.executable, '-c', 'import time; time.sleep(30)'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        processes.append(process)
        return process
    monkeypatch.setattr(scene, 'readiness', lambda: {'available':True})
    monkeypatch.setattr(scene, 'model_root', lambda:tmp_path)
    monkeypatch.setattr(scene.subprocess, 'Popen', child)
    started = time.monotonic()
    result = scene.understand(b'fixture-not-decodable-in-child', deadline=time.monotonic()+.25)
    assert result['status'] == 'timeout' and time.monotonic()-started < 3
    assert len(processes) == 1 and processes[0].poll() is not None


def test_scene_manifest_is_pinned_non_executable_safetensors_and_mit():
    lock = scene.manifest()
    assert lock['license']=='MIT' and lock['remote_code'] is False
    assert lock['download_bytes'] < 500_000_000
    assert all('/resolve/'+lock['revision']+'/' in row['url'] or row['relative_path']=='LICENSE' for row in lock['artifacts'])
    assert not any(row['relative_path'].endswith(('.py','.pkl','.bin','.exe')) for row in lock['artifacts'])
