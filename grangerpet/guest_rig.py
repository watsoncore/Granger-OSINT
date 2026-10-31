"""Independent guest limbs and faces, reusing the approved native ink palette."""
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QColor,QImage,QPainter,QPainterPath
from .articulated import HermioneRig,image,path,pen,SKIN,sole_points,plant_feet
from .scene_pose import ik,arm_points


class GuestRig:
    def __init__(self,master,name):
        self.master=master;self.name=name
        self.soles=sole_points(master,(170,247),(247,342),dy=-2)
        self.head=image(512);p=QPainter(self.head);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # A rectangular 256px crop included shoulder/lapel corners, which
        # detached under head rotation. Follow the actual jaw/hair boundary.
        if name=='ron':
            p.setClipPath(path([(0,0),(512,0),(512,239),(335,239),(321,245),(304,240),(288,244),
                (273,239),(250,240),(237,244),(220,248),(202,244),(180,237),(0,237)]))
        else:p.setClipRect(QRectF(0,0,512,239))
        p.drawImage(0,0,master);p.end()
        self.torso=image(512);p=QPainter(self.torso);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen(p,width=3.5);p.setBrush(QColor('#25272a'))
        coat=QPainterPath();coat.moveTo(204,259);coat.quadTo(186,296,190,350)
        coat.lineTo(169,421);coat.quadTo(191,436,215,430);coat.lineTo(226,415)
        coat.lineTo(271,415);coat.quadTo(294,449,338,426);coat.quadTo(297,350,300,276);coat.closeSubpath();p.drawPath(coat)
        # Preserve collar/vest and hem, excluding BOTH original posed sleeves.
        vest=path([(212,254),(257,242),(297,262),(277,314),(283,350),(293,414),
            (226,418),(201,412),(201,350),(207,298)])
        hem=path([(176,377),(305,377),(340,427),(292,449),(269,417),(224,419),(212,439),(166,423)])
        p.setClipPath(vest.united(hem));p.drawImage(0,0,master);p.end()
        self.legs=[]
        for rect in (QRectF(170,401,77,105),QRectF(247,401,90,106)):
            layer=image(512);p=QPainter(layer);p.setClipRect(rect);p.drawImage(0,0,master);p.end();self.legs.append(layer)
        self.eyes={'draco':[(174,154,41,42),(247,167,52,42)],
            'ron':[(167,163,43,43),(239,171,53,47)],'harry':[(195,175,42,40),(269,166,48,43)]}[name]
        self.mouth={'draco':(227,220),'ron':(225,230),'harry':(249,223)}[name]

    def draw(self,p,a,*,draw_hands=True,layers=None):
        plant_feet(a,self.soles,guest=True)
        layers={'legs','torso','arms','head','hands'} if layers is None else set(layers)
        p.save();p.translate(*a.shift);p.translate(246,412);p.rotate(a.lean);p.translate(-246,-412)
        for leg,pivot,angle in zip(self.legs,((218,410),(276,410)),(a.leg_left,a.leg_right)):
            p.save();p.translate(*pivot);p.rotate(angle);p.translate(-pivot[0],-pivot[1])
            if 'legs' in layers:p.drawImage(0,-2,leg)
            p.restore()
        p.save();p.setOpacity(1 if 'torso' in layers else 0)
        pen(p,width=3);p.setBrush(QColor(SKIN));p.drawRoundedRect(QRectF(215,229,55,65),9,9)
        p.translate(246+a.turn*5,265);p.scale(1-.025*abs(a.turn),1);p.translate(-246,-265)
        p.drawImage(0,0,self.torso);p.restore();hands=[]
        for side,mode in ((-1,a.left_hand),(1,a.right_hand)):
            s,elbow,wrist=arm_points(a,side,guest=True)
            if 'arms' in layers:HermioneRig.arm(p,s,elbow,wrist)
            hands.append((wrist,mode,side,a.hand_angle_left if side<0 else a.hand_angle_right))
        p.save();p.setOpacity(1 if 'head' in layers else 0)
        p.translate(246+a.turn*5,250+a.head_drop);p.rotate(a.head);p.translate(-246,-250);p.drawImage(0,0,self.head)
        for x,y,w,h in self.eyes:
            p.save();clip=QPainterPath();clip.addEllipse(QRectF(x+6,y+7,w-12,h-13));p.setClipPath(clip)
            p.fillPath(clip,QColor('#fffaf0'));p.drawImage(QPointF(a.gaze[0],a.gaze[1]),self.master);p.restore()
        if a.blink>.05:
            from .pet_actions import _closed_eyes
            p.save();p.scale(512,512);_closed_eyes(p,{'eye_rects':[[x/512,y/512,w/512,h/512] for x,y,w,h in self.eyes]},a.blink);p.restore()
        x,y=self.mouth;p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(SKIN));p.drawEllipse(QRectF(x-17,y-18,34,35))
        pen(p,'#68422b',2.2)
        if a.mouth=='open':p.setBrush(QColor('#c97d68'));p.drawEllipse(QRectF(x-6,y-7,12,16))
        elif a.mouth=='smile':
            p.setBrush(Qt.BrushStyle.NoBrush);line=QPainterPath(QPointF(x-8,y));line.quadTo(x,y+8,x+9,y-2);p.drawPath(line)
        else:p.drawLine(QPointF(x-7,y+2),QPointF(x+7,y+1))
        if a.brow:
            pen(p,'#4f3925',2)
            for i,(x,y,w,h) in enumerate(self.eyes):p.drawLine(QPointF(x+4,y-4-a.brow*4),QPointF(x+w-5,y-4+a.brow*5))
        p.restore()
        if draw_hands and 'hands' in layers:
            for args in hands:HermioneRig.hand(p,*args)
        p.restore()


