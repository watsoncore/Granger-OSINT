"""Local phone scene with authored bent-finger art and a shared glass contact model."""
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
from .scene_pose import track,mix,rotate,smooth


@lru_cache(maxsize=1)
def geometry():
    return json.loads((Path(__file__).parent/'assets/phone-solvnox-v1/geometry.json').read_text(encoding='utf-8'))


def phone_point(a,x,y):
    x,y=rotate((x,y),a.phone_angle)
    return a.phone_center[0]+x,a.phone_center[1]+y


@dataclass(frozen=True)
class PhoneContact:
    phone_pose:tuple
    phone_screen_geometry:tuple
    holding_hand_anchor:tuple|None
    typing_hand_anchor:tuple
    typing_fingertip:tuple|None
    tap_target:tuple
    press:float
    phase:str


def contact_model(a):
    art=geometry();left=art['hands'].get(a.left_hand,{})
    tip=left.get('tip');tip=rotate(tuple(tip),a.hand_angle_left) if tip else None
    hold=art['hands']['phone_hold']['anchor'];hold=rotate(tuple(hold),a.hand_angle_right)
    return PhoneContact((a.phone_center,a.phone_angle),tuple(phone_point(a,*v) for v in art['screen_polygon']),
        (a.right[0]+hold[0],a.right[1]+hold[1]) if a.right_hand=='phone_hold' else None,a.left,
        (a.left[0]+tip[0],a.left[1]+tip[1]) if tip else None,a.phone_target,a.phone_press,a.phase)


# Every contact is a deliberate beat, including two delete presses and a final
# send press. Different retype intervals are authored, not a wobbling phone.
TAPS=((.322,.020,(3.,13.)),(.369,.021,(7.,19.)),(.414,.018,(4.,25.)),(.461,.019,(8.,10.)),
    (.538,.015,(8.,25.)),(.576,.015,(8.,25.)),
    (.615,.022,(3.,14.)),(.663,.017,(7.,21.)),(.697,.019,(4.,24.)),(.737,.016,(7.,12.)),
    (.817,.019,(6.,0.)))


def press_at(q):
    return max((1. if abs(q-c)/width<=.18 else 1-smooth((abs(q-c)/width-.18)/.82)
        if abs(q-c)<width else 0.) for c,width,_ in TAPS)


