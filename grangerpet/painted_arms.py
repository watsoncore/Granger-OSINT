"""Painted pose textures, with a small CPU skinning mesh and rigid hand anchors.

The sleeve shapes, creases, cuffs and hands come from archived pose drawings.
No character face or guest asset is read here. Meshes and images are bounded
and prepared once; no timers, network, GPU context or generated runtime art.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from PySide6.QtCore import QPointF,QRectF
from PySide6.QtGui import QImage,QPainter,QPainterPath,QTransform
from .scene_pose import arm_points


def distance_segment(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
    t=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0.
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)


def bone_map(p,a,b,c,d):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy) or 1.
    ex,ey=d[0]-c[0],d[1]-c[1];target=math.hypot(ex,ey) or 1.
    along=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(length*length)
    across=((p[0]-a[0])*(-dy)+(p[1]-a[1])*dx)/length
    return c[0]+along*ex-across*ey/target,c[1]+along*ey+across*ex/target


def triangle_transform(source,target):
    (x,y),(a,b),(c,d)=source;(u,v),(e,f),(g,h)=target
    a-=x;b-=y;c-=x;d-=y;e-=u;f-=v;g-=u;h-=v
    determinant=a*d-c*b
    if abs(determinant)<1e-8:return None
    xx=(e*d-g*b)/determinant;xy=(f*d-h*b)/determinant
    yx=(g*a-e*c)/determinant;yy=(h*a-f*c)/determinant
    return QTransform(xx,xy,yx,yy,u-xx*x-yx*y,v-xy*x-yy*y)


class ArmDrawing:
    def __init__(self,directory,name,side,spec):
        self.bones=[tuple(p) for p in spec['bones']]
        self.sleeve=QImage(str(directory/f'{name}-{side}-sleeve.png'))
        self.hand=QImage(str(directory/f'{name}-{side}-hand.png'))
        if self.sleeve.isNull() or self.hand.isNull():raise ValueError('Missing painted Hermione arm: '+name+'/'+side)
        self.rect=spec['sleeve_rect'];self.hand_rect=spec['hand_rect'];self.mesh=[]
        x,y,w,h=self.rect;columns=4;rows=6
        vertices=[(x+w*i/columns,y+h*j/rows) for j in range(rows+1) for i in range(columns+1)]
        s,e,hand=self.bones;weights=[]
        guide=None
        if spec.get('forearm_guide'):
            guide=QPainterPath(QPointF(*spec['forearm_guide'][0]))
            for point in spec['forearm_guide'][1:]:guide.lineTo(*point)
            guide.closeSubpath()
        for point in vertices:
            upper=distance_segment(point,s,e);lower=distance_segment(point,e,hand)
            weight=upper/(upper+lower) if upper+lower>1e-6 else .5
            weights.append(1. if guide is not None and guide.contains(QPointF(*point)) else weight)
        self.vertices=vertices;self.weights=weights
        for j in range(rows):
            for i in range(columns):
                k=j*(columns+1)+i
                for ids in ((k,k+1,k+columns+1),(k+1,k+columns+2,k+columns+1)):
                    self.mesh.append(ids)

    def mapped_vertices(self,bones):
        s,e,w=self.bones;ts,te,tw=bones;result=[]
        for p,weight in zip(self.vertices,self.weights):
            first=bone_map(p,s,e,ts,te);second=bone_map(p,e,w,te,tw)
            result.append((first[0]*(1-weight)+second[0]*weight,first[1]*(1-weight)+second[1]*weight))
        return result

    def draw_sleeve(self,p,bones,*,forearm=False):
        vertices=self.mapped_vertices(bones)
        for ids in self.mesh:
            if forearm and sum(self.weights[i] for i in ids)/3<.45:continue
            source=[self.vertices[i] for i in ids];target=[vertices[i] for i in ids]
            transform=triangle_transform(source,target)
            if transform is None:continue
            clip=QPainterPath(QPointF(*target[0]));clip.lineTo(*target[1]);clip.lineTo(*target[2]);clip.closeSubpath()
            # The texture already has antialiased outer alpha. Antialiasing
            # internal triangle clips leaves translucent cracks between tiles.
            p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing,False)
            p.setClipPath(clip);p.setWorldTransform(transform,True)
            p.drawImage(QPointF(self.rect[0],self.rect[1]),self.sleeve);p.restore()

    def draw_hand(self,p,wrist,angle=0.,*,fingers_only=False,side=-1,mirror=False):
        # Source palm centre is also the prop contact anchor. The source wrist
        # remains attached; only the grouped fingers cross in front of a prop.
        source=self.bones[2];p.save();p.translate(*wrist);p.rotate(angle)
        if mirror:p.scale(-1,1)
        p.translate(-source[0],-source[1])
        if fingers_only:
            x,y,w,h=getattr(self,'front_rect',[-5 if side<0 else -26,-26,31,32])
            p.setClipRect(QRectF(source[0]+x,source[1]+y,w,h))
        p.drawImage(QPointF(self.hand_rect[0],self.hand_rect[1]),self.hand);p.restore()


class PaintedArms:
    def __init__(self,directory:Path):
        self.spec=json.loads((directory/'rig.json').read_text(encoding='utf-8'))
        self.drawings={(name,side):ArmDrawing(directory,name,side,spec[side])
            for name,spec in self.spec.items() for side in ('left','right')}
        self.hands={}
        for name,spec in json.loads((directory/'hands.json').read_text(encoding='utf-8')).items():
            drawing=object.__new__(ArmDrawing);drawing.hand=QImage(str(directory/('hand-'+name+'.png')))
            drawing.hand_rect=spec['rect'];drawing.bones=(None,None,tuple(spec['anchor']))
            drawing.front_rect=spec['front_rect']
            self.hands[name]=drawing

    def drawing(self,actor,side):
        name=getattr(actor,'arm_art_left' if side<0 else 'arm_art_right','') or actor.arm_art
        if name not in self.spec:name='rest'
        return self.drawings[name,'left' if side<0 else 'right']

    def sleeve(self,p,actor,side,*,forearm=False):
        self.drawing(actor,side).draw_sleeve(p,arm_points(actor,side),forearm=forearm)

    def hand(self,p,actor,side,*,fingers_only=False):
        wrist=actor.left if side<0 else actor.right
        angle=actor.hand_angle_left if side<0 else actor.hand_angle_right
        mode=actor.left_hand if side<0 else actor.right_hand
        sleeve=self.drawing(actor,side);elbow=arm_points(actor,side)[1]
        override=mode in ('index','pinch','wand_grip','closed_grip') or (mode=='grip' and not actor.book.visible and not actor.phone)
        if override:
            drawing=self.hands['point' if mode=='index' else 'pinch' if mode=='pinch' else 'wand']
            angle+=math.degrees(math.atan2(elbow[1]-wrist[1],elbow[0]-wrist[0]))-90.
        else:
            drawing=sleeve;source_e,source_w=sleeve.bones[1:]
            angle+=math.degrees(math.atan2(wrist[1]-elbow[1],wrist[0]-elbow[0])-
                math.atan2(source_w[1]-source_e[1],source_w[0]-source_e[0]))
        drawing.draw_hand(p,wrist,angle,fingers_only=fingers_only,side=-1 if override else side,mirror=override and side>0)

    def order(self,actor):
        name=getattr(actor,'arm_art','rest')
        return [-1 if side=='left' else 1 for side in self.spec.get(name,self.spec['rest'])['order']]
