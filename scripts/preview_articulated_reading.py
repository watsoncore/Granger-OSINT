"""Render real reading tracks at native logical sizes; no storyboard drawings."""
import argparse
import json
import os
from pathlib import Path
import sys
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def pil(q):
    q=q.convertToFormat(q.Format.Format_RGBA8888)
    return Image.frombytes('RGBA',(q.width(),q.height()),bytes(q.constBits()))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.pet_life import LifePose
    from grangerpet.articulated import render_reading
    from grangerpet.scene_pose import reading_pose
    app=QApplication([]);lib=SpriteLibrary();metadata=[]
    moments=(.04,.12,.20,.29,.39,.475,.515,.565,.63,.81,.86,.94)
    for variant in range(3):
        for size in (100,195,512):
            sheet=Image.new('RGB',(4*(size+16),3*(size+42)),'#17212b');draw=ImageDraw.Draw(sheet)
            for index,q in enumerate(moments):
                life=LifePose('reading','',q,q*18,1,int(q*18*24),0,variant=variant)
                im=pil(render_reading(lib,life,size));x=(index%4)*(size+16);y=(index//4)*(size+42)
                sheet.paste(im,(x+8,y+28),im);phase=reading_pose(q,q*18,variant).phase
                draw.text((x+5,y+6),f'{q:.3f} {phase}',fill='white')
                if size==512:im.save(args.output/f'reading-v{variant}-{index:02}.png')
            sheet.save(args.output/f'reading-v{variant}-{size}-timeline.png')
        frames=[]
        for i in range(18*24+1):
            q=i/(18*24);life=LifePose('reading','',q,i/24,1,i,0,variant=variant)
            im=pil(render_reading(lib,life,195));bg=Image.new('RGBA',im.size,'#17212b');bg.alpha_composite(im);frames.append(bg.convert('RGB'))
        frames[0].save(args.output/f'reading-v{variant}.webp',save_all=True,append_images=frames[1:],duration=42,loop=0,lossless=True)
        frames[0].save(args.output/f'reading-v{variant}.gif',save_all=True,append_images=frames[1:],duration=40,loop=0)
        metadata.append({'variant':variant,'frames':len(frames),'logical_size':195,'fps':24,'duration':18,
            'method':'Production articulated renderer, offline deterministic clock; not a native window capture'})
    (args.output/'report.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps({'variants':3,'output':str(args.output)}))


if __name__=='__main__':main()
