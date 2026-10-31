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

    @property
    def left_width(self):return 7+81*self.opening
    @property
    def right_width(self):return 57+24*self.opening
    def point(self,x,y):
        x,y=rotate((x*self.scale,y*self.scale),self.angle)
        return self.center[0]+x,self.center[1]+y
    def left_grip(self):return self.point(-self.left_width-9,-12+50*self.opening)
    def right_grip(self):return self.point(self.right_width+9,-12+50*self.opening)
    def page_corner(self,progress=None):
        t=max(0.,self.page if progress is None else progress)
        return self.point(75*math.cos(t*math.pi),-33-29*math.sin(t*math.pi))


@dataclass
class ActorPose:
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
    phone_center:Point=(270.,340.)
    phone_angle:float=-5.
    phone_lines:int=0
    hearts:float=0.
    pocket:bool=False


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
    a.head=5.5*reading+3*prepare;a.head_drop=3*reading
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
        a.head-=4*interest;a.brow=-interest;a.mouth='smile' if interest>.35 else 'neutral'
        a.lean+=2*interest
    elif v==2:
        indignation=track(q,(0.,0.),(.32,0.),(.37,1.),(.43,1.),(.47,0.),(.64,0.),(.69,1.),(.75,0.))
        a.head-=9*indignation;a.brow=indignation;a.mouth='pout' if indignation>.3 else 'neutral'
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
    wrist=(contact[0]-dx/distance*abs(tip[1]),contact[1]-dy/distance*abs(tip[1]))
    for _ in range(5):
        angle=math.degrees(math.atan2(elbow[1]-wrist[1],elbow[0]-wrist[0]))-90.
        offset=rotate(tip,angle);wrist=(contact[0]-offset[0],contact[1]-offset[1])
    return wrist


def hand_contact(actor,side):
    wrist=actor.left if side<0 else actor.right;mode=actor.left_hand if side<0 else actor.right_hand
    tip=HAND_CONTACTS.get(mode,(0.,0.));tip=(-tip[0],tip[1]) if side>0 else tip
    elbow=arm_points(actor,side)[1];extra=actor.hand_angle_left if side<0 else actor.hand_angle_right
    angle=math.degrees(math.atan2(elbow[1]-wrist[1],elbow[0]-wrist[0]))-90.+extra
    offset=rotate(tip,angle);return wrist[0]+offset[0],wrist[1]+offset[1]


