"""Authored phone surface, raster occlusion and visible repeated contact beats."""
from collections import Counter
from copy import deepcopy
import math
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QPainter,QPainterPath,QTransform
from PySide6.QtWidgets import QApplication
from grangerpet.scene_pose import ActorPose,action_pose
from grangerpet.phone_scene import TAPS,PhoneArt,phone_pose,contact_model,geometry
from grangerpet.articulated import image,render_actor
from grangerpet.animation import SpriteLibrary
from grangerpet.original_face import OriginalFace


@pytest.fixture(scope='module')
def art():
    app=QApplication.instance() or QApplication([])
    return app,SpriteLibrary(),PhoneArt()


def screen_path(points):
    p=QPainterPath(QPointF(*points[0]))
    for v in points[1:]:p.lineTo(*v)
    p.closeSubpath();return p


def test_every_authored_type_delete_retype_and_send_press_hits_glass(art):
    _,_,phone=art
    for q,_,_ in TAPS:
        a=phone_pose(q,q*13);c=contact_model(a)
        assert screen_path(c.phone_screen_geometry).contains(QPointF(*c.tap_target))
        assert math.dist(c.typing_fingertip,c.tap_target)<1e-8
        base=image(512);p=QPainter(base);phone.device(p,a);p.end()
        over=image(512);p=QPainter(over);phone.device(p,a);phone.hand(p,a,-1,front=True);p.end()
        x,y=map(round,c.tap_target)
        # The actual drawn glass, then the actual opaque finger contour/pad,
        # rather than a contact marker painted beside the case.
        glass=base.pixelColor(x,y);finger=over.pixelColor(x,y)
        assert glass.green()>glass.red()
        assert finger!=glass and finger.red()>finger.green()


def test_24fps_movie_contains_four_type_two_delete_four_retype_one_send_contacts():
    contacts=[];last=False
    for frame in range(313):
        q=frame/312;a=action_pose('phone_solvnox',q,q*13)
        down=a.phone_style=='solvnox' and a.phone_press>.95
        if down and not last:contacts.append(a.phase)
        last=down
    assert Counter(contacts)=={'type':4,'erase':2,'retype':4,'send':1}


def test_visible_lift_is_not_a_static_pointing_pose():
    poses=[phone_pose(q/1000,q*.013) for q in range(300,840)]
    contacts=[contact_model(a) for a in poses]
    lift=max(math.dist(c.typing_fingertip,c.tap_target) for c in contacts)
    assert lift*195/512>8  # More than eight logical pixels at primary size.
    assert lift*100/512>4
    assert {a.left_hand for a in poses}=={'phone_hover','phone_press'}
    # The phone stays still while the finger/hand does the typing movement.
    assert len({a.phone_center for a in poses})==1
    assert len({tuple(round(v,2) for v in a.left) for a in poses})>100
    assert all(a.head_drop>10 and a.gaze[1]>5 for a in poses if a.phase in ('type','erase','retype','send'))


def test_final_send_is_distinct_from_backspace_and_returns_original_neutral(art):
    _,lib,_=art
    delete=phone_pose(TAPS[5][0],7);send=phone_pose(TAPS[-1][0],10)
    assert delete.phase=='erase' and send.phase=='send'
    assert math.dist(contact_model(delete).tap_target,contact_model(send).tap_target)>20
    before=render_actor(lib,action_pose('idle',0,0),256)
    after=render_actor(lib,action_pose('phone_solvnox',1,13),256)
    assert bytes(before.constBits())==bytes(after.constBits())


def test_actual_rig_draws_fingertip_in_front_of_glass(art):
    _,lib,_=art;q=TAPS[0][0];a=phone_pose(q,q*13);without=deepcopy(a);without.left_hand='phone_rest'
    full=render_actor(lib,a,512);bare=render_actor(lib,without,512)
    c=contact_model(a);root=QTransform();root.translate(*a.shift);root.translate(*a.pivot);root.rotate(a.lean);root.translate(-a.pivot[0],-a.pivot[1])
    point=root.map(QPointF(*c.tap_target));x,y=round(point.x()),round(point.y())
    assert full.pixelColor(x,y)!=bare.pixelColor(x,y)
    assert full.pixelColor(x,y).red()>full.pixelColor(x,y).green()


def test_phone_gaze_does_not_move_original_eye_contours_or_change_alpha(art):
    _,lib,_=art;face=OriginalFace(lib.scenes.layers['base']);head=face.head.convertToFormat(face.head.Format.Format_RGBA8888)
    a=ActorPose(phone_style='solvnox',gaze=(3,5.8));shifted=face.image(a).convertToFormat(head.Format.Format_RGBA8888)
    before,after=bytes(head.constBits()),bytes(shifted.constBits());assert before!=after
    assert before[3::4]==after[3::4]
    for y in range(154,249):
        for x in range(150,290):
            if not any(p.contains(QPointF(x+.5,y+.5)) for p in face.interiors):
                i=(y*512+x)*4;assert before[i:i+4]==after[i:i+4]
    face.image(ActorPose(phone_style='solvnox',blink=1))
    restored=face.image(ActorPose(phone_style='solvnox')).convertToFormat(head.Format.Format_RGBA8888)
    assert bytes(restored.constBits())==before
