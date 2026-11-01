"""Separate original raster limbs/hair for motion; never overwrite source art."""
import hashlib
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QImage,QPainter,QPainterPath,QPainterPathStroker
from PySide6.QtWidgets import QApplication
from scripts.build_hermione_pose_assets import extract,save_crop,sleeve_layer


def polygon(points):
    p=QPainterPath(QPointF(*points[0]))
    for point in points[1:]:p.lineTo(*point)
    p.closeSubpath();return p


def main():
    app=QApplication([])
    source=ROOT/'grangerpet/assets/character.png';base=QImage(str(source))
    out=ROOT/'grangerpet/assets/original-motion-v1';out.mkdir(parents=True,exist_ok=True)
    # Outer edges lie outside the actual raster silhouette. The only interior
    # boundary follows the original collar and bottom hair curls.
    outline=[(55,0),(460,0),(460,320),(350,320),(335,312),(327,304),
        (314,303),(300,303),(292,305),(282,310),(276,306),(274,297),
        (277,286),(268,292),(263,299),(259,302),(251,300),(257,291),
        (263,284),(269,276),(272,264),(275,251),(282,246),(278,232),
        (261,239),(239,248),(213,252),(192,247),(171,240),(154,227),
        (147,248),(137,279),(119,296),(90,310),(60,310),(60,220),
        (79,223),(85,218),(92,214),(99,207),(91,201),(78,190),(75,181),(85,177),(55,177)]
    head=extract(base,outline)
    # Reuse the historical Rig's existing local repair, without its protruding
    # wand-shaped alpha. No new face/hair drawing is introduced here.
    repaired=QImage(str(ROOT/'grangerpet/assets/scenes/hermione-head.png'))
    mask=polygon(outline).intersected(polygon([(55,210),(154,210),(154,311),(55,311)]))
    p=QPainter(head);p.setClipPath(mask);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    p.drawImage(0,0,repaired);p.end()
    # Literal immutable face/bangs, including their alpha boundary. Copy bytes,
    # rather than another SourceOver/premultiplication pass through the paint API.
    head=head.convertToFormat(QImage.Format.Format_RGBA8888)
    original=repaired.convertToFormat(QImage.Format.Format_RGBA8888)
    target=head.bits();raw=bytes(original.constBits())
    for x,y,w,h in ((150,154,138,95),(145,60,150,100)):
        for row in range(y,y+h):
            start=row*head.bytesPerLine()+x*4;target[start:start+w*4]=raw[start:start+w*4]
    head.save(str(out/'head.png'))
    # Rebind the untouched original bent sleeve and the original extended arm.
    left={'bones':[[171,293],[157,335],[132,294]],
        'forearm_guide':[[128,286],[152,294],[164,320],[169,336],[153,344],[134,320]],
        'mask':[[185,278],[193,292],[178,319],[163,349],[151,354],[139,341],[132,311],[132,294],[146,284],[165,284]],
        'hand_mask':[[116,280],[134,280],[141,291],[137,303],[123,306],[115,295]]}
    right={'bones':[[281,294],[327,338],[365,364]],
        'mask':[[276,294],[297,303],[333,320],[378,346],[375,352],[383,358],[382,365],[375,371],[369,378],[349,378],[330,369],[316,350],[293,338]],
        'hand_mask':[[347,365],[347,359],[356,356],[364,352],[371,350],[377,353],[377,357],[383,358],[383,364],[377,369],[368,369],[367,376],[358,376],[357,371],[348,374]]}
    spec={'original':{'order':['right','left'],'left':left,'right':right}}
    for side,arm in (('left',left),('right',right)):
        arm['sleeve_rect']=save_crop(sleeve_layer(base,arm['mask'],[arm['hand_mask']]),out/f'original-{side}-sleeve.png')
        arm['hand_rect']=save_crop(extract(base,arm['hand_mask']),out/f'original-{side}-hand.png')
    (out/'rig.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    manifest={'source':'grangerpet/assets/character.png','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'method':'Raster separation only. Original face/bangs unchanged; reuse historical Rig local occluded-hair repair; exclude its protruding wand alpha. No generative art.',
        'head_mask':outline,'hair_repair':'Historical scenes/hermione-head.png crop x55..154,y210..311 inside head silhouette',
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.png'))}}
    (out/'provenance.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'layers':len(manifest['files']),'source_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==manifest['source_sha256']}))


if __name__=='__main__':main()
