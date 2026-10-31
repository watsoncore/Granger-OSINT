"""Bounded native-widget recorder, reachable only through isolated QA IPC."""
import json
from pathlib import Path
import time
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QImage,QPainter


def start_capture(pet,name,duration,fps):
    if getattr(pet,'_qa_capture',None) is not None:return False
    directory=Path(pet._trace_path).parent/name
    if directory.exists():return False
    directory.mkdir();timer=QTimer(pet);timer.setTimerType(Qt.TimerType.PreciseTimer)
    pet._qa_capture=timer;started=time.monotonic();rows=[]
    def frame():
        now=time.monotonic();pose=pet.life.pose(now);dpr=pet.devicePixelRatioF()
        bounds=pet.frameGeometry()
        guest=pet.cameo if pet.cameo and pet.cameo.isVisible() else None
        if guest:bounds=bounds.united(guest.frameGeometry())
        image=QImage(round(bounds.width()*dpr),round(bounds.height()*dpr),QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr);image.fill(Qt.GlobalColor.transparent)
        p=QPainter(image);p.drawPixmap(pet.pos()-bounds.topLeft(),pet.grab())
        if guest:p.drawPixmap(guest.pos()-bounds.topLeft(),guest.grab())
        p.end();image.save(str(directory/f'{len(rows):04}.png'))
        rows.append({'at':round(now-started,6),'action':pose.action,'variant':pose.variant,
            'progress':round(pose.progress,6),'frame':pose.frame,'signature':str(pet._render_signature),
            'bounds':list(bounds.getRect()),'dpr':dpr})
        if now-started>=duration or pet._ending:
            timer.stop();timer.deleteLater();pet._qa_capture=None
            report={'method':'Live native QWidget.grab of owned production windows; normal production clock; no desktop content',
                'requested_fps':fps,'duration':now-started,'frames':rows}
            (directory/'capture.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    timer.timeout.connect(frame);timer.start(round(1000/fps));return True
