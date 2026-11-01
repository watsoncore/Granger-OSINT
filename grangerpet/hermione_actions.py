"""Hermione's existing actions, staged from the reviewed painted pose masters.

Only local animation data. Phone captions never leave the renderer; there is
no message sender, service client or user-data access in this module.
"""
import math
from .scene_pose import track,mix,rotate,pointing_wrist
from .hermione_pose_bank import arm_pose_bank,pose_transition


def gesture(name,q,enter=.28,leave=.75):
    bank=arm_pose_bank();amount=track(q,(0.,0.),(enter,1.),(leave,1.),(1.,0.))
    return pose_transition(bank['relaxed'],bank[name],amount)


def phone_point(a,x,y):
    x,y=rotate((x,y),a.phone_angle)
    return a.phone_center[0]+x,a.phone_center[1]+y


def phone_pose(q,t):
    a=arm_pose_bank()['relaxed'];a.phone_back=True;a.phone=.005<q<.995;a.pocket=q<.14 or q>.89;a.pocket_lip=385.
    a.phone_center=track(q,(0.,(268.,448.)),(.07,(268.,405.)),(.23,(244.,333.)),
        (.67,(244.,333.)),(.76,(230.,327.)),(.835,(230.,327.)),(.9,(268.,367.)),(1.,(268.,448.)))
    a.phone_angle=track(q,(0.,-15.),(.23,-9.),(.67,-9.),(.76,5.),(.85,5.),(1.,-15.))
    follow=track(q,(0.,0.),(.055,1.),(.965,1.),(1.,0.))
    # Begin at the side grip; move to a supporting lower corner only once clear
    # of the pocket. The screen never floats in front of a distant palm.
    grip=track(q,(0.,(19.,-39.)),(.055,(19.,-39.)),(.13,(19.,6.)),(.23,(16.,35.)),
        (.85,(16.,35.)),(.92,(19.,6.)),(.965,(19.,-39.)),(1.,(19.,-39.)))
    a.right=mix(a.right,phone_point(a,*grip),follow);a.right_hand='grip'
    a.elbow_right=track(q,(0.,a.elbow_right),(.08,(347.,354.)),(.23,(310.,355.)),
        (.67,(310.,355.)),(.76,(292.,360.)),(.84,(292.,360.)),(.93,(347.,354.)),(1.,a.elbow_right))
    a.arm_art='reading' if .17<q<.89 else 'reach'
    if q<.035 or q>.985:a.arm_art='rest'
    a.elbow_left=track(q,(0.,a.elbow_left),(.25,a.elbow_left),(.315,(160.,366.)),
        (.675,(160.,366.)),(.76,(161.,357.)),(.835,(161.,357.)),(.94,a.elbow_left),(1.,a.elbow_left))
    erase=track(q,(0.,0.),(.505,0.),(.525,1.),(.54,1.),(.555,0.),(1.,0.))
    target=phone_point(a,-15.+3*erase,6.+10*erase)
    # A full lift-off between distinct taps is visible even at desktop size.
    # During the pause the finger remains away; it never taps continuously.
    tapping=track(q,(0.,0.),(.33,0.),(.34,1.),(.46,1.),(.47,0.),(.55,0.),(.56,1.),(.655,1.),(.665,0.),(1.,0.))
    lift=10.-tapping*(1-math.cos((t-4.29)*math.tau/.65))*5
    lift=min(lift,10*(1-erase))  # Deliberate backspace press after the pause.
    target=(target[0]-.85*lift,target[1]+.52*lift)
    wrist=pointing_wrist(a.elbow_left,target,'index',-1)
    approach=track(q,(0.,0.),(.25,0.),(.315,1.),(.675,1.),(.715,0.),(1.,0.))
    a.left=mix(a.left,wrist,approach)
    if approach>.01:a.left_hand='index'
    hug=track(q,(0.,0.),(.715,0.),(.76,1.),(.835,1.),(.94,0.),(1.,0.))
    a.left=mix(a.left,phone_point(a,-15.,30.),hug)
    if hug>.4:a.left_hand='grip'
    if q<.25 or q>.94:a.arm_art_left='rest'
    a.phone_lines=int(track(q,(0.,0.),(.33,0.),(.47,3.),(.51,3.),(.55,1.),(.665,3.),(1.,3.)))
    a.head=track(q,(0.,0.),(.12,4.),(.28,6.),(.49,3.),(.55,7.),(.72,5.),(.8,9.),(1.,0.))
    a.gaze=(track(q,(0.,0.),(.23,2.),(.48,2.),(.515,-2.),(.55,2.),(.84,2.),(1.,0.)),
        track(q,(0.,0.),(.13,4.),(.3,5.),(.8,5.),(1.,0.)))
    a.blush=track(q,(0.,0.),(.2,0.),(.3,.35),(.5,.65),(.6,.5),(.8,1.),(1.,0.))
    a.mouth='smile' if .29<q<.49 or .62<q<.87 else 'neutral'
    a.brow=-.4 if .49<q<.55 else 0.
    a.hearts=track(q,(0.,0.),(.69,0.),(.77,.7),(.86,0.),(1.,0.))
    a.lean=-1.5*track(q,(0.,0.),(.2,1.),(.84,1.),(1.,0.))
    a.phase='retrieve' if q<.23 else 'read' if q<.33 else 'type' if q<.47 else 'pause_erase' if q<.55 else 'retype' if q<.68 else 'hug' if q<.86 else 'stow'
    return a


