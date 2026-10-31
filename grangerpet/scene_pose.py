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


def ik(shoulder:Point,wrist:Point,side:int,upper=72.,lower=74.):
    """Two-bone elbow with bounded reach; returned wrist is the actual grip."""
    dx,dy=wrist[0]-shoulder[0],wrist[1]-shoulder[1];distance=math.hypot(dx,dy)
    length=max(abs(upper-lower)+.01,min(upper+lower-.01,distance))
    ux,uy=(dx/distance,dy/distance) if distance else (0.,1.)
    actual=(shoulder[0]+ux*length,shoulder[1]+uy*length)
    along=(upper*upper-lower*lower+length*length)/(2*length)
    away=math.sqrt(max(0.,upper*upper-along*along))
    elbow=(shoulder[0]+ux*along-side*uy*away,shoulder[1]+uy*along+side*ux*away)
    return elbow,actual


@dataclass
class BookPose:
    center:Point=(233.,340.)
    angle:float=-3.
    opening:float=1.
    page:float=-1.
    visible:bool=False
    pocket:bool=False

    @property
    def left_width(self):return 7+81*self.opening
    @property
    def right_width(self):return 57+24*self.opening
    def point(self,x,y):
        x,y=rotate((x,y),self.angle)
        return self.center[0]+x,self.center[1]+y
    def left_grip(self):return self.point(-self.left_width+4,18)
    def right_grip(self):return self.point(self.right_width-4,18)
    def page_corner(self,progress=None):
        t=max(0.,self.page if progress is None else progress)
        return self.point(75*math.cos(t*math.pi),-33-29*math.sin(t*math.pi))


@dataclass
class ActorPose:
    shift:Point=(0.,0.)
    lean:float=0.
    head:float=0.
    head_drop:float=0.
    gaze:Point=(0.,0.)
    mouth:str='neutral'
    blush:float=0.
    brow:float=0.
    blink:float=0.
    left:Point=(151.,352.)
    right:Point=(335.,352.)
    left_hand:str='relaxed'
    right_hand:str='relaxed'
    left_lift:float=0.
    right_lift:float=0.
    leg_left:float=0.
    leg_right:float=0.
    hair:float=0.
    book:BookPose=field(default_factory=BookPose)
    phase:str='rest'
    wand:bool=False
    wand_angle:float=-115.
    magic:float=0.
    phone:bool=False
    phone_center:Point=(270.,340.)
    phone_angle:float=-5.
    phone_lines:int=0
    hearts:float=0.


def reading_pose(q:float,elapsed:float,variant:int=0)->ActorPose:
    """Closed-book retrieval → grip → open → scan → turn → close → pocket."""
    a=ActorPose();b=a.book;v=variant%3
    b.visible=.025<q<.985
    b.center=track(q,(0.,(285.,444.)),(.06,(285.,406.)),(.145,(270.,344.)),
        (.25,(233.,340.)),(.76,(233.,340.)),(.86,(259.,345.)),(.90,(282.,365.)),(1.,(285.,450.)))
    b.angle=track(q,(0.,-14.),(.16,-10.),(.26,-3.),(.76,-3.),(.88,-14.),(1.,-14.))
    b.opening=track(q,(0.,0.),(.16,0.),(.265,1.),(.77,1.),(.87,0.),(1.,0.))
    b.pocket=q<.125 or q>.885
    right_follow=track(q,(0.,0.),(.055,1.),(.92,1.),(.99,0.))
    a.right=mix(a.right,b.right_grip(),right_follow)
    left_approach=track(q,(0.,0.),(.14,0.),(.23,1.),(.81,1.),(.91,0.))
    a.left=mix(a.left,b.left_grip(),left_approach)
    a.left_hand='grip' if left_approach>.6 else 'relaxed'
    a.right_hand='grip' if right_follow>.6 else 'relaxed'
    reading=track(q,(0.,0.),(.20,0.),(.29,1.),(.74,1.),(.88,0.))
    a.head=5.5*reading;a.head_drop=3*reading
    a.lean=track(q,(0.,0.),(.13,-2.5),(.28,1.3),(.75,1.3),(.87,-2.),(1.,0.))
    # Three deliberate line scans, with quick return saccades and a page glance.
    scan=track(q,(0.,0.),(.28,-1.),(.34,1.),(.355,-1.),(.415,1.),(.43,-1.),(.47,.8),
        (.49,1.),(.58,-1.),(.65,1.),(.665,-1.),(.73,.8),(.80,0.),(1.,0.))
    a.gaze=(scan*2.5,reading*5.)
    turn_start,turn_end=(.48,.58) if v!=1 else (.51,.61)
    if turn_start-.035<q<turn_end+.05:
        turn=max(0.,min(1.,(q-turn_start)/(turn_end-turn_start)))
        if turn_start<=q<=turn_end:b.page=turn
        corner=b.page_corner(turn)
        if q<turn_start:
            reach=smooth((q-turn_start+.035)/.035);a.right=mix(b.right_grip(),corner,reach)
        elif q>turn_end:
            a.right=mix(corner,b.right_grip(),smooth((q-turn_end)/.05))
        else:a.right=corner
        a.right_hand='pinch';a.gaze=(2.8*math.cos(turn*math.pi),4.)
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
    a.phase=('retrieve' if q<.16 else 'opening' if q<.27 else 'page_turn' if turn_start-.035<q<turn_end+.05
        else 'reading' if q<.77 else 'closing' if q<.885 else 'stowing')
    return a


