"""Every native cel and fixed-region facial crop; no reconstructed eye artwork."""
import argparse
import json
import math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',10);rows=[]
    parent=json.loads((args.source/'report.json').read_text(encoding='utf-8'))
    for folder in sorted(args.source.iterdir()):
        if not (folder/'capture.json').is_file():continue
        data=json.loads((folder/'capture.json').read_text(encoding='utf-8'))
        if data['mode']!='widget':continue
        files=sorted(folder.glob('*.png'));out=args.output/folder.name;out.mkdir(exist_ok=True)
        assembly=json.loads((args.source/(folder.name+'-assembly.json')).read_text(encoding='utf-8'))
        faces=Image.new('RGB',(16*122,math.ceil(len(files)/16)*104),'#f4f2ed')
        full=Image.new('RGB',(16*124,math.ceil(len(files)/16)*144),'#f4f2ed')
        fd=ImageDraw.Draw(faces);ad=ImageDraw.Draw(full)
        for i,file in enumerate(files):
            with Image.open(file) as im:
                im=im.convert('RGBA');scale=(data['frames'][i]['bounds'][2]-24)*data['frames'][i]['dpr']/512
                padding=12*data['frames'][i]['dpr']
                # Solo widget has a 12 logical px border. Crop generously enough
                # to keep deliberate head lean/drop and both eyebrows visible.
                box=tuple(round(padding+v*scale) for v in (115,126,320,270))
                face=im.crop(box);face.save(out/f'{i:04}.png')
                x=i%16*122;y=i//16*104
                faces.paste(face,(x+4,y+18),face)
                fd.text((x+3,y+3),f'{i:04} {data["frames"][i]["at"]:.2f}s',font=font,fill='#3f3b32')
                frame=im.crop(assembly['physical_crop']);frame.thumbnail((120,120),Image.Resampling.LANCZOS)
                x=i%16*124;y=i//16*144;full.paste(frame,(x+2,y+20),frame)
                ad.text((x+3,y+3),f'{i:04}',font=font,fill='#3f3b32')
        faces.save(args.output/(folder.name+'-all-faces.png'));full.save(args.output/(folder.name+'-all-frames.png'))
        rows.append({'scene':folder.name,'frames':len(files),'facial_crop':'Fixed native widget ROI; no warp or painted replacement'})
    (args.output/'report.json').write_text(json.dumps({'exe_sha256':parent.get('exe_sha256'),
        'method':'Every original native PNG inspected in overview; full-frame overview thumbnails only; unscaled fixed-region face crops retained separately. Not a new renderer.',
        'sequences':rows},indent=2),encoding='utf-8')
    print(json.dumps({'sequences':len(rows),'native_frames':sum(r['frames'] for r in rows)}))


if __name__=='__main__':main()
