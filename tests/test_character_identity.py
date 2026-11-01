"""An identity gate independent of joint reach, animation hashes or art scores."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from grangerpet.animation import SpriteLibrary
from grangerpet.articulated import render_actor,HermioneRig
from grangerpet.scene_pose import action_pose
from grangerpet.scene_pose import ActorPose
from grangerpet.original_face import OriginalFace
from grangerpet.original_idle import OriginalIdle
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QPainter
from grangerpet.original_identity import verify_original_assets

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'grangerpet/assets'
MANIFEST=json.loads((ASSETS/'original-hermione/identity.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('name,digest',MANIFEST['immutable_files'].items())
def test_historical_user_art_is_unchanged(name,digest):
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest


@pytest.fixture(scope='module')
def app():
    application=QApplication.instance() or QApplication([])
    return application


def rgba(image):
    converted=image.convertToFormat(QImage.Format.Format_RGBA8888)
    return bytes(converted.constBits())


def test_neutral_production_restores_exact_historical_atlas_and_high_dpi_face(app):
    lib=SpriteLibrary();neutral=action_pose('idle',0.,0.)
    assert rgba(render_actor(lib,neutral,256))==rgba(lib.frames['idle'][0])
    original=QImage(str(ASSETS/'character.png'))
    actual=render_actor(lib,neutral,512)
    # Eyes/brows/nose and the original open neutral mouth, not a new vector face.
    for x,y,w,h in ((155,165,129,43),(204,207,35,35)):
        assert rgba(actual.copy(x,y,w,h))==rgba(original.copy(x,y,w,h))


def test_derived_body_cannot_replace_the_original_head(app):
    lib=SpriteLibrary()
    rig=HermioneRig(lib.scenes.layers['base'],lib.scenes.hair_repair,lib.scenes.hair_fringe)
    assert rgba(rig.head)==rgba(lib.scenes.layers['head'])
    assert not rig.curls


def test_identity_guard_rejects_accidental_master_replacement(tmp_path):
    target=tmp_path/'assets';shutil.copytree(ASSETS,target)
    (target/'character.png').write_bytes(b'replaced master')
    with pytest.raises(ValueError,match='character.png'):verify_original_assets(target)


@pytest.mark.parametrize('script,target',[('create_wand_animations.py',ASSETS),('build_pet_scene_assets.py',ASSETS/'scenes')])
def test_generators_refuse_to_overwrite_protected_originals(script,target):
    result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),'--output',str(target)],capture_output=True,text=True)
    assert result.returncode!=0 and 'Refusing to overwrite' in result.stdout+result.stderr
    verify_original_assets(ASSETS)


def test_original_idle_layers_recompose_the_historical_neutral(app):
    lib=SpriteLibrary();frame=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied);frame.fill(Qt.GlobalColor.transparent)
    p=QPainter(frame);p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
    OriginalIdle(lib.scenes.layers).draw(p,ActorPose());p.end()
    assert rgba(frame)==rgba(lib.scenes.original_neutral)


def test_blink_restores_the_exact_source_without_mutating_it(app):
    lib=SpriteLibrary();head=lib.scenes.layers['head'];original=rgba(head);face=OriginalFace(lib.scenes.layers['base'])
    for blink in (0.,.25,.5,1.,.5,.25,0.):
        frame=face.image(ActorPose(blink=blink))
        assert rgba(frame)[3::4]==original[3::4]  # No alpha halo or head-edge flicker.
        if blink==0:assert rgba(frame)==original
        if blink>.35:assert rgba(frame)!=original  # A real closed cel is present.
    assert rgba(head)==original


@pytest.mark.parametrize('gaze',[(-5.,0.),(5.,0.),(0.,6.),(0.,-4.)])
def test_gaze_cannot_translate_eye_contours_or_change_the_iris_rim(app,gaze):
    lib=SpriteLibrary();head=lib.scenes.layers['head'];face=OriginalFace(lib.scenes.layers['base'])
    frame=face.image(ActorPose(gaze=gaze))
    before,after=rgba(head),rgba(frame)
    assert before!=after
    for y in range(160,212):
        for x in range(150,290):
            if not any(area.contains(QPointF(x+.5,y+.5)) for area in face.interiors):
                i=(y*512+x)*4;assert before[i:i+4]==after[i:i+4]


def test_original_idle_breathes_without_moving_its_feet(app):
    lib=SpriteLibrary();first=render_actor(lib,action_pose('idle',0,0),512)
    breathing=render_actor(lib,action_pose('idle',.1,.35),512)
    assert rgba(first)!=rgba(breathing)
    assert rgba(first.copy(0,420,512,92))==rgba(breathing.copy(0,420,512,92))


def test_motion_separation_keeps_literal_original_face_and_bangs(app):
    lib=SpriteLibrary();rig=HermioneRig(lib.scenes.layers['base'])
    for rect in ((150,154,138,95),(145,60,150,100)):
        assert rgba(rig.motion_head.copy(*rect))==rgba(rig.head.copy(*rect))
    assert rgba(rig.motion_face.image(ActorPose()).copy(150,154,138,95))==rgba(rig.head.copy(150,154,138,95))
