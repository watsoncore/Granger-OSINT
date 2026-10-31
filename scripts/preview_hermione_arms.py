"""Real renderer diagnostics: five painted arm masters, without any props."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
from grangerpet.animation import SpriteLibrary
from grangerpet.articulated import HermioneRig,render_actor
from grangerpet.painted_arms import PaintedArms
from grangerpet.scene_pose import ActorPose
from grangerpet.hermione_pose_bank import arm_pose_bank


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication([])
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/segoeui.ttf'))
    library=SpriteLibrary();art=library.scenes;painted=PaintedArms(args.assets)
    old=HermioneRig(art.layers['base'],art.hair_repair,art.hair_fringe)
    new=HermioneRig(art.layers['base'],art.hair_repair,art.hair_fringe,painted)
    bank=arm_pose_bank(painted)
    cell=260;sheet=QImage(cell*5,290*len(bank),QImage.Format.Format_RGB32);sheet.fill(QColor('#f4f2ed'))
    painter=QPainter(sheet);font=QFont('Segoe UI');font.setPixelSize(13);painter.setFont(font)
    poses=[]
    for row,(name,a) in enumerate(bank.items()):
        poses.append({'name':name,'props':False,'face_source':'unchanged approved master'})
        for column,(label,rig,size) in enumerate((('Previous arms / same pose',old,256),('Painted arms',new,256),('Painted 195px',new,195),('Painted 160px',new,160),('Painted 100px',new,100))):
            art.hermione_rig=rig;frame=render_actor(library,deepcopy(a),size)
            frame.save(str(args.output/f'{name}-{column}.png'))
            x=column*cell;y=row*290
            painter.setPen(QColor('#3f3b32'));painter.drawText(x+8,y+18,name+' / '+label)
            painter.drawImage(QPointF(x+(cell-size)/2,y+28),frame)
        art.hermione_rig=new;render_actor(library,deepcopy(a),512).save(str(args.output/(name+'-512.png')))
    painter.end();sheet.save(str(args.output/'arms-without-props.png'))
    (args.output/'report.json').write_text(json.dumps({'method':'Actual HermioneRig/render_actor; no props; new character face never consumed; old/new on identical pose',
        'poses':poses,'scales':[100,195,256],'artistic_acceptance':'pending visual review'},indent=2),encoding='utf-8')
    print(json.dumps({'poses':len(poses),'props':False,'sheet':str(args.output/'arms-without-props.png')}))


if __name__=='__main__':main()
