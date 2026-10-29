"""Actual optional CPU model checks; no user images, history or source credentials."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.visual_models.manager import VisualModelManager
    from grangerpet.visual_models.pipeline import haversine_km
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frozen',action='store_true');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--photos',type=Path,default=ROOT/'output/integrations19/visual-photos')
    p.add_argument('--probe-only',action='store_true');args=p.parse_args()
    out=args.output.resolve()
    if out.exists():raise SystemExit('Prior evidence preserved; choose a fresh output directory')
    out.mkdir(parents=True)
    executable=ROOT/'dist/Granger-OSINT.exe'
    report={'mode':'actual_frozen_child' if args.frozen else 'actual_source_child','models_mocked':False,
        'device':'cpu','checks':[],'observations':[],'passed':False,'source_head':None}
    if args.frozen:
        report.update(exe_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),exe_bytes=executable.stat().st_size)
        # Select the very same manager transport as production frozen GUI uses.
        sys.frozen=True;sys.executable=str(executable)
    manager=VisualModelManager(ROOT/'.toolenvs/visual-cpu')
    def save():
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def check(name,condition):
        report['checks'].append({'name':name,'passed':bool(condition)});save()
        if not condition:raise AssertionError(name)
    def observation(name,operation):
        start=time.perf_counter();value=operation();value['wall_seconds']=round(time.perf_counter()-start,3)
        (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        report['observations'].append({'name':name,'status':value.get('status'),'wall_seconds':value['wall_seconds'],
            'duration_ms':value.get('duration_ms'),'cached':value.get('cached'),'error_code':value.get('error_code'),
            'process_peak_rss_bytes':value.get('process_peak_rss_bytes'),'process_peak_private_bytes':value.get('process_peak_private_bytes')})
        print(json.dumps(report['observations'][-1]),flush=True);save();return value
    try:
        probe=observation('probe',lambda:manager.probe(deadline=time.monotonic()+120))
        check('real_CPU_imports_and_ONNX_execution',probe.get('status')=='completed' and probe.get('onnx_cpu_probe') is True and probe.get('torch_cuda_runtime') is None)
        if not args.probe_only:
            known={'moscow-no-gps':[55.7525,37.6231],'paris-no-gps':[48.85636,2.29743]}
            photos={name:(args.photos/(name+'.jpg')).read_bytes() for name in (*known,'texture-no-clues')}
            results={}
            for component in ('geoclip','waypoint'):
                for photo,raw in photos.items():
                    result=observation(component+'-'+photo,lambda c=component,b=raw:manager.infer(c,b,top_k=10,samples=32,deadline=time.monotonic()+180))
                    results[component,photo]=result
                    check(component+'_'+photo+'_executed',result.get('status')=='completed' and result.get('network_enabled') is False)
                    check(component+'_'+photo+'_uncalibrated',result.get('score_calibrated') is False)
                    if photo in known:
                        distances=[haversine_km(known[photo],[r['lat'],r['lon']]) for r in result.get('predictions',[])]
                        report.setdefault('known_photo_distances',{})[component+'-'+photo]={'minimum_candidate_distance_km':min(distances) if distances else None,
                            'meaning':'Distance to known site/camera, observed result; not a model accuracy benchmark'}
                    save()
            check('different_photos_not_same_cached_output',results['geoclip','moscow-no-gps']['predictions']!=results['geoclip','paris-no-gps']['predictions'])
            check('warm_model_cache_observed',results['geoclip','paris-no-gps'].get('cached') is True)
            match=observation('same_photo_matching',lambda:manager.match(photos['moscow-no-gps'],photos['moscow-no-gps'],deadline=time.monotonic()+180))
            check('DISK_LightGlue_actual_matches',match.get('status')=='completed' and match.get('match_count',0)>0)
            report['matching_limitation']='Same-image functional check, not independent street imagery or geolocation validation.'
            manager.close();cancel=threading.Event();reply=[]
            thread=threading.Thread(target=lambda:reply.append(manager.infer('waypoint',photos['moscow-no-gps'],samples=256,cancel_event=cancel,deadline=time.monotonic()+180)))
            thread.start();until=time.monotonic()+10
            while not manager._process and thread.is_alive() and time.monotonic()<until:time.sleep(.05)
            time.sleep(.5);start=time.monotonic();cancel.set();thread.join(8)
            report['cancellation']={'elapsed_seconds':round(time.monotonic()-start,3),'status':reply[0].get('status') if reply else None,
                'thread_finished':not thread.is_alive(),'child_reaped':manager._process is None}
            check('cancel_reaps_own_child',bool(reply) and reply[0].get('status')=='cancelled' and not thread.is_alive() and manager._process is None)
            restarted=observation('restart_cached_weights',lambda:manager.infer('waypoint',photos['paris-no-gps'],samples=8,deadline=time.monotonic()+180))
            check('restart_offline_no_download',restarted.get('status')=='completed' and restarted.get('network_enabled') is False)
        report['passed']=True
    except Exception as error:
        report['error_type']=type(error).__name__;report['error']=str(error)[:100]
    finally:
        manager.close();save()
    print(json.dumps({'passed':report['passed'],'checks':len(report['checks'])}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