def action_pose(action,q,t,variant=0,*,aim=(0.,0.),physics=None):
    if action=='reading':return reading_pose(q,t,variant)
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
            a.left=track(q,(0.,a.left),(.30,(187.,219.)),(.63,(191.,218.)),(1.,a.left))
            a.right=track(q,(0.,a.right),(.34,(256.,219.)),(.59,(260.,218.)),(1.,a.right))
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
        a.wand=.06<q<.95;a.left_hand='grip';v=variant%4
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
        follow=track(q,(0.,0.),(.07,1.),(.92,1.),(1.,0.));a.right=mix(a.right,(x+19,y+17),follow);a.right_hand='grip'
        a.head=5*envelope;a.gaze=(2*envelope,5*envelope)
        typing=.33<q<.47 or .55<q<.66
        contact=(x-2,y+11)
        a.left=track(q,(0.,a.left),(.29,a.left),(.33,contact),(.47,contact),(.50,(x-34,y+19)),
            (.55,contact),(.66,contact),(.76,(x-18,y+19)),(.84,(x-18,y+19)),(1.,a.left))
        if typing:
            a.left=(a.left[0]+2*math.sin(t*16),a.left[1]-2*max(0,math.sin(t*16)));a.left_hand='index'
        elif .72<q<.86:a.left_hand='grip'
        a.phone_lines=int(track(q,(0.,0.),(.32,0.),(.47,3.),(.51,3.),(.55,0.),(.66,3.),(1.,3.)))
        a.blush=track(q,(0.,0.),(.21,0.),(.29,.4),(.7,.8),(.82,1.),(1.,0.))
        a.mouth='smile' if .27<q<.86 else 'neutral';a.hearts=track(q,(0.,0.),(.68,0.),(.76,1.),(.87,0.),(1.,0.))
        a.lean=-2*envelope
    elif action=='daydream':
        a.head=-7*envelope;a.gaze=(3*envelope,-5*envelope);a.blush=.5*envelope
        a.right=track(q,(0.,a.right),(.28,(260.,247.)),(.77,(260.,247.)),(1.,a.right))
        a.left=track(q,(0.,a.left),(.25,(246.,335.)),(.78,(246.,335.)),(1.,a.left))
        a.mouth='smile';a.lean=-3*envelope;a.hearts=.45*envelope
    elif action in ('sleep','wake','yawn'):
        asleep=1. if action=='sleep' else 1-smooth(q) if action=='wake' else envelope
        a.head=11*asleep;a.head_drop=5*asleep;a.blink=asleep;a.lean=3*asleep
        a.right=mix(a.right,(246.,239.),asleep if action=='yawn' else 0.)
        a.mouth='open' if action=='yawn' and .25<q<.75 else 'neutral'
    elif action in ('leave','return','walk'):
        a.leg_left=math.sin(t*8)*11;a.leg_right=-a.leg_left
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
        a.lean+=physics.angle*.5;a.head-=physics.angle*.28
        a.head_drop+=physics.squash*6;a.shift=(0.,physics.sag*.5+physics.squash*3)
        a.left=mix(a.left,(157.,264.),min(1.,physics.tuck+physics.squash*.5))
        a.right=mix(a.right,(306.,265.),min(1.,physics.tuck+physics.squash*.5))
        a.leg_left+=physics.tuck*42+physics.leg_swing*4;a.leg_right-=physics.tuck*35+physics.leg_swing*4
        a.blush=max(a.blush,physics.embarrassed);a.brow=max(a.brow,physics.upset)
        if physics.upset>.2:a.mouth='pout'
    a.hair=a.head*.20-a.lean*.35;a.phase=action
    return a
