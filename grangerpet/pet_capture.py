"""Bounded native-widget recorder, reachable only through isolated QA IPC."""
import json
from pathlib import Path
import time
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QImage,QPainter


def start_capture(pet,name,duration,fps,mode='widget'):
    if getattr(pet,'_qa_capture',None) is not None:return False
    directory=Path(pet._trace_path).parent/name
    if directory.exists():return False
    directory.mkdir();timer=QTimer(pet);timer.setTimerType(Qt.TimerType.PreciseTimer)
    # Visual recording must not intercept clicks on the user's real workspace.
    # This guard is confined to an isolated QA instance, never normal runtime.
    restore_input=lambda:None;restore_background=lambda:None
    import sys
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        user=ctypes.WinDLL('user32');hwnd=int(pet.winId())
        user.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int];user.GetWindowLongW.restype=ctypes.c_long
        user.SetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_long]
        old=user.GetWindowLongW(hwnd,-20);user.SetWindowLongW(hwnd,-20,old|0x20)
        restore_input=lambda:user.SetWindowLongW(hwnd,-20,old)
        if mode=='native_text':
            # Keep only the isolated test app above the desktop during this
            # bounded recording. Focus stays with the user's current app.
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            background=int(pet.panel.winId());was_topmost=bool(user.GetWindowLongW(background,-20)&8)
            for window in (pet.panel,pet,pet.cameo):
                if window and window.isVisible():user.SetWindowPos(int(window.winId()),wintypes.HWND(-1),0,0,0,0,0x53)
            if not was_topmost:restore_background=lambda:user.SetWindowPos(background,wintypes.HWND(-2),0,0,0,0,0x13)
    pet._qa_capture=timer;started=time.monotonic();rows=[];record_bounds=None;screen_roi=None;dropped={}
    def finish(now):
        timer.stop();timer.deleteLater();pet._qa_capture=None;restore_input();restore_background()
        report={'method':'Guarded Win32 compositor capture over the actual owned Granger application with text' if mode=='native_text' else
            'Live native QWidget.grab of owned production windows; normal production clock; no desktop content',
            'requested_fps':fps,'duration':now-started,'physical_input':'QA recording only: native click-through enabled, then restored',
            'mode':mode,'background_guard':'Owned opaque app temporarily topmost; foreign overlapping windows rejected before and after BitBlt' if mode=='native_text' else None,
            'native_geometry':getattr(pet,'_qa_native_geometry',None),'dropped_frames':dropped,'frames':rows}
        (directory/'capture.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def frame():
        nonlocal record_bounds,screen_roi
        now=time.monotonic();pose=pet.life.pose(now);dpr=pet.devicePixelRatioF()
        bounds=pet.frameGeometry()
        guest=pet.cameo if pet.cameo and pet.cameo.isVisible() else None
        if record_bounds is None:
            record_bounds=bounds.adjusted(-pet.width(),0,pet.width(),0) if pose.cameo else bounds
        bounds=record_bounds
        if mode=='native_text':
            from .native_capture import capture_owned_background
            captured,reason=capture_owned_background(pet,screen_roi)
            if captured is None:
                dropped[reason]=dropped.get(reason,0)+1
                if now-started>=duration or pet._ending:finish(now)
                return
            image,screen_roi=captured
        else:
            image=QImage(round(bounds.width()*dpr),round(bounds.height()*dpr),QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(dpr);image.fill(Qt.GlobalColor.transparent)
            p=QPainter(image);p.drawPixmap(pet.pos()-bounds.topLeft(),pet.grab())
            if guest:p.drawPixmap(guest.pos()-bounds.topLeft(),guest.grab())
            p.end()
        image.save(str(directory/f'{len(rows):04}.png'))
        rows.append({'at':round(now-started,6),'action':pose.action,'variant':pose.variant,
            'progress':round(pose.progress,6),'frame':pose.frame,'signature':str(pet._render_signature),
            'bounds':list(screen_roi or bounds.getRect()),'dpr':dpr,'activity':pet.animation.state})
        if now-started>=duration or pet._ending:
            finish(now)
    timer.timeout.connect(frame);timer.start(round(1000/fps));return True
