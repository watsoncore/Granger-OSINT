"""Prop-aware preparation/return from the exact original wand-holding neutral."""
import math
from .scene_pose import ActorPose,track,smooth


def original_neutral():
    return ActorPose(arm_art='original',left=(132.,294.),elbow_left=(157.,335.),
        right=(365.,364.),elbow_right=(327.,338.),left_hand='wand_grip',wand=True,wand_angle=-119.)


def solo_sequence(q,t,make_pose,*,margin=.1):
    """Keep the main action contract; reserve explicit wand stow/retrieve time."""
    from .key_poses import interpolate
    from .hermione_pose_bank import arm_pose_bank
    q=max(0.,min(1.,q))
    if q in (0.,1.):
        a=original_neutral();a.source_idle=True;a.phase='original_neutral';return a
    if margin<=q<=1-margin:return make_pose((q-margin)/(1-2*margin),t)
    returning=q>1-margin
    u=(1-q)/margin if returning else q/margin
    start=original_neutral();pocket=original_neutral()
    pocket.left=(160.,385.);pocket.elbow_left=(159.,350.)
    pocket.right=(317.,379.);pocket.elbow_right=(308.,342.)
    pocket.wand_angle=-270.;pocket.pocket=True;pocket.pocket_lip=385.
    if u<=.8:
        a=interpolate(start,pocket,smooth(u/.8));a.arm_art='original'
        a.arm_art_left=a.arm_art_right='original';a.wand=True;a.pocket=True;a.pocket_lip=385.
        # Continuous leftward then downward arc; never swing across the face.
        a.wand_angle=-119.-151.*smooth(u/.8)
    else:
        rest=arm_pose_bank()['relaxed'];rest.wand_angle=-270.;pocket.wand=False;pocket.left_hand='relaxed'
        a=interpolate(pocket,rest,smooth((u-.8)/.2));a.wand=False
    a.source_idle=False;a.phase='retrieve_wand' if returning else 'stow_wand'
    a.head=2*math.sin(u*math.pi);a.gaze=(0.,a.head)
    return a
