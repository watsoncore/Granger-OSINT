"""Bounded input events for the application's own isolated release-QA window."""
import math
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def deliver(surface,payload):
    action=payload.get('kind')
    if action not in ('click','drag','wheel','text','key'):raise ValueError('Unsupported QA input')
    widget=surface.focusProxy() or surface
    def point(key):
        row=payload.get(key)
        if not isinstance(row,list) or len(row)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in row):raise ValueError('Invalid own-window coordinate')
        if not 0<=row[0]<surface.width() or not 0<=row[1]<surface.height():raise ValueError('QA input outside own surface')
        return QPoint(round(row[0]),round(row[1]))
    modifiers=Qt.KeyboardModifier.ControlModifier if payload.get('ctrl') is True else Qt.KeyboardModifier.NoModifier
    if action=='click':QTest.mouseClick(widget,Qt.MouseButton.LeftButton,modifiers,point('at'))
    elif action=='drag':
        start,end=point('at'),point('to')
        QTest.mousePress(widget,Qt.MouseButton.LeftButton,modifiers,start)
        for i in range(1,9):QTest.mouseMove(widget,start+(end-start)*i/8,12)
        QTest.mouseRelease(widget,Qt.MouseButton.LeftButton,modifiers,end)
    elif action=='wheel':
        at=point('at');delta=payload.get('delta',120)
        if type(delta) is not int or abs(delta)>1200:raise ValueError('Invalid wheel amount')
        event=QWheelEvent(QPointF(at),QPointF(widget.mapToGlobal(at)),QPoint(),QPoint(0,delta),
            Qt.MouseButton.NoButton,modifiers,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(widget,event)
    elif action=='text':
        text=payload.get('text','')
        if not isinstance(text,str) or len(text)>200 or not text.isascii():raise ValueError('QA typing expects bounded ASCII')
        QTest.keyClicks(widget,text)
    else:
        keys={'escape':Qt.Key.Key_Escape,'home':Qt.Key.Key_Home,'enter':Qt.Key.Key_Return,'all':Qt.Key.Key_A,'backspace':Qt.Key.Key_Backspace,
            'up':Qt.Key.Key_Up,'down':Qt.Key.Key_Down,'left':Qt.Key.Key_Left,'right':Qt.Key.Key_Right}
        if payload.get('key') not in keys:raise ValueError('Unsupported QA key')
        QTest.keyClick(widget,keys[payload['key']],modifiers)
