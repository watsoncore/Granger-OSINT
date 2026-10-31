"""Texture seams and portrait preservation are regressions, not artistic scores."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
import pytest
from PIL import Image,ImageChops
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from grangerpet.animation import SpriteLibrary
from grangerpet.articulated import HermioneRig,render_actor
from grangerpet.painted_arms import PaintedArms,triangle_transform
from grangerpet.hermione_pose_bank import arm_pose_bank

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def art():
    app=QApplication.instance() or QApplication([])
    lib=SpriteLibrary();painted=PaintedArms(ROOT/'grangerpet/assets/hermione-poses-v3')
    return app,lib,painted


def rgba(q):
    q=q.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes('RGBA',(q.width(),q.height()),bytes(q.constBits()))


@pytest.mark.parametrize('pose',['rest','cheek','reading','folded','chin','hip','wand','reach'])
def test_bind_pose_reprojection_has_no_internal_alpha_cracks(art,pose):
    _,lib,painted=art
    for side in ('left','right'):
        drawing=painted.drawings[pose,side]
        result=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied);result.fill(Qt.GlobalColor.transparent)
        expected=QImage(result);p=QPainter(expected)
        p.drawImage(QPointF(drawing.rect[0],drawing.rect[1]),drawing.sleeve);p.end()
        p=QPainter(result);p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
        drawing.draw_sleeve(p,drawing.bones);p.end()
        difference=ImageChops.difference(rgba(result).getchannel('A'),rgba(expected).getchannel('A'))
        assert difference.getbbox() is None,(pose,side,'alpha cracks in the texture mesh')


def test_painted_limbs_preserve_the_approved_eye_and_brow_region(art):
    _,lib,painted=art;s=lib.scenes
    old=HermioneRig(s.layers['base'],s.hair_repair,s.hair_fringe)
    new=HermioneRig(s.layers['base'],s.hair_repair,s.hair_fringe,painted)
    for name,a in arm_pose_bank(painted).items():
        s.hermione_rig=old;before=rgba(render_actor(lib,deepcopy(a),512)).crop((156,166,282,205))
        s.hermione_rig=new;after=rgba(render_actor(lib,deepcopy(a),512)).crop((156,166,282,205))
        assert before.tobytes()==after.tobytes(),name


def test_triangle_map_keeps_the_three_texture_anchors():
    source=((2.,3.),(11.,4.),(4.,17.));target=((20.,8.),(3.,11.),(8.,-5.))
    transform=triangle_transform(source,target)
    for first,second in zip(source,target):
        actual=transform.map(QPointF(*first))
        assert actual.x()==pytest.approx(second[0]) and actual.y()==pytest.approx(second[1])


@pytest.mark.parametrize('dpr',[1.,1.25,1.5,2.])
def test_scaled_triangle_clips_do_not_crack_opaque_fabric(art,dpr):
    _,lib,painted=art
    for drawing in painted.drawings.values():
        size=round(195*dpr)
        actual=QImage(size,size,QImage.Format.Format_ARGB32_Premultiplied);actual.fill(Qt.GlobalColor.transparent)
        expected=QImage(actual)
        for image,mesh in ((actual,True),(expected,False)):
            p=QPainter(image);p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
            p.scale(size/512,size/512)
            if mesh:drawing.draw_sleeve(p,drawing.bones)
            else:p.drawImage(QPointF(drawing.rect[0],drawing.rect[1]),drawing.sleeve)
            p.end()
        aa=rgba(actual).getchannel('A');ea=rgba(expected).getchannel('A')
        cracks=sum(a<240 and e>252 for a,e in zip(aa.tobytes(),ea.tobytes()))
        assert cracks==0,(dpr,drawing.rect,cracks)
