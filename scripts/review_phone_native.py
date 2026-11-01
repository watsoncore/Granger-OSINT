"""Inspect original native phone PNGs: real screen contact, hover, faces and stages."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
from PySide6.QtCore import QPointF
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QApplication
from grangerpet.animation import SpriteLibrary
from grangerpet.scene_pose import action_pose
from grangerpet.phone_scene import TAPS,contact_model
from grangerpet.articulated import HermioneRig,plant_feet


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);app=QApplication([]);lib=SpriteLibrary();rig=HermioneRig(lib.scenes.layers['base'])
    parent=json.loads((args.source/'report.json').read_text(encoding='utf-8'));folder=args.source/'phone_solvnox-v0'
    data=json.loads((folder/'capture.json').read_text(encoding='utf-8'));rows=data['frames'];font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',12)
    def location(row):
        a=action_pose('phone_solvnox',row['progress'],row['progress']*13);plant_feet(a,rig.soles)
        c=contact_model(a);root=QTransform();root.translate(*a.shift);root.translate(*a.pivot);root.rotate(a.lean);root.translate(-a.pivot[0],-a.pivot[1])
        logical=row['bounds'][2]-24;dpr=row['dpr'];physical=round(logical*dpr);scale=physical/512
        origin=((row['bounds'][2]*dpr-physical)/2,row['bounds'][3]*dpr-12*dpr-physical)
        point=root.map(QPointF(*c.tap_target));target=(origin[0]+point.x()*scale,origin[1]+point.y()*scale)
        return a,c,target,origin,scale
    def skin_count(im,target):
        x,y=map(round,target);count=0
        for yy in range(y-2,y+3):
            for xx in range(x-2,x+3):
                r,g,b,alpha=im.getpixel((xx,yy))
                count+=alpha>180 and r>180 and g>140 and b>100 and r>g+8 and g>b+8
        return count
    contacts=[];sheet=Image.new('RGB',(4*280,3*230),'#f4f2ed');draw=ImageDraw.Draw(sheet)
    for event,(center,_,_) in enumerate(TAPS):
        whole=.1+.8*center;candidates=[]
        for index,row in enumerate(rows):
            if row['action']!='phone_solvnox' or abs(row['progress']-whole)>.013:continue
            a,c,target,origin,scale=location(row)
            if c.press<.9:continue
            with Image.open(folder/f'{index:04}.png') as raw:
                im=raw.convert('RGBA');pixels=skin_count(im,target)
            candidates.append((pixels,-abs(row['progress']-whole),index,target,origin,scale,a.phase))
        if not candidates:raise AssertionError('No native contact sample: '+str(event))
        pixels,_,index,target,origin,scale,phase=max(candidates)
        raw=Image.open(folder/f'{index:04}.png').convert('RGBA');raw.save(args.output/f'contact-{event+1:02}-{phase}-native.png')
        # Unmodified native pixels: enlarge only this review crop using nearest
        # neighbour. Original full PNG is retained next to it, with actual index.
        box=tuple(round(v) for v in (origin[0]+145*scale,origin[1]+280*scale,origin[0]+340*scale,origin[1]+410*scale))
        crop=raw.crop(box);crop.save(args.output/f'contact-{event+1:02}-{phase}-crop.png')
        zoom=crop.resize((crop.width*2,crop.height*2),Image.Resampling.NEAREST)
        x=event%4*280;y=event//4*230;sheet.paste(zoom,(x+8,y+35),zoom)
        draw.text((x+7,y+7),f'{event+1:02} {phase} / frame {index}',font=font,fill='#3f3b32')
        contacts.append({'event':event+1,'phase':phase,'native_frame':index,'at':rows[index]['at'],
            'skin_pixels_near_projected_glass_target':pixels,'native_target_px':target,'passed':pixels>0})
    sheet.save(args.output/'all-native-contacts.png')
    hover_index=min((i for i,row in enumerate(rows) if row['action']=='phone_solvnox'),key=lambda i:abs(rows[i]['progress']-(.1+.8*.298)))
    a,c,target,origin,scale=location(rows[hover_index]);hover=Image.open(folder/f'{hover_index:04}.png').convert('RGBA')
    hover_pixels=skin_count(hover,target);hover.save(args.output/'hover-native.png')
    faces=Image.new('RGB',(3*300,250),'#f4f2ed');fd=ImageDraw.Draw(faces)
    for col,(label,q) in enumerate((('begin',0.),('typing',.5),('end',1.))):
        index=min(range(len(rows)),key=lambda i:abs(rows[i]['at']-q*13))
        raw=Image.open(folder/f'{index:04}.png').convert('RGBA');row=rows[index];logical=row['bounds'][2]-24;scale=round(logical*row['dpr'])/512;pad=12*row['dpr']
        box=tuple(round(pad+v*scale) for v in (115,126,320,280));im=raw.crop(box);im.save(args.output/f'face-{label}-native.png')
        zoom=im.resize((im.width*2,im.height*2),Image.Resampling.NEAREST);faces.paste(zoom,(col*300+10,35),zoom);fd.text((col*300+8,8),label+f' /frame {index}',font=font,fill='#3f3b32')
    faces.save(args.output/'native-face-begin-middle-end.png')
    # Phase storyboard sampled from the real movie, never a re-render.
    times=(0.,1.3,2.7,3.5,4.4,4.65,5.25,6.4,6.9,7.35,8.0,8.55,9.25,9.80,10.3,10.8,11.4,13.1)
    storyboard=Image.new('RGB',(6*250,3*290),'#f4f2ed');sd=ImageDraw.Draw(storyboard)
    for k,t in enumerate(times):
        i=min(range(len(rows)),key=lambda j:abs(rows[j]['at']-t));raw=Image.open(folder/f'{i:04}.png').convert('RGBA');raw.thumbnail((240,250),Image.Resampling.LANCZOS)
        x=k%6*250;y=k//6*290;storyboard.paste(raw,(x+5,y+30),raw);sd.text((x+5,y+7),f'{rows[i]["at"]:.2f}s /frame {i}',font=font,fill='#3f3b32')
    storyboard.save(args.output/'native-storyboard.png')
    report={'exe_sha256':parent['exe_sha256'],'method':'Original native PNGs only. Source geometry locates glass; actual warm skin pixels at the contact are counted. Phase labels use capture clock; nearest raw frames selected, not reconstructed.',
        'contacts':contacts,'hover':{'native_frame':hover_index,'skin_pixels_at_glass_target':hover_pixels},
        'passed':all(c['passed'] for c in contacts) and hover_pixels==0,
        'limitations':'Pixel neighbourhood is a raster sanity check, not an artistic score. Full native movie must also be reviewed without labels.'}
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'native_contacts':sum(c['passed'] for c in contacts),'expected':len(TAPS),'hover_skin_pixels':hover_pixels}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
