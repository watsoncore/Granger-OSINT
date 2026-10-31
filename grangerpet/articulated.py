"""Joint-driven painter retaining the approved Hermione face, hair and costume.

512px source layers are cached once. Poses are drawn directly at requested
physical resolution with premultiplied alpha; no pre-scaled scene raster.
"""
from __future__ import annotations
import math
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QColor,QFont,QImage,QPainter,QPainterPath,QPen,QPolygonF,QTransform
from .scene_pose import ActorPose,BookPose,ik,rotate,arm_points

INK='#302416';ROBE='#25272a';SKIN='#ffe5c9'


def path(points):
    p=QPainterPath(QPointF(*points[0]))
    for pt in points[1:]:p.lineTo(*pt)
    p.closeSubpath();return p


def pen(p,color=INK,width=3.):
    p.setPen(QPen(QColor(color),width,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))


def image(size):
    im=QImage(size,size,QImage.Format.Format_ARGB32_Premultiplied);im.fill(Qt.GlobalColor.transparent);return im


def sole_points(source,left,right,*,dy=0):
    """True alpha boundaries of each shoe; never use transparent bbox corners."""
    result=[]
    for lo,hi in (left,right):
        points=[]
        for x in range(lo,hi):
            ys=[y for y in range(470,source.height()) if source.pixelColor(x,y).alpha()>32]
            if ys:points.extend((QPointF(x,min(ys)+dy),QPointF(x,max(ys)+dy)))
        result.append(QPolygonF(points))
    return result


def plant_feet(a,soles,*,guest=False):
    if not a.grounded:return
    bounds=[];root=QTransform();root.translate(*a.shift)
    pivot=(246,412) if guest else a.pivot;root.translate(*pivot);root.rotate(a.lean);root.translate(-pivot[0],-pivot[1])
    for i,(sole,angle) in enumerate(zip(soles,(a.leg_left,a.leg_right))):
        if sole.isEmpty():continue
        transform=QTransform(root);hip=((218,410),(276,410))[i] if guest else ((216,412),(275,412))[i]
        transform.translate(*hip);transform.rotate(angle);transform.translate(-hip[0],-hip[1])
        if not guest:
            knee=((220,445),(280,445))[i];ankle=((222,476),(290,476))[i]
            transform.translate(*knee);transform.rotate((a.knee_left,a.knee_right)[i]);transform.translate(-knee[0],-knee[1])
            transform.translate(*ankle);transform.rotate((a.ankle_left,a.ankle_right)[i]);transform.translate(-ankle[0],-ankle[1])
        bounds.append(transform.map(sole).boundingRect().bottom())
    if bounds:a.shift=(a.shift[0],a.shift[1]+497-max(bounds))


