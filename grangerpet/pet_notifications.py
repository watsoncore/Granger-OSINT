"""One local pixel envelope with encrypted unread IDs. No Toast/WinRT/network."""
from __future__ import annotations
from collections import OrderedDict
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import uuid
from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPolygon, QRegion
from PySide6.QtWidgets import QApplication, QWidget
from .credentials import CredentialError, CredentialsStore
from .motion import reduced_motion

KINDS = frozenset(('reply', 'investigation', 'error'))
ACCENTS = {'reply':'#eee4c6', 'investigation':'#eee4c6', 'error':'#e7c9bf'}
ICON_SIZE = (64, 48)
_ID = re.compile(r'[A-Za-z0-9_-]{1,160}\Z')

@dataclass(frozen=True)
class NotificationPayload:
    kind: str
    message_id: str | None = None
    index: int | None = None
    conversation_id: str | None = None
    @property
    def key(self): return (self.conversation_id or '', self.message_id or '')

@dataclass(frozen=True)
class NotificationPose:
    phase: str
    opacity: float
    offset: int
    lid: int = 0
    spark: int = 0

def notification_pose(elapsed, animate=True):
    """Only the entrance animates; unread mail remains until actually viewed."""
    elapsed = max(0., elapsed)
    if not animate or elapsed >= .28: return NotificationPose('dwell', 1., 0)
    eased = 1-(1-elapsed/.28)**3
    return NotificationPose('appear', eased, round((1-eased)*5))

class UnreadLedger:
    """Opaque references only; unread entries are never silently evicted."""
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.unread, self.seen = OrderedDict(), OrderedDict()
        self.persistence_error = False
        self._load()

    @staticmethod
    def valid(row):
        return (row.kind in KINDS and isinstance(row.message_id,str) and bool(_ID.fullmatch(row.message_id))
            and (row.conversation_id is None or isinstance(row.conversation_id,str) and bool(_ID.fullmatch(row.conversation_id)))
            and (row.index is None or type(row.index) is int and 0 <= row.index <= 10_000_000))

    def _load(self):
        if self.path is None or not self.path.is_file(): return
        try:
            if self.path.stat().st_size > 8_000_000: raise ValueError('Unread ledger is too large')
            value = json.loads(CredentialsStore._protect(self.path.read_bytes(), decrypt=True).decode('utf-8'))
            if not isinstance(value,dict) or value.get('version') != 1: raise ValueError('Unsupported unread ledger')
            for row in value.get('unread',[]):
                if not isinstance(row,dict): continue
                payload = NotificationPayload(**{key:row.get(key) for key in ('kind','message_id','index','conversation_id')})
                if self.valid(payload): self.unread[payload.key] = payload
            for key in value.get('seen',[])[-1024:]:
                if isinstance(key,list) and len(key)==2 and all(isinstance(v,str) for v in key): self.seen[tuple(key)] = None
        except (OSError,ValueError,TypeError,UnicodeError,CredentialError):
            self.unread.clear(); self.seen.clear(); self.persistence_error = True

    def _save(self):
        if self.path is None: return
        try:
            raw=json.dumps({'version':1,'unread':[asdict(row) for row in self.unread.values()],
                'seen':list(self.seen)},ensure_ascii=False,separators=(',',':')).encode('utf-8')
            if len(raw)>7_500_000: raise ValueError('Unread storage limit reached')
            protected=CredentialsStore._protect(raw)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd,temporary=tempfile.mkstemp(prefix='unread-',dir=self.path.parent)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(protected);stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,self.path)
            finally: Path(temporary).unlink(missing_ok=True)
            self.persistence_error=False
        except (OSError,ValueError,CredentialError): self.persistence_error=True

    def add(self,row):
        if not self.valid(row) or row.key in self.unread or row.key in self.seen: return False
        self.unread[row.key]=row;self._save();return True

    def mark_seen(self,conversation_id,message_ids):
        if not isinstance(conversation_id,str) or not isinstance(message_ids,(list,tuple)): return 0
        removed=0;changed=False
        for identifier in message_ids:
            if not isinstance(identifier,str) or not _ID.fullmatch(identifier): continue
            key=(conversation_id,identifier)
            changed = changed or key not in self.seen or key in self.unread
            removed+=self.unread.pop(key,None) is not None
            self.seen[key]=None;self.seen.move_to_end(key)
        while len(self.seen)>1024:self.seen.popitem(last=False)
        if changed:self._save()
        return removed

