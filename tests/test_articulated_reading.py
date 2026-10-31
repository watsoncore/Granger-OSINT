"""Physical and narrative invariants, supplementing manual timeline review."""
import math
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from grangerpet.scene_pose import ik,reading_pose
from grangerpet.pet_life import PetLifeController


@pytest.mark.parametrize('variant',range(3))
def test_reading_is_closed_retrieval_open_scan_finger_turn_close_and_stow(variant):
    poses=[reading_pose(q,q*18,variant) for q in (.1,.3,.52,.7,.88,.96)]
    assert poses[0].book.visible and poses[0].book.opening==0
    assert poses[1].book.opening==1 and poses[1].gaze[1]>3
    assert all(p.blink==0 for p in poses)  # selected moments aren't blink frames
    turn=[reading_pose(i/1000,i*.018,variant) for i in range(450,670)]
    active=[p for p in turn if 0<=p.book.page<=1]
    assert len(active)>=99
    assert all(p.right_hand=='pinch' and math.dist(p.right,p.book.page_corner())<1e-6 for p in active)
    assert poses[-2].book.opening==0 and poses[-1].book.pocket
    assert not reading_pose(1,18,variant).book.visible


@pytest.mark.parametrize('variant',range(3))
def test_book_grips_reachable_and_continuous_without_hand_teleports(variant):
    previous=None
    for i in range(1801):
        a=reading_pose(i/1800,i/100,variant)
        for shoulder,wrist,side in (((171,293),a.left,-1),((281,294),a.right,1)):
            elbow,actual=ik(shoulder,wrist,side)
            assert math.dist(actual,wrist)<.1
            assert math.dist(shoulder,elbow)==pytest.approx(72)
            assert math.dist(elbow,actual)==pytest.approx(74)
        if previous:
            assert math.dist(a.left,previous.left)<4
            assert math.dist(a.right,previous.right)<4
            assert math.dist(a.book.center,previous.book.center)<3
        previous=a


def test_variant_latched_for_whole_action_and_invalid_values_rejected():
    life=PetLifeController(clock=lambda:100.)
    life.start_action('reading',variant=2)
    assert life.pose(101).variant==life.pose(112).variant==2
    life.finish()
    with pytest.raises(ValueError):life.start_action('reading',variant=3)


def test_downward_reading_eyes_stay_open_except_short_blinks():
    poses=[reading_pose(i/1800,i/100) for i in range(500,1300)]
    assert sum(a.blink>.1 for a in poses)/len(poses)<.04
    assert sum(a.gaze[1]>3 for a in poses)/len(poses)>.95


def test_direct_physical_resolution_premultiplied_alpha():
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.articulated import render_reading
    app=QApplication.instance() or QApplication([]);lib=SpriteLibrary()
    life=PetLifeController(clock=lambda:0.);life.start_action('reading',variant=0)
    for size,dpr in ((100,1.),(160,1.25),(195,1.5),(195,2.)):
        im=render_reading(lib,life.pose(7),size,dpr)
        assert im.width()==round(size*dpr) and im.devicePixelRatio()==dpr
        assert im.format()==QImage.Format.Format_ARGB32_Premultiplied
        assert im.pixelColor(0,0).alpha()==0
