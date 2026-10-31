"""Authored 2D conversation key drawings, expressed as editable joint poses.

Elbows are drawn deliberately for each silhouette rather than choosing an IK
branch near a folded shoulder. Projected limb shortening is foreshortening;
hands/props remain anchored. Face artwork is unchanged.
"""
from copy import deepcopy
from dataclasses import fields
from .scene_pose import ActorPose,mix,smooth,polar_between


def hero(**changes):
    a=ActorPose(elbow_left=(136.,340.),elbow_right=(316.,340.))
    for key,value in changes.items():setattr(a,key,value)
    return a


def guest(**changes):
    a=ActorPose(left=(159.,385.),right=(319.,385.),elbow_left=(169.,338.),elbow_right=(317.,338.),gaze=(-5.,0.))
    for key,value in changes.items():setattr(a,key,value)
    return a


H={
    'rest':hero(),
    'turn':hero(turn=-1,lean=-4,head=-8,gaze=(-5.,0.),left=(163.,365.),right=(301.,375.),
        elbow_left=(127.,331.),elbow_right=(320.,335.),leg_left=-5,leg_right=3),
    'explain':hero(turn=-1,lean=-4,head=-5,gaze=(-5.,0.),left=(140.,310.),right=(303.,300.),
        elbow_left=(126.,350.),elbow_right=(325.,344.),left_hand='palm',right_hand='palm',hand_angle_left=-30,hand_angle_right=25,
        leg_left=-5,leg_right=5),
    'point':hero(turn=-1,lean=-3,head=-7,gaze=(-5.,0.),left=(125.,262.),right=(292.,369.),
        elbow_left=(128.,325.),elbow_right=(316.,333.),left_hand='index',hand_angle_left=-25,leg_left=-6,leg_right=6),
    'open':hero(turn=-.5,lean=-2,head=-3,gaze=(-5.,0.),left=(105.,322.),right=(331.,323.),
        elbow_left=(115.,355.),elbow_right=(315.,366.),left_hand='palm',right_hand='palm',hand_angle_left=-65,hand_angle_right=65,
        leg_left=-7,leg_right=7),
    'listen':hero(turn=-1,lean=-1,head=-6,gaze=(-5.,0.),left=(215.,336.),right=(245.,336.),
        elbow_left=(158.,360.),elbow_right=(303.,357.),mouth='smile'),
    'wave':hero(turn=-.7,lean=-2,head=-4,gaze=(-5.,0.),left=(137.,257.),elbow_left=(124.,321.),
        left_hand='palm',hand_angle_left=-12,mouth='smile',leg_left=-3,leg_right=4),
    'reject':hero(turn=-1,lean=4,head=6,gaze=(-5.,0.),left=(143.,280.),right=(292.,369.),
        elbow_left=(124.,339.),elbow_right=(316.,333.),left_hand='palm',hand_angle_left=-20,brow=1,mouth='pout',leg_left=4,leg_right=-4),
    'cross':hero(turn=-.5,lean=2,head=-7,gaze=(-5.,0.),left=(264.,323.),right=(189.,333.),
        elbow_left=(184.,348.),elbow_right=(264.,365.),brow=1,mouth='pout',leg_left=5,leg_right=-5),
    'stomp':hero(turn=-.7,lean=4,head=-8,gaze=(-5.,0.),left=(252.,320.),right=(194.,328.),
        elbow_left=(177.,346.),elbow_right=(264.,360.),brow=1,mouth='pout',leg_left=4,leg_right=-20,shift=(0.,-3.)),
    'retort':hero(turn=-1,lean=-5,head=-8,gaze=(-5.,0.),left=(130.,292.),right=(285.,367.),
        elbow_left=(126.,349.),elbow_right=(316.,339.),left_hand='grip',brow=1,mouth='pout',wand=True,wand_angle=-150,
        leg_left=-8,leg_right=8),
    'draw_wand':hero(turn=-.7,lean=1,head=-4,gaze=(-5.,0.),left=(279.,398.),right=(285.,367.),
        elbow_left=(226.,348.),elbow_right=(316.,339.),left_hand='grip',brow=1,mouth='pout',wand=True,wand_angle=90,pocket=True),
    'calm':hero(head=-2,right=(301.,233.),elbow_right=(326.,306.),mouth='smile'),
    'friendly':hero(turn=-.5,head=-4,gaze=(-5.,0.),left=(190.,329.),right=(254.,328.),
        elbow_left=(143.,355.),elbow_right=(310.,354.),mouth='smile',leg_left=-3,leg_right=3),
}
G={
    'rest':guest(),
    'turn':guest(turn=-1,head=-8,lean=-3,left=(156.,362.),right=(311.,370.),
        elbow_left=(160.,334.),elbow_right=(322.,335.),leg_left=-4,leg_right=5),
    'wave':guest(turn=-.8,head=-5,lean=-2,left=(139.,267.),elbow_left=(150.,332.),
        left_hand='palm',hand_angle_left=-10,leg_left=-3,leg_right=3,mouth='smile'),
    'provoke':guest(turn=-1,head=-7,lean=-5,left=(122.,285.),right=(303.,356.),
        elbow_left=(139.,343.),elbow_right=(322.,329.),left_hand='index',hand_angle_left=-45,brow=-.5,mouth='smile',leg_left=-5,leg_right=5),
    'shrug':guest(turn=-.5,head=5,lean=3,left=(155.,276.),right=(328.,279.),
        elbow_left=(143.,337.),elbow_right=(328.,341.),left_hand='palm',right_hand='palm',
        hand_angle_left=-40,hand_angle_right=40,brow=-.5,mouth='smile',leg_left=4,leg_right=-4),
    'think':guest(turn=-1,head=7,lean=-4,left=(225.,249.),elbow_left=(163.,307.),mouth='neutral'),
    'listen':guest(turn=-1,head=6,lean=-2,left=(219.,338.),right=(253.,340.),
        elbow_left=(167.,351.),elbow_right=(318.,352.)),
    'nod':guest(turn=-1,head=11,head_drop=3,lean=-4,left=(219.,338.),right=(253.,340.),
        elbow_left=(167.,351.),elbow_right=(318.,352.)),
    'reply':guest(turn=-1,head=-6,lean=-4,left=(117.,316.),right=(301.,358.),
        elbow_left=(153.,357.),elbow_right=(318.,337.),left_hand='palm',hand_angle_left=-65,leg_left=-6,leg_right=6),
    'retreat':guest(turn=.5,head=9,lean=6,left=(169.,366.),right=(316.,363.),
        elbow_left=(158.,331.),elbow_right=(324.,331.),gaze=(3.,0.),leg_left=-14,leg_right=10,shift=(24.,0.)),
    'glasses':guest(turn=-1,head=-3,lean=-2,left=(193.,207.),elbow_left=(165.,269.),left_hand='index',mouth='smile'),
    'friendly':guest(turn=-.5,head=-4,lean=-2,left=(183.,324.),right=(279.,326.),
        elbow_left=(151.,349.),elbow_right=(320.,349.),mouth='smile',leg_left=-3,leg_right=3),
}


