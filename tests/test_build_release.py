"""Release failures must preserve the installed app and clean only owned work."""
import json
from pathlib import Path

import pytest

from scripts import build_release as release


def project(tmp_path,monkeypatch):
    (tmp_path/'Granger-OSINT.spec').write_text('fixture',encoding='utf-8')
    (tmp_path/'dist').mkdir();(tmp_path/'dist'/release.BINARY).write_bytes(b'old working executable')
    (tmp_path/'frontend'/'src').mkdir(parents=True)
    (tmp_path/'frontend'/'src'/'main.tsx').write_text('fixture',encoding='utf-8')
    monkeypatch.setattr(release,'running_images',lambda:[])
    return tmp_path


def fake_commands(monkeypatch, *, failure=None):
    monkeypatch.setattr(release,'build_frontend',lambda root,environment:
                        {'rebuilt':True,'input_sha256':release.frontend_input_digest(root)})
    def run(arguments, *, root, environment):
        stage=Path(environment[release.STAGE_ENV])
        assert stage.parent==root and stage.name.startswith(release.STAGE_PREFIX)
        assert environment['PYINSTALLER_CONFIG_DIR']==str(stage/'cache')
        if arguments[:2]==['-m','PyInstaller']:
            output=Path(arguments[arguments.index('--distpath')+1]);output.mkdir()
            (output/release.BINARY).write_bytes(b'new verified executable')
            if failure=='build':raise RuntimeError('build failed')
        else:
            name=Path(arguments[0]).name
            if failure=='interrupt':raise KeyboardInterrupt()
            flag='--report' if name in ('qa_clean_release.py','qa_v4_investigation.py','qa_v5_acceptance.py','qa_v6_media.py') else '--output'
            report=Path(arguments[arguments.index(flag)+1])
            data={'passed':name!=failure,'modules':[1], 'assets':[1], 'checks':[1]}
            if name=='qa_clean_release.py':
                limited='--allow-missing-external-tools' in arguments
                data['external_tools']={'availability':{'blockchain_gansar':not limited,'username_maigret':not limited},
                    'policy':'registry-only-for-external-tools' if limited else 'strict-local-availability',
                    'availability_required':not limited}
            report.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(release,'run_checked',run)


def test_failed_live_node_acceptance_cannot_promote_candidate(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch,failure='qa_v4_investigation.py')
    with pytest.raises(release.BuildError):release.release(root,verify_investigation_live=True)
    assert (root/'dist'/release.BINARY).read_bytes()==b'old working executable'
    assert list(root.glob(release.STAGE_PREFIX+'*'))==[]


def test_failed_media_acceptance_preserves_installed_application(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch,failure='qa_v6_media.py')
    with pytest.raises(release.BuildError):
        release.release(root,run_media_v6=True)
    assert (root/'dist'/release.BINARY).read_bytes()==b'old working executable'
    assert not list(root.glob(release.STAGE_PREFIX+'*'))


def test_graph_receipt_for_another_exe_cannot_promote(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch)
    previous=release.run_checked
    def stale_receipt(arguments,**kwargs):
        previous(arguments,**kwargs)
        if arguments[0]=='scripts/qa_v5_acceptance.py':
            report=Path(arguments[arguments.index('--report')+1])
            report.write_text(json.dumps({'passed':True,'exe_sha256':'stale','origin':'frozen-Windows-EXE',
                'fresh_network_requested':True,'temporary_profile_removed':True}),encoding='utf-8')
    monkeypatch.setattr(release,'run_checked',stale_receipt)
    with pytest.raises(release.BuildError,match='candidate and required live scope'):
        release.release(root,graph_v5_observations=root)
    assert (root/'dist'/release.BINARY).read_bytes()==b'old working executable'
    assert not list(root.glob(release.STAGE_PREFIX+'*'))


