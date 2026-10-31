"""Assemble untouched native frames with one fixed alpha crop for the full clip."""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageDraw


def assemble(directory):
    data=json.loads((directory/'capture.json').read_text(encoding='utf-8'));files=sorted(directory.glob('*.png'))
    if not files:raise ValueError('No native frames')
    boxes=[]
    for file in files:
        with Image.open(file) as im:
            box=im.convert('RGBA').getbbox()
            if box:boxes.append(box)
    with Image.open(files[0]) as first:width,height=first.size
    crop=(max(0,min(b[0] for b in boxes)-12),max(0,min(b[1] for b in boxes)-12),
        min(width,max(b[2] for b in boxes)+12),min(height,max(b[3] for b in boxes)+12))
    frames=[]
    for file in files:
        with Image.open(file) as raw:im=raw.convert('RGBA').crop(crop)
        bg=Image.new('RGBA',im.size,'#17212b');bg.alpha_composite(im);frames.append(bg.convert('RGB'))
    times=[r['at'] for r in data['frames']];durations=[max(1,round((b-a)*1000)) for a,b in zip(times,times[1:])]+[42]
    out=directory.parent;name=directory.name
    frames[0].save(out/f'{name}.webp',save_all=True,append_images=frames[1:],duration=durations,lossless=True,loop=0)
    frames[0].save(out/f'{name}.gif',save_all=True,append_images=frames[1:],duration=durations,loop=0)
    indices=[round((len(frames)-1)*q) for q in (.04,.12,.20,.29,.39,.475,.515,.565,.63,.81,.86,.94)]
    w,h=frames[0].size;sheet=Image.new('RGB',((w+10)*4,(h+30)*3),'#17212b');draw=ImageDraw.Draw(sheet)
    for i,index in enumerate(indices):
        x=i%4*(w+10);y=i//4*(h+30);sheet.paste(frames[index],(x,y+25))
        draw.text((x,y+4),f'{times[index]:.2f}s',fill='white')
    sheet.save(out/f'{name}-timeline.png')
    assembly={'method':'Fixed union-of-alpha crop across all native frames; original PNGs retained; no resizing or invented frames',
        'physical_crop':crop,'frames':len(frames),'source':str(directory/'capture.json')}
    (out/f'{name}-assembly.json').write_text(json.dumps(assembly,indent=2),encoding='utf-8')
    return assembly


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);args=p.parse_args();print(json.dumps(assemble(args.directory)))
