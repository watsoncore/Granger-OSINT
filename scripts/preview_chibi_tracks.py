"""Production articulated timelines and animations, explicitly offline previews."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenes',nargs='+',default=['shy','annoyed','wand_play','phone_solvnox','daydream'])
    parser.add_argument('--animation',action='store_true');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.pet_life import LifePose,SCENES
    from grangerpet.articulated import render_action
    from grangerpet.guest_rig import preview_pair
    from grangerpet.scene_pose import action_pose
    app=QApplication([]);lib=SpriteLibrary();report=[]
    counts={'reading':3,'shy':3,'annoyed':3,'wand_play':4,'malfoy':2,'harry':2,'ron_chat':2}
    for name in args.scenes:
        duration=SCENES[name].duration if name in SCENES else 4.
        for variant in range(counts.get(name,1)):
            frames=[];size=195
            for i in range(12):
                q=(i+.2)/12;life=LifePose(name,'',q,q*duration,1,i,0,variant=variant)
                cameo=SCENES[name].cameo if name in SCENES else ''
                if cameo:
                    from dataclasses import replace
                    life=replace(life,cameo=cameo)
                qimage=(preview_pair(lib,life,size) if cameo else render_action(lib,life,size)).convertToFormat(qimage_format())
                im=Image.frombytes('RGBA',(qimage.width(),qimage.height()),bytes(qimage.constBits()))
                bg=Image.new('RGBA',im.size,'#17212b');bg.alpha_composite(im);frames.append(bg.convert('RGB'))
            w,h=frames[0].size;sheet=Image.new('RGB',(4*(w+16),3*(h+30)),'#17212b');draw=ImageDraw.Draw(sheet)
            for i,frame in enumerate(frames):
                x=i%4*(w+16);y=i//4*(h+30);sheet.paste(frame,(x+8,y+25));draw.text((x+4,y+4),f'{name} v{variant} {(i+.2)/12:.2f}',fill='white')
            sheet.save(args.output/f'{name}-v{variant}-timeline.png')
            if args.animation:
                frames=[]
                for i in range(math.ceil(duration*24)+1):
                    q=min(1.,i/(duration*24));life=LifePose(name,'',q,i/24,1,i,0,variant=variant)
                    if cameo:life=replace(life,cameo=cameo)
                    qi=(preview_pair(lib,life,size) if cameo else render_action(lib,life,size)).convertToFormat(qimage_format());im=Image.frombytes('RGBA',(qi.width(),qi.height()),bytes(qi.constBits()))
                    bg=Image.new('RGBA',im.size,'#17212b');bg.alpha_composite(im);frames.append(bg.convert('RGB'))
                frames[0].save(args.output/f'{name}-v{variant}.webp',save_all=True,append_images=frames[1:],duration=42,loop=0,lossless=True)
                frames[0].save(args.output/f'{name}-v{variant}.gif',save_all=True,append_images=frames[1:],duration=40,loop=0)
            report.append({'name':name,'variant':variant,'method':'Actual production renderer, deterministic offline clock; not native capture'})
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'timelines':len(report)}))


def qimage_format():
    from PySide6.QtGui import QImage
    return QImage.Format.Format_RGBA8888


if __name__=='__main__':main()