@pytest.mark.parametrize('failure',['build','verify_frozen_sources.py','verify_frozen_assets.py','qa_clean_release.py','interrupt'])
def test_failed_or_interrupted_stage_preserves_canonical_and_removes_owned_work(tmp_path,monkeypatch,failure):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch,failure=failure)
    expected=KeyboardInterrupt if failure=='interrupt' else (RuntimeError,release.BuildError)
    with pytest.raises(expected):release.release(root)
    assert (root/'dist'/release.BINARY).read_bytes()==b'old working executable'
    assert list(root.glob(release.STAGE_PREFIX+'*'))==[]


def test_success_installs_verified_binary_and_leaves_one_dist_file(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch)
    result=release.release(root)
    assert result['passed'] and result['temporary_stage_removed']
    assert (root/'dist'/release.BINARY).read_bytes()==b'new verified executable'
    assert [p.name for p in (root/'dist').iterdir()]==[release.BINARY]
    assert not list(root.glob(release.STAGE_PREFIX+'*'))
    assert result['frontend_build']['rebuilt']


def test_frontend_source_edit_after_build_cannot_promote_stale_bundle(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch)
    previous=release.run_checked
    def changed(arguments,**kwargs):
        previous(arguments,**kwargs)
        if arguments[0]=='scripts/qa_clean_release.py':
            (root/'frontend/src/main.tsx').write_text('changed',encoding='utf-8')
    monkeypatch.setattr(release,'run_checked',changed)
    with pytest.raises(release.BuildError,match='Frontend inputs changed'):
        release.release(root)
    assert (root/'dist'/release.BINARY).read_bytes()==b'old working executable'


def test_frontend_compiler_runs_current_project_before_packaging(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);calls=[]
    monkeypatch.setattr(release.shutil,'which',lambda name:'npm-fixture')
    monkeypatch.setattr(release.subprocess,'run',lambda args,**kwargs:calls.append((args,kwargs)))
    result=release.build_frontend(root,{'PYTHONUTF8':'1'})
    assert calls[0][0]==['npm-fixture','--prefix',str(root/'frontend'),'run','build']
    assert calls[0][1]['check'] and calls[0][1]['cwd']==root
    assert result=={'rebuilt':True,'input_sha256':release.frontend_input_digest(root)}


def test_running_canonical_or_app_opened_during_qa_is_never_replaced(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch)
    images=[(123,str(root/'dist'/release.BINARY))]
    monkeypatch.setattr(release,'running_images',lambda:images)
    with pytest.raises(release.BuildError,match='running'):release.release(root)
    assert not list(root.glob(release.STAGE_PREFIX+'*'))
    counter=[0]
    def opened_later():
        counter[0]+=1
        return [] if counter[0]==1 else images
    monkeypatch.setattr(release,'running_images',opened_later)
    with pytest.raises(release.BuildError,match='running'):release.release(root)
    assert (root/'dist'/release.BINARY).read_bytes()==b'old working executable'
    assert not list(root.glob(release.STAGE_PREFIX+'*'))


def test_unknown_dist_entries_are_not_deleted_and_default_install_is_refused(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch)
    unknown=root/'dist'/'unique-investigation.dpapi';unknown.write_bytes(b'never delete unknown data')
    with pytest.raises(release.BuildError,match='legacy entries'):release.release(root)
    assert unknown.read_bytes()==b'never delete unknown data'
    result=release.release(root,allow_legacy_dist=True)
    assert result['legacy_entries_require_cleanup']==[unknown.name]
    assert unknown.read_bytes()==b'never delete unknown data'


