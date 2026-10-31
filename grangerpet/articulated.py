"""Joint-driven painter retaining the approved Hermione face, hair and costume.

512px source layers are cached once. Poses are drawn directly at requested
physical resolution with premultiplied alpha; no pre-scaled scene raster.
"""
from __future__ import annotations
import math
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QColor,QImage,QPainter,QPainterPath,QPen,QTransform
from .scene_pose import ActorPose,BookPose,ik,rotate

INK='#302416';ROBE='#25272a';SKIN='#ffe5c9'


def path(points):
    p=QPainterPath(QPointF(*points[0]))
    for pt in points[1:]:p.lineTo(*pt)
    p.closeSubpath();return p


def pen(p,color=INK,width=3.):
    p.setPen(QPen(QColor(color),width,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))


def image(size):
    im=QImage(size,size,QImage.Format.Format_ARGB32_Premultiplied);im.fill(Qt.GlobalColor.transparent);return im


class HermioneRig:
    def __init__(self,master:QImage,hair_repair:QImage|None=None):
        self.master=master
        self.head=image(512)
        p=QPainter(self.head);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Preserve the full external upper/right hair contour; exclude costume.
        mask=path([(0,0),(512,0),(512,335),(290,335),(275,263),(231,252),(192,244),(155,277),(155,335),(0,335)])
        p.setClipPath(mask);p.drawImage(0,0,master);p.setClipping(False)
        # The original wand crosses this curl. Replace that small editable curl
        # with matched native paths; never erase the wand with a skin/hair smear.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        p.fillRect(QRectF(0,187,136,153),Qt.GlobalColor.white)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        pen(p,INK,4);p.setBrush(QColor('#846f49'))
        curl=QPainterPath(QPointF(127,181));curl.cubicTo(116,192,87,200,92,219)
        curl.cubicTo(99,235,76,243,81,260);curl.cubicTo(90,275,67,288,78,300)
        curl.cubicTo(91,318,113,299,134,303);curl.cubicTo(127,286,148,276,137,260)
        curl.cubicTo(128,247,148,237,136,222);curl.cubicTo(130,210,142,194,127,181);p.drawPath(curl)
        pen(p,'#d3bd8e',3);p.setBrush(Qt.BrushStyle.NoBrush)
        strand=QPainterPath(QPointF(116,195));strand.cubicTo(88,215,118,218,103,237)
        strand.cubicTo(88,255,114,259,98,279);strand.cubicTo(87,292,95,301,104,302);p.drawPath(strand)
        pen(p,'#4d3a24',2)
        strand=QPainterPath(QPointF(130,227));strand.cubicTo(114,249,139,254,121,274)
        strand.cubicTo(111,286,125,293,128,297);p.drawPath(strand);p.end()
        if hair_repair is not None and not hair_repair.isNull():
            # Restore the source first; clear only the occluded left curl, then
            # overlap the fitted repair inside intact hair. Face stays original.
            self.head=image(512);p=QPainter(self.head);p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setClipPath(mask);p.drawImage(0,0,master);p.setClipping(False)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            p.fillRect(QRectF(0,190,139,145),Qt.GlobalColor.white)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.drawImage(0,0,hair_repair);p.end()
        self.curls=[]
        for rect,root in ((QRectF(60,224,91,105),(133,236)),(QRectF(318,220,139,114),(338,236))):
            layer=image(512);p=QPainter(layer);p.setClipRect(rect);p.drawImage(0,0,self.head);p.end()
            self.curls.append((layer,root))
        p=QPainter(self.head);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        p.fillRect(QRectF(60,242,91,90),Qt.GlobalColor.white);p.fillRect(QRectF(318,242,139,92),Qt.GlobalColor.white);p.end()
        # Original costume and footwear are texture layers, not new silhouettes.
        self.torso=image(512);p=QPainter(self.torso);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipPath(path([(178,270),(207,259),(258,249),(280,282),(287,320),(301,379),
            (346,414),(305,433),(272,432),(269,416),(201,416),(193,434),(169,427),
            (145,410),(158,369),(164,332),(171,300)]));p.drawImage(0,0,master);p.end()
        self.legs=[]
        for pts in ([(191,405),(234,405),(241,503),(176,503),(177,472),(205,458)],
                    [(249,406),(289,406),(305,461),(323,486),(319,506),(267,506),(264,468)]):
            layer=image(512);p=QPainter(layer);p.setClipPath(path(pts));p.drawImage(0,0,master);p.end();self.legs.append(layer)
        # Iris textures exclude skin/lashes, and stay clipped inside source eyes.
        self.iris=[]
        for rect in ((165,173,27,32),(244,168,29,34)):
            layer=QImage(rect[2],rect[3],QImage.Format.Format_ARGB32_Premultiplied);layer.fill(Qt.GlobalColor.transparent)
            p=QPainter(layer);p.setRenderHint(QPainter.RenderHint.Antialiasing)
            clip=QPainterPath();clip.addEllipse(QRectF(1,0,rect[2]-2,rect[3]))
            p.setClipPath(clip);p.drawImage(QPointF(-rect[0],-rect[1]),master);p.end();self.iris.append(layer)

    def draw(self,p:QPainter,a:ActorPose,*,debug=False):
        p.save();p.translate(*a.shift);p.translate(236,412);p.rotate(a.lean);p.translate(-236,-412)
        # Feet and lower legs attach to the same hip parent, behind the robe.
        for leg,pivot,angle in zip(self.legs,((216,407),(275,407)),(a.leg_left,a.leg_right)):
            p.save();p.translate(*pivot);p.rotate(angle);p.translate(-pivot[0],-pivot[1])
            p.drawImage(0,0,leg)
            p.restore()
        # A continuous neck and torso underlap eliminate collar/head gaps.
        pen(p,INK,3);p.setBrush(QColor(SKIN));p.drawRoundedRect(QRectF(205,239,55,62),12,12)
        p.drawImage(0,0,self.torso)
        shoulders=((171.,293.+a.left_lift),(281.,294.+a.right_lift))
        hands=[]
        for side,shoulder,target,mode in ((-1,shoulders[0],a.left,a.left_hand),(1,shoulders[1],a.right,a.right_hand)):
            elbow,wrist=ik(shoulder,target,side);self.arm(p,shoulder,elbow,wrist);hands.append((wrist,mode,side))
        # Head is independently articulated, but hair roots share its transform.
        p.save();p.translate(229,252+a.head_drop);p.rotate(a.head);p.translate(-229,-252)
        p.drawImage(0,0,self.head)
        for index,(curl,root) in enumerate(self.curls):
            p.save();p.translate(*root);p.rotate(a.hair*(1 if index==0 else -.8));p.translate(-root[0],-root[1]);p.drawImage(0,0,curl);p.restore()
        self.face(p,a);p.restore()
        if a.book.visible:self.book(p,a.book)
        for wrist,mode,side in hands:self.hand(p,wrist,mode,side)
        if debug:
            pen(p,'#00ccee',1)
            for shoulder,(wrist,_,_) in zip(shoulders,hands):
                elbow,_=ik(shoulder,wrist,-1 if shoulder==shoulders[0] else 1)
                p.drawLine(QPointF(*shoulder),QPointF(*elbow));p.drawLine(QPointF(*elbow),QPointF(*wrist))
        p.restore()

    @staticmethod
    def arm(p,s,e,w):
        # A single closed sleeve envelope, with a rounded elbow and real cuff.
        dx,dy=w[0]-e[0],w[1]-e[1];ln=math.hypot(dx,dy) or 1;nx,ny=-dy/ln,dx/ln
        dx0,dy0=e[0]-s[0],e[1]-s[1];ln0=math.hypot(dx0,dy0) or 1;n0=(-dy0/ln0,dx0/ln0)
        shape=QPainterPath(QPointF(s[0]+n0[0]*19,s[1]+n0[1]*19))
        shape.quadTo(e[0]+n0[0]*24,e[1]+n0[1]*24,e[0]+nx*23,e[1]+ny*23)
        shape.lineTo(w[0]+nx*18,w[1]+ny*18);shape.lineTo(w[0]-nx*18,w[1]-ny*18)
        shape.quadTo(e[0]-nx*22,e[1]-ny*22,e[0]-n0[0]*18,e[1]-n0[1]*18)
        shape.lineTo(s[0]-n0[0]*19,s[1]-n0[1]*19);shape.closeSubpath()
        pen(p,INK,3.5);p.setBrush(QColor(ROBE));p.drawPath(shape)
        pen(p,'#403b32',2);p.drawLine(QPointF(w[0]+nx*16,w[1]+ny*16),QPointF(w[0]-nx*16,w[1]-ny*16))

    @staticmethod
    def hand(p,w,mode,side):
        p.save();p.translate(*w);p.scale(-side,1)
        pen(p,INK,2.6);p.setBrush(QColor(SKIN))
        hand=QPainterPath(QPointF(-10,8));hand.quadTo(-15,2,-10,-4)
        if mode=='pinch':
            hand.cubicTo(-14,-12,-8,-16,-4,-10);hand.lineTo(4,-4)
            hand.quadTo(12,-13,14,-8);hand.quadTo(16,-3,9,3)
        elif mode=='index':
            hand.lineTo(-8,-23);hand.quadTo(-2,-29,1,-22);hand.lineTo(3,-9)
            hand.quadTo(14,-14,13,-4)
        elif mode=='grip':
            hand.quadTo(-16,-15,-10,-16);hand.quadTo(-5,-17,-3,-8)
            hand.quadTo(13,-11,14,-3);hand.quadTo(13,5,6,8)
        else:
            hand.quadTo(-8,-11,-3,-8);hand.quadTo(2,-13,5,-6)
            hand.quadTo(12,-10,13,-3);hand.quadTo(17,2,8,9)
        hand.quadTo(0,13,-10,8);p.drawPath(hand)
        pen(p,'#bb8d6b',1.2);p.drawLine(QPointF(2,0),QPointF(9,0));p.restore()

    def face(self,p,a):
        # Exact source eye outlines remain; iris movement stays inside white.
        eyes=[[(158,180),(171,173),(188,175),(198,185),(193,202),(174,207),(163,200)],
              [(239,176),(251,170),(269,170),(281,180),(276,199),(254,202),(243,195)]]
        for i,pts in enumerate(eyes):
            clip=path(pts);p.save();p.setClipPath(clip)
            p.fillPath(clip,QColor('#fffaf0'));x,y=(165,173) if i==0 else (244,168)
            p.drawImage(QPointF(x+a.gaze[0],y+a.gaze[1]),self.iris[i]);p.restore()
        if a.blink>.05:
            for i,pts in enumerate(eyes):
                p.save();p.setOpacity(a.blink);p.setBrush(QColor(SKIN));p.setPen(Qt.PenStyle.NoPen)
                p.drawPath(path(pts));pen(p,'#4c3222',3)
                x,y=(158,191) if i==0 else (239,186)
                lid=QPainterPath(QPointF(x,y));lid.quadTo(x+19,y+10,x+39,y-1);p.drawPath(lid);p.restore()
        # A source-colored patch is local to the mouth, never the jaw/hair edge.
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(SKIN));p.drawEllipse(QRectF(208,215,30,28))
        pen(p,'#68422b',2.2);p.setBrush(QColor('#c97d68'))
        if a.mouth=='open':p.drawEllipse(QRectF(217,221,12,16))
        elif a.mouth=='smile':
            line=QPainterPath(QPointF(214,225));line.quadTo(223,236,232,224);p.setBrush(Qt.BrushStyle.NoBrush);p.drawPath(line)
        elif a.mouth=='pout':
            p.drawLine(QPointF(214,229),QPointF(229,227))
        else:p.drawLine(QPointF(217,228),QPointF(230,227))
        if a.blush:
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(223,128,115,round(105*a.blush)))
            p.drawEllipse(QRectF(156,208,27,9));p.drawEllipse(QRectF(258,202,27,9))
        if a.brow:
            pen(p,'#4f3925',2.7)
            p.drawLine(QPointF(160,167-4*a.brow),QPointF(186,168+5*a.brow))
            p.drawLine(QPointF(241,164+5*a.brow),QPointF(269,158-3*a.brow))

    @staticmethod
    def book(p,b:BookPose):
        p.save()
        if b.pocket:p.setClipRect(QRectF(0,0,512,399))
        p.translate(*b.center);p.rotate(b.angle);lw,rw=b.left_width,b.right_width
        pen(p,'#3e2a19',3);p.setBrush(QColor('#794a32'))
        p.drawPath(path([(-lw-4,-43),(-4,-48),(rw+4,-43),(rw+4,48),(0,54),(-lw-4,48)]))
        if b.opening>.08:
            for side,width in ((-1,lw),(1,rw)):
                pen(p,'#b29865',1.2);p.setBrush(QColor('#f0dfb6'))
                leaf=QPainterPath(QPointF(side*3,-37));leaf.quadTo(side*width*.5,-48,side*(width-3),-36)
                leaf.lineTo(side*(width-3),40);leaf.quadTo(side*width*.5,34,side*3,47);leaf.closeSubpath();p.drawPath(leaf)
                pen(p,'#ae986f',1.1)
                for y in range(-22,34,11):p.drawLine(QPointF(side*13,y),QPointF(side*(width-11),y-3))
            if b.page>=0:
                edge=75*math.cos(b.page*math.pi);lift=29*math.sin(b.page*math.pi)
                pen(p,'#a89163',1.2);p.setBrush(QColor('#fff0c9'))
                page=QPainterPath(QPointF(1,-36));page.cubicTo(edge*.3,-40-lift,edge*.8,-39-lift,edge,-33-lift)
                page.lineTo(edge,39-lift*.45);page.quadTo(edge*.5,29-lift*.3,1,46);page.closeSubpath();p.drawPath(page)
                pen(p,'#c7b38b',1)
                for y in (-18,-5,8,21):
                    line=QPainterPath(QPointF(7 if edge>0 else -7,y));line.quadTo(edge*.5,y-lift*.4,edge*.85,y-lift*.7);p.drawPath(line)
        else:
            pen(p,'#bd934f',2);p.drawRoundedRect(QRectF(10,-31,rw-19,63),3,3)
            p.drawLine(QPointF(20,-7),QPointF(rw-17,-7));p.drawLine(QPointF(20,1),QPointF(rw-17,1))
        pen(p,'#5b3626',2);p.drawLine(QPointF(0,-43),QPointF(0,50));p.restore()


def render_reading(library,life,size=256,dpr=1.,*,debug=False):
    from .scene_pose import reading_pose
    art=library.scenes
    if not hasattr(art,'hermione_rig'):art.hermione_rig=HermioneRig(art.layers['base'],art.hair_repair)
    a=reading_pose(life.progress,life.elapsed,getattr(life,'variant',0))
    canvas=image(max(1,round(size*dpr)));p=QPainter(canvas)
    p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(canvas.width()/512,canvas.height()/512);art.hermione_rig.draw(p,a,debug=debug);p.end()
    canvas.setDevicePixelRatio(dpr);return canvas