def interpolate(a,b,t):
    result=deepcopy(a)
    for field in fields(ActorPose):
        x,y=getattr(a,field.name),getattr(b,field.name)
        if isinstance(x,bool) or isinstance(x,str):setattr(result,field.name,y if t>=.5 else x)
        elif isinstance(x,(float,int)) and isinstance(y,(float,int)):setattr(result,field.name,mix(x,y,t))
        elif isinstance(x,tuple) and isinstance(y,tuple):setattr(result,field.name,mix(x,y,t))
    for side in ('left','right'):
        first,second=getattr(a,'elbow_'+side),getattr(b,'elbow_'+side)
        wa,wb,w=getattr(a,side),getattr(b,side),getattr(result,side)
        vector=polar_between((first[0]-wa[0],first[1]-wa[1]),(second[0]-wb[0],second[1]-wb[1]),t)
        setattr(result,'elbow_'+side,(w[0]+vector[0],w[1]+vector[1]))
    result.wand_angle=a.wand_angle+((b.wand_angle-a.wand_angle+180)%360-180)*t
    return result


def drawing_track(q,bank,*keys):
    if q<=keys[0][0]:return deepcopy(bank[keys[0][1]])
    for (a,first),(b,second) in zip(keys,keys[1:]):
        if q<=b:return interpolate(bank[first],bank[second],smooth((q-a)/(b-a)))
    return deepcopy(bank[keys[-1][1]])


def face_other_side(a):
    # Mirror gesture offsets around the asymmetric approved resting hands,
    # retaining the same neutral pose when a conversation changes sides.
    a.left,a.right=(475-a.right[0],a.right[1]),(475-a.left[0],a.left[1])
    a.elbow_left,a.elbow_right=(452-a.elbow_right[0],a.elbow_right[1]),(452-a.elbow_left[0],a.elbow_left[1])
    a.left_hand,a.right_hand=a.right_hand,a.left_hand
    a.hand_angle_left,a.hand_angle_right=-a.hand_angle_right,-a.hand_angle_left
    a.head=-a.head;a.lean=-a.lean;a.turn=-a.turn;a.gaze=(-a.gaze[0],a.gaze[1]);a.shift=(-a.shift[0],a.shift[1])
    a.leg_left,a.leg_right=-a.leg_right,-a.leg_left
    if a.wand:a.wand=False;a.right_hand='index'
    return a
