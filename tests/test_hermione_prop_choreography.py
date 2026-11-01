"""Prop attachment and meaningful contact checks for the actual painted rig."""
import math
import pytest
from grangerpet.scene_pose import action_pose,hand_contact,rotate
from grangerpet.hermione_actions import phone_point


def test_raised_phone_is_supported_and_finger_lifts_between_taps():
    gaps=[]
    for i in range(330,470):
        q=i/1000;a=action_pose('phone_solvnox',q,q*13)
        assert a.phone and a.left_hand=='index'
        assert math.dist(a.right,phone_point(a,9.,40.))<1e-6
        gaps.append(math.dist(hand_contact(a,-1),phone_point(a,-8.,19.)))
    assert min(gaps)<.2 and max(gaps)>9
    pause=action_pose('phone_solvnox',.5,6.5)
    assert math.dist(hand_contact(pause,-1),phone_point(pause,-8.,19.))>9
    assert action_pose('phone_solvnox',.55,7.15).phone_lines==0
    assert action_pose('phone_solvnox',.67,8.71).phone_lines==3


@pytest.mark.parametrize('variant',range(4))
def test_wand_shaft_stays_outside_face_and_has_no_full_spin(variant):
    last=None
    for i in range(1001):
        q=i/1000;a=action_pose('wand_play',q,q*8,variant)
        tip=rotate((0.,-106.),a.wand_angle+90)
        # Every shaft point stays left of the unturned facial rectangle.
        for t in (0,.25,.5,.75,1):assert a.left[0]+tip[0]*t<165
        if last is not None:assert abs(a.wand_angle-last)<3
        last=a.wand_angle
    assert action_pose('wand_play',.4,3.2,variant).arm_art_left=='wand'


@pytest.mark.parametrize('action,count',[('shy',3),('annoyed',3),('daydream',1),('phone_solvnox',1),('wand_play',4)])
def test_solo_actions_return_to_same_painted_neutral_joints(action,count):
    rest=action_pose('idle',0,0)
    for variant in range(count):
        for q in (0.,1.):
            a=action_pose(action,q,q*13,variant)
            for side in ('left','right'):
                assert math.dist(getattr(a,side),getattr(rest,side))<1e-6
                assert math.dist(getattr(a,'elbow_'+side),getattr(rest,'elbow_'+side))<1e-6


def test_closed_lids_occlude_iris_instead_of_alpha_ghosting():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPainter
    from grangerpet.animation import SpriteLibrary
    from grangerpet.articulated import HermioneRig,image
    from grangerpet.scene_pose import ActorPose
    app=QApplication.instance() or QApplication([]);lib=SpriteLibrary();rig=HermioneRig(lib.scenes.layers['base'])
    im=image(512);p=QPainter(im);rig.face(p,ActorPose(blink=1.));p.end()
    # Above and below the moving lash, the original dark iris is fully hidden.
    for x,y in ((177,185),(177,202),(258,181),(258,196)):
        c=im.pixelColor(x,y)
        assert c.alpha()==rig.head.pixelColor(x,y).alpha() and c.red()>240 and c.green()>200


def test_secondary_curls_overlap_interior_cut_edges():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPainter
    from grangerpet.animation import SpriteLibrary
    from grangerpet.articulated import HermioneRig,image
    app=QApplication.instance() or QApplication([]);lib=SpriteLibrary()
    rig=HermioneRig(lib.scenes.layers['base'],lib.scenes.hair_repair,lib.scenes.hair_fringe)
    for angle in (-2.,0.,2.):
        im=image(512);p=QPainter(im);p.drawImage(0,0,rig.head)
        for index,(layer,root) in enumerate(rig.curls):
            p.save();p.translate(*root);p.rotate(angle*(1 if index==0 else -.8));p.translate(-root[0],-root[1]);p.drawImage(0,0,layer);p.restore()
        p.end()
        # These are interior hair pixels, not the moving outer silhouette.
        assert all(im.pixelColor(319,y).alpha()>240 for y in range(252,280))
