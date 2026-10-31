"""Joint reach, exclusive dialogue turns, true shared-paper contact and timing."""
import math
import random
import pytest
from grangerpet.scene_pose import action_pose,ik,rotate,arm_points
from grangerpet.conversation_pose import conversation_pose
from grangerpet.pet_life import LifePose,PetLifeController,SCENES


def life(name,q,variant=0):
    return LifePose(name,'',q,q*SCENES[name].duration,1,int(q*SCENES[name].duration*24),0,cameo=SCENES[name].cameo,variant=variant)


@pytest.mark.parametrize('name,count',[('shy',3),('annoyed',3),('wand_play',4),('phone_solvnox',1),('daydream',1)])
def test_solo_joint_reach_and_continuity(name,count):
    for variant in range(count):
        previous=None
        for i in range(1201):
            a=action_pose(name,i/1200,i*SCENES[name].duration/1200,variant)
            for side in (-1,1):
                shoulder,elbow,wrist=arm_points(a,side)
                assert wrist==(a.left if side<0 else a.right)
                assert 15<math.dist(shoulder,elbow)<92,(name,variant,i,'upper')
                assert 15<math.dist(elbow,wrist)<92,(name,variant,i,'forearm')
            if previous:
                assert math.dist(a.left,previous.left)<8,(name,variant,i,'left')
                assert math.dist(a.right,previous.right)<8,(name,variant,i,'right')
                for side in (-1,1):assert math.dist(arm_points(a,side)[1],arm_points(previous,side)[1])<8,(name,variant,i,'elbow')
            previous=a


@pytest.mark.parametrize('separation,mirror',[(-260,True),(-346,True),(260,False),(346,False)])
def test_one_note_has_both_grips_in_contact_before_ownership_changes(separation,mirror):
    for q in (.445,.46,.48):
        scene=conversation_pose(life('ron_note',q),separation,mirror)
        assert scene.note_owner=='transferring' and scene.note is not None
        direction=-1 if separation<0 else 1
        hero_hand=scene.hero.left if direction<0 else scene.hero.right
        guest_hand=scene.guest.left
        guest_world=(separation+(512-guest_hand[0] if mirror else guest_hand[0]),guest_hand[1])
        for actual,edge in ((hero_hand,-direction*28),(guest_world,direction*28)):
            dx,dy=rotate((edge,7.),scene.note_angle);expected=(scene.note[0]+dx,scene.note[1]+dy)
            assert math.dist(actual,expected)<1e-6
    assert conversation_pose(life('ron_note',.4),separation,mirror).note_owner=='held_by_ron'
    assert conversation_pose(life('ron_note',.52),separation,mirror).note_owner=='held_by_hermione'


@pytest.mark.parametrize('name,count',[('malfoy',2),('harry',2),('ron_chat',2),('ron_note',1)])
def test_each_conversation_has_alternating_speaker_and_independent_reactions(name,count):
    for variant in range(count):
        speakers=[];hero_heads=set();guest_heads=set()
        for i in range(1001):
            scene=conversation_pose(life(name,i/1000,variant))
            if scene.speaker and (not speakers or speakers[-1]!=scene.speaker):speakers.append(scene.speaker)
            assert scene.speaker in ('','hero','guest')
            hero_heads.add(round(scene.hero.head,2));guest_heads.add(round(scene.guest.head,2))
        assert set(speakers)=={'hero','guest'}
        assert len(hero_heads)>20 and len(guest_heads)>20
        if name=='malfoy' and variant==1:assert len(speakers)>=6


def test_guest_deadlines_observable_bounded_and_do_not_use_windows_input():
    for seed in range(8):
        clock=[0.];c=PetLifeController(clock=lambda:clock[0],rng=random.Random(seed));events=[];before=''
        assert 120<=c.next_guest_due<=240
        for second in range(1,7201):
            clock[0]=second;c.update(system_idle=0,context='working')
            if c.action in SCENES and c.action!=before and SCENES[c.action].cameo:events.append((second,c.action))
            before=c.action
        assert events and 120<=events[0][0]<=280
        assert all(300<=b[0]-a[0]<=660 for a,b in zip(events,events[1:]))
        assert c.last_activity==0


