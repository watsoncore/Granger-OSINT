"""Small articulated raster pass over the approved rig and matching cameo masters."""
from __future__ import annotations
import math
from pathlib import Path
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QColor,QFont,QImage,QPainter,QPainterPath,QPen


class SceneArtLibrary:
    def __init__(self,directory:Path):
        self.layers={name:QImage(str(directory/f'hermione-{name}.png'))
            for name in ('base','head','body','wand_arm','free_arm','left_leg','right_leg')}
        self.cameos={name:QImage(str(directory/f'{name}.png')) for name in ('draco','ron','harry')}
        self.hair_repair=QImage(str(directory/'hermione-left-curl-v2.png'))
        if any(image.isNull() for image in (*self.layers.values(),*self.cameos.values())):
            raise ValueError('Не удалось прочитать локальные слои сцен персонажа')
        self.cameo_arms={};self.cameo_bodies={}
        arm=_path([(146,255),(176,252),(199,286),(207,332),(196,361),(148,358),(141,320)])
        for name,base in self.cameos.items():
            layer=QImage(base.size(),QImage.Format.Format_ARGB32_Premultiplied);layer.fill(Qt.GlobalColor.transparent)
            p=QPainter(layer);p.setClipPath(arm);p.drawImage(0,0,base);p.end();self.cameo_arms[name]=layer
            body=base.copy();p=QPainter(body);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            p.fillPath(arm,Qt.GlobalColor.white);p.end();self.cameo_bodies[name]=body


def _path(points):
    result=QPainterPath(QPointF(*points[0]))
    for x,y in points[1:]:result.lineTo(x,y)
    result.closeSubpath();return result


