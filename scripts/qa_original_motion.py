"""Pose/prop diagnostic from the production renderer; not a native EXE capture."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
from PySide6.QtWidgets import QApplication
from grangerpet.animation import SpriteLibrary
from grangerpet.articulated import render_actor
from grangerpet.scene_pose import action_pose
from grangerpet.pet_life import SCENES


def pil(q):
    q=q.convertToFormat(q.Format.Format_RGBA8888)
    return Image.frombytes('RGBA',(q.width(),q.height()),bytes(q.constBits()))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True);app=QApplication([]);lib=SpriteLibrary()
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',12)
    names=[('reading',3),('phone_solvnox',1),('shy',3),('annoyed',3),('wand_play',4),('thinking',1),('daydream',1)]
    fractions=(0,.025,.06,.1,.18,.27,.36,.44,.50,.55,.63,.71,.82,.9,.96,1.)
    overview=Image.new('RGB',(720,16*225),'#f4f2ed');row=0;reports=[]
    for name,count in names:
        duration=SCENES[name].duration if name in SCENES else 6
        for variant in range(count):
            sheet=Image.new('RGB',(4*220,4*245),'#f4f2ed');draw=ImageDraw.Draw(sheet)
            bare_sheet=Image.new('RGB',sheet.size,'#f4f2ed');bd=ImageDraw.Draw(bare_sheet)
            for i,q in enumerate(fractions):
                pose=action_pose(name,q,q*duration,variant);bare=deepcopy(pose)
                bare.source_idle=False;bare.magic=bare.hearts=0
                for target,d,a,props in ((sheet,draw,pose,True),(bare_sheet,bd,bare,False)):
                    raw=pil(render_actor(lib,a,195,props=props));x=i%4*220;y=i//4*245
                    target.paste(raw,(x+12,y+30),raw);d.text((x+6,y+6),f'{name} v{variant} / {q*duration:.2f}s',font=font,fill='#3f3b32')
            sheet.save(out/f'{name}-v{variant}-poses.png');bare_sheet.save(out/f'{name}-v{variant}-no-props.png')
            pose=action_pose(name,.5,.5*duration,variant);bare=deepcopy(pose)
            bare.source_idle=False;bare.magic=bare.hearts=0
            for column,a in enumerate((bare,pose)):
                raw=pil(render_actor(lib,a,512,props=column==1)).crop((100,235,390,414))
                overview.paste(raw,(column*360+20,row*225+30),raw)
                ImageDraw.Draw(overview).text((column*360+8,row*225+5),f'{name} v{variant} / '+('no props' if column==0 else 'with props'),font=font,fill='#3f3b32')
            reports.append({'action':name,'variant':variant,'keyframes':len(fractions)});row+=1
    overview.save(out/'hands-with-and-without-props.png')
    (out/'report.json').write_text(json.dumps({'method':__doc__,'sequences':reports,'source_master_changed':False},indent=2),encoding='utf-8')
    print(json.dumps({'sequences':len(reports),'pose_renders':sum(r['keyframes']*2 for r in reports)}))


if __name__=='__main__':main()
