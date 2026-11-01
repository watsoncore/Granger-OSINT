"""Compare historical user artwork to the active production neutral renderer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
from create_wand_animations import Rig
from grangerpet.animation import SpriteLibrary
from grangerpet.scene_pose import action_pose
from grangerpet.articulated import render_actor


def rgba(image):return image.convertToFormat(QImage.Format.Format_RGBA8888)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);app=QApplication([])
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/segoeui.ttf'))
    manifest=json.loads((ROOT/'grangerpet/assets/original-hermione/identity.json').read_text(encoding='utf-8'))
    protected=[{'path':name,'matches':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest}
        for name,digest in manifest['immutable_files'].items()]
    reference=Rig(QImage(str(ROOT/'resources/wand-reference/base-512.png'))).posed('idle',0)
    lib=SpriteLibrary();production=render_actor(lib,action_pose('idle',0.,0.),512)
    before,after=rgba(reference),rgba(production)
    face=before.copy(150,154,138,95);restored_face=after.copy(150,154,138,95)
    face_exact=bytes(face.constBits())==bytes(restored_face.constBits())
    # PNG premultiplication round trips may differ at antialiased transparent
    # edges. Opaque pixels and the exact face must remain bit-identical.
    first,second=bytes(before.constBits()),bytes(after.constBits());opaque_changes=0;alpha_changes=0
    for i in range(0,len(first),4):
        if first[i+3]!=second[i+3]:alpha_changes+=1
        if first[i+3]==second[i+3]==255 and first[i:i+3]!=second[i:i+3]:opaque_changes+=1
    reference.save(str(args.output/'historical-neutral-512.png'));production.save(str(args.output/'restored-neutral-512.png'))
    face.save(str(args.output/'historical-face.png'));restored_face.save(str(args.output/'restored-face.png'))
    sheet=QImage(1064,800,QImage.Format.Format_RGB32);sheet.fill(QColor('#f4f2ed'));p=QPainter(sheet)
    font=QFont('Segoe UI');font.setPixelSize(17);p.setFont(font);p.setPen(QColor('#3f3b32'))
    p.drawText(12,26,'Historical original / 1b75ee9');p.drawText(544,26,'Restored / production renderer')
    p.drawImage(8,38,reference);p.drawImage(540,38,production)
    p.drawText(12,586,'Same original face pixels');p.drawText(544,586,'Exact neutral face match: '+str(face_exact))
    p.drawImage(QPointF(80,610),face.scaled(276,190));p.drawImage(QPointF(612,610),restored_face.scaled(276,190));p.end()
    sheet.save(str(args.output/'identity-comparison.png'))
    original256=lib.frames['idle'][0];prod256=render_actor(lib,action_pose('idle',0.,0.),256)
    original_pixels,production_pixels=rgba(original256),rgba(prod256)
    atlas_exact=bytes(original_pixels.constBits())==bytes(production_pixels.constBits())
    original256.save(str(args.output/'historical-idle-atlas-frame0.png'));prod256.save(str(args.output/'restored-idle-256.png'))
    report={'source_commit':manifest['source_commit'],'protected_files':protected,'neutral_face_exact':face_exact,
        'opaque_pixel_changes':opaque_changes,'alpha_pixel_changes':alpha_changes,'historical_atlas_256_exact':atlas_exact,
        'method':'Historical generator and immutable user master versus actual render_actor; no AI generation; original seven atlases retained',
        'passed':all(r['matches'] for r in protected) and face_exact and atlas_exact and opaque_changes==alpha_changes==0}
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='protected_files'}));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