def _arm(p,start,end,*,hand=True):
    p.setPen(QPen(QColor('#332515'),.008,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    p.setBrush(QColor('#25272a'))
    x,y=start;ex,ey=end
    arm=QPainterPath(QPointF(x-.028,y));arm.quadTo(ex-.04,ey-.025,ex-.022,ey+.025)
    arm.lineTo(ex+.022,ey+.025);arm.quadTo(ex+.045,ey-.008,x+.027,y);arm.closeSubpath();p.drawPath(arm)
    if hand:
        p.setBrush(QColor('#ffe5c9'));p.drawEllipse(QRectF(ex-.022,ey-.017,.044,.035))


def _heart(p,x,y,scale,opacity):
    p.save();p.setOpacity(opacity);p.translate(x,y);p.scale(scale,scale)
    p.setPen(QPen(QColor('#b27676'),.07));p.setBrush(QColor('#e4a1a1'))
    heart=QPainterPath(QPointF(0,.65));heart.cubicTo(-1,0,-.6,-.65,0,-.17)
    heart.cubicTo(.6,-.65,1,0,0,.65);p.drawPath(heart);p.restore()


def _face(p,base,geometry,elapsed,*,gaze=0,shy=0,annoyed=0,talking=False,look_down=False):
    from .pet_actions import _closed_eyes,_mouth
    # All coordinates are normalized to the same 512px approved master.
    p.save()
    for x,y,w,h in geometry.get('eye_rects',[]):
        if gaze or look_down:
            p.save();p.setClipRect(QRectF(x+.008,y+.012,w-.016,h-.018))
            p.fillRect(QRectF(x,y,w,h),QColor('#fffaf0'))
            p.drawImage(QRectF(gaze*.006,.005 if look_down else 0,1,1),base);p.restore()
    closure=max(0,1-abs(elapsed%4.8-3.7)/.14)
    if closure:_closed_eyes(p,geometry,closure)
    _mouth(p,geometry,yawn=.25*max(0,math.sin(elapsed*8)) if talking else 0)
    if shy:
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(226,124,116,round(100*shy)))
        for x,y,w,h in geometry.get('eye_rects',[]):p.drawEllipse(QRectF(x+.006,y+h+.009,w*.8,.026))
    if annoyed:
        p.setPen(QPen(QColor('#563c24'),.006,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        for i,(x,y,w,h) in enumerate(geometry.get('eye_rects',[])):
            p.drawLine(QPointF(x+.009,y+.003 if i==0 else y+.022),QPointF(x+w-.009,y+.022 if i==0 else y+.003))
    p.restore()


def scene_frame(library,pose):
    """A bounded scene timeline, with time-based micro-motions at 12 fps."""
    from .pet_actions import _book
    art=library.scenes;layers=art.layers;t=pose.elapsed;q=pose.progress;s=pose.strength
    action=pose.action;phone=action in ('phone_solvnox','daydream')
    reading=action in ('reading','ron_note');shy=action in ('shy','daydream') or phone and q>.6
    annoyed=action in ('annoyed','malfoy')
    canvas=QImage(256,256,QImage.Format.Format_ARGB32_Premultiplied);canvas.fill(Qt.GlobalColor.transparent)
    p=QPainter(canvas);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(.5,.5);breath=math.sin(t*1.7)*.8
    stomp=-abs(math.sin(t*6))*2*s if action=='annoyed' and .3<q<.6 else 0
    p.translate(0,breath+stomp)
    for name in ('left_leg','right_leg'):p.drawImage(0,0,layers[name])
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#25272a'))
    p.drawPath(_path([(146,287),(177,270),(265,267),(322,326),(300,376),(164,376)]))
    p.drawImage(0,0,layers['body'])
    custom=reading or phone or shy or annoyed
    p.save();p.setOpacity(1-s if custom else 1)
    p.drawImage(0,0,layers['free_arm'])
    p.save();p.translate(171,298);p.rotate(math.sin(t*3)*18*s if action=='wand_play' else 0)
    p.translate(-171,-298);p.drawImage(0,0,layers['wand_arm']);p.restore();p.restore()
    head_angle=(-2.2*s if reading else 3*s if shy else -2*s if annoyed else 0)+math.sin(t*1.5)*.3
    p.save();p.translate(229,252);p.rotate(head_angle);p.translate(-229,-252)
    p.drawImage(0,0,layers['head']);p.scale(512,512)
    _face(p,layers['base'],library.geometry,t,gaze=(.7 if shy else -.5 if pose.cameo else 0),
        shy=s*.9 if shy else 0,annoyed=s if annoyed else 0,talking=pose.cameo and 2<t%4<3.5,
        look_down=reading or phone and q<.7)
    p.restore()
    p.save();p.scale(512,512)
    if custom:
        p.save();p.setOpacity(s)
        if reading:
            _arm(p,(.32,.59),(.29,.68));_arm(p,(.56,.60),(.57,.68))
        elif phone:
            _arm(p,(.32,.59),(.48,.68));_arm(p,(.56,.60),(.58,.65))
        elif shy:
            _arm(p,(.32,.59),(.39,.59));_arm(p,(.56,.60),(.52,.59))
        else:
            _arm(p,(.32,.59),(.54,.65));_arm(p,(.56,.60),(.35,.66))
        p.restore()
    if reading:
        opening=min(1,max(.12,t/.9))*s
        p.save();p.translate(.435,.635);p.scale(max(.12,opening),1);p.translate(-.435,-.635)
        _book(p,t,s);p.restore()
    elif action=='shy':
        p.save();p.translate(0,-.10*s*math.sin(q*math.pi));_book(p,t,s*.9);p.restore()
    elif phone:
        hug=max(0,1-abs(q-.8)/.13) if action=='phone_solvnox' else 0
        x=.52-.05*hug;y=.64+.15*(1-s)-.02*hug
        p.save();p.setOpacity(s);p.translate(x,y);p.rotate(-8+6*math.sin(t*1.4))
        p.setPen(QPen(QColor('#493b35'),.008));p.setBrush(QColor('#676176'))
        p.drawRoundedRect(QRectF(-.045,-.105,.09,.16),.012,.012)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#f7e7d8'));p.drawRoundedRect(QRectF(-.034,-.087,.068,.117),.004,.004)
        font=QFont('Segoe UI');font.setPixelSize(10);p.save();p.scale(1/512,1/512);p.setFont(font);p.setPen(QColor('#65505c'))
        p.drawText(QRectF(-18,-43,38,14),Qt.AlignmentFlag.AlignCenter,'Solvnox');p.restore()
        p.setPen(QPen(QColor('#bd8d93'),.005,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        bars=int(t*3)%4 if q<.48 or q>.58 else 0
        for i in range(bars):p.drawLine(QPointF(-.023,-.035+i*.018),QPointF(.022-i*.004,-.035+i*.018))
        p.restore()
        if .28<q<.78 and not .48<q<.58:
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#ffe5c9'))
            p.drawEllipse(QRectF(x+.017+.008*math.sin(t*15),y-.008,.032,.022))
        if q>.6:_heart(p,.69,.34-math.sin(t)*.01,.025,s*.7)
    elif action=='wand_play':
        tip=library.geometry.get('wand_tip',[.145,.38]);spark=max(0,math.sin(q*math.pi))
        p.setPen(QPen(QColor('#c6c2dc'),.004));p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(5):
            angle=t*2+i*math.tau/5;r=(.03+.03*math.sin(t*2))*spark
            p.drawEllipse(QPointF(tip[0]+math.cos(angle)*r,tip[1]+math.sin(angle)*r),.006,.006)
    p.restore();p.end();return canvas


def cameo_frame(library,pose):
    art=library.scenes;base=art.cameos[pose.cameo];body=art.cameo_bodies[pose.cameo];t=pose.elapsed
    canvas=QImage(256,256,QImage.Format.Format_ARGB32_Premultiplied);canvas.fill(Qt.GlobalColor.transparent)
    p=QPainter(canvas);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);p.scale(.5,.5)
    p.drawImage(QRectF(0,244,512,268),body,QRectF(0,244,512,268))
    p.save();p.translate(210,270);p.rotate(math.sin(t*4)*6);p.translate(-210,-270)
    p.drawImage(0,0,art.cameo_arms[pose.cameo]);p.restore()
    p.save();p.translate(249,249);p.rotate(math.sin(t*2)*1.4);p.translate(-249,-249)
    p.drawImage(QRectF(0,0,512,252),base,QRectF(0,0,512,252))
    # Small conversational gestures: nod, mouth and blink remain local raster
    # operations. No generated video/extra timer or interactive chat actor.
    p.scale(512,512)
    from .pet_actions import _closed_eyes
    draco=pose.cameo=='draco'
    eyes=[[.340,.300,.080,.081],[.483,.327,.102,.082]] if draco else [[.326,.318,.083,.083],[.468,.335,.103,.092]]
    closure=max(0,1-abs(t%4.8-3.7)/.14)
    if closure:_closed_eyes(p,{'eye_rects':eyes},closure)
    if int(t*2)%4>=2:
        x,y=(.443,.430) if draco else (.440,.450)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#ffe5c9'))
        p.drawEllipse(QRectF(x-.035,y-.026,.070,.056))
        p.setPen(QPen(QColor('#533728'),.004,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x-.012,y+.002),QPointF(x+.013,y+.002))
    p.restore();p.end();return canvas
