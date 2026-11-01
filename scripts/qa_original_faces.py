"""All facial cels from the production head component in head-local coordinates."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
from grangerpet.animation import SpriteLibrary
from grangerpet.original_face import OriginalFace
from grangerpet.scene_pose import ActorPose,action_pose
from grangerpet.pet_life import SCENES


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);app=QApplication([])
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/segoeui.ttf'))
    lib=SpriteLibrary();face=OriginalFace(lib.scenes.layers['base'],lib.scenes.layers['head'])
    motion=OriginalFace(lib.scenes.layers['base'],QImage(str(ROOT/'grangerpet/assets/original-motion-v1/head.png')))
    font=QFont('Segoe UI');font.setPixelSize(10);reports=[]
    names=[('idle',1),('hover',1),('reading',3),('phone_solvnox',1),('shy',3),('annoyed',3),('thinking',1),('wand_play',4)]
    for name,count in names:
        duration=18. if name=='idle' else SCENES[name].duration if name in SCENES else 6.
        for variant in range(count):
            frames=math.ceil(duration*24)+1;directory=args.output/f'{name}-v{variant}';directory.mkdir(exist_ok=True)
            sheet=QImage(16*146,math.ceil(frames/16)*115,QImage.Format.Format_RGB32);sheet.fill(QColor('#f4f2ed'))
            p=QPainter(sheet);p.setFont(font);p.setPen(QColor('#3f3b32'))
            for i in range(frames):
                t=min(duration,i/24);pose=action_pose(name,t/duration,t,variant,aim=(math.sin(t),.5) if name=='hover' else (0.,0.))
                component=face if pose.source_idle else motion
                im=component.image(pose).copy(150,154,138,95);im.save(str(directory/f'{i:04}.png'))
                x=i%16*146;y=i//16*115;p.drawText(x+3,y+12,f'{i:04} {t:.2f}s');p.drawImage(x+3,y+17,im)
            p.end();sheet.save(str(args.output/f'{name}-v{variant}-all-faces.png'))
            reports.append({'name':name,'variant':variant,'frames':frames,'seconds':duration})
    cases=[('Original',ActorPose()),('Blink',ActorPose(blink=1)),('After blink',ActorPose()),('Hover',ActorPose(gaze=(-4,0)))]
    cases.extend((n,action_pose(n,.4,2,v)) for n,v in [('reading',0),('phone_solvnox',0),('shy',1),('annoyed',0),('thinking',0),('wand_play',1)])
    sheet=QImage(1320,690,QImage.Format.Format_RGB32);sheet.fill(QColor('#f4f2ed'));p=QPainter(sheet);font.setPixelSize(16);p.setFont(font);p.setPen(QColor('#3f3b32'))
    for i,(label,pose) in enumerate(cases):
        x=i%4*330;y=i//4*230;p.drawText(x+8,y+22,label)
        component=face if i<4 or pose.source_idle else motion
        p.drawImage(QRectF(x+8,y+32,276,190),component.image(pose),QRectF(150,154,138,95))
    p.end();sheet.save(str(args.output/'face-comparison.png'))
    (args.output/'report.json').write_text(json.dumps({'method':'Actual production OriginalFace.image before the head-parent transform; every cel; not an EXE capture or new character art',
        'source_commit':'1b75ee99ef5329880048287f962e7b00684346b2','sequences':reports},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'sequences':len(reports),'facial_cels':sum(r['frames'] for r in reports)}))


if __name__=='__main__':main()
