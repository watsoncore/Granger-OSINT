"""QA-only native-cost A/B; isolated source GUI, numeric counters, no real keys.

Changes live widget/timer/QSS state only inside this process. No production
defaults, global GPU flags, system settings or other apps are modified.
"""
from __future__ import annotations
import argparse
import collections
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import ctypes
from ctypes import wintypes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def own_threads():
    """Read CPU counters/descriptions for this process's own Windows threads."""
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    class Entry(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('tid',wintypes.DWORD),('pid',wintypes.DWORD),('base',wintypes.LONG),('delta',wintypes.LONG),('flags',wintypes.DWORD)]
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD];kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.Thread32First.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];kernel.Thread32Next.argtypes=kernel.Thread32First.argtypes
    kernel.OpenThread.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenThread.restype=wintypes.HANDLE
    kernel.GetThreadTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.GetThreadDescription.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.LPWSTR)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.LocalFree.argtypes=[ctypes.c_void_p]
    snapshot=kernel.CreateToolhelp32Snapshot(4,0);entry=Entry();entry.size=ctypes.sizeof(entry);rows={}
    ok=kernel.Thread32First(snapshot,ctypes.byref(entry))
    try:
        while ok:
            if entry.pid==os.getpid():
                handle=kernel.OpenThread(0x0800,False,entry.tid)
                if handle:
                    try:
                        born,exit,kern,user=(wintypes.FILETIME() for _ in range(4))
                        if kernel.GetThreadTimes(handle,ctypes.byref(born),ctypes.byref(exit),ctypes.byref(kern),ctypes.byref(user)):
                            name=wintypes.LPWSTR()
                            desc=''
                            if kernel.GetThreadDescription(handle,ctypes.byref(name))>=0 and name:
                                desc=name.value or '';kernel.LocalFree(ctypes.cast(name,ctypes.c_void_p))
                            ticks=lambda value:(value.dwHighDateTime<<32)|value.dwLowDateTime
                            rows[entry.tid]={'name':desc,'ticks':ticks(kern)+ticks(user)}
                    finally:kernel.CloseHandle(handle)
            ok=kernel.Thread32Next(snapshot,ctypes.byref(entry))
    finally:kernel.CloseHandle(snapshot)
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=6)
    parser.add_argument('--variant-group',choices=('full','running-qss','baseline'),default='full')
    parser.add_argument('--event-loop',choices=('qtest','qt'),default='qtest')
    parser.add_argument('--system-font-only',action='store_true')
    args=parser.parse_args()
    out=args.output.resolve()
    if out.exists():raise SystemExit('Prior evidence preserved')
    out.mkdir(parents=True)
    os.environ['APPDATA']=str(out/'appdata')
    for key in ('DEEPSEEK_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtCore import QEvent,QEventLoop,QTimer
    from PySide6.QtGui import QColor,QFont,QPalette
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from grangerpet.desktop_surface import register_desktop_scheme
    from grangerpet.config import Settings,SettingsStore
    import grangerpet.credentials as credentials
    from grangerpet.pet import PetWindow
    from grangerpet.theme import apply_theme
    from grangerpet.typography import apply_app_font
    if args.system_font_only:
        import grangerpet.typography as typography
        typography.font_family=lambda:'Segoe UI'
    from perf_process_metrics import ProcessSampler,summarize
    register_desktop_scheme()
    operations={}
    active=[False]
    class ProbeApplication(QApplication):
        def notify(self,watched,event):
            if not active[0]:return super().notify(watched,event)
            kind=int(event.type())
            name=f'{watched.metaObject().className()}:{kind}'
            before=time.perf_counter_ns()
            try:return super().notify(watched,event)
            finally:
                row=operations.setdefault(name,{'calls':0,'total_ns':0,'max_ns':0})
                spent=time.perf_counter_ns()-before
                row['calls']+=1;row['total_ns']+=spent;row['max_ns']=max(row['max_ns'],spent)
    app=ProbeApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setProperty('web_desktop',True)
    apply_app_font(app);app.setStyle('Fusion');apply_theme(app,'dark')
    profile=out/'appdata/GrangerPet'
    credentials._STORE=credentials.CredentialsStore(prefix='GrangerPet/NativeCost-QA/'+uuid.uuid4().hex,
        directory=profile/'vault',data_root=profile)
    credentials._STORE.portable.create('synthetic native cost QA passphrase',secrets={})
    settings=Settings(ai_provider='none',size=195,cursor_reaction=True,reduced_motion=False)
    store=SettingsStore(profile/'settings.json');store.save(settings)
    pet=PetWindow(settings,store,interaction_qa=True)
    pet.show();panel=pet.panel;surface=panel.desktop_surface
    panel.show();panel.raise_();panel.activateWindow()
    monitor=ProcessSampler(gpu=False)
    # venv Windows launcher hands execution to its base interpreter. This is
    # still our own exact PID/image, never a discovered unrelated Python process.
    monitor.source_images.add(monitor.api.counters(os.getpid())['image'].casefold())
    results=[]
    def pause(milliseconds):
        if args.event_loop=='qtest':return QTest.qWait(milliseconds)
        loop=QEventLoop();QTimer.singleShot(milliseconds,loop.quit);loop.exec()
    def wait(predicate,seconds=30):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            app.processEvents()
            if predicate():return
            pause(30)
        raise TimeoutError('Own source UI timed out')
    def js(code):
        result=[];surface.page().runJavaScript(code,lambda value:result.append(value));wait(lambda:bool(result));return result[0]
    def sample(name):
        pause(1500)
        operations.clear();active[0]=True
        thread_start=own_threads()
        start_cpu=time.process_time();start=time.perf_counter()
        monitor.sample(source_main_pids=[os.getpid()]);values=[]
        for _ in range(args.seconds):
            pause(1000)
            values.append(monitor.sample(source_main_pids=[os.getpid()]))
        active[0]=False
        wall=time.perf_counter()-start
        thread_end=own_threads()
        thread_cpu=[{'tid':tid,'name':row['name'],'cpu_percent_one_core':100*(row['ticks']-thread_start[tid]['ticks'])/10_000_000/wall} for tid,row in thread_end.items() if tid in thread_start]
        row={'name':name,'samples':values,'summary':summarize(values),
            'own_cpu_percent_one_core':100*(time.process_time()-start_cpu)/(time.perf_counter()-start),
            'native_events':dict(sorted(operations.items(),key=lambda item:item[1]['total_ns'],reverse=True)[:30]),
            'own_threads_cpu':sorted(thread_cpu,key=lambda row:row['cpu_percent_one_core'],reverse=True)[:12],
            'pet_visible':pet.isVisible(),'frame_timer_active':pet.frame_timer.isActive(),'configured_size':pet.settings.size,
            'display_size':pet._display_size,'workspace_active':panel.isActiveWindow(),
            'pet_geometry':[pet.x(),pet.y(),pet.width(),pet.height()],
            'dock_geometry':[panel.hermione_dock_geometry().x(),panel.hermione_dock_geometry().y(),panel.hermione_dock_geometry().width(),panel.hermione_dock_geometry().height()]}
        results.append(row);save()
        print(json.dumps({'name':name,'onecore':round(row['summary']['medians']['cpu_percent_one_core'],2),'own_onecore':round(row['own_cpu_percent_one_core'],2),'events':list(row['native_events'].items())[:3]}),flush=True)
    def save():
        (out/'report.json').write_text(json.dumps({'method':'QA-only changes inside an isolated production source PetWindow/QtWebEngine process; 1000 synthetic messages, empty unique encrypted QA vault, no APIs or real credentials; no global/system/other-app changes',
            'pid':os.getpid(),'native_dpr':app.primaryScreen().devicePixelRatio(),'seconds':args.seconds,'event_loop':args.event_loop,'native_font_registration_skipped':args.system_font_only,
            'event_timing_notes':'QApplication.notify durations include nested events and are not additive CPU; ProcessSampler CPU is authoritative. Per-event timing adds QA overhead equally to each variant.',
            'variants':results},indent=2),'utf-8')
    try:
        wait(lambda:surface.bridge.ui_ready)
        panel.chat_widget.messages=[{'id':f'qa-{i}','role':'model' if i%2 else 'user',
            'text':f'ТЕСТОВАЯ запись {i}. Публичный пример; не реальные результаты.\n\n'+('Контекст и ограничения. '*10)} for i in range(1000)]
        surface.bridge.publish(force=True);pause(3000)
        app_qss=app.styleSheet();panel_qss=panel.styleSheet();palette=app.palette();font=app.font();background=surface.page().backgroundColor()
        if args.variant_group=='baseline':
            sample('normal_1000_visible')
            return 0
        if args.variant_group=='running-qss':
            sample('running_current_qss_font_palette')
            app.setStyleSheet('');panel.setStyleSheet('')
            sample('running_no_app_or_panel_qss_current_font_palette')
            baseline=subprocess.run(['git','show','034e289:grangerpet/theme.py'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True).stdout
            import ast
            parsed=ast.parse(baseline)
            old_qss=next(ast.literal_eval(node.value) for node in parsed.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='STYLE' for target in node.targets))
            app.setStyleSheet(old_qss);panel.setStyleSheet(old_qss)
            sample('running_legacy_style_current_palette')
            app.setPalette(app.style().standardPalette())
            old_font=QFont('Segoe UI');old_font.setPixelSize(14);app.setFont(old_font)
            sample('running_legacy_style_legacy_palette_segoe')
            app.setStyleSheet(app_qss);panel.setStyleSheet(panel_qss)
            sample('running_current_style_legacy_palette_segoe')
            app.setPalette(palette);app.setFont(font)
            sample('running_current_all_restored')
            return 0
        sample('normal_1000_visible')
        frame_interval=pet.frame_timer.interval();cursor_interval=pet.cursor_timer.interval()
        pet.frame_timer.stop();pet.cursor_timer.stop()
        sample('visible_pet_timers_stopped')
        pet.hide()
        sample('hidden_pet_timers_stopped')
        app.setStyleSheet('');panel.setStyleSheet('')
        sample('hidden_pet_no_application_or_panel_qss')
        app.setFont(QFont('Segoe UI',10))
        sample('hidden_pet_no_qss_system_font')
        app.setStyleSheet(app_qss);panel.setStyleSheet(panel_qss);app.setFont(font);app.setPalette(palette)
        pet.show();pet.frame_timer.start(frame_interval);pet.cursor_timer.start(cursor_interval)
        sample('restored_normal_1000_visible')
        surface.page().setBackgroundColor(QColor('white'))
        sample('normal_page_background_white')
        surface.page().setBackgroundColor(background)
        js("document.querySelector('[aria-label=\"Показать Гермиону и источники\"]')?.click()")
        pause(700)
        sample('explicit_open_dock_normal_animation')
        # Keep the precise current alpha region stable, for diagnostic A/B only.
        normal_mask=pet.setMask
        pet.setMask=lambda region:None
        sample('open_dock_stable_native_region')
        pet.setMask=normal_mask
        normal_mask(pet._region)
        sample('open_dock_native_region_restored')
        js("document.querySelector('[aria-label=\"Свернуть панель Гермионы\"]')?.click()")
        pause(700)
        sample('collapsed_dock_normal_animation')
        panel.showMinimized()
        sample('minimized_workspace_normal_pet_animation')
        panel.showNormal();panel.raise_();panel.activateWindow()
        pause(1000)
        # A zero-alpha view is diagnostic only; not a proposed production mode.
        pet.frame_timer.stop();pet.cursor_timer.stop();pet.hide()
        surface.hide()
        sample('webengine_widget_hidden')
        surface.show();panel.activateWindow();pause(1500)
        sample('webengine_widget_reshown_pet_hidden')
    finally:
        active[0]=False;monitor.close();pet.shutdown();panel.close();app.processEvents();save()
    return 0


if __name__=='__main__':raise SystemExit(main())
