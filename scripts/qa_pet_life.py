"""Render actual code-native pet action frames and verify source-art identity."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'output/master-qa/pet-life')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.pet_life import PetLifeController,SCENES
    from grangerpet.pet_actions import action_frame
    app=QApplication.instance() or QApplication([])
    font_path=Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts/segoeui.ttf'
    if font_path.is_file():
        QFontDatabase.addApplicationFont(str(font_path))
    library=SpriteLibrary();actions=list(SCENES)+['cast','avada','yawn','sleep','leave','return','wake']
    report={'tested_at_utc':datetime.now(timezone.utc).isoformat(),'method':'Actual QPainter action renderer over unchanged supplied sprites; no network or model image generation',
            'checks':[],'actions':{},'asset_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'grangerpet/assets').glob('*') if p.is_file()}}
    sheet=QImage(4*256,len(actions)*290,QImage.Format.Format_ARGB32_Premultiplied);sheet.fill(QColor('#17212b'))
    painter=QPainter(sheet);font=QFont('Segoe UI');font.setPixelSize(16);painter.setFont(font)
    for row,name in enumerate(actions):
        clock=[100.0];life=PetLifeController(clock=lambda:clock[0],rng=random.Random(42));life.start_action(name,duration=4)
        hashes=[]
        for column,sample in enumerate((.35,1.15,2.1,3.25)):
            clock[0]=100+sample;image=action_frame(library,life.pose());file=args.output/f'{name}-{column}.png';image.save(str(file))
            hashes.append(hashlib.sha256(bytes(image.constBits())).hexdigest())
            painter.drawImage(column*256,row*290+26,image)
            painter.setPen(QColor('#f1f3f5'));painter.drawText(QRectF(column*256+8,row*290,250,25),Qt.AlignmentFlag.AlignLeft,f'{name} · {sample:.2f}s')
        report['actions'][name]={'distinct_frames':len(set(hashes)),'frame_hashes':hashes}
        report['checks'].append({'name':name+'_real_frames','passed':len(set(hashes))>1})
    painter.end();sheet.save(str(args.output/'contact-sheet.png'))
    for start in range(0,len(actions),4):sheet.copy(0,start*290,sheet.width(),min(4,len(actions)-start)*290).save(str(args.output/f'page-{start//4+1}.png'))
    report['passed']=all(x['passed'] for x in report['checks'])
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(report['checks']),'contact_sheet':str(args.output/'contact-sheet.png')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