def phone_pose(q,t):
    from .hermione_pose_bank import arm_pose_bank
    a=arm_pose_bank()['relaxed'];a.phone_style='solvnox';a.phone=.001<q<.999
    a.pocket=q<.12 or q>.92;a.pocket_lip=385.
    a.phone_center=track(q,(0.,(295.,445.)),(.055,(295.,417.)),(.17,(280.,334.)),
        (.86,(280.,334.)),(.915,(289.,361.)),(.97,(295.,417.)),(1.,(295.,445.)))
    a.phone_angle=track(q,(0.,-15.),(.17,-10.),(.85,-10.),(1.,-15.))
    grip=track(q,(0.,(25.,-42.)),(.055,(25.,-42.)),(.12,(24.,-8.)),(.17,(24.,42.)),
        (.86,(24.,42.)),(.915,(24.,-8.)),(.97,(25.,-42.)),(1.,(25.,-42.)))
    follow=track(q,(0.,0.),(.04,1.),(.985,1.),(1.,0.))
    a.right=mix(a.right,phone_point(a,*grip),follow)
    a.elbow_right=track(q,(0.,a.elbow_right),(.12,(337.,345.)),(.20,(330.,350.)),
        (.86,(330.,350.)),(.97,(337.,345.)),(1.,a.elbow_right))
    if follow>.02:a.right_hand='phone_hold';a.hand_angle_right=a.phone_angle
    a.arm_art_right='phone' if .035<q<.985 else 'rest'
    approach=track(q,(0.,0.),(.22,0.),(.295,1.),(.845,1.),(.905,0.),(1.,0.))
    a.elbow_left=track(q,(0.,a.elbow_left),(.22,a.elbow_left),(.295,(178.,363.)),
        (.845,(178.,363.)),(.905,a.elbow_left),(1.,a.elbow_left))
    a.phone_press=press_at(q)
    local_target=track(q,*((c,pt) for c,_,pt in TAPS));a.phone_target=phone_point(a,*local_target)
    # The fingertip clears the narrow screen visibly: ~8 logical pixels at195.
    lift=(1-a.phone_press);tip=(a.phone_target[0]-18*lift,a.phone_target[1]-14*lift)
    a.hand_angle_left=-8*approach
    offset=rotate(tuple(geometry()['hands']['phone_press']['tip']),a.hand_angle_left)
    desired=(tip[0]-offset[0],tip[1]-offset[1]);a.left=mix(a.left,desired,approach)
    if approach>.02:
        a.left_hand='phone_press' if a.phone_press>.7 else 'phone_hover';a.arm_art_left='phone'
    # Clear facial intention without drawing or scaling new eyes/face features.
    focus=track(q,(0.,0.),(.07,.35),(.20,1.),(.86,1.),(1.,0.))
    ponder=track(q,(0.,0.),(.48,0.),(.495,1.),(.515,0.),(1.,0.))
    a.head=6*focus-4*ponder;a.head_drop=14*focus-3*ponder
    scan=track(q,(0.,0.),(.17,-.6),(.21,.6),(.255,-.5),(.29,.4),(.48,.4),(.50,-1.),(.52,.4),(.78,.4),(.86,0.),(1.,0.))
    a.gaze=(3*focus+scan,5.8*focus-5*ponder)
    a.lean=1.5*focus;a.turn=.2*focus
    a.blush=track(q,(0.,0.),(.21,0.),(.29,.22),(.49,.4),(.59,.32),(.80,.35),(.85,.6),(.91,.35),(1.,0.))
    a.mouth='smile' if .25<q<.31 or .59<q<.68 or .80<q<.91 else 'focused' if focus>.2 else 'neutral'
    a.brow=-.35 if .79<q<.86 else -.25*ponder
    a.phone_lines=int(track(q,(0.,0.),(.30,0.),(.48,3.),(.52,3.),(.59,1.),(.75,3.),(1.,3.)))
    a.phase=('retrieve' if q<.17 else 'read' if q<.30 else 'type' if q<.48 else 'pause' if q<.52
        else 'erase' if q<.59 else 'retype' if q<.75 else 'review' if q<.795 else 'send' if q<.84 else 'delight' if q<.89 else 'stow')
    return a


class PhoneArt:
    """Cached phone-only cels; base/fingers are disjoint depth layers."""
    def __init__(self):
        from PySide6.QtGui import QImage
        self.meta=geometry();folder=Path(__file__).parent/'assets/phone-solvnox-v1'
        self.device_image=QImage(str(folder/'phone.png'))
        self.hands={name:QImage(str(folder/spec['file'])) for name,spec in self.meta['hands'].items()}
        if self.device_image.isNull() or any(im.isNull() for im in self.hands.values()):raise ValueError('Missing phone-only artwork')

    def device(self,p,a):
        from PySide6.QtCore import QPointF,QRectF
        p.save()
        if a.pocket:p.setClipRect(QRectF(0,0,512,a.pocket_lip))
        p.translate(*a.phone_center);p.rotate(a.phone_angle)
        p.drawImage(QPointF(*self.meta['device_origin']),self.device_image);p.restore()

    def hand(self,p,a,side,*,front=False):
        from PySide6.QtCore import QPointF,QRectF
        from PySide6.QtGui import QPainterPath
        mode=a.left_hand if side<0 else a.right_hand;spec=self.meta['hands'][mode]
        p.save();p.translate(*(a.left if side<0 else a.right));p.rotate(a.hand_angle_left if side<0 else a.hand_angle_right)
        region=spec['front']
        if front:
            if not region:p.restore();return
            p.setClipRect(QRectF(*region))
        elif region:
            mask=QPainterPath();mask.addRect(QRectF(-60,-60,140,140));cut=QPainterPath();cut.addRect(QRectF(*region))
            p.setClipPath(mask.subtracted(cut))
        p.drawImage(QPointF(*spec['origin']),self.hands[mode]);p.restore()