def draw_note(p,scene):
    if scene.note is None:return
    p.save()
    if scene.note_pocket:p.setClipRect(QRectF(-512,0,1536,399))
    p.translate(*scene.note);p.rotate(scene.note_angle)
    pen(p,'#8b7853',1.6);p.setBrush(QColor('#f5e8c8'));p.drawRoundedRect(QRectF(-32,-22,64,44),2,2)
    pen(p,'#b9a77b',1)
    for y in (-12,-4,4,12):p.drawLine(QPointF(-23,y),QPointF(22,y))
    p.drawLine(QPointF(0,-19),QPointF(0,19))
    p.restore()


def rigs(library,name):
    art=library.scenes
    if not hasattr(art,'hermione_rig'):art.hermione_rig=HermioneRig(art.layers['base'],art.hair_repair,art.hair_fringe)
    if not hasattr(art,'guest_rigs'):art.guest_rigs={}
    if name not in art.guest_rigs:art.guest_rigs[name]=GuestRig(art.cameos[name],name)
    return art.hermione_rig,art.guest_rigs[name]


def front_hands(p,a,*,guest=False):
    p.save();p.translate(*a.shift);pivot=(246,412) if guest else a.pivot
    p.translate(*pivot);p.rotate(a.lean);p.translate(-pivot[0],-pivot[1])
    for side,mode in ((-1,a.left_hand),(1,a.right_hand)):
        _,_,wrist=arm_points(a,side,guest=guest)
        HermioneRig.hand(p,wrist,mode,side,a.hand_angle_left if side<0 else a.hand_angle_right)
    p.restore()


def paint_pair(p,library,life,separation=-260.,mirror=True,hero_filter=None):
    from .conversation_pose import conversation_pose
    scene=conversation_pose(life,separation,mirror);hero,guest=rigs(library,life.cameo)
    if hero_filter is not None:scene.hero=hero_filter(scene.hero)
    hero.draw(p,scene.hero,draw_hands=False)
    p.save();p.translate(separation,0)
    if mirror:p.translate(512,0);p.scale(-1,1)
    guest.draw(p,scene.guest,draw_hands=False);p.restore()
    draw_note(p,scene)
    front_hands(p,scene.hero)
    p.save();p.translate(separation,0)
    if mirror:p.translate(512,0);p.scale(-1,1)
    front_hands(p,scene.guest,guest=True);p.restore()
    return scene


def render_guest(library,life,size=256,dpr=1.):
    from .conversation_pose import conversation_pose
    _,rig=rigs(library,life.cameo);a=conversation_pose(life).guest
    result=image(round(size*dpr));p=QPainter(result)
    p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(result.width()/512,result.height()/512);rig.draw(p,a);p.end();result.setDevicePixelRatio(dpr);return result


def preview_pair(library,life,size=195,dpr=1.,separation=-260.,mirror=True):
    left=min(0,separation);width=max(512,separation+512)-left
    result=QImage(round(width*size/512*dpr),round(size*dpr),QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(Qt.GlobalColor.transparent);p=QPainter(result)
    p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(size*dpr/512,size*dpr/512);p.translate(-left,0);paint_pair(p,library,life,separation,mirror);p.end()
    result.setDevicePixelRatio(dpr);return result