def test_spec_guard_rejects_default_dist_and_traversal_but_accepts_owned_pyinstaller_paths(tmp_path,monkeypatch):
    with pytest.raises(release.BuildError,match='direct release'):release.validate_spec_paths(tmp_path,str(tmp_path/'dist'),str(tmp_path/'build/Granger-OSINT'))
    with release.owned_stage(tmp_path) as stage:
        monkeypatch.setenv(release.STAGE_ENV,str(stage))
        release.validate_spec_paths(tmp_path,str(stage/'dist'),str(stage/'work/Granger-OSINT'))
        with pytest.raises(release.BuildError):release.validate_spec_paths(tmp_path,str(tmp_path/'dist/master-fix-final'),str(stage/'work/Granger-OSINT'))
        with pytest.raises(release.BuildError):release.contained(tmp_path/'../outside',tmp_path)
    assert not stage.exists()


def test_reparse_dist_is_refused_before_work_or_replacement(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch)
    monkeypatch.setattr(release,'reparse',lambda path:path==root/'dist')
    with pytest.raises(release.BuildError,match='junctions'):release.release(root)
    assert (root/'dist'/release.BINARY).read_bytes()==b'old working executable'
    assert not list(root.glob(release.STAGE_PREFIX+'*'))


@pytest.mark.parametrize('limited_ci',[False,True])
def test_only_explicit_ci_option_relaxes_external_tool_requirement(tmp_path,monkeypatch,limited_ci):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch)
    previous=release.run_checked;calls=[]
    def record(arguments,**kwargs):
        calls.append(arguments)
        previous(arguments,**kwargs)
        if arguments[0]=='scripts/qa_clean_release.py':
            report=Path(arguments[arguments.index('--report')+1]);data=json.loads(report.read_text())
            data['external_tools']={'availability':{'blockchain_gansar':not limited_ci,'username_maigret':not limited_ci},
                'policy':'registry-only-for-external-tools' if limited_ci else 'strict-local-availability',
                'availability_required':not limited_ci}
            report.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(release,'run_checked',record)
    result=release.release(root,allow_missing_external_tools=limited_ci)
    native=next(arguments for arguments in calls if arguments[0]=='scripts/qa_clean_release.py')
    assert ('--allow-missing-external-tools' in native) is limited_ci
    assert all('--allow-missing-external-tools' not in arguments for arguments in calls if arguments is not native)
    assert result['external_tools']['availability']=={'blockchain_gansar':not limited_ci,'username_maigret':not limited_ci}
    assert result['external_tools_policy']==('registry-only-for-external-tools' if limited_ci else 'strict-local-availability')


def test_passed_ci_receipt_cannot_silently_weaken_default_local_release(tmp_path,monkeypatch):
    root=project(tmp_path,monkeypatch);fake_commands(monkeypatch);previous=release.run_checked
    def weaker_receipt(arguments,**kwargs):
        previous(arguments,**kwargs)
        if arguments[0]=='scripts/qa_clean_release.py':
            report=Path(arguments[arguments.index('--report')+1]);data=json.loads(report.read_text())
            data['external_tools']['policy']='registry-only-for-external-tools'
            data['external_tools']['availability_required']=False
            report.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(release,'run_checked',weaker_receipt)
    with pytest.raises(release.BuildError,match='scope does not match'):release.release(root)
    assert (root/'dist'/release.BINARY).read_bytes()==b'old working executable'
    assert not list(root.glob(release.STAGE_PREFIX+'*'))
def test_frontend_digest_tracks_inputs_and_not_generated_compiler_state(tmp_path):
    from scripts.build_release import frontend_input_digest
    root=tmp_path
    (root/'frontend/scripts').mkdir(parents=True)
    (root/'frontend/src').mkdir()
    (root/'frontend/public').mkdir()
    (root/'frontend/src/main.ts').write_text('export const value=1')
    generator=root/'frontend/scripts/licenses.mjs'
    generator.write_text('generate_v1')
    baseline=frontend_input_digest(root)
    (root/'frontend/tsconfig.app.tsbuildinfo').write_text('compiler cache changed')
    (root/'frontend/public/THIRD_PARTY_NOTICES.txt').write_text('generated notice')
    assert frontend_input_digest(root)==baseline
    generator.write_text('generate_v2')
    assert frontend_input_digest(root)!=baseline
