"""Compatible original facial cels, composed once with the original alpha."""
from collections import OrderedDict
from pathlib import Path
from PySide6.QtCore import QPointF,QRect,QRectF,Qt
from PySide6.QtGui import QColor,QImage,QPainter,QPainterPath,QPen


class OriginalFace:
    def __init__(self,master,head=None):
        folder=Path(__file__).parent/'assets'
        self.head=head if head is not None else QImage(str(folder/'scenes/hermione-head.png'))
        self.closed=QImage(str(folder/'original-hermione/blink-closed-head.png'))
        if self.closed.isNull():raise ValueError('Missing historical closed-eye derivative')
        self.master=master;self.rect=QRect(150,154,140,95)
        self.original_patch=self.head.copy(self.rect).convertToFormat(QImage.Format.Format_RGBA8888)
        self.alpha=bytes(self.original_patch.constBits())[3::4]
        self.interiors=[];self.pupils=[]
        # Pupil interiors only: original iris rims, whites and lashes stay fixed.
        for rect in (QRectF(172,184,15,17),QRectF(251,179,15,17)):
            area=QPainterPath();area.addRect(rect);self.interiors.append(area)
            source=rect.adjusted(-2,-2,2,2).toAlignedRect()
            self.pupils.append((master.copy(source),QPointF(source.topLeft())))
        self.cache=OrderedDict();self.last_key=None;self.last_image=None

    def key(self,a):
        return (a.blink>.35,round(max(-1.,min(1.,a.gaze[0]*.25))*4)/4,
            round(max(-.8,min(1.2,a.gaze[1]*.25))*4)/4,a.mouth,
            1 if a.brow>.2 else -1 if a.brow<-.2 else 0,round(max(0.,min(1.,a.blush))*16)/16)

    def image(self,a):
        key=self.key(a)
        if key==(False,0.,0.,'neutral',0,0.):return self.head
        if key==self.last_key:return self.last_image
        if key in self.cache:
            patch=self.cache.pop(key);self.cache[key]=patch
        else:
            patch=self._patch(key);self.cache[key]=patch
            if len(self.cache)>16:self.cache.popitem(last=False)
        # Replace the little patch before the head is painted. Another head
        # overlay would raise the original alpha253/254 to255.
        result=self.head.convertToFormat(QImage.Format.Format_RGBA8888)
        target=result.bits();source=bytes(patch.constBits());width=self.rect.width()*4
        for row in range(self.rect.height()):
            offset=(row+self.rect.y())*result.bytesPerLine()+self.rect.x()*4
            target[offset:offset+width]=source[row*width:(row+1)*width]
        self.last_key=key;self.last_image=result;return result

    def _patch(self,key):
        blink,dx,dy,mouth,brow,blush=key;patch=self.original_patch.copy();p=QPainter(patch)
        p.setRenderHint(QPainter.RenderHint.Antialiasing);p.translate(-self.rect.x(),-self.rect.y())
        if blink:
            p.save();p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.drawImage(0,0,self.closed);p.restore()
        elif dx or dy:
            for interior,(pupil,origin) in zip(self.interiors,self.pupils):
                p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing,False);p.setClipPath(interior)
                p.drawImage(origin+QPointF(dx,dy),pupil);p.restore()
        if mouth!='neutral':
            # The existing working/error mouth paths from1b75ee9.
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#ffe5c9'));p.drawEllipse(QRectF(211,215,28,30))
            p.setPen(QPen(QColor('#30200f'),1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.setBrush(Qt.BrushStyle.NoBrush)
            line=QPainterPath(QPointF(215,231 if mouth=='smile' else 235))
            if mouth=='smile':line.quadTo(224,238,233,230)
            elif mouth=='pout':line.quadTo(225,226,234,234)
            elif mouth=='focused':line=QPainterPath(QPointF(219,231));line.quadTo(226,229,233,231)
            else:p.drawImage(QPointF(211,215),self.master.copy(211,215,28,30));line=QPainterPath()
            p.drawPath(line)
        if brow:
            p.setPen(QPen(QColor('#30200f'),2.4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.setBrush(Qt.BrushStyle.NoBrush)
            for x,y,sign in ((163,162,1),(240,156,-1)):
                line=QPainterPath(QPointF(x,y-(2 if brow<0 else 0)));line.quadTo(x+10,y-5,x+22,y+sign*(3 if brow>0 else -2));p.drawPath(line)
        if blush:
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(223,128,115,round(70*blush)))
            p.drawEllipse(QRectF(156,209,27,8));p.drawEllipse(QRectF(258,203,27,8))
        p.end()
        # Preserve literal original alpha, including its interior253/254 values.
        data=bytearray(patch.constBits());data[3::4]=self.alpha
        return QImage(bytes(data),patch.width(),patch.height(),patch.bytesPerLine(),QImage.Format.Format_RGBA8888).copy()
