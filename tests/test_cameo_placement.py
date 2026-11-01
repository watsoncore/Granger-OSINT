"""Actual stage visibility in the narrow HUD and interruption position safety."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from grangerpet.config import Settings,SettingsStore
from grangerpet.pet import PetWindow
from grangerpet.pet_cameo import pair_placement
from grangerpet.pet_life import LifePose


@pytest.mark.parametrize('size',[100,160,195])
def test_narrow_hud_stage_actually_paints_both_actors(tmp_path,size):
    app=QApplication.instance() or QApplication([])
    pet=PetWindow(Settings(size=size,ai_provider='none'),SettingsStore(tmp_path/'settings.json'))
    try:
        pet.frame_timer.stop();pet.cursor_timer.stop();pet.show()
        box=QRect(1281,118,241,240);pet._dock_bounds=box;pet.move(1315,118)
        pose=LifePose('malfoy','',.4,3.6,1,86,0,cameo='draco')
        pet.cameo.update_pose(pose)
        assert pet.cameo.isVisible() and pet.cameo.hero_pose is not None
        assert not pet.cameo.image.isNull()
        target,guest,_=pair_placement(box,size,pet._padding,1315)
        for x,left,right in ((target,.09,.91),(guest,.21,.80)):
            assert box.left()+4<=x+pet._padding+round(size*left)
            assert x+pet._padding+round(size*right)<=box.right()-4
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()


def test_actual_guest_drag_detaches_stage_home_and_keeps_user_position(tmp_path):
    app=QApplication.instance() or QApplication([])
    pet=PetWindow(Settings(size=160,ai_provider='none'),SettingsStore(tmp_path/'settings.json'))
    try:
        pet.frame_timer.stop();pet.cursor_timer.stop();pet.show();pet.move(100,100)
        pet.cameo.home=QPoint(80,100)
        point=QPoint(pet._padding+80,pet._padding+115)
        QTest.mousePress(pet,Qt.MouseButton.LeftButton,pos=point)
        pet._drag_to(pet._pressed_at+QPoint(75,45),'test_native_event')
        assert pet._dragging and pet.cameo.home is None
        pet._finish_drag('test_release');placed=QPoint(pet.pos())
        pet.cameo.update_pose(LifePose('','',0,0,0,0,0))
        assert pet.pos()==placed and not pet.cameo.isVisible()
        assert QPoint(pet.settings.x,pet.settings.y)==placed
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()


def test_articulated_transition_moves_one_pose_without_old_bitmap_ghosts(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtGui import QColor
    from grangerpet.scene_pose import action_pose
    app=QApplication.instance() or QApplication([])
    pet=PetWindow(Settings(size=160,ai_provider='none'),SettingsStore(tmp_path/'settings.json'))
    try:
        pet.frame_timer.stop();pet.cursor_timer.stop();pet.show()
        pet._actor_pose=action_pose('working',.4,2)
        old=pet._actor_pose.right
        pet._rendered.fill(QColor('magenta'))
        clock=[100.];monkeypatch.setattr('grangerpet.pet.time',SimpleNamespace(monotonic=lambda:clock[0]))
        pet._begin_transition('idle');clock[0]+=.08
        target=action_pose('idle',.3,2)
        halfway=pet._transition_actor(target)
        assert not halfway.source_idle  # Actual renderer must use the moving joints.
        assert min(old[1],target.right[1])<halfway.right[1]<max(old[1],target.right[1])
        assert pet._previous.isNull()
        pet._draw_frame(force=True,life_pose=LifePose('','',0,0,0,0,0))
        assert pet._rendered.pixelColor(0,0).alpha()==0
        assert any(pet._rendered.pixelColor(x,y).alpha()>250 for y in range(0,pet._rendered.height(),8)
                   for x in range(0,pet._rendered.width(),8))
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()
