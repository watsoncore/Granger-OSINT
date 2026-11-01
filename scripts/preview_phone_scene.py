"""Phone-only production-renderer movie and contact sheets; not a native capture."""
import argparse
from copy import deepcopy
import json
import math
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
from grangerpet.phone_scene import contact_model


def pil(q):
    q=q.convertToFormat(q.Format.Format_RGBA8888)
    return Image.frombytes('RGBA',(q.width(),q.height()),bytes(q.constBits()))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sizes',nargs='+',type=int,default=[195]);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);lib=SpriteLibrary();font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',12);reports=[]
    duration=13.;count=math.ceil(duration*24)+1;fractions=(0,.1,.18,.25,.35,.40,.44,.49,.535,.58,.64,.69,.754,.80,.85,.90,.96,1)
    for size in args.sizes:
        directory=args.output/f'frames-{size}';directory.mkdir(exist_ok=True);frames=[]
        for i in range(count):
            t=min(duration,i/24);a=action_pose('phone_solvnox',t/duration,t)
            im=pil(render_actor(lib,a,size));im.save(directory/f'{i:04}.png')
            matte=Image.new('RGB',im.size,'#f4f2ed');matte.paste(im,(0,0),im);frames.append(matte)
        delays=[round((i+1)*1000/24)-round(i*1000/24) for i in range(count)]
        frames[0].save(args.output/f'phone-{size}.webp',save_all=True,append_images=frames[1:],duration=delays,lossless=True,loop=0)
        sheet=Image.new('RGB',(6*(size+10),3*(size+34)),'#f4f2ed');d=ImageDraw.Draw(sheet)
        for index,q in enumerate(fractions):
            i=round(q*(count-1));x=index%6*(size+10);y=index//6*(size+34)
            sheet.paste(frames[i],(x,y+28));a=action_pose('phone_solvnox',q,q*duration)
            d.text((x+3,y+4),f'{q*duration:.2f}s {a.phase}',font=font,fill='#3f3b32')
        sheet.save(args.output/f'storyboard-{size}.png');reports.append({'size':size,'frames':count,'seconds':duration})
    # Actual hand/phone crops at source resolution, plus the same exact poses
    # with only the prop hidden. No replacement hand modes for that diagnostic.
    sheet=Image.new('RGB',(3*330,4*240),'#f4f2ed');d=ImageDraw.Draw(sheet)
    for row,q in enumerate((.35,.43,.56,.754)):
        a=action_pose('phone_solvnox',q,q*duration)
        for col,props in enumerate((True,False)):
            im=pil(render_actor(lib,deepcopy(a),512,props=props)).crop((130,270,350,420))
            sheet.paste(im,(col*330+20,row*240+34),im)
            d.text((col*330+8,row*240+8),f'{a.phase} '+('with prop' if props else 'same hands /no prop'),font=font,fill='#3f3b32')
        if a.phone_style:
            c=contact_model(a);d.text((2*330+8,row*240+8),f'press {c.press:.2f}',font=font,fill='#3f3b32')
    sheet.save(args.output/'hands-contact-review.png')
    (args.output/'report.json').write_text(json.dumps({'method':__doc__,'sequences':reports},indent=2),encoding='utf-8');print(json.dumps(reports))


if __name__=='__main__':main()
