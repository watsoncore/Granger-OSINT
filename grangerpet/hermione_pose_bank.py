"""Ten curated prop-free key poses, binding finished artwork to its real joints."""
import math
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from .scene_pose import ActorPose,smooth


@lru_cache(maxsize=1)
def pose_spec():
    return json.loads((Path(__file__).parent/'assets/hermione-poses-v3/rig.json').read_text(encoding='utf-8'))


def arm_pose_bank(painted=None):
    specs=painted.spec if painted else pose_spec()
    def bind(name):
        spec=specs[name]
        return ActorPose(arm_art=name,left=tuple(spec['left']['bones'][2]),right=tuple(spec['right']['bones'][2]),
            elbow_left=tuple(spec['left']['bones'][1]),elbow_right=tuple(spec['right']['bones'][1]))
    rest=bind('rest');chest=bind('cheek');chest.arm_art_right='rest'
    chest.right=rest.right;chest.elbow_right=rest.elbow_right
    phone=bind('reading');phone.left=(220.,347.);phone.elbow_left=(180.,366.)
    phone.right=(267.,354.);phone.elbow_right=(310.,355.);phone.left_hand='index'
    wand=bind('wand');wand.left_hand='wand_grip'
    gesture=bind('reading');gesture.arm_art_left='rest';gesture.left=rest.left;gesture.elbow_left=rest.elbow_left
    gesture.right=(331.,288.);gesture.elbow_right=(326.,337.)
    return {'relaxed':rest,'chest':chest,'cheek':bind('cheek'),'chin':bind('chin'),'hip':bind('hip'),
        'folded':bind('folded'),'book_hold':bind('reading'),'phone_hold':phone,'wand_grip':wand,'explain':gesture}


def pose_transition(rest,target,t,painted=None):
    """Route large raises through an actual drawn preparation sleeve pose."""
    from .key_poses import interpolate
    if target is rest:return deepcopy(rest)
    def large_bend(side):
        first=getattr(rest,side);fe=getattr(rest,'elbow_'+side)
        last=getattr(target,side);le=getattr(target,'elbow_'+side)
        delta=math.atan2(last[1]-le[1],last[0]-le[0])-math.atan2(first[1]-fe[1],first[0]-fe[0])
        return abs(math.atan2(math.sin(delta),math.cos(delta)))>math.radians(80)
    needs=[large_bend('left'),large_bend('right')]
    if not any(needs):return interpolate(rest,target,smooth(t))
    spec=(painted.spec if painted else pose_spec())['reach'];mid=deepcopy(rest);mid.arm_art='reach'
    for side,raised in zip(('left','right'),needs):
        if raised:
            setattr(mid,side,tuple(spec[side]['bones'][2]));setattr(mid,'elbow_'+side,tuple(spec[side]['bones'][1]))
        else:setattr(mid,'arm_art_'+side,'rest')
    if target.left_hand=='wand_grip':
        mid.arm_art_left='wand';mid.left=(132.,357.);mid.elbow_left=(161.,350.);mid.left_hand='wand_grip'
    if t<.45:return interpolate(rest,mid,smooth(t/.45))
    return interpolate(mid,target,smooth((t-.45)/.55))
