"""Deterministic articulated scene tracks in the approved 512-pixel art space.

Tracks describe intentions; the painter resolves shoulders/elbows/wrists and
renders props from the same anchors. No widget, timer, I/O or random state here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math

Point = tuple[float, float]


def mix(a, b, t):
    if isinstance(a, tuple):return tuple(mix(x,y,t) for x,y in zip(a,b))
    return a+(b-a)*t


def smooth(t):
    t=max(0.,min(1.,t));return t*t*(3-2*t)


def track(t, *keys):
    if t<=keys[0][0]:return keys[0][1]
    for (a,x),(b,y) in zip(keys,keys[1:]):
        if t<=b:return mix(x,y,smooth((t-a)/(b-a)))
    return keys[-1][1]


def rotate(point:Point, angle:float, origin:Point=(0.,0.))->Point:
    a=math.radians(angle);x,y=point[0]-origin[0],point[1]-origin[1]
    return origin[0]+x*math.cos(a)-y*math.sin(a),origin[1]+x*math.sin(a)+y*math.cos(a)


def polar_between(first,second,t):
    start,end=math.atan2(first[1],first[0]),math.atan2(second[1],second[0])
    delta=math.atan2(math.sin(end-start),math.cos(end-start))
    radius=mix(math.hypot(*first),math.hypot(*second),t);angle=start+delta*t
    return radius*math.cos(angle),radius*math.sin(angle)


def elbow_track(q,keys,wrist_at):
    if q<=keys[0][0]:return keys[0][1]
    for (a,first),(b,second) in zip(keys,keys[1:]):
        if q<=b:
            if first==second:return first
            t=smooth((q-a)/(b-a));wa,wb,w=wrist_at(a),wrist_at(b),wrist_at(q)
            vector=polar_between((first[0]-wa[0],first[1]-wa[1]),(second[0]-wb[0],second[1]-wb[1]),t)
            return w[0]+vector[0],w[1]+vector[1]
    return keys[-1][1]


def ik(shoulder:Point,wrist:Point,side:int,upper=72.,lower=74.):
    """Two-bone elbow with bounded reach; returned wrist is the actual grip."""
    dx,dy=wrist[0]-shoulder[0],wrist[1]-shoulder[1];distance=math.hypot(dx,dy)
    length=max(abs(upper-lower)+.01,min(upper+lower-.01,distance))
    ux,uy=(dx/distance,dy/distance) if distance else (0.,1.)
    actual=(shoulder[0]+ux*length,shoulder[1]+uy*length)
    along=(upper*upper-lower*lower+length*length)/(2*length)
    away=math.sqrt(max(0.,upper*upper-along*along))
    elbow=(shoulder[0]+ux*along+side*uy*away,shoulder[1]+uy*along-side*ux*away)
    return elbow,actual


@dataclass
class BookPose:
    center:Point=(233.,340.)
    angle:float=-3.
    opening:float=1.
    page:float=-1.
    visible:bool=False
    pocket:bool=False
    scale:float=1.
    pocket_lip:float=399.
    pitch:float=1.
    perspective:float=0.

    @property
    def left_width(self):return 7+81*self.opening
    @property
    def right_width(self):return 57+24*self.opening
    def point(self,x,y):
        divisor=1-self.perspective*y
        x,y=x/divisor,y*self.pitch/divisor
        x,y=rotate((x*self.scale,y*self.scale),self.angle)
        return self.center[0]+x,self.center[1]+y
    def left_grip(self):return self.point(-self.left_width-9,-12+50*self.opening)
    def right_grip(self):return self.point(self.right_width+9,-12+50*self.opening)
    def page_corner(self,progress=None):
        t=max(0.,self.page if progress is None else progress)
        return self.point(75*math.cos(t*math.pi),-33-29*math.sin(t*math.pi))


@dataclass
class ActorPose:
    source_idle:bool=False
    source_time:float=0.
    arm_art:str='rest'
    arm_art_left:str=''
    arm_art_right:str=''
    grounded:bool=True
    pivot:Point=(236.,412.)
    shift:Point=(0.,0.)
    lean:float=0.
    turn:float=0.
    head:float=0.
    head_drop:float=0.
    gaze:Point=(0.,0.)
    mouth:str='neutral'
    blush:float=0.
    brow:float=0.
    blink:float=0.
    left:Point=(156.,385.)
    right:Point=(319.,385.)
    left_hand:str='relaxed'
    right_hand:str='relaxed'
    left_lift:float=0.
    right_lift:float=0.
    elbow_left:Point|None=None
    elbow_right:Point|None=None
    hand_angle_left:float=0.
    hand_angle_right:float=0.
    leg_left:float=0.
    leg_right:float=0.
    knee_left:float=0.
    knee_right:float=0.
    ankle_left:float=0.
    ankle_right:float=0.
    hair:float=0.
    book:BookPose=field(default_factory=BookPose)
    phase:str='rest'
    wand:bool=False
    wand_angle:float=-115.
    magic:float=0.
    magic_color:str='#c6c2e0'
    spell_text:str=''
    sleeping:bool=False
    sleep_lift:float=0.
    phone:bool=False
    phone_back:bool=False
    phone_style:str=''
    phone_press:float=0.
    phone_target:Point=(0.,0.)
    phone_center:Point=(270.,340.)
    phone_angle:float=-5.
    phone_lines:int=0
    hearts:float=0.
    pocket:bool=False
    pocket_lip:float=399.


def reading_pose(q:float,elapsed:float,variant:int=0,*,_draw_elbows=True,rest_pose=None)->ActorPose:
    """Closed-book retrieval → grip → open → scan → turn → close → pocket."""
    a=ActorPose(left=rest_pose.left if rest_pose else (164.,379.),right=rest_pose.right if rest_pose else (317.,379.))
    rest_left=rest_pose.elbow_left if rest_pose and rest_pose.elbow_left else (164.,342.)
    rest_right=rest_pose.elbow_right if rest_pose and rest_pose.elbow_right else (308.,342.)
    b=a.book;v=variant%3
    b.scale=.72;b.pocket_lip=385.;b.visible=.055<q<.985
    b.center=track(q,(0.,(268.,430.)),(.06,(268.,399.)),(.145,(270.,344.)),
        (.27,(233.,315.)),(.76,(233.,315.)),(.86,(259.,334.)),(.90,(268.,365.)),(1.,(268.,430.)))
    b.angle=track(q,(0.,-14.),(.16,-10.),(.285,-3.),(.76,-3.),(.88,-14.),(1.,-14.))
    b.opening=track(q,(0.,0.),(.18,0.),(.285,1.),(.77,1.),(.87,0.),(1.,0.))
    if rest_pose is None:
        b.pitch=1-.22*b.opening;b.perspective=.0012*b.opening
        b.center=(b.center[0],b.center[1]+8*b.opening)
    b.pocket=q<.125 or q>.885
    right_follow=track(q,(0.,0.),(.055,1.),(.965,1.),(.999,0.))
    a.right=mix(a.right,b.right_grip(),right_follow)
    left_approach=track(q,(0.,0.),(.08,0.),(.17,1.),(.875,1.),(.94,0.))
    a.left=mix(a.left,b.left_grip(),left_approach)
    a.left_hand='grip' if left_approach>.6 else 'relaxed'
    a.right_hand='grip' if right_follow>.6 else 'relaxed'
    if b.opening<.25:
        if left_approach>.6:a.left_hand='closed_grip'
        if right_follow>.6:a.right_hand='closed_grip'
    a.arm_art='rest' if q<.045 or q>.985 else 'reach' if q<.18 or q>.9 else 'reading'
    if left_approach<.05:a.arm_art_left='rest'
    reading=track(q,(0.,0.),(.20,0.),(.29,1.),(.74,1.),(.88,0.))
    prepare=track(q,(0.,0.),(.055,1.),(.145,1.),(.24,0.),(1.,0.))
    a.head=(7. if rest_pose is None else 5.5)*reading+3*prepare
    a.head_drop=(5 if rest_pose is None else 3)*reading
    a.mouth='focused' if reading>.2 and rest_pose is None else 'neutral'
    a.lean=track(q,(0.,0.),(.13,2.5),(.28,1.3),(.75,1.3),(.87,2.),(1.,0.))
    # Three deliberate line scans, with quick return saccades and a page glance.
    scan=track(q,(0.,0.),(.28,-1.),(.34,1.),(.355,-1.),(.415,1.),(.43,-1.),(.47,.8),
        (.49,1.),(.58,-1.),(.65,1.),(.665,-1.),(.73,.8),(.80,0.),(1.,0.))
    a.gaze=(scan*2.5,reading*5.+prepare*4)
    turn_start,turn_end=(.48,.58) if v!=1 else (.51,.61)
    left_keys=((0.,rest_left),(.08,rest_left),(.17,(210.,361.)),(.285,(143.,366.)),
        (.77,(143.,366.)),(.875,(205.,361.)),(.94,(164.,350.)),(1.,rest_left))
    right_keys=((0.,rest_right),(.08,(351.,340.)),(.18,(340.,340.)),(.285,(330.,365.)),
        (turn_start-.035,(330.,365.)),(turn_start,(350.,330.)),((turn_start+turn_end)/2,(319.,326.)),
        (turn_end,(268.,330.)),(turn_end+.05,(330.,365.)),(.8,(330.,365.)),(.89,(351.,340.)),(.965,(351.,340.)),(1.,rest_right))
    a.elbow_left=track(q,*left_keys);a.elbow_right=track(q,*right_keys)
    if turn_start-.035<q<turn_end+.05:
        turn=max(0.,min(1.,(q-turn_start)/(turn_end-turn_start)))
        if turn_start<=q<=turn_end:b.page=turn
        corner=b.page_corner(turn)
        pinch=pointing_wrist(a.elbow_right,corner,'pinch',1)
        if q<turn_start:
            reach=smooth((q-turn_start+.035)/.035);a.right=mix(b.right_grip(),pinch,reach)
        elif q>turn_end:
            a.right=mix(pinch,b.right_grip(),smooth((q-turn_end)/.05))
        else:
            a.right=pinch
            for _ in range(3):
                a.elbow_right=arm_points(a,1)[1]
                a.right=pointing_wrist(a.elbow_right,corner,'pinch',1)
        a.right_hand='pinch';a.gaze=(2.8*math.cos(turn*math.pi),4.)
        if math.dist(a.right,a.elbow_right)>58:a.arm_art_right='page'
    if v==1:
        interest=track(q,(0.,0.),(.34,0.),(.39,1.),(.46,1.),(.51,0.),(.63,0.),(.68,1.),(.74,0.))
        a.head-=4*interest;a.brow=-interest;a.mouth='smile' if interest>.35 else a.mouth
        a.lean+=2*interest
    elif v==2:
        indignation=track(q,(0.,0.),(.32,0.),(.37,1.),(.43,1.),(.47,0.),(.64,0.),(.69,1.),(.75,0.))
        a.head-=9*indignation;a.brow=indignation;a.mouth='pout' if indignation>.3 else a.mouth
        a.gaze=(a.gaze[0],a.gaze[1]-5*indignation)
    a.hair=a.head*.13-a.lean*.4
    a.blink=max(0.,1-abs(elapsed%5.9-4.4)/.075)  # short blink; no long closed reading
    a.phase=('retrieve' if q<.18 else 'opening' if q<.30 else 'page_turn' if turn_start-.035<q<turn_end+.05
        else 'reading' if q<.77 else 'closing' if q<.885 else 'stowing')
    return a


def arm_points(a,side,*,guest=False):
    """Authored projected elbows take priority over the fallback 2-bone solve."""
    if side<0:
        shoulder=(193.+a.turn*5,281.+a.left_lift) if guest else (171.+a.turn*5,293.+a.left_lift)
        target,elbow=a.left,a.elbow_left
    else:
        shoulder=(295.+a.turn*5,282.+a.right_lift) if guest else (281.+a.turn*5,294.+a.right_lift)
        target,elbow=a.right,a.elbow_right
    if elbow is None:elbow,target=ik(shoulder,target,side)
    else:
        # Keep projected segments anatomical during inbetweens. Wrist contacts
        # never move; correct the elbow inside the two reachable annuli.
        x,y=elbow
        for _ in range(10):
            for center in (shoulder,target):
                dx,dy=x-center[0],y-center[1];length=math.hypot(dx,dy)
                if length<1e-8:dx,dy=side*.6,.8;length=1.
                bounded=max(22.,min(86.,length))
                if bounded!=length:x,y=center[0]+dx/length*bounded,center[1]+dy/length*bounded
        elbow=(x,y)
    return shoulder,elbow,target


HAND_CONTACTS={'index':(1.,-33.),'pinch':(0.,-24.)}


def pointing_wrist(elbow,contact,mode,side):
    tip=HAND_CONTACTS[mode];tip=(-tip[0],tip[1]) if side>0 else tip
    dx,dy=contact[0]-elbow[0],contact[1]-elbow[1];distance=math.hypot(dx,dy) or 1.
    # Exact projected contact. Fixed-point iteration oscillated when the short
    # forearm length approached the index length (visible near a small phone).
    along=math.sqrt(max(0.,distance*distance-tip[0]*tip[0]))
    angle=math.atan2(dy,dx)-math.atan2(tip[0],along)
    reach=along-abs(tip[1])
    return elbow[0]+reach*math.cos(angle),elbow[1]+reach*math.sin(angle)


def hand_contact(actor,side):
    wrist=actor.left if side<0 else actor.right;mode=actor.left_hand if side<0 else actor.right_hand
    tip=HAND_CONTACTS.get(mode,(0.,0.));tip=(-tip[0],tip[1]) if side>0 else tip
    elbow=arm_points(actor,side)[1];extra=actor.hand_angle_left if side<0 else actor.hand_angle_right
    angle=math.degrees(math.atan2(elbow[1]-wrist[1],elbow[0]-wrist[0]))-90.+extra
    offset=rotate(tip,angle);return wrist[0]+offset[0],wrist[1]+offset[1]


def action_pose(action,q,t,variant=0,*,aim=(0.,0.),physics=None,_draw_elbows=True):
    from .solo_sequence import solo_sequence,original_neutral
    if action=='reading':return solo_sequence(q,t,lambda u,elapsed:reading_pose(u,elapsed,variant))
    from .hermione_actions import drawn_action
    from .hermione_pose_bank import arm_pose_bank
    if action in ('phone_solvnox','wand_play','cast','avada','shy','annoyed','daydream','happy','error','yawn'):
        a=solo_sequence(q,t,lambda u,elapsed:drawn_action(action,u,elapsed,variant))
    else:a=drawn_action(action,q,t,variant) or arm_pose_bank()['relaxed']
    if action in ('idle','hover','') and physics is None:a=original_neutral()
    a.source_idle=action in ('idle','hover','') and physics is None
    a.source_time=t
    a.blink=max(a.blink,max(0.,1-abs(t%5.3-4.1)/.075))
    envelope=track(q,(0.,0.),(.16,1.),(.80,1.),(1.,0.))
    if action in ('sleep','wake'):
        asleep=1. if action=='sleep' else 1-smooth(q)
        a.head=11*asleep;a.head_drop=5*asleep;a.blink=asleep;a.lean=3*asleep
        if action=='sleep':
            a.head+=math.sin(t*.9)*.65;a.head_drop+=math.sin(t*.9)*.4
            a.left_lift=a.right_lift=math.sin(t*.9)*.9
            a.sleeping=True;a.sleep_lift=(t%2.5)/2.5
    elif action in ('leave','return','walk'):
        a.leg_left=math.sin(t*8)*11;a.leg_right=-a.leg_left
        a.knee_left=max(0,-math.sin(t*8))*28;a.knee_right=-max(0,math.sin(t*8))*28
        a.ankle_left=-a.knee_left*.35;a.ankle_right=-a.knee_right*.35
        a.shift=(0.,-abs(math.sin(t*8))*3);a.lean=-2 if action=='leave' else 2
        a.left=(164+math.sin(t*8)*8,379);a.right=(317-math.sin(t*8)*8,379)
        a.head=-2*math.sin(t*4)
    elif action=='hover':a.gaze=(aim[0]*4,aim[1]*3);a.head=aim[0]*1.5
    elif action in ('idle','settle','away',''):
        a.left_lift=a.right_lift=math.sin(t*1.7)*.7
    if physics is not None:
        a.grounded=False;a.pivot=(229.,267.)
        a.lean+=physics.angle*.5;a.head-=physics.angle*.28
        a.head_drop+=physics.squash*6;a.shift=(0.,physics.sag*.5+physics.squash*3)
        strength=min(1.,physics.tuck+physics.squash*.5)
        # Keep cloth attached to its moving wrist during cursor suspension.
        # A separate folded sleeve handles the raised forearm, never a raster
        # crossfade or the old shoulder-only white-hand overlay.
        for side,target_e,target_w in (('left',(129.,314.),(157.,264.)),('right',(326.,314.),(306.,265.))):
            start=getattr(a,side);elbow=getattr(a,'elbow_'+side)
            current=mix(start,target_w,strength)
            vector=polar_between((elbow[0]-start[0],elbow[1]-start[1]),(target_e[0]-target_w[0],target_e[1]-target_w[1]),strength)
            setattr(a,side,current);setattr(a,'elbow_'+side,(current[0]+vector[0],current[1]+vector[1]))
        if strength>.45:a.arm_art='cheek';a.arm_art_left=a.arm_art_right=''
        a.leg_left+=physics.tuck*42+physics.leg_swing*4;a.leg_right-=physics.tuck*35+physics.leg_swing*4
        a.knee_left=physics.tuck*120+physics.squash*55;a.knee_right=-physics.tuck*120-physics.squash*55
        a.ankle_left=-a.knee_left*.45;a.ankle_right=-a.knee_right*.45
        a.blush=max(a.blush,physics.embarrassed);a.brow=max(a.brow,physics.upset)
        if physics.upset>.2:a.mouth='pout'
    a.hair=a.head*.20-a.lean*.35
    if action=='phone_solvnox' and q in (0.,1.) and physics is None:
        # Match the immutable neutral atlas, including its historical sampling.
        a.source_idle=True;a.source_time=0.;a.blink=0.
    if a.phase=='rest':a.phase=action
    return a
