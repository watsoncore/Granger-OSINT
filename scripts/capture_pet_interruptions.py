"""Record real EXE click/drag/hover events through the production renderbuffer.

The camera follows the owned pet window; no other desktop pixels are read.
QTest events and the normal cursor/physics timers drive the reactions.
"""
import argparse
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--exe',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Existing evidence preserved')
    out.mkdir(parents=True);ns=uuid.uuid4().hex
    os.environ.update(APPDATA=str(out/'appdata'),GRANGERPET_QA_NAMESPACE=ns,
        GRANGERPET_QA_VAULT='GrangerPet/QA/interrupt_'+ns,GRANGERPET_INTERACTION_TRACE=str(out/'trace.jsonl'))
    for key in ('QT_QPA_PLATFORM','DEEPSEEK_API_KEY','GEMINI_API_KEY'):os.environ.pop(key,None)
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    from grangerpet.config import Settings,SettingsStore
    from grangerpet.ipc import send_command
    SettingsStore().save(Settings(ai_provider='none',size=195,cursor_reaction=True,x=30,y=400))
    user=ctypes.WinDLL('user32');user.GetWindowLongW.argtypes=[W.HWND,ctypes.c_int];user.GetWindowLongW.restype=ctypes.c_long
    user.SetWindowLongW.argtypes=[W.HWND,ctypes.c_int,ctypes.c_long]
    user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
    user.IsWindowVisible.argtypes=[W.HWND];user.GetWindowRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
    user.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int]
    owned=None;process=None;guards=[];hwnd=None;report={'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'events':[],'api_requests':0}
    def cmd(name,payload=None):
        value=send_command('pet',name,payload,timeout=3000)
        if not value or not value.get('ok'):raise RuntimeError('Own command failed: '+name)
        if name=='status' and owned and value['pid']!=owned:raise RuntimeError('Own PID mismatch')
        return value
    def wait(fn,seconds=60):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=fn()
            if value:return value
            time.sleep(.1)
        raise TimeoutError('Own interruption capture timed out')
    try:
        with (out/'process.log').open('wb') as log:process=subprocess.Popen([str(args.exe.resolve()),'--pet','--interaction-qa'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
        owned=wait(lambda:send_command('pet','status'))['pid'];wait(lambda:cmd('status').get('desktop',{}).get('ready'))
        callback_type=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM);user.EnumWindows.argtypes=[callback_type,W.LPARAM]
        @callback_type
        def guard(window,_):
            nonlocal hwnd
            pid=W.DWORD();user.GetWindowThreadProcessId(window,ctypes.byref(pid))
            if pid.value==owned and user.IsWindowVisible(window):
                style=user.GetWindowLongW(window,-20);guards.append((window,style));user.SetWindowLongW(window,-20,style|0x20)
                if hwnd is None:hwnd=window
            return True
        user.EnumWindows(guard,0)
        if hwnd is None:raise RuntimeError('No owned native pet surface')
        cmd('qa_figure',{'action':'away'});time.sleep(.2)
        plan=[(0.,'reading'),(2.8,'click'),(5.,'reading'),(7.8,'drag_up'),(10.5,'reading'),(13.3,'drag_down'),
            (16.,'reading'),(18.8,'hover'),(19.3,'left'),(19.8,'right'),(20.3,'up'),(20.8,'down'),(21.4,'away')]
        directory=out/'drag-interrupt';directory.mkdir();rows=[];start=time.monotonic();step=0
        for i in range(22*24):
            due=start+i/24
            while time.monotonic()<due:time.sleep(min(.01,due-time.monotonic()))
            elapsed=time.monotonic()-start
            while step<len(plan) and elapsed>=plan[step][0]:
                event=plan[step][1]
                if event=='reading':cmd('qa_life',{'action':'reading','duration':18,'variant':0})
                elif event in ('left','right','up','down'):
                    box=W.RECT();user.GetWindowRect(hwnd,ctypes.byref(box))
                    x,y={'left':(.23,.4),'right':(.76,.4),'up':(.45,.17),'down':(.45,.82)}[event]
                    user.SetCursorPos(round(box.left+(box.right-box.left)*x),round(box.top+(box.bottom-box.top)*y))
                else:cmd('qa_figure',{'action':event})
                report['events'].append({'at':elapsed,'event':event});step+=1
            state=cmd('status');name='interrupt-'+str(i).zfill(4)
            cmd('qa_snapshot',{'name':name});source=out/(name+'-pet.png')
            wait(lambda:source.is_file(),3);source.rename(directory/f'{len(rows):04}.png')
            rows.append({'at':time.monotonic()-start,'action':state['life']['action'],'progress':0,'variant':0,
                'activity':state['state'],'reaction':state['drag_reaction'],'signature':state['pet_render']['signature']})
        capture={'method':'Live production EXE renderbuffers following the pet window; real QTest input/cursor/physics clocks; no desktop capture',
            'frames':rows,'duration':time.monotonic()-start,'requested_fps':24}
        (directory/'capture.json').write_text(json.dumps(capture,indent=2),encoding='utf-8')
        from assemble_chibi_capture import assemble
        assemble(directory)
        seen={r['reaction'] for r in rows};report['passed']={'jerk_up','jerk_down'}<=seen
        report['reactions']=sorted(seen);report['frames']=len(rows)
        for window,style in guards:user.SetWindowLongW(window,-20,style)
        guards=[];cmd('stop');process.wait(timeout=30);owned=None
    finally:
        for window,style in guards:user.SetWindowLongW(window,-20,style)
        if owned and process and process.poll() is None:cmd('stop');process.wait(timeout=30)
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report.get('passed'),'frames':report.get('frames'),'reactions':report.get('reactions')}))


if __name__=='__main__':main()
