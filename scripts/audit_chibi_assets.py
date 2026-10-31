"""Inspect existing production art without replacing any source asset."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary,STATES
    app=QApplication([]);lib=SpriteLibrary();report={}
    sheet=Image.new('RGB',(4*215,len(STATES)*225),'#17212b');draw=ImageDraw.Draw(sheet)
    for row,name in enumerate(STATES):
        frames=lib.frames[name];items=[]
        for col,index in enumerate((0,len(frames)//3,len(frames)*2//3,len(frames)-1)):
            im=frames[index].convertToFormat(frames[index].Format.Format_RGBA8888)
            p=Image.frombytes('RGBA',(im.width(),im.height()),bytes(im.constBits())).resize((195,195),Image.Resampling.LANCZOS)
            sheet.paste(p,(col*215,row*225+25),p);draw.text((col*215+5,row*225+5),f'{name} {index}',fill='white')
            items.append({'frame':index,'alpha_bbox':p.getbbox()})
        report[name]={'frames':len(frames),'samples':items}
    sheet.save(args.output/'old-atlas-contact.png')
    comparison=Image.new('RGB',(4*230,250),'#17212b');d=ImageDraw.Draw(comparison)
    for col,name in enumerate(('hermione','draco','harry','ron')):
        path=ROOT/'grangerpet/assets'/('character.png' if name=='hermione' else f'scenes/{name}.png')
        im=Image.open(path).convert('RGBA');small=im.resize((195,195),Image.Resampling.LANCZOS)
        comparison.paste(small,(col*230+15,35),small);d.text((col*230+15,10),name,fill='white')
        report[name+'_master']={'size':im.size,'alpha_bbox':im.getbbox(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    comparison.save(args.output/'old-four-character-comparison.png')
    (args.output/'asset-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    native=ROOT/'output/chibi-reconstruction/released-reading'
    frames=[]
    for path in sorted(native.glob('reading-*-pet.png')):
        im=Image.open(path).convert('RGBA');bg=Image.new('RGBA',im.size,'#17212b');bg.alpha_composite(im);frames.append(bg.convert('RGB'))
    if frames:
        frames[0].save(native/'released-reading.gif',save_all=True,append_images=frames[1:],duration=500,loop=0)
        (native/'assembly.json').write_text(json.dumps({'captures':len(frames),'source':'Actual released EXE snapshots','old_driver_error':'GIF packing mistakenly called PIL Image.size tuple; raw snapshots retained and assembled without restarting or changing the original report'}),encoding='utf-8')
    print(json.dumps({'states':len(STATES),'baseline_snapshots':len(frames)}))


if __name__=='__main__':main()
