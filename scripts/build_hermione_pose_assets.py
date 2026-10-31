"""Align archived pose drawings and extract reviewed masks; never edit the face."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QImage,QPainter,QPainterPath,QPainterPathStroker,QColor,QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def polygon(points):
    path=QPainterPath(QPointF(*points[0]))
    for point in points[1:]:path.lineTo(*point)
    path.closeSubpath();return path


def blank():
    result=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent);return result


def extract(source,points,subtract=()):
    mask=polygon(points)
    for cut in subtract:mask=mask.subtracted(polygon(cut))
    result=blank();p=QPainter(result);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setClipPath(mask);p.drawImage(0,0,source);p.end();return result


def sleeve_layer(source,points,hands):
    # Both hands can cross a sleeve in a painted master. Exclude the complete
    # other hand too, including its ink/antialias fringe, before rig binding.
    mask=polygon(points);stroker=QPainterPathStroker();stroker.setWidth(5.)
    for hand in hands:
        shape=polygon(hand);mask=mask.subtracted(shape.united(stroker.createStroke(shape)))
    result=blank();p=QPainter(result);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setClipPath(mask);p.drawImage(0,0,source);p.end();return result


def align(source):
    points=[(x,y) for y in range(source.height()) for x in range(source.width())
            if source.pixelColor(x,y).alpha()>16]
    if not points:raise ValueError('Empty pose source')
    left=min(x for x,y in points);top=min(y for x,y in points)
    right=max(x for x,y in points)+1;bottom=max(y for x,y in points)+1
    result=blank();p=QPainter(result);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(QRectF(70,14,372,486),source,QRectF(left,top,right-left,bottom-top));p.end()
    return result,[left,top,right,bottom]


def save_crop(image,path):
    rgba=image.convertToFormat(QImage.Format.Format_RGBA8888)
    box=Image.frombytes('RGBA',(512,512),bytes(rgba.constBits())).getbbox()
    if box is None:raise ValueError('Empty reviewed layer: '+str(path))
    x,y,right,bottom=box;image.copy(x,y,right-x,bottom-y).save(str(path))
    return [x,y,right-x,bottom-y]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'grangerpet/assets/hermione-poses-v3')
    parser.add_argument('--align-only',action='store_true');args=parser.parse_args()
    app=QApplication([]);sources=ROOT/'resources/hermione-pose-masters-v3'
    font_file=Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/consola.ttf'
    if font_file.is_file():QFontDatabase.addApplicationFont(str(font_file))
    args.output.mkdir(parents=True,exist_ok=True)
    previews=args.output if args.align_only else ROOT/'output/hermione-art-v3/aligned-final'
    previews.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((sources/'rig.json').read_text(encoding='utf-8')) if (sources/'rig.json').is_file() else {}
    provenance={}
    for file in sorted(sources.glob('*-source.png')):
        name=file.stem.removesuffix('-source');master,bbox=align(QImage(str(file)))
        master.save(str(previews/(name+'-aligned.png')))
        provenance[name]={'source':file.relative_to(ROOT).as_posix(),
            'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'source_bbox':bbox,
            'alignment':[70,14,372,486],'runtime_face_consumed':False}
        grid=QImage(master);p=QPainter(grid);p.setPen(QColor('#60a5ae'))
        font=QFont('Consolas');font.setPixelSize(9);p.setFont(font)
        for at in range(128,513,32):
            p.drawLine(at,240,at,420);p.drawText(at+2,248,str(at))
            p.drawLine(128,at,360,at);p.drawText(130,at-2,str(at))
        p.end();grid.save(str(previews/(name+'-grid.png')))
        if args.align_only:continue
        spec=metadata[name]
        for side in ('left','right'):
            arm=spec[side];hand=arm['hand_mask']
            arm['sleeve_rect']=save_crop(sleeve_layer(master,arm['mask'],[spec[s]['hand_mask'] for s in ('left','right')]),args.output/f'{name}-{side}-sleeve.png')
            arm['hand_rect']=save_crop(extract(master,hand),args.output/f'{name}-{side}-hand.png')
    if not args.align_only:
        from PySide6.QtSvg import QSvgRenderer
        # New vector drawings are build-time artwork, not a runtime dependency.
        hip=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied);hip.fill(Qt.GlobalColor.transparent)
        p=QPainter(hip);QSvgRenderer(str(sources/'hip-right.svg')).render(p);p.end()
        metadata['hip']={'order':['left','right'],'left':deepcopy(metadata['rest']['left']),
            'right':{'bones':[[281,294],[331,331],[287,358]],
                'mask':[[274,276],[304,276],[345,302],[353,337],[330,358],[306,373],[278,352]],
                'hand_mask':[[278,348],[287,347],[296,355],[299,361],[289,372],[278,370],[274,360]]}}
        for kind in ('sleeve','hand'):
            QImage(str(args.output/f'rest-left-{kind}.png')).save(str(args.output/f'hip-left-{kind}.png'))
        spec=metadata['hip']['right'];spec['sleeve_rect']=save_crop(extract(hip,spec['mask'],[spec['hand_mask']]),args.output/'hip-right-sleeve.png')
        spec['hand_rect']=save_crop(extract(hip,spec['hand_mask']),args.output/'hip-right-hand.png')
        # The approved master already has a drawn bent wand sleeve. Rebind that
        # genuine garment drawing, replacing its tiny original hand separately.
        master=QImage(str(ROOT/'grangerpet/assets/character.png'))
        metadata['wand']={'order':['right','left'],'right':deepcopy(metadata['rest']['right']),
            'left':{'bones':[[171,293],[157,335],[132,294]],
                'forearm_guide':[[128,286],[152,294],[164,320],[169,336],[153,344],[134,320]],
                'mask':[[185,278],[193,292],[178,319],[163,349],[151,354],[139,341],[132,311],[132,294],[146,284],[165,284]],
                'hand_mask':[[116,280],[134,280],[141,291],[137,303],[123,306],[115,295]]}}
        for kind in ('sleeve','hand'):
            QImage(str(args.output/f'rest-right-{kind}.png')).save(str(args.output/f'wand-right-{kind}.png'))
        spec=metadata['wand']['left']
        spec['sleeve_rect']=save_crop(sleeve_layer(master,spec['mask'],[spec['hand_mask']]),args.output/'wand-left-sleeve.png')
        spec['hand_rect']=save_crop(extract(master,spec['hand_mask']),args.output/'wand-left-hand.png')
        hands={}
        for name in ('point','wand'):
            drawing=blank();p=QPainter(drawing)
            QSvgRenderer(str(sources/(name+'-hand.svg'))).render(p,QRectF(224,214,64,80));p.end()
            hands[name]={'anchor':[256,256],'rect':save_crop(drawing,args.output/('hand-'+name+'.png')),
                'source':(sources/(name+'-hand.svg')).relative_to(ROOT).as_posix()}
        (args.output/'hands.json').write_text(json.dumps(hands,indent=2),encoding='utf-8')
        reach=blank();p=QPainter(reach);QSvgRenderer(str(sources/'reach-arms.svg')).render(p);p.end()
        metadata['reach']={'order':['left','right']}
        for side,bones in (('left',[[171,293],[148,345],[194,362]]),('right',[[281,294],[304,345],[258,362]])):
            source_spec=metadata['rest'][side];old=source_spec['bones'][2];new=bones[2]
            from PySide6.QtGui import QTransform
            angle=-70 if side=='left' else 70
            transform=QTransform();transform.translate(*new);transform.rotate(angle);transform.translate(-old[0],-old[1])
            hand=blank();p=QPainter(hand);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);p.setWorldTransform(transform)
            rect=source_spec['hand_rect'];p.drawImage(QPointF(rect[0],rect[1]),QImage(str(args.output/f'rest-{side}-hand.png')));p.end()
            points=[transform.map(QPointF(*point)) for point in source_spec['hand_mask']]
            mask=[[v.x(),v.y()] for v in points]
            cloth_box=[[130,278],[215,278],[215,384],[130,384]] if side=='left' else [[237,278],[322,278],[322,384],[237,384]]
            metadata['reach'][side]={'bones':bones,'mask':cloth_box,'hand_mask':mask,
                'sleeve_rect':save_crop(extract(reach,cloth_box),args.output/f'reach-{side}-sleeve.png'),
                'hand_rect':save_crop(hand,args.output/f'reach-{side}-hand.png')}
        (args.output/'rig.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        for name in ('hip-right','point-hand','wand-hand','reach-arms'):
            source=sources/(name+'.svg')
            provenance[name]={'source':source.relative_to(ROOT).as_posix(),
                'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'method':'Editable drawn SVG; rasterized by existing QtSvg at build time only',
                'runtime_face_consumed':False}
        source=ROOT/'grangerpet/assets/character.png'
        provenance['approved-wand-sleeve']={'source':source.relative_to(ROOT).as_posix(),
            'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'method':'Approved original bent garment; original hand separated',
            'runtime_face_consumed':False}
    (args.output/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    print(json.dumps({'pose_drawings':len(provenance),'aligned_only':args.align_only}))


if __name__=='__main__':main()
