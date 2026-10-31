"""Own native Pet/Qt/WebEngine QA; isolated profile, no credentials or API calls."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exe',type=Path)
    parser.add_argument('--scenes',action='store_true')
    parser.add_argument('--only-scenes',nargs='+')
    parser.add_argument('--soak-seconds',type=int,choices=range(0,601),default=0)
    parser.add_argument('--natural-seconds',type=int,choices=range(130,481),default=130)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Choose a new output; previous evidence retained')
    out.mkdir(parents=True);namespace=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=namespace,
        GRANGERPET_QA_VAULT='GrangerPet/QA/pet_'+namespace,GRANGERPET_INTERACTION_TRACE=str(out/'interaction.jsonl'))
    for name in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(name,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    SettingsStore().save(Settings(ai_provider='none',size=160,cursor_reaction=True,source_root=str(ROOT)))
    report={'mode':'native_final_exe' if args.exe else 'native_current_source','network_calls':0,
        'empty_isolated_profile':True,'checks':[]}
    if args.exe:report['exe_sha256']=hashlib.sha256(args.exe.read_bytes()).hexdigest()
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def check(name,ok):
        report['checks'].append({'name':name,'passed':bool(ok)});save();print(name+': '+str(bool(ok)),flush=True)
        if not ok:raise AssertionError(name)
    owned=None;process=None
    def state():
        value=send_command('pet','status',timeout=1500)
        if value and owned and value['pid']!=owned:raise RuntimeError('Own isolated PID mismatch')
        return value
    def command(name,payload=None):
        value=send_command('pet',name,payload,timeout=3000)
        if not value or not value.get('ok'):raise RuntimeError('Own command failed: '+name)
        return value
    def action(name,payload=None):command('qa_desktop',{'action':name,'payload':payload or {}})
    def wait(fn,seconds=40):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.12)
        raise TimeoutError('Own pet QA condition did not complete')
    def dom():
        action('dom');time.sleep(.12)
        return (state().get('desktop') or {}).get('dom',{})
    def capture(name):command('qa_snapshot',{'name':name})
    def native_click_through_guest():
        import ctypes
        from ctypes import wintypes as W
        user=ctypes.WinDLL('user32');found=[]
        user.GetWindowLongW.argtypes=[W.HWND,ctypes.c_int];user.GetWindowLongW.restype=ctypes.c_long
        user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
        user.IsWindowVisible.argtypes=[W.HWND]
        callback_type=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        @callback_type
        def visit(hwnd,param):
            pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value==owned and user.IsWindowVisible(hwnd) and user.GetWindowLongW(hwnd,-20)&0x20:found.append(True)
            return True
        user.EnumWindows(visit,0)
        return bool(found)
    try:
        argv=([str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'main.py')])+['--pet','--interaction-qa']
        with (out/'process.log').open('wb') as log:
            process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(state,60)['pid'];wait(lambda:state().get('desktop',{}).get('ready'))
        command('qa_figure',{'action':'away'})
        a=state();time.sleep(.4);b=state()
        check('native_idle_pixels_advance',a['pet_render']['signature']!=b['pet_render']['signature'])
        command('show_workspace',{'route':'chat'});action('window',{'mode':'maximize'})
        wait(lambda:next((e for e in dom().get('elements',[]) if e.get('label')=='Сообщение Гермионе'),None))
        restore=next((e for e in dom().get('elements',[]) if e.get('label')=='Показать Гермиону и источники' and e['width']>0),None)
        if restore:action('input',{'kind':'click','at':[restore['x']+restore['width']/2,restore['y']+restore['height']/2]})
        wait(lambda:state()['pet_render']['visible'])
        command('qa_figure',{'action':'away'});time.sleep(.3)
        command('qa_life',{'action':'schedule'})
        live=wait(lambda:s if (s:=state())['life']['active'] else None,10)
        from grangerpet.pet_life import SCENES
        name=live['life']['action'];check('scheduler_starts_while_workspace_active',name in SCENES)
        command('qa_life',{'action':'reading','duration':18});time.sleep(.2);name='reading'
        for route in ('search','settings','history','chat'):
            action('route',{'route':route});time.sleep(.3)
            check('navigation_'+route+'_does_not_reset_figure_idle',state()['life']['action']==name)
        e=wait(lambda:next((e for e in dom().get('elements',[]) if e.get('label')=='Сообщение Гермионе' and e['width']>0),None))
        action('input',{'kind':'click','at':[e['x']+30,e['y']+15]})
        action('input',{'kind':'text','text':'Native QA draft, no request sent.'})
        check('typing_draft_does_not_cancel_autonomy',state()['life']['action']==name)
        capture('autonomy-during-work')
        command('qa_figure',{'action':'hover'})
        wait(lambda:not state()['life']['active'],4)
        check('real_figure_hover_interrupts_scene',state()['near'] or state()['hovered'])
        command('qa_figure',{'action':'away'})
        command('qa_life',{'action':'reading'});time.sleep(.8);capture('reading')
        command('qa_figure',{'action':'drag_up'});time.sleep(.2)
        check('actual_up_drag_reaction',state()['drag_reaction']=='jerk_up')
        capture('up-drag');time.sleep(2.6)
        command('qa_figure',{'action':'drag_down'});time.sleep(.2)
        check('actual_down_drag_reaction',state()['drag_reaction']=='jerk_down')
        capture('down-drag')
        wait(lambda:state()['drag_reaction']=='calm',8)
        check('release_recovers_without_drag_timer',not state()['pet_render']['drag_timer'])
        for size in (100,195,160):
            command('settings',{'size':size});time.sleep(.3)
            check('scale_'+str(size)+'_visible',state()['pet_render']['visible'])
        command('qa_figure',{'action':'away'});command('qa_life',{'action':'reading'})
        wait(lambda:state()['life']['active']);wait(lambda:not state()['life']['active'],8)
        check('scene_completes_and_clears',True)
        if args.scenes or args.only_scenes:
            for name,spec in SCENES.items():
                if args.only_scenes and name not in args.only_scenes:continue
                command('qa_figure',{'action':'away'});time.sleep(.2)
                command('qa_life',{'action':name,'duration':3})
                wait(lambda:state()['life']['action']==name)
                time.sleep(.85);capture('scene-'+name)
                if spec.cameo:
                    report.setdefault('cameo_diagnostics',{})[name]=state()['cameo'];save()
                    wait(lambda:state()['cameo']['visible'],2)
                    check(name+'_actual_guest_visible',state()['cameo']['actor']==spec.cameo)
                    check(name+'_native_input_transparency',state()['cameo']['input_transparent'])
                    check(name+'_actual_Windows_input_transparent_style',native_click_through_guest())
                wait(lambda:not state()['life']['active'],6)
                check(name+'_finishes_and_removes_guest',not state()['cameo']['visible'])
            command('settings',{'size':195});time.sleep(.4)
            command('qa_life',{'action':'malfoy','duration':8});wait(lambda:state()['cameo']['visible'])
            time.sleep(.8);capture('malfoy-default-scale')
            check('default_195_scale_cameo_fits_existing_dock',state()['cameo']['room_available'])
            command('qa_figure',{'action':'hover'})
            wait(lambda:not state()['cameo']['visible'],3)
            check('figure_interrupt_removes_actual_cameo',True)
        command('qa_figure',{'action':'away'});command('qa_life',{'action':'reading','duration':15})
        for mode in ('minimize','maximize','maximize','close'):
            action('window',{'mode':mode});time.sleep(.4)
            command('show_workspace',{'route':'chat'});time.sleep(.4)
            wait(lambda:state()['pet_render']['visible'])
            check('window_'+mode+'_retains_live_figure',state()['pet_render']['frame_timer'])
        command('qa_life',{'action':'interrupt'});wait(lambda:not state()['life']['active'])
        action('window',{'mode':'close'});time.sleep(.6)
        home=state()['position']
        command('qa_figure',{'action':'away'});command('qa_life',{'action':'malfoy','duration':8})
        wait(lambda:state()['cameo']['visible']);time.sleep(.8);capture('desktop-cameo')
        command('show_workspace',{'route':'chat'});time.sleep(.7)
        command('qa_life',{'action':'interrupt'});wait(lambda:not state()['life']['active'])
        action('window',{'mode':'close'});time.sleep(.7)
        check('open_close_workspace_during_cameo_restores_original_desktop_position',state()['position']==home)
        command('show_workspace',{'route':'chat'});time.sleep(.5)
        if args.soak_seconds:
            from perf_process_metrics import ProcessSampler
            # Forced scene previews legitimately consume their cooldowns.
            # A real restart establishes the ordinary cold-start schedule;
            # no scene clocks, last-played values or deadlines are shortened.
            command('stop');process.wait(timeout=30);owned=None
            with (out/'soak-restart.log').open('wb') as log:
                process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
            owned=wait(state,60)['pid'];wait(lambda:state().get('desktop',{}).get('ready'))
            command('show_workspace',{'route':'chat'});time.sleep(.5)
            restore=next((e for e in dom().get('elements',[]) if e.get('label')=='Показать Гермиону и источники' and e['width']>0),None)
            if restore:action('input',{'kind':'click','at':[restore['x']+restore['width']/2,restore['y']+restore['height']/2]})
            wait(lambda:state()['pet_render']['visible'])
            check('cold_restart_before_unmodified_natural_schedule',not state()['life']['active'])
            monitor=ProcessSampler(args.exe,gpu=False)
            def metrics():return monitor.sample([owned]) if args.exe else monitor.sample(source_main_pids=[owned])
            command('qa_figure',{'action':'away'});time.sleep(1)
            action('route',{'route':'chat'})
            metrics();samples=[];signatures=set();timers=[];natural=set();observations=[];visible_samples=0;start=time.monotonic();turn=0
            previous_visible=None;visible_pairs=0;render_changes=0
            while time.monotonic()-start<args.soak_seconds:
                elapsed=time.monotonic()-start
                if elapsed>=args.natural_seconds and turn%6==0:
                    command('qa_life',{'action':list(SCENES)[(turn//6)%len(SCENES)]})
                    action('route',{'route':['chat','search','settings','history'][(turn//6)%4]})
                elif elapsed<args.natural_seconds and turn%6==0:
                    action('route',{'route':'chat'})
                    e=next((e for e in dom().get('elements',[]) if e.get('label')=='Сообщение Гермионе' and e['width']>0),None)
                    if e:
                        action('input',{'kind':'click','at':[e['x']+30,e['y']+15]})
                        action('input',{'kind':'text','text':' more draft'})
                time.sleep(min(1 if elapsed<args.natural_seconds else 5,max(.1,args.soak_seconds-(time.monotonic()-start))))
                current=state()
                if current['pet_render']['visible']:
                    signature=current['pet_render']['signature']
                    visible_samples+=1;signatures.add(signature)
                    if previous_visible is not None:
                        visible_pairs+=1;render_changes+=signature!=previous_visible
                    previous_visible=signature
                else:previous_visible=None
                if time.monotonic()-start<args.natural_seconds:
                    observations.append({'elapsed':round(time.monotonic()-start,2),'life':current['life'],
                        'near':current['near'],'hovered':current['hovered'],'visible':current['pet_render']['visible']})
                    if current['life']['action']:
                        if current['life']['action'] not in natural:capture('natural-'+current['life']['action'])
                        natural.add(current['life']['action'])
                timers.append(current['pet_render']['owned_timer_count'])
                samples.append(metrics());turn+=1
                if turn%10==0:
                    report['soak_progress']={'elapsed_seconds':round(time.monotonic()-start,2),
                        'natural_actions':sorted(natural),'recent_observations':observations[-3:]};save()
            monitor.close()
            report['soak']={'elapsed_seconds':round(time.monotonic()-start,2),'samples':samples,
                'distinct_render_signatures':len(signatures),'owned_timer_counts':timers,
                'natural_actions_during_130s_typing':sorted(natural),'visible_samples':visible_samples,
                'natural_observations':observations,
                'adjacent_visible_pairs':visible_pairs,'adjacent_render_changes':render_changes,
                'private_commit_notes':'Sum across the owned process tree; not private working set'}
            # A valid looping atlas repeats its frames. Compare adjacent visible
            # observations; distinct-frame cardinality cannot grow with uptime.
            check('native_soak_keeps_rendering',visible_pairs>=2 and render_changes>=visible_pairs*.8)
            if args.soak_seconds>=130:check('natural_figure_idle_starts_during_real_typing_without_shortened_deadline',bool(natural))
            if args.natural_seconds>=280 and args.soak_seconds>=args.natural_seconds:
                check('natural_guest_arrives_without_shortened_deadline',any(SCENES[n].cameo for n in natural if n in SCENES))
            check('native_soak_has_no_timer_accumulation',max(timers)<=timers[0]+1)
            check('native_soak_frame_timer_stays_active',state()['pet_render']['frame_timer'])
        from perf_process_metrics import ProcessSampler
        final_monitor=ProcessSampler(args.exe,gpu=False)
        def final_metrics():return final_monitor.sample([owned]) if args.exe else final_monitor.sample(source_main_pids=[owned])
        final_metrics()
        command('stop');process.wait(timeout=30);owned=None
        check('native_exit_zero',process.returncode==0)
        wait(lambda:final_monitor.sample()['process_count']==0,30)
        check('no_owned_orphans_after_first_exit',True)
        with (out/'restart.log').open('wb') as log:
            process=subprocess.Popen(argv,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(state,60)['pid'];wait(lambda:state().get('desktop',{}).get('ready'))
        check('actual_restart_has_no_leftover_guest_or_scene',not state()['cameo']['visible'] and not state()['life']['active'])
        final_metrics();command('stop');process.wait(timeout=30);owned=None
        wait(lambda:final_monitor.sample()['process_count']==0,30);final_monitor.close()
        check('restart_exit_zero_without_orphans',process.returncode==0);report['passed']=True
    except Exception as error:
        if owned:
            try:
                last=state();report['last_pet']={k:last.get(k) for k in ('state','near','hovered','life','pet_render','cameo')}
                report['last_dock']=last.get('desktop',{}).get('dock_geometry')
            except Exception:pass
        report.update(passed=False,error_type=type(error).__name__,error=str(error));raise
    finally:
        if owned and process and process.poll() is None:
            try:command('stop');process.wait(timeout=30)
            except Exception:process.terminate()
        save()


if __name__=='__main__':main()
