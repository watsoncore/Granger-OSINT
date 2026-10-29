"""No live downloads/deletions: mock HTTP, tiny fixture wheels, owned temp roots."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import zipfile

import httpx
import pytest

from grangerpet.visual_models import installation as install


def artifact(data, url='https://huggingface.co/fixture/file'):
    return {'url': url, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def factory(handler):
    def make(**kwargs):
        assert kwargs['trust_env'] is False
        assert kwargs['follow_redirects'] is True and kwargs['max_redirects'] == 8
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
    return make


def wheel_bytes(entries=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as wheel:
        for name, value in (entries or {'fixture/__init__.py': 'VALUE=7', 'fixture-1.dist-info/METADATA': 'Name: fixture\nVersion: 1\n'}).items():
            wheel.writestr(name, value)
    return stream.getvalue()


def test_verified_cache_never_makes_an_http_request(tmp_path):
    data = b'published artifact'
    target = tmp_path/'model.onnx'
    target.write_bytes(data)
    def unexpected(**kwargs):
        raise AssertionError('cached artifact should not use HTTP')
    events=[]
    install.download(artifact(data),target,client_factory=unexpected,progress=events.append)
    assert target.read_bytes()==data and events[-1]['cached'] is True


def test_resume_requests_the_exact_known_partial_offset_and_activates_after_hash(tmp_path):
    data=b'123456789'
    target=tmp_path/'model.onnx';partial=tmp_path/'model.onnx.part';partial.write_bytes(data[:3])
    def handler(request):
        assert request.headers['Range']=='bytes=3-'
        assert not target.exists() and partial.read_bytes()==data[:3]
        return httpx.Response(206,headers={'Content-Range':'bytes 3-8/9'},content=data[3:])
    install.download(artifact(data),target,client_factory=factory(handler))
    assert target.read_bytes()==data and not partial.exists()


def test_server_ignoring_range_restarts_instead_of_appending(tmp_path):
    data=b'123456789';target=tmp_path/'model';(tmp_path/'model.part').write_bytes(b'old')
    def handler(request):
        assert request.headers['Range']=='bytes=3-'
        return httpx.Response(200,content=data)
    install.download(artifact(data),target,client_factory=factory(handler))
    assert target.read_bytes()==data


def test_complete_valid_partial_is_promoted_without_out_of_range_http(tmp_path):
    data=b'complete';target=tmp_path/'model';(tmp_path/'model.part').write_bytes(data)
    def unexpected(**kwargs):raise AssertionError('valid complete partial needs no request')
    install.download(artifact(data),target,client_factory=unexpected)
    assert target.read_bytes()==data


def test_complete_corrupt_partial_restarts_at_zero(tmp_path):
    data=b'complete';target=tmp_path/'model';(tmp_path/'model.part').write_bytes(b'x'*len(data))
    def handler(request):
        assert 'Range' not in request.headers
        return httpx.Response(200,content=data)
    install.download(artifact(data),target,client_factory=factory(handler))
    assert target.read_bytes()==data


@pytest.mark.parametrize('response_headers', [{'Content-Range':'bytes 0-8/9'}, {}])
def test_inconsistent_partial_range_is_refused_before_appending(tmp_path,response_headers):
    data=b'123456789';target=tmp_path/'model';partial=tmp_path/'model.part';partial.write_bytes(data[:3])
    with pytest.raises(ValueError,match='Unexpected artifact range'):
        install.download(artifact(data),target,client_factory=factory(lambda request:httpx.Response(206,headers=response_headers,content=data[3:])))
    assert not target.exists() and partial.read_bytes()==data[:3]


def test_hash_mismatch_never_replaces_the_previous_artifact(tmp_path):
    target=tmp_path/'model';target.write_bytes(b'old')
    with pytest.raises(ValueError,match='hash/size mismatch'):
        install.download(artifact(b'good'),target,client_factory=factory(lambda request:httpx.Response(200,content=b'evil')))
    assert target.read_bytes()==b'old' and (tmp_path/'model.part').read_bytes()==b'evil'


def test_oversized_stream_and_oversized_partial_are_refused(tmp_path):
    target=tmp_path/'model'
    with pytest.raises(ValueError,match='exceeds pinned size'):
        install.download(artifact(b'x'),target,client_factory=factory(lambda request:httpx.Response(200,content=b'xx')))
    assert not target.exists()
    (tmp_path/'model.part').write_bytes(b'xxx')
    with pytest.raises(ValueError,match='Partial artifact exceeds'):
        install.download(artifact(b'x'),target)


def test_trusted_redirect_is_followed_and_hash_verified(tmp_path):
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        if len(calls)==1:return httpx.Response(302,headers={'Location':'https://cdn-lfs.hf.co/file'})
        return httpx.Response(200,content=b'weights')
    target=tmp_path/'model'
    install.download(artifact(b'weights'),target,client_factory=factory(handler))
    assert len(calls)==2 and target.read_bytes()==b'weights'


@pytest.mark.parametrize('url', ['http://huggingface.co/file','https://user:secret@huggingface.co/file',
    'https://huggingface.co.evil.example/file','https://127.0.0.1/file','file:///C:/private'])
def test_initial_untrusted_url_is_never_requested(tmp_path,url):
    def unexpected(**kwargs):raise AssertionError('untrusted URL must not reach client')
    with pytest.raises(ValueError,match='Unexpected artifact host'):
        install.download(artifact(b'x',url),tmp_path/'model',client_factory=unexpected)


def test_redirect_to_untrusted_host_is_rejected_before_second_request(tmp_path):
    calls=[]
    def handler(request):
        calls.append(str(request.url));return httpx.Response(302,headers={'Location':'https://attacker.example/private'})
    with pytest.raises(ValueError,match='Unexpected artifact host'):
        install.download(artifact(b'x'),tmp_path/'model',client_factory=factory(handler))
    assert len(calls)==1 and not (tmp_path/'model').exists()


class Blocks(httpx.SyncByteStream):
    def __init__(self,blocks,interrupted=False):self.blocks=blocks;self.interrupted=interrupted
    def __iter__(self):
        yield from self.blocks
        if self.interrupted:raise httpx.ReadError('fixture transport interrupted')


def test_midstream_cancel_retains_only_the_written_partial(tmp_path):
    block=b'x'*(1024*1024);data=block*3;cancel=threading.Event();target=tmp_path/'model'
    def progress(row):cancel.set()
    with pytest.raises(InterruptedError):
        install.download(artifact(data),target,cancel_event=cancel,progress=progress,
            client_factory=factory(lambda request:httpx.Response(200,stream=Blocks([block,block,block]))))
    assert not target.exists() and (tmp_path/'model.part').stat().st_size==len(block)


def test_transport_retry_resumes_instead_of_redownloading_completed_bytes(tmp_path,monkeypatch):
    block=b'x'*(1024*1024);data=block+b'end';calls=[]
    clock=iter(range(0,10000,10));monkeypatch.setattr(install.time,'monotonic',lambda:next(clock))
    def handler(request):
        calls.append(request)
        if len(calls)==1:return httpx.Response(200,stream=Blocks([block],interrupted=True))
        assert request.headers['Range']==f'bytes={len(block)}-'
        return httpx.Response(206,headers={'Content-Range':f'bytes {len(block)}-{len(data)-1}/{len(data)}'},content=b'end')
    target=tmp_path/'model';install.download(artifact(data),target,client_factory=factory(handler))
    assert len(calls)==2 and target.read_bytes()==data


@pytest.mark.parametrize('name',['../escape','/absolute','C:/drive','folder/../../escape','folder\\..\\escape'])
def test_wheel_traversal_never_writes_outside_site(tmp_path,name):
    wheel=tmp_path/'bad.whl';wheel.write_bytes(wheel_bytes({name:'bad'}))
    with pytest.raises(ValueError,match='Unsafe wheel member'):install.extract_wheel(wheel,tmp_path/'site')
    assert not (tmp_path/'escape').exists()


def test_wheel_symlink_is_rejected(tmp_path):
    wheel=tmp_path/'bad.whl'
    with zipfile.ZipFile(wheel,'w') as archive:
        entry=zipfile.ZipInfo('link');entry.create_system=3;entry.external_attr=(stat.S_IFLNK|0o777)<<16
        archive.writestr(entry,'../outside')
    with pytest.raises(ValueError,match='symbolic link'):install.extract_wheel(wheel,tmp_path/'site')


def test_wheel_maps_only_purelib_platlib_and_never_executes_scripts_or_pth(tmp_path):
    marker=tmp_path/'executed';wheel=tmp_path/'fixture.whl'
    wheel.write_bytes(wheel_bytes({'fixture.data/purelib/a.py':'VALUE=1', 'fixture.data/platlib/b.pyd':'binary',
        'fixture.data/scripts/launch.exe':'must skip','fixture.data/data/extra.txt':'must skip',
        'fixture.data/headers/header.h':'must skip','danger.pth':f"import pathlib; pathlib.Path({str(marker)!r}).touch()",
        'fixture-1.dist-info/licenses/LICENSE':'license retained'}))
    site=tmp_path/'site';install.extract_wheel(wheel,site)
    assert (site/'a.py').read_text()=='VALUE=1' and (site/'b.pyd').read_text()=='binary'
    assert (site/'fixture-1.dist-info/licenses/LICENSE').is_file() and (site/'danger.pth').is_file()
    assert not (site/'fixture.data').exists() and not marker.exists()


@pytest.fixture
def tiny_manifest(tmp_path,monkeypatch):
    data=wheel_bytes();filename='fixture-1-py3-none-any.whl'
    package={**artifact(data,'https://files.pythonhosted.org/fixture.whl'),'filename':filename,'name':'fixture','version':'1'}
    model={**artifact(b'weights'),'relative_path':'models/fixture/model.onnx','id':'fixture'}
    lock={'runtime_packages':[package],'artifacts':[model]}
    monkeypatch.setattr(install,'manifest',lambda:lock)
    original=install.download
    def downloaded(row,target,**kwargs):
        payload=data if str(target).endswith('.whl') else b'weights'
        return original(row,target,**kwargs,client_factory=factory(lambda request:httpx.Response(200,content=payload)))
    monkeypatch.setattr(install,'download',downloaded)
    return lock


def test_install_requires_real_explicit_consent_before_any_directory_is_created(tmp_path,tiny_manifest):
    root=tmp_path/'runtime'
    for consent in (False,None,1,'yes'):
        with pytest.raises(PermissionError):install.install(root,consent=consent)
    assert not root.exists()


def test_install_stages_before_activation_and_writes_matching_receipt(tmp_path,tiny_manifest):
    root=tmp_path/'runtime';(root/'site-packages').mkdir(parents=True);(root/'site-packages/old.txt').write_text('old')
    receipt=install.install(root,consent=True)
    assert receipt['status']=='files_verified_probe_pending'
    assert (root/'site-packages/fixture/__init__.py').read_text()=='VALUE=7'
    assert not (root/'site-packages/old.txt').exists()
    previous=list(root.glob('site-packages.previous-*'));assert len(previous)==1 and (previous[0]/'old.txt').read_text()=='old'
    assert not list(root.glob('site-packages.pending-*'))
    assert json.loads((root/'receipt.json').read_text())==receipt


def test_extraction_failure_preserves_active_site_and_receipt(tmp_path,tiny_manifest,monkeypatch):
    root=tmp_path/'runtime';(root/'site-packages').mkdir(parents=True);(root/'site-packages/old.txt').write_text('old');(root/'receipt.json').write_text('old receipt')
    def fail(wheel,site,**kwargs):
        site.mkdir();(site/'partial.txt').write_text('partial');raise ValueError('corrupt fixture wheel')
    monkeypatch.setattr(install,'extract_wheel',fail)
    with pytest.raises(ValueError):install.install(root,consent=True)
    assert (root/'site-packages/old.txt').read_text()=='old'
    assert (root/'receipt.json').read_text()=='old receipt'
    assert len(list(root.glob('site-packages.pending-*')))==1


def test_activation_failure_restores_previous_site(tmp_path,tiny_manifest,monkeypatch):
    root=tmp_path/'runtime';(root/'site-packages').mkdir(parents=True);(root/'site-packages/old.txt').write_text('old')
    original=Path.replace
    def replace(path,target):
        if path.name.startswith('site-packages.pending-'):raise OSError('fixture activation failure')
        return original(path,target)
    monkeypatch.setattr(Path,'replace',replace)
    with pytest.raises(OSError):install.install(root,consent=True)
    assert (root/'site-packages/old.txt').read_text()=='old'
    assert not list(root.glob('site-packages.previous-*'))


def owned_runtime(tmp_path):
    # Fixture wheels/models are the only paths ever removed by these tests.
    root=tmp_path/'owned-runtime';install.install(root,consent=True);return root


def test_remove_only_known_temp_owned_runtime_and_preserve_adjacent_files(tmp_path,tiny_manifest):
    root=owned_runtime(tmp_path);outside=tmp_path/'personal.txt';outside.write_text('keep')
    (root/'site-packages/fixture/__pycache__').mkdir()
    (root/'site-packages/fixture/__pycache__/__init__.cpython-314.pyc').write_bytes(b'cache')
    result=install.remove_runtime(root,_allowed_root=root)
    assert result['status']=='removed' and result['removed_files']>0 and result['removed_bytes']>0
    assert not root.exists() and outside.read_text()=='keep'


@pytest.mark.parametrize('unknown',['personal.txt','models/private.txt','downloads/unrelated.zip','site-packages/fixture/private.txt','offline-cache/private.txt'])
def test_remove_refuses_unknown_files_before_deleting_anything(tmp_path,tiny_manifest,unknown):
    root=owned_runtime(tmp_path);path=root/unknown;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('personal')
    before={p.relative_to(root).as_posix():p.read_bytes()for p in root.rglob('*')if p.is_file()}
    with pytest.raises(ValueError,match='Unknown file or directory'):install.remove_runtime(root,_allowed_root=root)
    assert before=={p.relative_to(root).as_posix():p.read_bytes()for p in root.rglob('*')if p.is_file()}


def test_remove_refuses_an_arbitrary_root_relative_root_and_wrong_receipt(tmp_path,tiny_manifest):
    root=owned_runtime(tmp_path)
    with pytest.raises(ValueError,match='exact app-owned'):install.remove_runtime(root,_allowed_root=tmp_path/'different')
    with pytest.raises(ValueError,match='absolute'):install.remove_runtime(Path('relative'),_allowed_root=root)
    receipt=json.loads((root/'receipt.json').read_text());receipt['manifest_sha256']='0'*64;(root/'receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match='receipt does not match'):install.remove_runtime(root,_allowed_root=root)
    assert (root/'site-packages/fixture/__init__.py').is_file()


def test_remove_refuses_modified_wheel_cache_and_missing_receipt(tmp_path,tiny_manifest):
    root=owned_runtime(tmp_path);wheel=root/'downloads'/tiny_manifest['runtime_packages'][0]['filename'];wheel.write_bytes(b'changed')
    with pytest.raises(ValueError,match='Verified wheel cache'):install.remove_runtime(root,_allowed_root=root)
    (root/'receipt.json').unlink()
    with pytest.raises(ValueError,match='known installation receipt'):install.remove_runtime(root,_allowed_root=root)
    assert (root/'site-packages/fixture/__init__.py').is_file()


def _make_link(link,target):
    if os.name=='nt':
        # Junctions require no symlink privilege. Values travel in child env,
        # never as interpolated shell text; only fixture directories are used.
        env={**os.environ,'GRANGER_TEST_LINK':str(link),'GRANGER_TEST_LINK_TARGET':str(target)}
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
            'New-Item -ItemType Junction -Path $env:GRANGER_TEST_LINK -Target $env:GRANGER_TEST_LINK_TARGET -ErrorAction Stop | Out-Null'],
            env=env,capture_output=True,timeout=15)
        assert result.returncode==0,result.stderr.decode(errors='replace')
    else:link.symlink_to(target,target_is_directory=True)


def test_remove_refuses_symlink_or_junction_without_touching_target(tmp_path,tiny_manifest):
    root=owned_runtime(tmp_path);outside=tmp_path/'outside';outside.mkdir();(outside/'personal').write_text('keep')
    _make_link(root/'site-packages/link',outside)
    with pytest.raises(ValueError,match='symbolic link or junction'):install.remove_runtime(root,_allowed_root=root)
    assert (outside/'personal').read_text()=='keep' and (root/'receipt.json').is_file()


def test_remove_rejects_root_junction_even_when_resolution_matches_allowed_root(tmp_path,tiny_manifest):
    root=owned_runtime(tmp_path);alias=tmp_path/'alias'
    _make_link(alias,root)
    with pytest.raises(ValueError,match='symbolic link or junction'):install.remove_runtime(alias,_allowed_root=root)
    assert (root/'receipt.json').is_file()


@pytest.mark.parametrize('arguments',[['--remove'],['--confirm-remove'],['--remove','--confirm-remove','--consent-download']])
def test_cli_removal_requires_its_own_confirmation_and_never_starts_download(monkeypatch,arguments):
    from scripts import setup_visual_runtime
    def unexpected(*args,**kwargs):raise AssertionError('No mutation is authorized by these arguments')
    monkeypatch.setattr(install,'remove_runtime',unexpected);monkeypatch.setattr(install,'install',unexpected)
    monkeypatch.setattr(sys,'argv',['setup_visual_runtime.py',*arguments])
    with pytest.raises(SystemExit):setup_visual_runtime.main()


def test_cli_passes_confirmed_path_to_guarded_remover_only(monkeypatch,tmp_path,capsys):
    from scripts import setup_visual_runtime
    calls=[]
    def remove(root):calls.append(root);return {'status':'removed'}
    monkeypatch.setattr(install,'remove_runtime',remove)
    monkeypatch.setattr(sys,'argv',['setup_visual_runtime.py','--remove','--confirm-remove','--root',str(tmp_path/'owned')])
    assert setup_visual_runtime.main()==0 and calls==[tmp_path/'owned']
    assert json.loads(capsys.readouterr().out)['status']=='removed'
