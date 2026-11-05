"""Bounded input events for the application's own isolated release-QA window."""
import math
from PySide6.QtCore import QMimeData, QPoint, QPointF, QTimer, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def deliver(surface,payload):
    action=payload.get('kind')
    if action not in ('click','double_click','drag','wheel','text','key'):raise ValueError('Unsupported QA input')
    widget=surface.focusProxy() or surface
    def point(key):
        row=payload.get(key)
        if not isinstance(row,list) or len(row)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in row):raise ValueError('Invalid own-window coordinate')
        if not 0<=row[0]<surface.width() or not 0<=row[1]<surface.height():raise ValueError('QA input outside own surface')
        return QPoint(round(row[0]),round(row[1]))
    modifiers=Qt.KeyboardModifier.ControlModifier if payload.get('ctrl') is True else Qt.KeyboardModifier.NoModifier
    if action=='click':QTest.mouseClick(widget,Qt.MouseButton.LeftButton,modifiers,point('at'))
    elif action=='double_click':
        at=point('at')
        QTest.mouseClick(widget,Qt.MouseButton.LeftButton,modifiers,at)
        QTest.qWait(35)
        QTest.mouseClick(widget,Qt.MouseButton.LeftButton,modifiers,at)
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
            'up':Qt.Key.Key_Up,'down':Qt.Key.Key_Down,'left':Qt.Key.Key_Left,'right':Qt.Key.Key_Right,'k':Qt.Key.Key_K}
        if payload.get('key') not in keys:raise ValueError('Unsupported QA key')
        QTest.keyClick(widget,keys[payload['key']],modifiers)


def deliver_media(surface,path,payload):
    """Use Qt input against the QA window, preserving the system clipboard."""
    kind=payload.get('kind')
    if kind=='drop':
        at=payload.get('at',[])
        if not isinstance(at,list) or len(at)!=2 or not all(type(n) in (int,float) and math.isfinite(n) for n in at):return
        if not 0<=at[0]<surface.width() or not 0<=at[1]<surface.height():return
        point=QPoint(round(at[0]),round(at[1]))
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(path))])
        buttons=Qt.MouseButton.LeftButton;modifiers=Qt.KeyboardModifier.NoModifier
        action=Qt.DropAction.CopyAction
        enter=QDragEnterEvent(point,action,mime,buttons,modifiers)
        QApplication.sendEvent(surface,enter)
        if enter.isAccepted():
            QApplication.sendEvent(surface,QDropEvent(QPointF(point),action,mime,buttons,modifiers))
    elif kind=='clipboard':
        import ctypes
        sequence=ctypes.windll.user32.GetClipboardSequenceNumber
        clipboard=QApplication.clipboard()
        previous=clipboard.mimeData()
        backup=QMimeData();size=0
        if previous:
            for format_name in previous.formats():
                data=previous.data(format_name);size+=data.size()
                if size>24_000_000:return
                backup.setData(format_name,data)
            if previous.hasImage():backup.setImageData(previous.imageData())
            if previous.hasUrls():backup.setUrls(previous.urls())
        image=QImage(str(path))
        if image.isNull():return
        clipboard.setImage(image)
        set_sequence=sequence()
        widget=surface.focusProxy() or surface
        QTest.keyClick(widget,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)

        def restore():
            if sequence()==set_sequence:clipboard.setMimeData(backup)

        QTimer.singleShot(900,restore)