def wand_pose(action,q,t,variant):
    a=gesture('wand_grip',q,.24,.78);v=1 if action in ('cast','avada') else variant%4
    a.wand=.005<q<.995;a.left_hand='wand_grip' if a.wand else 'relaxed'
    # Retrieve on the left of the robe, then hold the original drawn bent
    # sleeve. Keep the entire shaft to the left of the facial silhouette.
    a.left=track(q,(0.,(164.,379.)),(.09,(160.,385.)),(.24,(132.,294.)),
        (.38,(125.,287.)),(.56,(134.,297.)),(.72,(126.,289.)),(.82,(139.,317.)),(.94,(160.,385.)),(1.,(164.,379.)))
    a.elbow_left=track(q,(0.,(164.,342.)),(.09,(159.,350.)),(.24,(157.,335.)),
        (.56,(155.,338.)),(.78,(157.,335.)),(.94,(159.,350.)),(1.,(164.,342.)))
    a.arm_art_left='wand' if .16<q<.89 else 'reach' if .035<q<.985 else 'rest'
    angle_keys=[((.3,-112.),(.43,-126.),(.54,-108.),(.66,-119.)),
        ((.3,-113.),(.43,-136.),(.54,-107.),(.66,-118.)),
        ((.3,-116.),(.43,-128.),(.54,-110.),(.66,-125.)),
        ((.3,-110.),(.43,-132.),(.54,-114.),(.66,-122.))][v]
    a.wand_angle=track(q,(0.,90.),(.06,90.),(.14,180.),(.24,250.),
        *((u,angle+360) for u,angle in angle_keys),(.82,250.),(.9,180.),(.97,90.),(1.,90.))
    a.wand_angle-=360.  # Same physical angle, continuous with original-neutral preparation.
    a.hand_angle_left=track(q,(0.,0.),(.32,0.),(.43,-9.),(.54,7.),(.68,0.),(1.,0.))
    a.magic=track(q,(0.,0.),(.45,0.),(.52,1.),(.61,.65),(.69,0.),(1.,0.)) if v!=0 or action!='wand_play' else 0.
    a.pocket=q<.2 or q>.84;a.pocket_lip=385.
    a.gaze=(-3.,-2.) if .2<q<.8 else (0.,3.) if q<.2 else (0.,0.)
    a.head=track(q,(0.,0.),(.2,-3.),(.4,-5.),(.56,3. if v==2 else -3.),(.73,-2.),(1.,0.))
    a.mouth='open' if v==2 and .52<q<.64 else 'smile' if .66<q<.82 else 'neutral'
    a.lean=-1.5*track(q,(0.,0.),(.25,1.),(.78,1.),(1.,0.))
    if v==2:a.brow=-.6 if .52<q<.64 else 0.
    if action=='avada':a.magic_color='#77d56f';a.spell_text='«Авада Кедавра»' if .3<q<.78 else ''
    return a