def test_new_rig_drag_bends_knees_and_retains_face_dimensions():
    from grangerpet.physics import DragPose
    up=action_pose('idle',.2,1,physics=DragPose(tuck=1,held=True))
    down=action_pose('idle',.2,1,physics=DragPose(squash=1,held=True))
    assert abs(up.knee_left)>abs(down.knee_left)>0
    assert up.knee_left==-up.knee_right and down.knee_left==-down.knee_right
    assert up.pivot==down.pivot==(229.,267.)


def test_legacy_actions_remain_natural_without_travel_during_work():
    clock=[0.];c=PetLifeController(clock=lambda:clock[0],rng=random.Random(12));seen=set()
    for second in range(0,200000,5):
        clock[0]=second;c.update(allow_travel=False)
        assert c.action not in ('leave','away','return')
        if c.action:seen.add(c.action)
    assert {'cast','avada','yawn','sleep','wake'}<=seen


def test_folded_sleeves_do_not_enclose_transparent_holes():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PIL import Image,ImageDraw
    from PySide6.QtGui import QPainter,QImage
    from PySide6.QtWidgets import QApplication
    from grangerpet.articulated import HermioneRig,image
    app=QApplication.instance() or QApplication([])
    for shoulder,elbow,wrist in (((181,285),(246,256),(178,268)),((292,285),(222,268),(300,271))):
        im=image(512);p=QPainter(im);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        HermioneRig.arm(p,shoulder,elbow,wrist);p.end();im=im.convertToFormat(QImage.Format.Format_RGBA8888)
        alpha=Image.frombytes('RGBA',(512,512),bytes(im.constBits())).getchannel('A').point(lambda a:255 if a>32 else 0)
        ImageDraw.floodfill(alpha,(0,0),128,border=255)
        assert alpha.histogram()[0]==0


def test_guest_layers_exclude_original_hands_and_shoulder_fragments():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.guest_rig import GuestRig
    app=QApplication.instance() or QApplication([]);lib=SpriteLibrary()
    for name in ('draco','harry','ron'):
        rig=GuestRig(lib.scenes.cameos[name],name)
        for y in range(252,306):
            for x in range(160,201):
                color=rig.torso.pixelColor(x,y)
                assert not (color.alpha()>32 and color.red()>180 and color.green()>130 and color.blue()>100)
        if name!='ron':assert all(rig.head.pixelColor(x,y).alpha()==0 for x in range(512) for y in range(239,260))


@pytest.mark.parametrize('name,count',[('malfoy',2),('harry',2),('ron_chat',2),('ron_note',1)])
def test_directed_conversation_uses_authored_elbows_without_overstretch(name,count):
    for variant in range(count):
        for separation,mirror in ((-260,True),(-346,True),(260,False),(346,False)):
            previous=None
            for i in range(301):
                scene=conversation_pose(life(name,i/300,variant),separation,mirror)
                for actor,guest in ((scene.hero,False),(scene.guest,True)):
                    for side in (-1,1):
                        s,e,w=arm_points(actor,side,guest=guest)
                        assert 15<math.dist(s,e)<95,(name,variant,i,separation,'upper',s,e)
                        assert 15<math.dist(e,w)<95,(name,variant,i,separation,'forearm',e,w)
                if previous:
                    assert math.dist(scene.hero.left,previous.hero.left)<22
                    assert math.dist(scene.guest.left,previous.guest.left)<22
                    for actor,old,guest in ((scene.hero,previous.hero,False),(scene.guest,previous.guest,True)):
                        for side in (-1,1):assert math.dist(arm_points(actor,side,guest=guest)[1],arm_points(old,side,guest=guest)[1])<22,(name,variant,i,'elbow')
                previous=scene
