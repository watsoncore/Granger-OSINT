"""Render real compact pixel-letter code at three device scales; no live API."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QFont,QFontDatabase,QImage,QPainter
from PySide6.QtWidgets import QApplication
from grangerpet.pet_notifications import PetNotification,notification_pose

def main():
    app=QApplication.instance() or QApplication([])
    font=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Fonts/segoeui.ttf'
    if font.exists():QFontDatabase.addApplicationFont(str(font))
    output=ROOT/'output/refinement-qa/pixel-letter';output.mkdir(parents=True,exist_ok=True)
    sheet=QImage(800,540,QImage.Format.Format_ARGB32_Premultiplied);sheet.fill(QColor('#17212b'))
    painter=QPainter(sheet);painter.setFont(QFont('Segoe UI',11));painter.setPen(QColor('#e8edf3'))
    frames=[]
    for row,dpr in enumerate((1.,1.25,1.5)):
        for column,(kind,count) in enumerate((('reply',1),('investigation',2),('reply',12),('error',0))):
            image=QImage(round(64*dpr),round(48*dpr),QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(dpr);image.fill(Qt.GlobalColor.transparent)
            drawing=QPainter(image);PetNotification.paint_letter(drawing,kind,notification_pose(1),count);drawing.end()
            name=f'{kind}-{count}-{dpr:.2f}.png';image.save(str(output/name))
            painter.drawText(column*200+15,row*180+28,f'{kind} / count {count}')
            painter.drawText(column*200+15,row*180+52,f'DPR {dpr:.2f}')
            painter.drawImage(column*200+64,row*180+86,image)
            frames.append({'kind':kind,'count':count,'device_pixel_ratio':dpr,'physical_pixels':[image.width(),image.height()],'path':name})
    painter.end();sheet.save(str(output/'contact-sheet.png'))
    (output/'report.json').write_text(json.dumps({'renderer':'production PetNotification.paint_letter','fixture':True,'real_api':False,'frames':frames},indent=2),encoding='utf-8')
    print(output/'contact-sheet.png')

if __name__=='__main__':main()
