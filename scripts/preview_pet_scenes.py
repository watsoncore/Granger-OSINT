"""Render GIF previews from production QPainter poses; not a screen recording."""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenes',nargs='+',default=['reading','phone_solvnox','malfoy'])
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import QRect,Qt
    from PySide6.QtGui import QColor,QImage,QPainter
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.pet_actions import action_frame
    from grangerpet.pet_life import PetLifeController,SCENES
    from grangerpet.scene_art import cameo_frame
    app=QApplication([]);library=SpriteLibrary();report={}
    for name in args.scenes:
        if name not in SCENES:raise ValueError('Unknown scene')
        clock=[0.];life=PetLifeController(clock=lambda:clock[0]);life.start_action(name)
        frames=[];times=[]
        for index in range(math.ceil(life.duration*12)):
            clock[0]=index/12;pose=life.pose();start=time.perf_counter()
            main=action_frame(library,pose)
            guest=cameo_frame(library,pose) if pose.cameo else None
            times.append((time.perf_counter()-start)*1000)
            image=QImage(400,220,QImage.Format.Format_RGBA8888);image.fill(QColor('#17212b'))
            p=QPainter(image);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(QRect(210 if guest else 120,20,180,180),main)
            if guest:
                p.setOpacity(pose.strength)
                p.drawImage(QRect(round(15-(1-pose.strength)*12),20,180,180),guest.flipped(Qt.Orientation.Horizontal))
            p.end();frames.append(Image.frombytes('RGBA',(400,220),bytes(image.constBits())).convert('RGB'))
        frames[0].save(args.output/f'{name}.gif',save_all=True,append_images=frames[1:],duration=83,loop=0,optimize=False)
        report[name]={'frames':len(frames),'duration_seconds':life.duration,'raster_ms_median':statistics.median(times),
            'raster_ms_p95':sorted(times)[round((len(times)-1)*.95)],'method':'production action_frame/cameo_frame; preview composition, not a native screen recording'}
    (args.output/'render-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
