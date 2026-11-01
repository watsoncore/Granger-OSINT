"""Extend the approved QPainter rig; normalize cameo masters without replacing Hermione."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor,QImage,QPainter,QPainterPath,QPen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from create_wand_animations import Rig


def normalize(source,target):
    image=Image.open(source).convert('RGBA')
    alpha=image.getchannel('A').point(lambda a:a if a>8 else 0)
    image.putalpha(alpha);image=image.crop(alpha.getbbox())
    image.thumbnail((470,484),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(512,512));canvas.alpha_composite(image,((512-image.width)//2,500-image.height))
    canvas.save(target)


def harry_from_ron(source,target):
    # The common body/contours are retained. Hair and iris palettes are edited
    # only within documented head/eye masks; glasses/scar are native rig paths.
    image=Image.open(source).convert('RGBA');pixels=image.load()
    for y in range(16,260):
        for x in range(110,405):
            r,g,b,a=pixels[x,y]
            if not a:continue
            hair_region=y<165 or x<164 and y<190 or x>300 and y<242
            if hair_region and r>g*1.18 and b<g*.84 and r>70:
                light=(r+g+b)/3
                value=round(24+light*.21)
                pixels[x,y]=(max(0,value-4),value,min(255,value+5),a)
    for left,top,right,bottom in ((165,163,213,209),(240,171,293,218)):
        for y in range(top,bottom):
            for x in range(left,right):
                r,g,b,a=pixels[x,y]
                if r>g*1.25 and g>b*1.15 and r>30:
                    pixels[x,y]=(round(g*.70),min(180,round(g*1.25)),round(g*.75),a)
    image.save(target)
    base=QImage(str(target));p=QPainter(base);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor('#382a20'),2.3));p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(188,185),31,31);p.drawEllipse(QPointF(267,194),32,32)
    bridge=QPainterPath(QPointF(219,187));bridge.quadTo(227,181,235,192);p.drawPath(bridge)
    p.drawLine(QPointF(156,180),QPointF(144,174));p.drawLine(QPointF(299,194),QPointF(318,189))
    p.setPen(QPen(QColor('#9c5c4d'),2.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    scar=QPainterPath(QPointF(230,128));scar.lineTo(224,141);scar.lineTo(233,141);scar.lineTo(225,153);p.drawPath(scar)
    p.end();base.save(str(target))


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'output/derived-character/scenes')
    args=parser.parse_args(argv);out=args.output.resolve()
    if out==(ROOT/'grangerpet/assets/scenes').resolve():
        raise SystemExit('Refusing to overwrite original scene layers; use a separate derived output directory')
    out.mkdir(parents=True,exist_ok=True)
    rig=Rig(QImage(str(ROOT/'resources/wand-reference/base-512.png')))
    for name in ('base','head','body','wand_arm','free_arm','left_leg','right_leg'):
        getattr(rig,name).save(str(out/f'hermione-{name}.png'))
    for name in ('draco','ron'):normalize(ROOT/f'resources/cameo-masters/{name}-source.png',out/f'{name}.png')
    harry_from_ron(out/'ron.png',out/'harry.png')
    metadata={'version':1,'canvas':512,'hermione_master_unchanged':True,
        'prompts':'resources/cameo-masters/PROMPTS.md',
        'generator':'scripts/build_pet_scene_assets.py','runtime':'existing Qt QPainter layered raster pipeline',
        'cameos':{'draco':{'method':'built-in ImageGen; Hermione style reference'},
            'ron':{'method':'built-in ImageGen; Hermione style reference'},
            'harry':{'method':'deterministic Ron-derived palette and QPainter glasses/scar; same body contours',
                'reason':'Two built-in ImageGen output moderation failures; no CLI fallback or external API used'}},
        'boy_geometry':{'eyes':[[.318,.317,.104,.104],[.463,.333,.115,.110]],'mouth':[.417,.446]},
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.png'))}}
    (out/'provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'assets':len(metadata['files']),'hermione_original_replaced':False}))


if __name__=='__main__':main()
