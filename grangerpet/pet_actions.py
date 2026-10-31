"""Code-native action frames using the unchanged supplied character artwork.

Props and effects are QPainter shapes in the original sprite's palette. No
replacement face, generated portrait, external image or executable content.
"""
from __future__ import annotations

import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen


def _closed_eyes(painter, geometry, amount=1.0):
    painter.save()
    painter.setOpacity(max(0.0, min(1.0, amount)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#ffe5c9'))
    for x,y,w,h in geometry.get('eye_rects', [[.3027,.332,.0879,.0762],[.457,.3223,.0957,.0781]]):
        painter.drawEllipse(QRectF(x-.005,y-.002,w+.01,h+.008))
        painter.setPen(QPen(QColor('#4b3325'),.005,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        line=QPainterPath(QPointF(x+.006,y+h*.52))
        line.quadTo(x+w*.5,y+h*.7,x+w-.004,y+h*.43)
        painter.drawPath(line)
        painter.setPen(Qt.PenStyle.NoPen)
    painter.restore()


def _mouth(painter, geometry, *, yawn=0):
    x,y=geometry.get('mouth_center',[.4355,.4492])
    painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#ffe5c9'))
    painter.drawEllipse(QRectF(x-.025,y-.028,.05,.064))
    painter.setPen(QPen(QColor('#68422b'),.004,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    if yawn>.01:
        painter.setBrush(QColor('#a95f4c'))
        painter.drawEllipse(QRectF(x-.013-yawn*.005,y-.006,.027+yawn*.01,.013+yawn*.037))
    else:
        painter.drawLine(QPointF(x-.014,y+.008),QPointF(x+.016,y+.008))


def attention_frame(image, geometry, elapsed):
    """Keep time-based breath/blink alive while the gaze frame follows a cursor."""
    result=QImage(image.size(),QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent)
    p=QPainter(result);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(0,-math.sin(elapsed*1.7)*image.height()*.002)
    p.drawImage(0,0,image);p.scale(image.width(),image.height())
    phase=elapsed%4.6
    closure=max(0.0,1-abs(phase-3.8)/.13)
    if closure>0:_closed_eyes(p,geometry,closure)
    p.end();return result


def _book(painter, elapsed, strength):
    painter.save();painter.setOpacity(strength)
    painter.translate(.435,.635+(1-strength)*.08)
    painter.scale(.55+.45*strength,.55+.45*strength)
    painter.rotate(math.sin(elapsed*1.3)*1.1)
    painter.setPen(QPen(QColor('#3e2a19'),.009,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(QColor('#794a32'))
    cover=QPainterPath(QPointF(-.168,-.073));cover.lineTo(-.02,-.095);cover.lineTo(0,-.075);cover.lineTo(.02,-.095);cover.lineTo(.17,-.073);cover.lineTo(.165,.10);cover.lineTo(0,.112);cover.lineTo(-.17,.10);cover.closeSubpath()
    painter.drawPath(cover)
    painter.setPen(QPen(QColor('#b29865'),.003));painter.setBrush(QColor('#f0dfb6'))
    for side in (-1,1):
        page=QPainterPath(QPointF(side*.012,-.068));page.quadTo(side*.07,-.09,side*.151,-.056);page.lineTo(side*.15,.082);page.quadTo(side*.068,.061,side*.012,.092);page.closeSubpath();painter.drawPath(page)
        painter.setPen(QPen(QColor('#aa9367'),.0025))
        for row in range(5):
            height=-.028+row*.019
            painter.drawLine(QPointF(side*.035,height),QPointF(side*.128,height-.006))
        painter.setPen(QPen(QColor('#b29865'),.003))
    # A single leaf sweeps across the open book every few seconds.
    flip=(elapsed%4.2)/.8
    if flip<1:
        edge=.145*math.cos(flip*math.pi)
        turn=QPainterPath(QPointF(0,-.067));turn.quadTo(edge*.5,-.108,edge,-.056);turn.lineTo(edge,.082);turn.quadTo(edge*.5,.055,0,.092);turn.closeSubpath()
        painter.setBrush(QColor('#fff0c9'));painter.drawPath(turn)
    painter.setPen(QPen(QColor('#5b3626'),.004));painter.drawLine(QPointF(0,-.072),QPointF(0,.10))
    painter.restore()


def action_frame(library, pose):
    """Return one transparent 256px articulated frame, retaining the face/hair."""
    action=pose.action
    from .pet_life import SCENES
    if action in SCENES and getattr(library,'scenes',None):
        from .scene_art import scene_frame
        return scene_frame(library,pose)
    source='walk' if action in ('leave','return') else 'working' if action in ('cast','avada') else 'thinking' if action=='reading' else 'idle'
    frames=library.frames.get(source,library.frames['idle'])
    index=pose.frame%len(frames)
    closed = action == 'sleep' or action == 'wake' and pose.progress < .65 or action == 'yawn' and .22 < pose.progress < .78
    if closed:
        blink=getattr(library,'features',{}).get('blink_frames',{}).get('idle',[31])
        index=min(len(frames)-1,blink[-1])
    original=frames[index]
    canvas=QImage(original.size(),QImage.Format.Format_ARGB32_Premultiplied);canvas.fill(Qt.GlobalColor.transparent)
    p=QPainter(canvas);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    width,height=canvas.width(),canvas.height();geometry=getattr(library,'geometry',{})
    # A restrained breathing/nodding silhouette preserves the original hair
    # edge. Rotating a hard rectangular head crop would create a neck seam.
    nod=(3.0+math.sin(pose.elapsed*1.4)*1.2)*pose.strength if action=='reading' else 8.0*pose.strength if action in ('sleep','wake') else math.sin(pose.progress*math.pi)*3 if action in ('cast','avada') else 0
    bob=math.sin(pose.elapsed*1.8)*.004*height if action in ('reading','sleep','wake') else 0
    if action in ('leave','return'):
        # Frame-local stride supplements the real widget's travel to screen edge.
        bob=-abs(math.sin(pose.elapsed*8))*.008*height
    body_angle=nod*.4
    p.save();p.translate(width*.48,height*.98+bob);p.rotate(body_angle);p.drawImage(QPointF(-width*.48,-height*.98),original);p.restore()
    p.scale(width,height)
    p.translate(.48,.98+bob/height);p.rotate(body_angle);p.translate(-.48,-.98)
    def face(draw):
        draw()
    if action in ('reading','sleep','wake','yawn','settle'):
        if action=='reading':
            face(lambda:_mouth(p,geometry));_book(p,pose.elapsed,pose.strength)
        elif action=='settle' and pose.previous=='reading':
            face(lambda:_mouth(p,geometry));_book(p,pose.elapsed,pose.strength)
        elif action in ('sleep','wake'):
            face(lambda:_mouth(p,geometry))
            if action=='sleep':
                p.setPen(QColor('#c7d6e3'));font=QFont('Segoe UI');font.setPixelSize(12);p.setFont(font)
                # painter is normalized: use an unscaled pixel text pass below.
        elif action=='yawn':
            face(lambda:_mouth(p,geometry,yawn=math.sin(pose.progress*math.pi)))
    if action in ('cast','avada'):
        tip=geometry.get('wand_tip',[.145,.38]);phase=pose.progress
        strength=math.sin(min(1,max(0,(phase-.15)/.7))*math.pi)
        if strength>0:
            green=action=='avada';color=QColor('#77d56f' if green else '#c4c4ff')
            p.setPen(QPen(color,.006));p.setBrush(Qt.BrushStyle.NoBrush)
            radius=.025+.055*phase
            p.drawEllipse(QPointF(tip[0],tip[1]),radius*strength,radius*strength)
            for n in range(7):
                angle=n*math.pi*2/7+pose.elapsed*1.8
                length=(.035+.025*math.sin(n+pose.elapsed*4))*strength
                end=QPointF(tip[0]+math.cos(angle)*length,tip[1]+math.sin(angle)*length)
                p.drawLine(QPointF(tip[0],tip[1]),end)
            if green and .32<phase<.76:
                bolt=QPainterPath(QPointF(tip[0],tip[1]));bolt.lineTo(max(.015,tip[0]-.09),tip[1]-.05);bolt.lineTo(tip[0]-.035,tip[1]-.07);bolt.lineTo(max(.015,tip[0]-.12),tip[1]-.13)
                p.setPen(QPen(color,.01,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.drawPath(bolt)
    p.resetTransform()
    if action=='sleep':
        p.setPen(QColor('#b6c5d5'));font=QFont('Segoe UI');font.setPixelSize(max(7,round(width*.044)));p.setFont(font)
        lift=(pose.elapsed%2.5)/2.5
        p.setOpacity(1-lift*.65);p.drawText(QPointF(width*(.67+lift*.025),height*(.22-lift*.07)),'z');p.setOpacity(1)
    if action=='avada' and .25<pose.progress<.78:
        font=QFont('Segoe UI');font.setPixelSize(max(7,round(width*.037)));p.setFont(font)
        p.setPen(QColor('#b5eeb2'))
        p.drawText(QRectF(width*.16,height*.95,width*.77,height*.04),Qt.AlignmentFlag.AlignCenter,'«Авада Кедавра»')
    p.end()
    return canvas
