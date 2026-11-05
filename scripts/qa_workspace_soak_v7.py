"""Long, owned-window graph switching; numeric process/GPU counters only."""
import argparse
import base64
import ctypes
import hashlib
import io
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts.qa_v5_acceptance import V5Session
from scripts.qa_canvas_stress import synthetic_document
from scripts.qa_clean_release import isolated_environment, wait_for
from scripts.perf_process_metrics import ProcessSampler


def run(exe,report_path,*,seconds=1200,interval=30,source=False,keep_awake=False):
    from PySide6.QtCore import QCoreApplication
    from PIL import Image
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.research_canvas import CanvasStore
    app=QCoreApplication.instance() or QCoreApplication([])
    result={'origin':'native-source' if source else 'frozen-Windows-EXE','exe_sha256':None if source else hashlib.sha256(exe.read_bytes()).hexdigest(),
        'requested_seconds':seconds,'switch_interval_seconds':interval,'synthetic':True,'passed':False,'samples':[],
        'temporary_display_request':keep_awake,'permanent_windows_settings_changed':False,'surface_restores':0,
        'switch_checks':[]}
    report_path.parent.mkdir(parents=True,exist_ok=True)
    def save():report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='.granger-soak-v7-',dir=ROOT) as name:
        directory=Path(name).resolve();assert directory.parent==ROOT.resolve()
        with isolated_environment(directory):
            SettingsStore().save(Settings(source_root=str(ROOT),ai_provider='none',cursor_reaction=False,reduced_motion=True))
            store=CanvasStore(InvestigationJournal(directory/'appdata/GrangerPet/investigations'))
            pixels=io.BytesIO();Image.new('RGB',(64,64),'#497077').save(pixels,'PNG')
            thumbnail='data:image/png;base64,'+base64.b64encode(pixels.getvalue()).decode('ascii')
            docs=[store.save(synthetic_document(n,thumbnail),0) for n in (50,5000)]
            session=V5Session(exe,directory,source);sampler=ProcessSampler(None if source else exe)
            if source:sampler.source_images.add(str(Path(sys._base_executable).resolve()).casefold())
            execution_state=None
            try:
                if keep_awake:
                    execution_state=ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
                    if not execution_state:raise RuntimeError('Temporary display request unavailable')
                session.start(0);session.click('Поиск');session.click('Моё полотно')
                started=time.monotonic();last=-interval;cycle=0
                while time.monotonic()-started<seconds:
                    elapsed=time.monotonic()-started
                    if elapsed-last>=interval:
                        status=wait_for(session.status,10)['desktop']
                        if not status.get('visible') or not status.get('page_visible'):
                            result['surface_restores']+=1;session.show_workspace()
                            session.click('Поиск');session.click('Моё полотно')
                        document=docs[cycle%2];count=len(document['entities']);switch_started=time.monotonic()
                        session.open_document(document['id'])
                        if cycle==0:
                            session.click('Полноэкранное окно Windows')
                            wait_for(lambda:session.snapshot()['window']['fullscreen'],15)
                            session.click('Полноэкранное окно Windows')
                            wait_for(lambda:not session.snapshot()['window']['fullscreen'],15)
                            result['native_fullscreen_round_trip']=True
                        def rendered():
                            metrics=session.metrics()
                            if metrics.get('canvas_id')==document['id'] and int(metrics.get('canvas',{}).get('modelNodes',0))==count:
                                return metrics['canvas']
                        canvas=wait_for(rendered,30)
                        # Two opposing wheel gestures exercise the live renderer
                        # on every open and leave the same camera for comparison.
                        center=[canvas['x']+canvas['width']/2,canvas['y']+canvas['height']/2]
                        for delta in (-120,120):session.action('input',{'kind':'wheel','at':center,'delta':delta})
                        session.idle()
                        result['switch_checks'].append({'nodes':count,'rendered_nodes':int(canvas['modelNodes']),
                            'renderer':canvas.get('renderer'),'seconds':round(time.monotonic()-switch_started,3)})
                        cycle+=1;last=time.monotonic()-started
                    sample=sampler.sample(source_main_pids=[session.owned_pid] if source else [],root_pids=[] if source else [session.process.pid,session.owned_pid])
                    result['samples'].append({k:v for k,v in sample.items() if k not in ('processes','rejected_roots')}
                        |{'elapsed_seconds':round(time.monotonic()-started,3),'nodes':50 if cycle%2 else 5000,'switches':cycle})
                    save();time.sleep(min(5,max(.01,seconds-(time.monotonic()-started))))
                result.update(elapsed_seconds=round(time.monotonic()-started,3),switches=cycle)
                comparisons=[]
                for count in (50,5000):
                    rows=[row for row in result['samples'] if row['nodes']==count and row['elapsed_seconds']>=min(180,seconds/4) and row.get('private_commit_bytes_sum') is not None]
                    half=max(1,len(rows)//2);first=statistics.median(row['private_commit_bytes_sum'] for row in rows[:half]);last_memory=statistics.median(row['private_commit_bytes_sum'] for row in rows[-half:])
                    comparisons.append({'nodes':count,'first_half_private_commit_median':first,'last_half_private_commit_median':last_memory,
                        'change_bytes':last_memory-first,'within_warm_cache_tolerance':last_memory-first<=max(128*1024**2,first*.2)})
                result['memory_comparison']=comparisons
                result['memory_semantics']='Own process-tree private commit. Compare same graph size after warm-up; tolerance max(128 MiB, 20%). This bounds this run, not proof against every leak.'
                result['passed']=all(row['within_warm_cache_tolerance'] for row in comparisons);save()
            except BaseException as error:
                result.update(error_type=type(error).__name__,error=str(error)[:200],step=getattr(session,'qa_step',''))
                try:
                    status=session.status().get('desktop',{})
                    result['failure_surface']={k:status.get(k) for k in ('visible','page_visible','lifecycle_state','recommended_state','ready','diagnostics')}
                    result['failure_canvas_metrics']=session.canvas().get('metrics',{})
                except Exception:pass
                save();raise
            finally:
                try:session.stop()
                finally:
                    if execution_state:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
                    result['owned_processes_left']=sampler.sample()['process_count'];sampler.close();save()
    result['temporary_profile_removed']=not directory.exists()
    result['passed']=result['passed'] and not result['owned_processes_left'];save()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=1200);parser.add_argument('--interval',type=int,default=30);parser.add_argument('--source',action='store_true');parser.add_argument('--keep-display-awake',action='store_true')
    args=parser.parse_args()
    if not 120<=args.seconds<=3600 or not 5<=args.interval<=60:parser.error('Use 120–3600 seconds and 5–60 second switching intervals.')
    if args.report.resolve().is_relative_to((ROOT/'dist').resolve()):parser.error('Reports must be outside dist.')
    report=run(args.exe.resolve(),args.report.resolve(),seconds=args.seconds,interval=args.interval,source=args.source,keep_awake=args.keep_display_awake)
    print(json.dumps({k:v for k,v in report.items() if k not in ('samples','switch_checks')},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
