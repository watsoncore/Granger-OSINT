"""Alpha/background/scale inspection plates from actual articulated renderers."""
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.articulated import render_actor,render_action
    from grangerpet.scene_pose import action_pose
    from grangerpet.pet_life import LifePose,SCENES
    from grangerpet.physics import DragPose
    app=QApplication([])
    from PySide6.QtGui import QFontDatabase
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/segoeui.ttf'))
    lib=SpriteLibrary()
    def life(name,q=.5):return LifePose(name,'',q,q*SCENES[name].duration,1,0,0,cameo=SCENES[name].cameo)
    images=[('Hermione',pil(render_actor(lib,action_pose('idle',.4,1),195)))]
    images.extend([('Reading / turn',pil(render_action(lib,life('reading',.515),195))),
        ('Shy / cheek',pil(render_actor(lib,action_pose('shy',.45,2,1),195))),
        ('Wand',pil(render_actor(lib,action_pose('wand_play',.49,3,1),195))),
        ('Phone',pil(render_action(lib,life('phone_solvnox',.4),195))),
        ('Folded',pil(render_actor(lib,action_pose('annoyed',.5,2,0),195))),
        ('Thinking',pil(render_actor(lib,action_pose('thinking',.5,2),195))),
        ('Hip',pil(render_actor(lib,action_pose('annoyed',.5,2,2),195)))])
    backgrounds={'black':'#000000','white':'#ffffff','gray':'#808080','light':'#f4f2ed','dark':'#17212b'}
    metadata=[]
    for name,color in backgrounds.items():
        sheet=Image.new('RGB',(4*220,2*230),color or '#17212b');draw=ImageDraw.Draw(sheet)
        for i,(label,im) in enumerate(images):
            x=i%4*220;y=i//4*230
            sheet.paste(im,(x+12,y+29),im);draw.text((x+8,y+8),label,fill='#666666' if name=='white' else '#d4bda1')
        sheet.save(args.output/f'alpha-{name}.png')
    for size in (100,160,195,256):
        images2=[]
        for dpr in (1.,1.25,1.5,2.):
            im=pil(render_action(lib,life('reading',.515),size,dpr));im.save(args.output/f'reading-{size}-dpr{dpr}.png')
            images2.append((dpr,im));metadata.append({'logical_size':size,'dpr':dpr,'physical_size':im.size,'alpha_bbox':im.getbbox()})
        width=sum(im.width+16 for _,im in images2);height=max(im.height for _,im in images2)+40
        sheet=Image.new('RGB',(width,height),'#17212b');draw=ImageDraw.Draw(sheet);x=0
        for dpr,im in images2:
            sheet.paste(im,(x+8,30),im);draw.text((x+4,5),f'{size}px DPR{dpr}',fill='white');x+=im.width+16
        sheet.save(args.output/f'scale-{size}.png')
    im=pil(render_actor(lib,action_pose('idle',.4,1),512));im.save(args.output/'rest-512.png')
    for name,pose in (('up',DragPose(tuck=1,angle=-7,embarrassed=.6,held=True)),('down',DragPose(squash=1,upset=1,held=True))):
        im=pil(render_actor(lib,action_pose('idle',.3,1,physics=pose),512));im.save(args.output/f'drag-{name}-512.png')
    (args.output/'report.json').write_text(json.dumps({'method':'Actual renderer alpha plates; DPR is explicit offscreen render, not monitor switching',
        'photographic_background':None,'scope':'Hermione only',
        'scales':metadata},indent=2),encoding='utf-8');print(json.dumps({'backgrounds':len(backgrounds),'scale_renders':len(metadata)}))


if __name__=='__main__':main()