def notification_position(character,bounds,size,obstacle=None):
    width,height=size.width(),size.height()
    candidates=(QPoint(character.right()+5,character.center().y()-height//2),
        QPoint(character.left()-width-4,character.center().y()-height//2),
        QPoint(character.center().x()-width//2,character.top()-height-5),
        QPoint(character.center().x()-width//2,character.bottom()+6))
    placed=[]
    for point in candidates:
        point=QPoint(max(bounds.left(),min(point.x(),bounds.right()-width+1)),max(bounds.top(),min(point.y(),bounds.bottom()-height+1)))
        rect=QRect(point,size);overlap=rect.intersected(character);score=overlap.width()*overlap.height()
        if obstacle is not None and not obstacle.isEmpty():
            overlap=rect.intersected(obstacle);score+=overlap.width()*overlap.height()*2
        placed.append((score,point))
    return min(placed,key=lambda row:row[0])[1]

_DIGITS={
 '0':('111','101','101','101','111'),'1':('010','110','010','010','111'),
 '2':('111','001','111','100','111'),'3':('111','001','111','001','111'),
 '4':('101','101','111','001','001'),'5':('111','100','111','001','111'),
 '6':('111','100','111','101','111'),'7':('111','001','010','010','010'),
 '8':('111','101','111','101','111'),'9':('111','101','111','001','111'),
 '+':('000','010','111','010','000'),'!':('010','010','010','000','010')}

class PetNotification(QWidget):
    activated=Signal(str,object)
    unread_changed=Signal(int)
    def __init__(self,parent=None,*,clock=None,ledger_path=None):
        # A separate Window exposes its own native hit bounds. Qt.Tool
        # was grouped under the219px character by accessibility/input clients,
        # making the adjacent letter impossible to target independently.
        # Lifetime stays tied to the character; NOACTIVATE without APPWINDOW
        # keeps the small overlay out of task switching and the taskbar.
        super().__init__(None,Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        if parent is not None:parent.destroyed.connect(self.deleteLater)
        self.setWindowTitle('Granger-OSINT · Непрочитанные ответы Гермионы')
        self.setObjectName('HermioneNotification')
        self.setStyleSheet('QWidget#HermioneNotification { background: transparent; border: none; }')
        for attribute in (Qt.WidgetAttribute.WA_TranslucentBackground,Qt.WidgetAttribute.WA_ShowWithoutActivating,Qt.WidgetAttribute.WA_NoSystemBackground):self.setAttribute(attribute)
        self.setCursor(Qt.CursorShape.PointingHandCursor);self.setFixedSize(*ICON_SIZE)
        self._clock=clock or time.monotonic;self._started=0.;self._animate=True;self._enabled=True
        self._allowed=dict.fromkeys(KINDS,True);self._suppressed=False;self._suppressed_conversation=None
        self._pressed=None;self._pose=notification_pose(1);self._last_anonymous={}
        self.ledger=UnreadLedger(ledger_path);self.payload=None
        self._timer=QTimer(self);self._timer.setTimerType(Qt.TimerType.PreciseTimer);self._timer.setInterval(24);self._timer.timeout.connect(self.tick)
        self.setMask(QRegion(QRect(2,12,52,34)).united(QRegion(QRect(38,0,26,29))))
        self._keep_out_of_taskbar()

    def _keep_out_of_taskbar(self):
        """Independent native bounds without a taskbar button or activation.

        NOACTIVATE windows are absent from taskbar by default. Qt's normal
        Window adds APPWINDOW, so remove that one bit before the first show.
        Do not register Toast/ActionCenter/WinRT services or global hooks.
        """
        if sys.platform!='win32' or QApplication.platformName()!='windows':return
        try:
            import ctypes
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.GetWindowLongPtrW.argtypes=[ctypes.c_void_p,ctypes.c_int]
            user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
            user.SetWindowLongPtrW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_ssize_t]
            user.SetWindowLongPtrW.restype=ctypes.c_ssize_t
            window=int(self.winId());style=user.GetWindowLongPtrW(window,-20)
            user.SetWindowLongPtrW(window,-20,(style & ~0x00040000)|0x08000000)
        except (OSError,AttributeError):pass

    def showEvent(self,event):
        self._keep_out_of_taskbar()
        super().showEvent(event)

    @property
    def unread_count(self):return sum(row.kind!='error' for row in self.ledger.unread.values())
    @property
    def visible_count(self):return sum(row.kind!='error' and self._allowed[row.kind] for row in self.ledger.unread.values())
    def apply_settings(self,settings):
        self._enabled=bool(getattr(settings,'notifications_enabled',True))
        self._animate=bool(getattr(settings,'notifications_animate',True)) and not reduced_motion()
        self._allowed={'reply':bool(getattr(settings,'notifications_reply',True)),
            'investigation':bool(getattr(settings,'notifications_investigation',True)),'error':bool(getattr(settings,'notifications_errors',True))}
        self.refresh()
    def set_context(self,conversation_id=None,*,suppressed=False):
        if (conversation_id,bool(suppressed))!=(self._suppressed_conversation,self._suppressed):
            self._suppressed_conversation,self._suppressed=conversation_id,bool(suppressed);self.refresh()
    def notify(self,kind,message_id=None,*,index=None,conversation_id=None):
        if kind not in KINDS:raise ValueError('Unknown notification event')
        if message_id is None:
            now=self._clock()
            if now-self._last_anonymous.get(kind,-100)<2:return False
            self._last_anonymous[kind]=now;message_id='local_'+uuid.uuid4().hex
        row=NotificationPayload(kind,message_id,index,conversation_id);added=self.ledger.add(row)
        if added:self.unread_changed.emit(self.unread_count);self.refresh(animate=True)
        return added and self._enabled and self._allowed[kind]
    def mark_seen(self,conversation_id,message_ids):
        removed=self.ledger.mark_seen(conversation_id,message_ids)
        if removed:self.unread_changed.emit(self.unread_count);self.refresh()
        return removed
    def refresh(self,*,animate=False):
        candidates=[row for row in self.ledger.unread.values() if self._allowed[row.kind] and (self._suppressed_conversation is None or row.conversation_id!=self._suppressed_conversation)]
        candidates=[row for row in candidates if row.kind!='error']+[row for row in candidates if row.kind=='error']
        self.payload=candidates[0] if candidates else None
        if not self._enabled or self._suppressed or self.payload is None:self._timer.stop();self.hide();return
        if animate or not self.isVisible():self._started=self._clock()
        self.setAccessibleName(f'Ответов не прочитано: {self.visible_count}. Открыть разговор с Гермионой')
        self.setToolTip(f'Непрочитанных ответов: {self.visible_count}. Открыть ответ' if self.visible_count else 'Произошла ошибка. Открыть сообщение')
        self.tick();self.show();self.raise_();self.update()
    def dismiss(self):
        """Hide only. Opening a window does not prove its messages were read."""
        self._timer.stop();self._pressed=None;self.hide()
    def tick(self):
        if self.payload is None:return
        self._pose=notification_pose(self._clock()-self._started,self._animate);self.update()
        self._timer.start() if self._pose.phase=='appear' else self._timer.stop()
    def paintEvent(self,event):
        if self.payload:
            painter=QPainter(self);self.paint_letter(painter,self.payload.kind,self._pose,self.visible_count)
    @staticmethod
    def paint_letter(painter,kind,pose,count=1):
        painter.save();painter.setRenderHint(QPainter.RenderHint.Antialiasing,False);painter.setOpacity(pose.opacity);painter.translate(0,pose.offset)
        outline=QColor('#302b2a');paper=QColor(ACCENTS[kind]);painter.setPen(Qt.PenStyle.NoPen)
        painter.fillRect(2,14,52,30,outline);painter.fillRect(4,12,48,34,outline);painter.fillRect(6,16,44,26,paper);painter.fillRect(6,39,44,3,QColor('#c6b58f'))
        for step in range(11):
            painter.fillRect(6+step*2,17+step,2,2,outline);painter.fillRect(48-step*2,17+step,2,2,outline)
        for step in range(7):
            painter.fillRect(6+step*2,38-step,2,2,QColor('#b7a88c'));painter.fillRect(48-step*2,38-step,2,2,QColor('#b7a88c'))
        badge=QPolygon([QPoint(44,0),QPoint(56,0),QPoint(56,2),QPoint(60,2),QPoint(60,6),QPoint(63,6),QPoint(63,20),QPoint(60,20),QPoint(60,24),QPoint(56,24),QPoint(56,27),QPoint(44,27),QPoint(44,24),QPoint(40,24),QPoint(40,20),QPoint(38,20),QPoint(38,6),QPoint(40,6),QPoint(40,2),QPoint(44,2)])
        painter.setBrush(outline);painter.drawPolygon(badge)
        painter.save();painter.translate(50.5,13.5);painter.scale(.83,.83);painter.translate(-50.5,-13.5);painter.setBrush(QColor('#c94c4d'));painter.drawPolygon(badge);painter.restore()
        label='!' if kind=='error' and count==0 else str(max(1,count)) if count<100 else '99+'
        scale=2 if len(label)<=2 else 1;left=round(50.5-(len(label)*4-1)*scale/2);top=9 if scale==2 else 11
        for index,char in enumerate(label):
            for y,line in enumerate(_DIGITS[char]):
                for x,pixel in enumerate(line):
                    if pixel=='1':painter.fillRect(left+(index*4+x)*scale,top+y*scale,scale,scale,QColor('#fff7ed'))
        painter.restore()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self._pressed=event.position().toPoint();event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self._pressed is None:return
        pressed,self._pressed=self._pressed,None
        if self.payload and (event.position().toPoint()-pressed).manhattanLength()<=6 and self.mask().contains(event.position().toPoint()):self.activated.emit(self.payload.kind,self.payload)
        event.accept()
