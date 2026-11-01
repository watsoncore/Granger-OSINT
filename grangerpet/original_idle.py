"""Historical idle body mechanics over its exact original raster layers."""
import math
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QPainterPath,QColor
from .original_face import OriginalFace


def poly(points):
    result=QPainterPath(QPointF(*points[0]))
    for point in points[1:]:result.lineTo(*point)
    result.closeSubpath();return result


class OriginalIdle:
    def __init__(self,layers):
        self.layers=layers;self.face=OriginalFace(layers['base'],layers['head'])

    def draw(self,p,a):
        breath=math.sin(a.source_time*math.tau/4*2)
        p.save()
        for name in ('left_leg','right_leg'):p.drawImage(0,0,self.layers[name])
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#25272a'))
        p.drawPath(poly(((156,289),(201,269),(252,263),(297,307),(328,345),(303,368),(278,379),(171,376),(149,335))))
        p.drawImage(QPointF(0,breath*.45),self.layers['body'])
        p.drawPath(poly(((146,287),(177,286),(182,318),(158,342),(142,321))))
        p.drawPath(poly(((276,299),(300,312),(330,344),(309,359),(280,339))))
        p.save();p.translate(282,306);p.rotate(.5*breath);p.translate(-282,-306)
        p.drawImage(QPointF(0,-breath*.4),self.layers['free_arm']);p.restore()
        p.save();p.translate(229,252-.8*breath+a.head_drop);p.rotate(.12*breath+a.head);p.translate(-229,-252)
        p.drawImage(0,0,self.face.image(a));p.restore()
        p.save();p.translate(171,298);p.rotate(.25*breath);p.translate(-171,-298)
        p.drawImage(QPointF(0,-breath*.4),self.layers['wand_arm']);p.restore();p.restore()
