"""Rasterize authored phone-only SVG derivatives; original character is read-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'output/derived-character/phone-solvnox-v1');args=p.parse_args()
    out=args.output.resolve();protected=ROOT/'grangerpet/assets'
    if out==protected or out==protected/'scenes' or out==protected/'original-hermione':raise SystemExit('Refusing original character directory')
    out.mkdir(parents=True,exist_ok=True);app=QApplication([]);src=ROOT/'resources/hermione-phone-v1'
    spec={'phone':{'order':['left','right'],
        'left':{'bones':[[171,293],[178,363],[253,355]],'forearm_guide':[[164,354],[180,380],[258,366],[260,335],[233,336],[192,348]]},
        'right':{'bones':[[281,294],[330,350],[310,372]],'forearm_guide':[[317,337],[343,350],[325,385],[301,389],[297,363]]}}}
    for side,name in (('left','typing-sleeve'),('right','holding-sleeve')):
        im=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied);im.fill(Qt.GlobalColor.transparent)
        painter=QPainter(im);QSvgRenderer(str(src/(name+'.svg'))).render(painter,QRectF(0,0,512,512));painter.end()
        # Tight alpha bounds, preserving the exact 512px source coordinates.
        from PIL import Image
        rgba=im.convertToFormat(QImage.Format.Format_RGBA8888)
        box=Image.frombytes('RGBA',(512,512),bytes(rgba.constBits())).getbbox();x,y,r,b=box
        im.copy(x,y,r-x,b-y).save(str(out/f'phone-{side}-sleeve.png'))
        spec['phone'][side]['sleeve_rect']=[x,y,r-x,b-y]
        spec['phone'][side]['hand_rect']=[0,0,1,1]
        blank=QImage(1,1,QImage.Format.Format_ARGB32_Premultiplied);blank.fill(Qt.GlobalColor.transparent);blank.save(str(out/f'phone-{side}-hand.png'))
    images={'phone':(64,112,[-32,-56]),'typing-hover':(96,96,[-32,-48]),'typing-press':(96,96,[-32,-48]),'holding-hand':(96,96,[-48,-48]),'rest-hand':(64,64,[-32,-32])}
    for name,(w,h,_) in images.items():
        im=QImage(w,h,QImage.Format.Format_ARGB32_Premultiplied);im.fill(Qt.GlobalColor.transparent)
        painter=QPainter(im);QSvgRenderer(str(src/(name+'.svg'))).render(painter,QRectF(0,0,w,h));painter.end();im.save(str(out/(name+'.png')))
    meta={'device_origin':[-32,-56],'screen_polygon':[[-5,-34],[7,-31],[13,29],[1,33]],
        'hands':{'phone_hover':{'file':'typing-hover.png','origin':[-32,-48],'tip':[36,-2],'front':[8,-44,42,46]},
            'phone_press':{'file':'typing-press.png','origin':[-32,-48],'tip':[36,-2],'front':[8,-44,42,46]},
            'phone_hold':{'file':'holding-hand.png','origin':[-48,-48],'anchor':[-24,-4],'front':[-17,-33,14,27]},
            'phone_rest':{'file':'rest-hand.png','origin':[-32,-32],'front':None}},
        'method':'Authored phone-only SVG artwork; original character master/head/face/hair never read or overwritten'}
    (out/'rig.json').write_text(json.dumps(spec,indent=2),encoding='utf-8');(out/'geometry.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    provenance={'source_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(src.glob('*.svg'))},
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.png'))},'identity_assets_modified':False,'method':meta['method']}
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8');print(json.dumps({'phone_only_assets':len(provenance['outputs'])}))


if __name__=='__main__':main()