def drawn_action(action,q,t,variant):
    env=track(q,(0.,0.),(.25,1.),(.75,1.),(1.,0.));v=variant%3
    if action=='phone_solvnox':return phone_pose(q,t)
    if action in ('wand_play','cast','avada'):return wand_pose(action,q,t,variant)
    if action=='shy':
        a=gesture(('chest','cheek','chin')[v],q,.32,.70)
        a.blush=env;a.gaze=(2*env,4*env);a.head=6*env;a.lean=-1.5*env
        a.mouth='smile' if .45<q<.84 else 'neutral'
        a.head_drop=2*env;a.left_lift=a.right_lift=-env
        fidget=track(q,(0.,0.),(.33,0.),(.39,1.),(.65,1.),(.71,0.),(1.,0.))
        a.left=(a.left[0]+math.sin(t*3.5)*1.4*fidget,a.left[1]+math.sin(t*3.5)*fidget)
        a.gaze=(a.gaze[0]+math.sin(t*.9)*env,a.gaze[1]);a.head+=math.sin(t*1.3)*.5*env
    elif action=='annoyed':
        a=gesture(('folded','explain','hip')[v],q,.29,.72)
        a.brow=env;a.mouth='pout' if env>.1 else 'neutral';a.lean=-2*env
        if v==0:
            a.leg_right=track(q,(0.,0.),(.36,0.),(.42,-11.),(.48,0.),(.54,-5.),(.60,0.),(1.,0.))
        elif v==1:
            a.right_hand='index' if env>.6 else 'relaxed'
            a.hand_angle_right=math.sin(t*4)*7*env
            a.mouth='open' if .34<q<.65 and int(t*5)%2 else a.mouth
        else:
            a.head=track(q,(0.,0.),(.27,-8.),(.48,-8.),(.62,-4.),(.78,-4.),(1.,0.))
            a.gaze=track(q,(0.,(0.,0.)),(.28,(-4.,0.)),(.49,(-4.,0.)),(.62,(3.,0.)),(.77,(3.,0.)),(1.,(0.,0.)))
    elif action in ('daydream','thinking','working'):
        a=gesture('chin',q,.28,.77) if action=='daydream' else arm_pose_bank()['chin']
        strength=env if action=='daydream' else 1.
        a.head=-4*strength;a.gaze=(2*strength,-3*strength)
        a.blush=.4*env if action=='daydream' else 0.;a.mouth='smile' if action=='daydream' else 'focused'
        a.hearts=.4*env if action=='daydream' else 0.;a.lean=-2*strength
        if action=='working':a.gaze=(track(t%3,(0.,-3.),(1.1,3.),(1.3,-3.),(3.,3.)),3.)
        a.head+=math.sin(t*.9)*.5*strength
    elif action=='happy':
        a=gesture('explain',q,.25,.72);a.mouth='smile'
        a.hand_angle_right=math.sin(t*5)*10*env
        a.head=track(q,(0.,0.),(.25,-4.),(.48,2.),(.72,-2.),(1.,0.))
    elif action=='error':
        a=gesture('chest',q,.25,.75);a.mouth='pout';a.brow=env
        a.head=track(q,(0.,0.),(.2,-6.),(.4,5.),(.6,-4.),(.8,2.),(1.,0.))
    elif action=='yawn':
        a=gesture('chin',q,.28,.7);a.head=8*env;a.blink=env
        a.mouth='open' if .25<q<.75 else 'neutral'
    else:return None
    return a