def action_pose(action,q,t,variant=0,*,aim=(0.,0.),physics=None,_draw_elbows=True):
    if action=='reading':return reading_pose(q,t,variant,_draw_elbows=_draw_elbows)
    a=ActorPose();a.blink=max(0.,1-abs(t%5.3-4.1)/.075)
    envelope=track(q,(0.,0.),(.16,1.),(.80,1.),(1.,0.))
    if action=='shy':
        v=variant%3;a.blush=envelope;a.gaze=(3*envelope,4*envelope)
        a.head=track(q,(0.,0.),(.18,6.),(.40,8.),(.70,4.),(1.,0.))
        a.lean=-2*envelope;a.left_lift=a.right_lift=-4*envelope
        if v==0:
            a.left=track(q,(0.,a.left),(.27,(203.,306.)),(.7,(210.,311.)),(1.,a.left))
            a.right=track(q,(0.,a.right),(.27,(249.,311.)),(.7,(244.,311.)),(1.,a.right))
        elif v==1:
            a.left=track(q,(0.,a.left),(.16,(150.,285.)),(.30,(185.,213.)),(.63,(189.,211.)),(.85,(150.,285.)),(1.,a.left))
            a.right=track(q,(0.,a.right),(.18,(305.,282.)),(.34,(260.,208.)),(.59,(263.,210.)),(.85,(305.,282.)),(1.,a.right))
            a.left_hand=a.right_hand='cover'
            a.head_drop=5*envelope;a.gaze=(0.,4*envelope)
        else:
            a.brow=track(q,(0.,0.),(.20,.7),(.43,.7),(.56,-.7),(.8,-.7),(1.,0.))
            a.right=track(q,(0.,a.right),(.23,(270.,286.)),(.45,(270.,286.)),(.65,(245.,237.)),(1.,a.right))
            a.mouth='smile' if .48<q<.84 else 'pout'
        if v!=2:a.mouth='smile' if q>.45 else 'neutral'
    elif action=='annoyed':
        a.brow=envelope;a.mouth='pout';v=variant%3
        a.lean=track(q,(0.,0.),(.18,-3.),(.72,-3.),(1.,0.))
        if v==0:
            a.left=track(q,(0.,a.left),(.25,(264.,323.)),(.76,(264.,323.)),(1.,a.left))
            a.right=track(q,(0.,a.right),(.29,(189.,333.)),(.76,(189.,333.)),(1.,a.right))
            a.leg_right=track(q,(0.,0.),(.36,0.),(.42,-14.),(.48,0.),(.53,-7.),(.58,0.),(1.,0.))
            a.shift=(0.,track(q,(0.,0.),(.43,0.),(.48,-3.),(.52,1.),(.56,0.),(1.,0.)))
        elif v==1:
            a.left=track(q,(0.,a.left),(.25,(159.,344.)),(.75,(159.,344.)),(1.,a.left))
            a.right=track(q,(0.,a.right),(.24,(307.,245.)),(.4,(319.,237.)),(.52,(303.,247.)),(.65,(318.,240.)),(1.,a.right))
            a.right_hand='index';a.mouth='open' if .3<q<.66 and int(t*5)%2 else 'pout'
        else:
            a.head=track(q,(0.,0.),(.27,-10.),(.48,-10.),(.57,-6.),(.70,-6.),(1.,0.))
            a.gaze=track(q,(0.,(0.,0.)),(.28,(-4.,0.)),(.49,(-4.,0.)),(.60,(3.,0.)),(.75,(3.,0.)),(1.,(0.,0.)))
            a.right=track(q,(0.,a.right),(.24,(275.,351.)),(.76,(275.,351.)),(1.,a.right))
    elif action in ('wand_play','cast','avada'):
        a.wand=.06<q<.95;a.left_hand='grip';v=1 if action in ('cast','avada') else variant%4
        if action=='avada':a.magic_color='#77d56f';a.spell_text='«Авада Кедавра»' if .3<q<.78 else ''
        a.left=track(q,(0.,a.left),(.08,(281.,372.)),(.22,(143.,316.)),(.35,(136.,284.)),
            (.55,(161.,309.)),(.70,(136.,285.)),(.82,(162.,326.)),(.94,(280.,374.)),(1.,a.left))
        a.right=track(q,(0.,a.right),(.25,(281.,346.)),(.78,(281.,346.)),(1.,a.right))
        angles=[[(.22,-108.),(.36,-118.),(.56,242.),(.7,242.)],
                [(.22,-100.),(.34,-137.),(.49,-58.),(.6,-63.),(.72,-110.)],
                [(.22,-109.),(.36,-72.),(.48,-65.),(.55,-125.),(.66,-102.)],
                [(.22,-110.),(.36,-135.),(.48,-80.),(.62,-110.),(.72,-118.)]][v]
        a.wand_angle=track(q,(0.,-95.),*angles,(.91,-95.),(1.,-95.))
        a.magic=track(q,(0.,0.),(.43,0.),(.49,1.),(.60,.7),(.67,0.),(1.,0.)) if v!=0 or action!='wand_play' else 0.
        a.head=track(q,(0.,0.),(.30,-4.),(.50,2. if v==2 else -6.),(.72,-3.),(1.,0.))
        a.gaze=(-3*envelope,-2*envelope);a.lean=-2.5*envelope
        a.mouth='open' if v==2 and .49<q<.65 else 'smile' if .63<q<.82 else 'neutral'
        if v==2 and .5<q<.62:a.leg_right=-7*envelope;a.brow=-envelope
    elif action=='phone_solvnox':
        a.phone=.055<q<.95
        a.phone_center=track(q,(0.,(282.,436.)),(.08,(282.,399.)),(.22,(266.,338.)),
            (.65,(266.,338.)),(.76,(230.,313.)),(.83,(230.,313.)),(.90,(282.,374.)),(1.,(282.,448.)))
        a.phone_angle=track(q,(0.,-15.),(.25,-5.),(.65,-5.),(.76,5.),(.85,5.),(1.,-15.))
        x,y=a.phone_center
        def phone_point(px,py):
            px,py=rotate((px,py),a.phone_angle);return x+px,y+py
        follow=track(q,(0.,0.),(.07,1.),(.92,1.),(1.,0.));a.right=mix(a.right,phone_point(29,17),follow);a.right_hand='grip'
        a.head=5*envelope;a.gaze=(2*envelope,5*envelope)
        typing=.33<q<.47 or .55<q<.66
        contact=phone_point(-2,11);contact=(contact[0]+5,contact[1]+24)
        a.left=track(q,(0.,a.left),(.29,a.left),(.33,contact),(.47,contact),(.50,(x-34,y+19)),
            (.55,contact),(.66,contact),(.76,(x-18,y+19)),(.84,(x-18,y+19)),(1.,a.left))
        if typing:
            a.left=(a.left[0]+2*math.sin(t*16),a.left[1]-2*max(0,math.sin(t*16)));a.left_hand='index'
        elif .72<q<.86:a.left_hand='grip'
        a.phone_lines=int(track(q,(0.,0.),(.32,0.),(.47,3.),(.51,3.),(.55,0.),(.66,3.),(1.,3.)))
        a.blush=track(q,(0.,0.),(.21,0.),(.29,.4),(.7,.8),(.82,1.),(1.,0.))
        a.mouth='smile' if .27<q<.86 else 'neutral';a.hearts=track(q,(0.,0.),(.68,0.),(.76,1.),(.87,0.),(1.,0.))
        a.lean=-2*envelope
        a.pocket=q<.16 or q>.88
    elif action=='daydream':
        a.head=track(q,(0.,0.),(.28,-7.),(.43,-7.),(.55,-3.),(.68,-5.),(.8,-5.),(1.,0.))
        a.gaze=(3*envelope,-5*envelope);a.blush=.5*envelope
        a.right=track(q,(0.,a.right),(.15,(309.,287.)),(.28,(260.,247.)),(.77,(260.,247.)),(.9,(309.,287.)),(1.,a.right))
        a.left=track(q,(0.,a.left),(.25,(246.,335.)),(.78,(246.,335.)),(1.,a.left))
        a.mouth='smile';a.lean=-3*envelope;a.hearts=.45*envelope
    elif action in ('sleep','wake','yawn'):
        asleep=1. if action=='sleep' else 1-smooth(q) if action=='wake' else envelope
        a.head=11*asleep;a.head_drop=5*asleep;a.blink=asleep;a.lean=3*asleep
        if action=='sleep':
            a.head+=math.sin(t*.9)*.65;a.head_drop+=math.sin(t*.9)*.4
            a.left_lift=a.right_lift=math.sin(t*.9)*.9
            a.sleeping=True;a.sleep_lift=(t%2.5)/2.5
        a.right=mix(a.right,(246.,239.),asleep if action=='yawn' else 0.)
        a.mouth='open' if action=='yawn' and .25<q<.75 else 'neutral'
    elif action in ('leave','return','walk'):
        a.leg_left=math.sin(t*8)*11;a.leg_right=-a.leg_left
        a.knee_left=max(0,-math.sin(t*8))*28;a.knee_right=-max(0,math.sin(t*8))*28
        a.ankle_left=-a.knee_left*.35;a.ankle_right=-a.knee_right*.35
        a.shift=(0.,-abs(math.sin(t*8))*3);a.lean=-2 if action=='leave' else 2
        a.left=(151+math.sin(t*8)*12,348);a.right=(335-math.sin(t*8)*12,348)
        a.head=-2*math.sin(t*4)
    elif action=='hover':a.gaze=(aim[0]*4,aim[1]*3);a.head=aim[0]*1.5
    elif action=='happy':
        a.mouth='smile';a.head=track(q,(0.,0.),(.25,-5.),(.48,3.),(.72,-2.),(1.,0.))
        a.right=track(q,(0.,a.right),(.22,(319.,245.)),(.4,(335.,253.)),(.57,(312.,247.)),(.73,(332.,253.)),(1.,a.right))
    elif action=='error':
        a.mouth='pout';a.brow=envelope;a.head=track(q,(0.,0.),(.2,-7.),(.4,6.),(.6,-5.),(.8,3.),(1.,0.))
        a.right=mix(a.right,(286.,259.),envelope)
    elif action in ('thinking','working'):
        a.right=(263.,244.);a.head=-4.;a.gaze=(2.,-3.);a.left=(239.,337.)
        if action=='working':a.gaze=(track(t%3,(0.,-3.),(1.1,3.),(1.3,-3.),(3.,3.)),3.)
    else:
        # Breath is a subpixel chest/shoulder motion, not whole-sprite wobble.
        a.left_lift=a.right_lift=math.sin(t*1.7)*.7
    if physics is not None:
        a.grounded=False
        a.pivot=(229.,267.)
        a.lean+=physics.angle*.5;a.head-=physics.angle*.28
        a.head_drop+=physics.squash*6;a.shift=(0.,physics.sag*.5+physics.squash*3)
        a.left=mix(a.left,(157.,264.),min(1.,physics.tuck+physics.squash*.5))
        a.right=mix(a.right,(306.,265.),min(1.,physics.tuck+physics.squash*.5))
        a.leg_left+=physics.tuck*42+physics.leg_swing*4;a.leg_right-=physics.tuck*35+physics.leg_swing*4
        a.knee_left=physics.tuck*120+physics.squash*55;a.knee_right=-physics.tuck*120-physics.squash*55
        a.ankle_left=-a.knee_left*.45;a.ankle_right=-a.knee_right*.45
        a.blush=max(a.blush,physics.embarrassed);a.brow=max(a.brow,physics.upset)
        if physics.upset>.2:a.mouth='pout'
    a.hair=a.head*.20-a.lean*.35;a.phase=action
    if _draw_elbows:_drawn_elbows(a,action,q,variant,physics)
    return a