class HermioneRig:
    def __init__(self,master:QImage,hair_repair:QImage|None=None,hair_fringe:QImage|None=None,painted_arms=None):
        self.master=master
        self.painted_arms=painted_arms
        self.soles=sole_points(master,(178,244),(260,326))
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
        if hair_fringe is not None and not hair_fringe.isNull():
            # Costume from the master can sit between the hanging curls. Use
            # the clean lower fringe instead of retaining sleeve-colored holes.
            p=QPainter(self.head);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            p.fillRect(QRectF(0,258,512,80),Qt.GlobalColor.white)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.setClipRect(QRectF(0,250,512,88));p.drawImage(0,0,hair_fringe);p.end()
        self.curls=[]
        for rect,root in ((QRectF(60,224,91,105),(133,236)),(QRectF(318,220,139,114),(338,236))):
            layer=image(512);p=QPainter(layer);p.setClipRect(rect);p.drawImage(0,0,self.head);p.end()
            self.curls.append((layer,root))
        p=QPainter(self.head);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        p.fillRect(QRectF(60,242,91,90),Qt.GlobalColor.white);p.fillRect(QRectF(318,242,139,92),Qt.GlobalColor.white);p.end()
        # Original costume and footwear are texture layers, not new silhouettes.
        self.torso=image(512);p=QPainter(self.torso);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen(p,INK,4);p.setBrush(QColor(ROBE))
        robe=QPainterPath(QPointF(177,273));robe.quadTo(160,314,158,365)
        robe.lineTo(146,409);robe.quadTo(167,430,193,433);robe.lineTo(202,414)
        robe.lineTo(272,415);robe.quadTo(306,446,345,413);robe.quadTo(293,369,280,277);robe.closeSubpath();p.drawPath(robe)
        preserve=path([(201,264),(258,249),(277,277),(269,322),(278,415),(200,415),(198,353)])
        preserve=preserve.united(path([(151,380),(300,380),(349,413),(306,437),(270,431),(268,414),(202,414),(192,438),(141,414)]))
        p.setClipPath(preserve);p.drawImage(0,0,master);p.end()
        self.legs=[]
        for pts in ([(191,405),(234,405),(241,503),(176,503),(177,472),(205,458)],
                    [(249,406),(289,406),(305,461),(323,486),(319,506),(267,506),(264,468)]):
            layer=image(512);p=QPainter(layer);p.setClipPath(path(pts));p.drawImage(0,0,master);p.end();self.legs.append(layer)
        self.leg_parts=[]
        for leg in self.legs:
            parts=[]
            for rect in (QRectF(0,419,512,27),QRectF(0,442,512,37),QRectF(0,475,512,37)):
                layer=image(512);p=QPainter(layer);p.setClipRect(rect);p.drawImage(0,0,leg);p.end();parts.append(layer)
            self.leg_parts.append(parts)
        # Iris textures exclude skin/lashes, and stay clipped inside source eyes.
        self.iris=[]
        for rect in ((165,173,27,32),(244,168,29,34)):
            layer=QImage(rect[2],rect[3],QImage.Format.Format_ARGB32_Premultiplied);layer.fill(Qt.GlobalColor.transparent)
            p=QPainter(layer);p.setRenderHint(QPainter.RenderHint.Antialiasing)
            clip=QPainterPath();clip.addEllipse(QRectF(1,0,rect[2]-2,rect[3]))
            p.setClipPath(clip);p.drawImage(QPointF(-rect[0],-rect[1]),master);p.end();self.iris.append(layer)

    def draw(self,p:QPainter,a:ActorPose,*,debug=False,draw_hands=True,hand_base=False,draw_props=True):
        plant_feet(a,self.soles)
        p.save();p.translate(*a.shift);p.translate(*a.pivot);p.rotate(a.lean);p.translate(-a.pivot[0],-a.pivot[1])
        # Feet and lower legs attach to the same hip parent, behind the robe.
        for parts,pivot,knee,ankle,angle,bend,foot_angle in zip(self.leg_parts,((216,412),(275,412)),((220,445),(280,445)),
                ((222,476),(290,476)),(a.leg_left,a.leg_right),(a.knee_left,a.knee_right),(a.ankle_left,a.ankle_right)):
            p.save();p.translate(*pivot);p.rotate(angle);p.translate(-pivot[0],-pivot[1])
            p.drawImage(0,0,parts[0]);p.translate(*knee);p.rotate(bend);p.translate(-knee[0],-knee[1]);p.drawImage(0,0,parts[1])
            p.translate(*ankle);p.rotate(foot_angle);p.translate(-ankle[0],-ankle[1]);p.drawImage(0,0,parts[2])
            p.restore()
        # A continuous neck and torso underlap eliminate collar/head gaps.
        pen(p,INK,3);p.setBrush(QColor(SKIN));p.drawRoundedRect(QRectF(205,239,55,62),12,12)
        p.save();p.translate(229+a.turn*5,267);p.scale(1-.025*abs(a.turn),1);p.translate(-229,-267)
        p.drawImage(0,0,self.torso);p.restore()
        shoulders=[]
        hands=[]
        order=self.painted_arms.order(a) if self.painted_arms else (-1,1)
        for side in order:
            mode=a.left_hand if side<0 else a.right_hand
            shoulder,elbow,wrist=arm_points(a,side);shoulders.append(shoulder)
            if self.painted_arms:self.painted_arms.sleeve(p,a,side)
            else:self.arm(p,shoulder,elbow,wrist)
            hands.append((wrist,mode,side,a.hand_angle_left if side<0 else a.hand_angle_right))
        # Head is independently articulated, but hair roots share its transform.
        p.save();p.translate(229+a.turn*5,252+a.head_drop);p.rotate(a.head);p.translate(-229,-252)
        p.drawImage(0,0,self.head)
        for index,(curl,root) in enumerate(self.curls):
            p.save();p.translate(*root);p.rotate(a.hair*(1 if index==0 else -.8));p.translate(-root[0],-root[1]);p.drawImage(0,0,curl);p.restore()
        self.face(p,a);p.restore()
        held=a.book.visible or a.phone or a.wand
        if self.painted_arms:
            if draw_hands or held or hand_base:
                for side in order:self.painted_arms.hand(p,a,side)
            for side in order:
                wrist=a.left if side<0 else a.right
                elbow=arm_points(a,side)[1]
                if wrist[1]<elbow[1]+5:self.painted_arms.sleeve(p,a,side,forearm=True)
        if draw_props:
            if a.book.visible:self.book(p,a.book)
            if a.phone:self.phone(p,a)
            if a.wand:self.wand(p,a)
        if draw_hands:
            for wrist,mode,side,angle in hands:
                if self.painted_arms:
                    if held and draw_props:self.painted_arms.hand(p,a,side,fingers_only=True)
                else:self.hand(p,wrist,mode,side,angle)
        if a.book.visible and a.book.pocket:
            # The actual robe front occludes book and hand entering its pocket.
            # This is a garment depth layer, using the unchanged torso artwork.
            p.save();p.translate(229+a.turn*5,267);p.scale(1-.025*abs(a.turn),1);p.translate(-229,-267)
            p.setClipPath(path([(273,a.book.pocket_lip),(335,a.book.pocket_lip),(349,416),(306,437),(272,415)]))
            p.drawImage(0,0,self.torso);p.restore()
        if a.hearts:
            p.save();p.setOpacity(a.hearts);p.translate(330,185);p.scale(12,12)
            pen(p,'#b27676',.11);p.setBrush(QColor('#e4a1a1'))
            heart=QPainterPath(QPointF(0,.65));heart.cubicTo(-1,0,-.6,-.65,0,-.17)
            heart.cubicTo(.6,-.65,1,0,0,.65);p.drawPath(heart);p.restore()
        if a.sleeping:
            p.save();p.setOpacity(1-a.sleep_lift*.7);p.setPen(QColor('#b6c5d5'))
            font=QFont('Segoe UI');font.setPixelSize(22);p.setFont(font);p.drawText(QPointF(355+a.sleep_lift*6,113-a.sleep_lift*25),'z');p.restore()
        if a.spell_text:
            font=QFont('Segoe UI');font.setPixelSize(14);p.setFont(font);p.setPen(QColor('#b5eeb2'))
            p.drawText(QRectF(6,469,175,34),Qt.AlignmentFlag.AlignCenter,a.spell_text)
        if debug:
            pen(p,'#00ccee',1)
            for side in order:
                shoulder,elbow,wrist=arm_points(a,side)
                p.drawLine(QPointF(*shoulder),QPointF(*elbow));p.drawLine(QPointF(*elbow),QPointF(*wrist))
        p.restore()

    @staticmethod
    def arm(p,s,e,w):
        # Authored tapered sleeve pieces are united BEFORE outlining. A folded
        # single envelope produced hollow loops; a union cannot cancel itself.
        dx,dy=w[0]-e[0],w[1]-e[1];ln=math.hypot(dx,dy) or 1;nx,ny=-dy/ln,dx/ln
        ux,uy=e[0]-s[0],e[1]-s[1];ul=math.hypot(ux,uy) or 1;un=(-uy/ul,ux/ul)
        upper=path([(s[0]+un[0]*17,s[1]+un[1]*17),(e[0]+un[0]*16,e[1]+un[1]*16),
            (e[0]-un[0]*16,e[1]-un[1]*16),(s[0]-un[0]*17,s[1]-un[1]*17)])
        lower=path([(e[0]+nx*16,e[1]+ny*16),(w[0]+nx*22,w[1]+ny*22),
            (w[0]-nx*22,w[1]-ny*22),(e[0]-nx*16,e[1]-ny*16)])
        joint=QPainterPath();joint.addEllipse(QRectF(e[0]-16,e[1]-16,32,32))
        contour=upper.united(lower).united(joint);pen(p,INK,3.5);p.setBrush(QColor(ROBE));p.drawPath(contour)
        pen(p,'#403b32',1.8);p.drawLine(QPointF(w[0]+nx*20,w[1]+ny*20),QPointF(w[0]-nx*20,w[1]-ny*20))

    @staticmethod
    def hand(p,w,mode,side,angle=0.):
        p.save();p.translate(*w);p.rotate(angle);p.scale(-side,1)
        pen(p,INK,2.6);p.setBrush(QColor(SKIN))
        hand=QPainterPath(QPointF(-10,8));hand.quadTo(-15,2,-10,-4)
        if mode in ('cover','palm'):
            hand.lineTo(-13,-20);hand.quadTo(-10,-27,-7,-20);hand.lineTo(-6,-8)
            hand.lineTo(-5,-26);hand.quadTo(-1,-31,2,-25);hand.lineTo(3,-9)
            hand.lineTo(5,-25);hand.quadTo(9,-29,11,-22);hand.lineTo(11,-4)
            hand.quadTo(18,-14,20,-7);hand.quadTo(18,5,9,10)
        elif mode=='pinch':
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
        if b.pocket:p.setClipRect(QRectF(0,0,512,b.pocket_lip))
        p.translate(*b.center);p.rotate(b.angle);p.scale(b.scale,b.scale);lw,rw=b.left_width,b.right_width
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

    @staticmethod
    def phone(p,a):
        p.save()
        if a.pocket:p.setClipRect(QRectF(0,0,512,399))
        p.translate(*a.phone_center);p.rotate(a.phone_angle)
        pen(p,'#493b35',3);p.setBrush(QColor('#676176'));p.drawRoundedRect(QRectF(-32,-60,64,104),8,8)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#f7e7d8'));p.drawRoundedRect(QRectF(-26,-50,52,82),3,3)
        p.setPen(QColor('#65505c'));font=QFont('Segoe UI');font.setPixelSize(13);p.setFont(font)
        p.drawText(QRectF(-25,-48,50,18),Qt.AlignmentFlag.AlignCenter,'Solvnox')
        for row in range(a.phone_lines):
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#ceb9c1' if row%2 else '#dbcbb1'))
            p.drawRoundedRect(QRectF(-20+(row%2)*5,-24+row*13,35,8),3,3)
        pen(p,'#a694a1',1)
        for row in range(2):
            for col in range(5):p.drawPoint(QPointF(-17+col*8,19+row*6))
        p.restore()

    @staticmethod
    def wand(p,a):
        p.save()
        if a.pocket:p.setClipRect(QRectF(0,0,512,399))
        x,y=a.left;tip=rotate((0.,-106.),a.wand_angle+90)
        tip=(x+tip[0],y+tip[1]);pen(p,'#352512',6)
        p.drawLine(QPointF(x,y+9),QPointF(*tip));pen(p,'#b68d47',2)
        p.drawLine(QPointF(x-1,y+7),QPointF(tip[0]-1,tip[1]+1))
        if a.magic:
            pen(p,a.magic_color,2);p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(*tip),a.magic*12,a.magic*12)
            for i in range(7):
                angle=i*math.tau/7;r=10+15*a.magic
                p.drawLine(QPointF(tip[0]+math.cos(angle)*r,tip[1]+math.sin(angle)*r),
                    QPointF(tip[0]+math.cos(angle)*(r+7),tip[1]+math.sin(angle)*(r+7)))
        p.restore()


def render_actor(library,a,size=256,dpr=1.,*,debug=False,props=True):
    art=library.scenes
    if not hasattr(art,'hermione_rig'):art.hermione_rig=HermioneRig(art.layers['base'],art.hair_repair,art.hair_fringe,getattr(art,'painted_arms',None))
    canvas=image(max(1,round(size*dpr)));p=QPainter(canvas)
    p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(canvas.width()/512,canvas.height()/512);art.hermione_rig.draw(p,a,debug=debug,draw_props=props);p.end()
    canvas.setDevicePixelRatio(dpr);return canvas


def render_reading(library,life,size=256,dpr=1.,*,debug=False):
    from .scene_pose import reading_pose
    a=reading_pose(life.progress,life.elapsed,getattr(life,'variant',0))
    return render_actor(library,a,size,dpr,debug=debug)


def render_action(library,life,size=256,dpr=1.):
    from .scene_pose import action_pose
    if life.cameo:
        from .conversation_pose import conversation_pose
        a=conversation_pose(life).hero
    else:a=action_pose(life.action,life.progress,life.elapsed,getattr(life,'variant',0))
    return render_actor(library,a,size,dpr)
