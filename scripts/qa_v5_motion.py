"""Actual owned-window motion snapshots and camera telemetry, never synthetic art.

The application exposes a bounded Qt drag (eight mouse moves per gesture).
This helper records discrete native snapshots after consecutive gestures and
checks the renderer's intermediate requestAnimationFrame camera observations.
It does not measure continuous video FPS or claim whole-session frame timing.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import time

from scripts.qa_clean_release import QaFailure, wait_for


def _rows(value):
    if isinstance(value,str):
        try:value=json.loads(value)
        except (TypeError,ValueError):return []
    return value if isinstance(value,list) else []


def find_pan_path(canvas,segments=6):
    """Choose a visible free corridor, away from nodes, clusters and minimap."""
    width,height=canvas.get('width',0),canvas.get('height',0)
    if width<360 or height<240:raise QaFailure('motion_canvas_too_small')
    dx,dy=18,10
    boxes=[]
    for row in _rows(canvas.get('qaNodes'))+_rows(canvas.get('qaFarClusters')):
        if not isinstance(row,dict):continue
        if all(type(row.get(key)) in (int,float) for key in ('x','y','width','height')):
            boxes.append((row['x']-row['width']/2-24,row['y']-row['height']/2-24,
                row['x']+row['width']/2+24,row['y']+row['height']/2+24))
    for row in _rows(canvas.get('qaEdges')):
        if isinstance(row,dict) and type(row.get('x')) in (int,float) and type(row.get('y')) in (int,float):
            boxes.append((row['x']-18,row['y']-18,row['x']+18,row['y']+18))
    minimap=(width-205,height-135,width,height)
    def inside(x,y,box):
        left,top,right,bottom=box
        return left<=x<=right and top<=y<=bottom
    for y in (45,85,height*.32,height*.62,height-105,*range(25,int(height)-80,24)):
        for x in (45,90,width*.22,width*.48,width*.66,*range(25,int(width)-125,24)):
            path=[(round(x+dx*step),round(y+dy*step)) for step in range(segments+1)]
            # After a successful segment, the graph and pointer have moved by
            # the same vector. Only the initial point must avoid graph cards.
            # The minimap stays fixed, so the entire path must avoid it.
            if any(inside(*path[0],box) for box in boxes):continue
            if all(18<=a<width-20 and 18<=b<height-20 and not inside(a,b,minimap) for a,b in path):return path
    raise QaFailure('motion_no_free_pan_corridor')


def check_motion_frames(frames,start,end,expected_delta,*,tolerance=3):
    """Check observed pan direction/scale and settled ACK; no FPS inference."""
    keys=('x','y','scale')
    valid=[]
    for row in frames:
        if not isinstance(row,dict) or not all(type(row.get(key)) in (int,float) and math.isfinite(row[key]) for key in keys):continue
        valid.append({key:row[key] for key in (*keys,'time','event') if key in row})
    dx,dy=expected_delta;length=math.hypot(dx,dy)
    if not valid or length<1:return {'passed':False,'failure_code':'motion_missing_camera_observations'}
    scale_stable=all(abs(row['scale']-start['scale'])<1e-5 for row in valid)
    progress=[((row['x']-start['x'])*dx+(row['y']-start['y'])*dy)/length for row in valid]
    reversals=[before-after for before,after in zip(progress,progress[1:]) if after<before-tolerance]
    endpoint_error=math.hypot(end['x']-start['x']-dx,end['y']-start['y']-dy)
    endpoint_matches=endpoint_error<=tolerance
    last=valid[-1]
    ack_error=math.hypot(last['x']-end['x'],last['y']-end['y'])
    passed=scale_stable and not reversals and endpoint_matches and ack_error<=tolerance and len(valid)>=4
    return {'passed':passed,'camera_observations':len(valid),'stable_scale':scale_stable,
        'backward_jumps':len(reversals),'largest_backward_jump_px':round(max(reversals,default=0),4),
        'expected_pan_px':[dx,dy],'actual_pan_px':[round(end['x']-start['x'],4),round(end['y']-start['y'],4)],
        'endpoint_error_px':round(endpoint_error,4),'settled_ack_error_px':round(ack_error,4),
        'failure_code':None if passed else 'motion_camera_rewind_scale_or_delta'}


def _camera(canvas):
    try:return {'x':float(canvas['panX']),'y':float(canvas['panY']),'scale':float(canvas['zoom'])}
    except (KeyError,TypeError,ValueError):raise QaFailure('motion_camera_metrics_missing') from None


def _capture(session,name):
    session.command('qa_snapshot',{'name':name})
    path=session.directory/(name+'-search.png')
    wait_for(lambda:path.is_file() and path.stat().st_size>0,10)
    return path


def capture_motion(session,screenshots_dir,name):
    """Record six real Qt pan segments in an already-owned isolated session.

    Caller controls the public QA data and window; this helper never discovers
    another window, starts a process, changes Windows settings or reads profiles.
    Raw snapshots remain in the caller's auto-cleaned temporary QA directory.
    """
    if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,35}',name):raise ValueError('Invalid motion receipt name')
    from PIL import Image
    screenshots_dir=Path(screenshots_dir)
    if screenshots_dir.resolve().is_relative_to((Path(__file__).resolve().parents[1]/'dist').resolve()):raise ValueError('Motion receipts must be outside dist')
    initial=session.metrics()['canvas'];start=_camera(initial);path=find_pan_path(initial)
    baseline=_rows(initial.get('qaCameraFrames'));last_time=max((row.get('time',-1) for row in baseline if isinstance(row,dict)),default=-1)
    frames=[];times=[]
    frames.append(_capture(session,name+'-motion-0'));times.append(time.monotonic())
    for index,(before,after) in enumerate(zip(path,path[1:]),1):
        session.action('input',{'kind':'drag','at':[initial['x']+before[0],initial['y']+before[1]],
            'to':[initial['x']+after[0],initial['y']+after[1]]})
        frames.append(_capture(session,f'{name}-motion-{index}'));times.append(time.monotonic())
    # Observe a settled save ACK as well as the immediate local camera. The
    # caller's document may publish several revisions; do not drive it here.
    time.sleep(.7)
    final=session.metrics()['canvas'];end=_camera(final)
    telemetry=[row for row in _rows(final.get('qaCameraFrames')) if isinstance(row,dict) and row.get('time',-1)>last_time]
    expected=(path[-1][0]-path[0][0],path[-1][1]-path[0][1])
    analysis=check_motion_frames(telemetry,start,end,expected)
    screenshots_dir.mkdir(parents=True,exist_ok=True)
    images=[]
    try:
        for frame in frames:
            with Image.open(frame) as source:images.append(source.convert('RGB'))
        if len({image.size for image in images})!=1:raise QaFailure('motion_window_size_changed')
        durations=[max(20,min(2000,round((b-a)*1000))) for a,b in zip(times,times[1:])]+[700]
        target=screenshots_dir/(name+'-motion.gif')
        images[0].save(target,save_all=True,append_images=images[1:],duration=durations,loop=0,optimize=False,disposal=2)
    finally:
        for image in images:image.close()
    receipts=[]
    for suffix,index in [('start',0),('middle',len(frames)//2),('end',len(frames)-1)]:
        destination=screenshots_dir/(name+'-motion-'+suffix+'.png');destination.write_bytes(frames[index].read_bytes())
        receipts.append({'name':destination.name,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()})
    receipts.append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    if telemetry:
        epoch=telemetry[0].get('time',0)
        public_frames=[{key:row[key] for key in ('x','y','scale','event') if key in row}|{'at_ms':round(row.get('time',epoch)-epoch,4)} for row in telemetry]
    else:public_frames=[]
    return {**analysis,'origin':'actual owned QWidget snapshots + renderer rAF telemetry',
        'recording_semantics':'Discrete native frames after six Qt drag gestures, each eight mouse moves at12ms; GIF timing reflects snapshot times. No continuous FPS claim.',
        'native_drag_segments':len(path)-1,'native_pointer_moves':8*(len(path)-1),'native_snapshots':len(frames),
        'recording_duration_seconds':round(times[-1]-times[0],4),'camera_frames':public_frames,'artifacts':receipts}
