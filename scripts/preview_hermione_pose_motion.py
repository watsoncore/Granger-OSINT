"""Prop-free pose sweep through the real renderer (offline, explicitly not EXE)."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from grangerpet.animation import SpriteLibrary
from grangerpet.articulated import HermioneRig,render_actor
from grangerpet.painted_arms import PaintedArms
from grangerpet.hermione_pose_bank import arm_pose_bank,pose_transition
from grangerpet.key_poses import interpolate
from grangerpet.scene_pose import smooth


def pil(image):
    q=image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes('RGBA',(q.width(),q.height()),bytes(q.constBits()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);app=QApplication([]);lib=SpriteLibrary();art=lib.scenes
    painted=PaintedArms(ROOT/'grangerpet/assets/hermione-poses-v3');bank=arm_pose_bank(painted)
    art.hermione_rig=HermioneRig(art.layers['base'],art.hair_repair,art.hair_fringe,painted)
    font=ImageFont.truetype(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/segoeui.ttf'),12)
    frames=[];rows=[];sheet=Image.new('RGB',(6*210,len(bank)*240),'#f4f2ed')
    for row,(name,target) in enumerate(bank.items()):
        for index in range(72):
            if index<24:a=pose_transition(bank['relaxed'],target,index/23,painted)
            elif index<48:a=deepcopy(target)
            else:a=pose_transition(bank['relaxed'],target,1-(index-48)/23,painted)
            raw=render_actor(lib,a,195);im=Image.new('RGB',(210,225),'#f4f2ed');im.paste(pil(raw),(7,25),pil(raw))
            ImageDraw.Draw(im).text((8,5),name+' / no props',font=font,fill='#3f3b32')
            frames.append(im);rows.append({'pose':name,'pose_frame':index})
            if index in (5,11,17,23,53,65):
                column=(5,11,17,23,53,65).index(index);sheet.paste(im,(column*210,row*240))
                raw.save(str(args.output/f'{name}-{index:02}.png'))
    durations=[round((i+1)*1000/24)-round(i*1000/24) for i in range(len(frames))]
    frames[0].save(args.output/'no-props-sweep.webp',save_all=True,append_images=frames[1:],duration=durations,quality=90,method=4,loop=0)
    sheet.save(args.output/'transition-review.png')
    (args.output/'report.json').write_text(json.dumps({'method':'Offline actual production QPainter renderer and joint interpolation; NOT a native EXE recording',
        'props':False,'size':195,'fps':24,'duration_ms':sum(durations),'frames':rows,'artistic_acceptance':'pending visual review'},indent=2),encoding='utf-8')
    print(json.dumps({'poses':len(bank),'frames':len(frames),'duration_ms':sum(durations)}))


if __name__=='__main__':main()
