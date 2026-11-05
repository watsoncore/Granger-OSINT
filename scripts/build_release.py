"""Build and verify in an owned temporary stage, then install one canonical EXE.

No release versions, backups, source ZIPs, profiles or reports are written to dist.
Failed checks preserve the installed binary. Temporary work is removed on ordinary
failure and KeyboardInterrupt as well as success; foreign processes are never killed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAGE_ENV = 'GRANGER_BUILD_STAGE'
STAGE_PREFIX = '.granger-build-'
STAGE_MARKER = '.granger-build-owner'
STAGE_SCHEMA = 'granger-build-stage/1'
BINARY = 'Granger-OSINT.exe'


class BuildError(RuntimeError):
    pass


def reparse(path: Path) -> bool:
    try:
        return bool(path.lstat().st_file_attributes & 0x400)
    except AttributeError:
        return path.is_symlink()


def contained(path: Path, root: Path) -> Path:
    """Check the lexical path and all reparse entries before resolving it."""
    path,root = path.absolute(),root.absolute()
    try:
        parts = path.relative_to(root).parts
    except ValueError as error:
        raise BuildError('Build path is outside its intended workspace.') from error
    for item in [root, *[root.joinpath(*parts[:i]) for i in range(1,len(parts)+1)]]:
        if (item.exists() or item.is_symlink()) and reparse(item):
            raise BuildError('Build paths must not contain symbolic links or junctions.')
    result = path.resolve()
    if not result.is_relative_to(root.resolve()):
        raise BuildError('Resolved build path leaves its intended workspace.')
    return result


def validate_stage(stage: Path, root: Path) -> Path:
    stage = contained(stage,root)
    if stage.parent != root.resolve() or not stage.name.startswith(STAGE_PREFIX):
        raise BuildError('Expected an owned temporary build directory.')
    marker = stage/STAGE_MARKER
    if (not marker.is_file() or reparse(marker)
            or marker.read_text(encoding='utf-8') != STAGE_SCHEMA+'\n'+str(root.resolve())+'\n'):
        raise BuildError('Temporary build ownership marker does not match.')
    return stage


@contextmanager
def owned_stage(root: Path):
    contained(root,root)
    stage = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX,dir=root))
    marked = False
    try:
        (stage/STAGE_MARKER).write_text(STAGE_SCHEMA+'\n'+str(root.resolve())+'\n',encoding='utf-8')
        marked = True
        yield stage
    finally:
        if stage.exists():
            # The only recursive removal here: verify the resolved absolute
            # target and its ownership immediately before native Python cleanup.
            target = validate_stage(stage,root) if marked else contained(stage,root)
            if target.parent != root.resolve() or not target.name.startswith(STAGE_PREFIX):
                raise BuildError('Refusing cleanup outside the owned temporary build directory.')
            shutil.rmtree(target)


def validate_spec_paths(root: Path, distpath: str, workpath: str) -> None:
    """Both specs reject unchecked direct output to canonical/versioned dist."""
    value = os.environ.get(STAGE_ENV)
    if not value:
        raise BuildError('Use build.ps1 or scripts/build_release.py; unchecked direct release output is disabled.')
    stage = validate_stage(Path(value),root)
    work = contained(Path(workpath),root)
    # PyInstaller adds the spec filename below the explicit --workpath.
    if (contained(Path(distpath),root) != stage/'dist'
            or work.parent != stage/'work' or work.name not in ('Granger-OSINT','GrangerPet')):
        raise BuildError('PyInstaller output/work must use the owned temporary stage.')


def running_images() -> list[tuple[int,str]]:
    """Read full native Win32 image paths through the installed system CIM API."""
    if sys.platform != 'win32':
        raise BuildError('Release installation requires native Windows.')
    shell = Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); Get-CimInstance Win32_Process -Filter \"name = 'Granger-OSINT.exe'\" -ErrorAction Stop | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"
    result = subprocess.run([str(shell),'-NoProfile','-NonInteractive','-Command',command],
        check=True,capture_output=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
    values = json.loads(result.stdout) if result.stdout.strip() else []
    if isinstance(values,dict):values=[values]
    if not isinstance(values,list) or any(not row.get('ExecutablePath') for row in values):
        raise BuildError('Cannot verify a running Granger-OSINT image; installation refused.')
    return [(int(row['ProcessId']),row['ExecutablePath']) for row in values]


def assert_not_running(executable: Path) -> None:
    target = os.path.normcase(str(executable.resolve()))
    if any(os.path.normcase(str(Path(path).resolve())) == target for _,path in running_images()):
        raise BuildError('The canonical Granger-OSINT.exe is running. Close it normally before installation; it was not terminated or replaced.')


def dist_entries(root: Path, *, allow_legacy: bool = False) -> list[str]:
    directory = contained(root/'dist',root)
    if directory.exists() and not directory.is_dir():raise BuildError('dist is not a directory.')
    extras = sorted(p.name for p in directory.iterdir() if p.name != BINARY) if directory.exists() else []
    if extras and not allow_legacy:
        raise BuildError('dist must contain only Granger-OSINT.exe. Review/remove legacy entries first: '+', '.join(extras[:12]))
    if (directory/BINARY).exists() or (directory/BINARY).is_symlink():
        target = contained(directory/BINARY,root)
        if not target.is_file():raise BuildError('Canonical executable is not a regular file.')
    return extras


def run_checked(arguments: list[str], *, root: Path, environment: dict) -> None:
    subprocess.run([sys.executable,*arguments],cwd=root,env=environment,check=True)


def read_passed(path: Path) -> dict:
    result = json.loads(path.read_text(encoding='utf-8'))
    if result.get('passed') is not True:raise BuildError('Candidate validation did not pass: '+path.name)
    return result


def verify_graph_v5(root, candidate, stage, observations, captures, environment):
    report = stage/'graph-v5.json'
    captures = (captures or stage/'graph-v5-captures').resolve()
    if captures.is_relative_to((root/'dist').resolve()):
        raise BuildError('Graph captures must be outside dist.')
    run_checked(['scripts/qa_v5_acceptance.py','--exe',str(candidate),'--observed-dir',str(observations),
                 '--report',str(report),'--screenshots',str(captures)],root=root,environment=environment)
    native = read_passed(report)
    with candidate.open('rb') as image:
        candidate_hash = hashlib.file_digest(image,'sha256').hexdigest()
    if (native.get('exe_sha256') != candidate_hash or native.get('origin') != 'frozen-Windows-EXE'
            or not native.get('fresh_network_requested') or not native.get('temporary_profile_removed')):
        raise BuildError('Graph V5 receipt did not verify the candidate and required live scope.')
    stress = stage/'graph-v5-stress'
    run_checked(['scripts/qa_canvas_stress.py','--exe',str(candidate),'--output',str(stress),
                 '--observed-result',str(observations/'ton-observed-private.json')],root=root,environment=environment)
    measurements = read_passed(stress/'report.json')
    if measurements.get('exe_sha256') != candidate_hash or measurements.get('owned_processes_left') != 0:
        raise BuildError('Graph V5 stress receipt did not match the candidate or clean up its processes.')
    cases = measurements.get('cases',[])
    synthetic_sizes = {case['underlying_nodes'] for case in cases if case['data_origin']=='synthetic_fixture'}
    if synthetic_sizes != {50,100,500,1000,5000} or not any(case['data_origin']=='provided_observed_result' for case in cases):
        raise BuildError('Graph V5 stress receipt is missing a required workload.')
    metrics = ('data_origin','underlying_nodes','edges','open_and_expand_seconds','paint_ms',
               'event_to_paint_ms','active_intervals_ms','resources','renderer')
    native['performance'] = {'metric_semantics':measurements['metric_semantics'],
                             'cases':[{key:case[key] for key in metrics if key in case}
                                      for case in cases]}
    return native


def release(root: Path = ROOT, *, allow_legacy_dist: bool = False, allow_missing_external_tools: bool = False,
            verify_investigation_live: bool = False, graph_v5_observations: Path | None = None,
            graph_v5_captures: Path | None = None) -> dict:
    root = root.resolve()
    if not (root/'Granger-OSINT.spec').is_file():raise BuildError('Existing Granger-OSINT project not found.')
    extras = dist_entries(root,allow_legacy=allow_legacy_dist)
    canonical = root/'dist'/BINARY
    assert_not_running(canonical)
    if graph_v5_observations:
        graph_v5_observations = graph_v5_observations.resolve(strict=True)
        if allow_missing_external_tools or not graph_v5_observations.is_dir():
            raise BuildError('Graph V5 acceptance needs real observation receipts and installed external tools.')
    with owned_stage(root) as stage:
        environment = {**os.environ,STAGE_ENV:str(stage),'PYTHONDONTWRITEBYTECODE':'1',
                       'PYINSTALLER_CONFIG_DIR':str(stage/'cache')}
        run_checked(['-m','PyInstaller','--noconfirm','--clean','--distpath',str(stage/'dist'),
            '--workpath',str(stage/'work'),'Granger-OSINT.spec'],root=root,environment=environment)
        candidate = contained(stage/'dist'/BINARY,root)
        if not candidate.is_file() or sorted(p.name for p in candidate.parent.iterdir()) != [BINARY]:
            raise BuildError('Staged one-file build missing or unexpected sidecar files produced.')
        checks = {}
        for script,name in [('verify_frozen_sources.py','sources'),('verify_frozen_assets.py','resources'),('qa_clean_release.py','native')]:
            report = stage/(name+'.json');flag = '--report' if name == 'native' else '--output'
            arguments = ['scripts/'+script,'--exe',str(candidate),flag,str(report)]
            if name == 'native' and allow_missing_external_tools:
                arguments.append('--allow-missing-external-tools')
            run_checked(arguments,root=root,environment=environment)
            checks[name] = read_passed(report)
        expected_policy = 'registry-only-for-external-tools' if allow_missing_external_tools else 'strict-local-availability'
        tool_scope = checks['native'].get('external_tools',{})
        if (tool_scope.get('policy') != expected_policy
                or tool_scope.get('availability_required') is not (not allow_missing_external_tools)
                or (not allow_missing_external_tools and not all(tool_scope.get('availability',{}).get(name) is True
                    for name in ('blockchain_gansar','username_maigret')))):
            raise BuildError('Native QA external-tool scope does not match the requested release policy.')
        if verify_investigation_live:
            if allow_missing_external_tools:raise BuildError('Live node acceptance requires installed external tools.')
            report=stage/'investigation-live.json'
            run_checked(['scripts/qa_v4_investigation.py','--exe',str(candidate),'--report',str(report),
                '--screenshots',str(root/'docs/validation/master-fix-v4')],root=root,environment=environment)
            checks['investigation_live']=read_passed(report)
        if graph_v5_observations:
            checks['graph_v5']=verify_graph_v5(root,candidate,stage,graph_v5_observations,graph_v5_captures,environment)
        # Long native/live checks must not promote an EXE made from sources
        # changed by another editor while QA was running.
        for script,name in [('verify_frozen_sources.py','sources'),('verify_frozen_assets.py','resources')]:
            report=stage/(name+'-before-install.json')
            run_checked(['scripts/'+script,'--exe',str(candidate),'--output',str(report)],root=root,environment=environment)
            checks[name]=read_passed(report)
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest();size = candidate.stat().st_size
        # A user may open the old app while the isolated QA runs: recheck now.
        dist_entries(root,allow_legacy=allow_legacy_dist);assert_not_running(canonical)
        canonical.parent.mkdir(exist_ok=True)
        os.replace(candidate,canonical)
        if hashlib.sha256(canonical.read_bytes()).hexdigest() != digest:
            raise BuildError('Installed digest does not match the verified candidate.')
    if not extras:dist_entries(root)
    return {'passed':True,'canonical_path':'dist/'+BINARY,'bytes':size,'sha256':digest,
        'frozen_modules':len(checks['sources'].get('modules',[])),
        'resource_checks':len(checks['resources'].get('assets',[])),
        'native_checks':len(checks['native'].get('checks',[])),
        'investigation_live':checks.get('investigation_live'),
        'graph_v5':checks.get('graph_v5'),
        'external_tools':checks['native'].get('external_tools',{}),
        'external_tools_policy':expected_policy,
        'temporary_stage_removed':not stage.exists(),'legacy_entries_require_cleanup':extras}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-legacy-dist',action='store_true',help='One-time migration: existing extra entries remain for explicit review/cleanup; none are created or deleted')
    parser.add_argument('--verify-investigation-live',action='store_true',help='Before promotion, actually create username/wallet and run Maigret/Gansar from native UI')
    parser.add_argument('--verify-graph-v5',type=Path,help='Private directory containing real public observation receipts for native Graph V5 acceptance')
    parser.add_argument('--graph-v5-captures',type=Path,help='Optional own-window captures outside dist')
    parser.add_argument('--report',type=Path,help='Optional small summary outside dist; all raw QA/work files are automatically removed')
    parser.add_argument('--allow-missing-external-tools',action='store_true',
        help='Explicit source-only CI: require external tool registration and report actual availability; do not require ignored Gansar/Maigret runtimes. Default local release remains strict.')
    args = parser.parse_args()
    if args.report and args.report.resolve().is_relative_to((ROOT/'dist').resolve()):parser.error('Build reports must be outside dist.')
    if args.graph_v5_captures and not args.verify_graph_v5:parser.error('--graph-v5-captures requires --verify-graph-v5.')
    try:
        result = release(allow_legacy_dist=args.allow_legacy_dist,allow_missing_external_tools=args.allow_missing_external_tools,
                         verify_investigation_live=args.verify_investigation_live,graph_v5_observations=args.verify_graph_v5,
                         graph_v5_captures=args.graph_v5_captures)
    except (OSError,ValueError,BuildError,subprocess.CalledProcessError) as error:
        print('Build/install failed: '+str(error),file=sys.stderr);return 1
    payload = json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(payload,encoding='utf-8')
    print(payload,end='');return 0


if __name__ == '__main__':raise SystemExit(main())