def _drawn_elbows(a,action,q,variant,physics):
    """Authored elbow silhouettes for the existing actions, with local tweens."""
    left,right=(136.,340.),(316.,340.)
    left_keys=((0.,left),(1.,left));right_keys=((0.,right),(1.,right))
    envelope=track(q,(0.,0.),(.22,1.),(.77,1.),(1.,0.))
    if action=='shy':
        if variant%3==1:
            left_keys=((0.,left),(.16,(127.,325.)),(.30,(132.,268.)),(.63,(132.,268.)),(.85,(127.,325.)),(1.,left))
            right_keys=((0.,right),(.18,(328.,321.)),(.34,(316.,265.)),(.59,(316.,265.)),(.85,(328.,321.)),(1.,right))
        else:
            left_keys=((0.,left),(.22,(154.,344.)),(.77,(154.,344.)),(1.,left))
            target=(303.,344.) if variant%3==0 else (314.,288.);right_keys=((0.,right),(.22,target),(.77,target),(1.,right))
    elif action=='annoyed':
        if variant%3==0:
            left_keys=((0.,left),(.22,(184.,348.)),(.77,(184.,348.)),(1.,left));target=(264.,365.)
        elif variant%3==1:target=(325.,313.)
        else:target=(315.,339.)
        right_keys=((0.,right),(.22,target),(.77,target),(1.,right))
    elif action in ('wand_play','cast','avada'):
        left_keys=((0.,left),(.08,(226.,333.)),(.22,(127.,356.)),(.35,(124.,340.)),(.55,(127.,346.)),(.72,(124.,340.)),(.94,(226.,333.)),(1.,left))
    elif action=='phone_solvnox':
        left_keys=((0.,left),(.29,left),(.33,(210.,360.)),(.65,(210.,360.)),(.76,(174.,354.)),(.85,(174.,354.)),(1.,left))
        right_keys=((0.,right),(.12,(326.,366.)),(.27,(318.,330.)),(.65,(318.,330.)),(.76,(290.,357.)),(.85,(290.,357.)),(.93,(326.,366.)),(1.,right))
    elif action=='daydream':
        left_keys=((0.,left),(.22,(183.,354.)),(.77,(183.,354.)),(1.,left));right_keys=((0.,right),(.22,(318.,296.)),(.77,(318.,296.)),(1.,right))
    elif action in ('working','thinking'):a.elbow_left=(180.,354.);a.elbow_right=(319.,302.);return
    elif action in ('leave','return','walk'):a.elbow_left=(124.,326.);a.elbow_right=(327.,326.);return
    elif action in ('happy','error','yawn'):
        target={'happy':(325.,306.),'error':(320.,315.),'yawn':(303.,297.)}[action]
        right_keys=((0.,right),(.22,target),(.77,target),(1.,right))
    duration={'shy':5.5,'annoyed':4.5,'wand_play':8.,'phone_solvnox':13.,'daydream':9.,'yawn':2.1}.get(action,6.)
    wrist=lambda u,side:getattr(action_pose(action,u,u*duration,variant,_draw_elbows=False),side)
    left=elbow_track(q,left_keys,lambda u:wrist(u,'left'))
    right=elbow_track(q,right_keys,lambda u:wrist(u,'right'))
    if physics is not None:
        strength=min(1.,physics.tuck+physics.squash*.5)
        base=action_pose(action,q,q*duration,variant,_draw_elbows=False)
        for side,elbow,target_e,target_w in (('left',left,(129.,314.),(157.,264.)),('right',right,(326.,314.),(306.,265.))):
            start=getattr(base,side);current=getattr(a,side)
            vector=polar_between((elbow[0]-start[0],elbow[1]-start[1]),(target_e[0]-target_w[0],target_e[1]-target_w[1]),strength)
            if side=='left':left=(current[0]+vector[0],current[1]+vector[1])
            else:right=(current[0]+vector[0],current[1]+vector[1])
    a.elbow_left,a.elbow_right=left,right
