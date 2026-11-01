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
