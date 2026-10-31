"""Behavioral invariants for scene arbitration, rare scheduling and actual pixels."""
import os
import random
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from grangerpet.animation import SpriteLibrary
from grangerpet.pet_life import PetLifeController,SCENES
from grangerpet.pet_actions import action_frame
from grangerpet.scene_art import cameo_frame


def test_big_scenes_cannot_replace_each_other_without_explicit_interrupt():
    now=[0.];life=PetLifeController(clock=lambda:now[0])
    life.start_action('reading');started=life.started
    now[0]=2;life.start_action('malfoy')
    assert life.action=='reading' and life.started==started
    life.notify_activity(immediate=True);assert not life.active
    now[0]+=2;life.start_action('shy');assert life.action=='shy'


def test_hidden_or_system_block_does_not_invent_figure_activity():
    now=[0.];life=PetLifeController(clock=lambda:now[0]);deadline=life.next_due
    now[0]=200;life.update(available=False)
    assert life.last_activity==0 and life.next_due==deadline
    life.start_action('reading');now[0]+=1;life.update(available=False)
    assert not life.active and life.last_activity==0
    due=life.next_due;now[0]+=10;life.update(available=False)
    assert life.next_due==due


def test_rare_scene_cooldowns_and_no_repeats_over_simulated_three_days():
    now=[0.];life=PetLifeController(clock=lambda:now[0],rng=random.Random(199))
    observed=[];previous='';last={};last_guest=-1e9
    for _ in range(22000):
        now[0]+=12;before=life.action
        life.update(context='working',allow_travel=False)
        if life.active and life.action!=before:
            name=life.action
            if name not in SCENES:continue  # Sleep/away/wake/return are natural continuations.
            assert name!=previous;previous=name
            assert now[0]-last.get(name,-1e9)>=SCENES[name].cooldown
            last[name]=now[0]
            if SCENES[name].cameo:
                assert now[0]-last_guest>=300;last_guest=now[0]
            observed.append(name)
    assert {n for n,s in SCENES.items() if not s.travel}<=set(observed)


def test_no_room_blocks_cameos_and_work_context_favors_reading():
    now=[0.];life=PetLifeController(clock=lambda:now[0],rng=random.Random(55));counts={}
    for _ in range(5000):
        now[0]+=20;before=life.action;life.update(context='working',allow_cameo=False)
        if life.action and before!=life.action:
            assert not life.pose().cameo
            counts[life.action]=counts.get(life.action,0)+1
    assert counts['reading']>counts['shy']


@pytest.mark.parametrize('name',list(SCENES))
def test_every_scene_has_distinct_enter_active_exit_pixels_and_transparency(name):
    app=QApplication.instance() or QApplication([]);library=SpriteLibrary()
    now=[100.];life=PetLifeController(clock=lambda:now[0]);life.start_action(name)
    frames=[];phases=[]
    for at in (.1,life.duration*.4,life.duration-.2):
        now[0]=100+at;pose=life.pose();phases.append(pose.phase)
        image=action_frame(library,pose);frames.append(bytes(image.constBits()))
        assert image.hasAlphaChannel() and image.pixelColor(0,0).alpha()==0
        assert image.width()==256
        if pose.cameo:
            guest=cameo_frame(library,pose)
            assert not guest.isNull() and guest.pixelColor(0,0).alpha()==0
            from grangerpet.guest_rig import preview_pair
            frames[-1]=bytes(preview_pair(library,pose).constBits())
    assert phases==['enter','active','exit'] and len(set(frames))==3


def test_guest_window_is_owned_click_through_and_removed_after_interrupt(tmp_path,monkeypatch):
    from grangerpet.pet import PetWindow
    from grangerpet.config import Settings,SettingsStore
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('grangerpet.credentials.get_secret',lambda _: '')
    pet=PetWindow(Settings(size=100,cursor_reaction=False),SettingsStore(tmp_path/'settings.json'))
    pet.frame_timer.stop();pet.cursor_timer.stop();pet.show();app.processEvents()
    try:
        pet.move(400,250);home=pet.pos()
        pet.life.start_action('malfoy');pet.life.started-=2;pet._tick()
        assert pet.cameo.isVisible()
        assert pet.cameo.windowFlags()&Qt.WindowType.WindowTransparentForInput
        assert pet.cameo.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pet.notify_user_activity();pet.life.finish();pet._tick()
        assert not pet.cameo.isVisible() and pet.pos()==home
        assert pet.cameo.parentWidget() is pet
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()


def test_duplicate_press_cannot_lose_collar_identity(tmp_path,monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from grangerpet.pet import PetWindow
    from grangerpet.config import Settings,SettingsStore
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('grangerpet.credentials.get_secret',lambda _: '')
    pet=PetWindow(Settings(size=160),SettingsStore(tmp_path/'settings.json'))
    pet.frame_timer.stop();pet.cursor_timer.stop();pet.drag_timer.stop()
    try:
        point=QPoint(86,96)
        QTest.mousePress(pet,Qt.MouseButton.LeftButton,pos=point)
        origin=pet._pressed_at;assert pet._collar_grab and pet.physics.pose.held
        QTest.mousePress(pet,Qt.MouseButton.LeftButton,pos=QPoint(20,20))
        assert pet._pressed_at==origin and pet._collar_grab
        pet._finish_drag('test-capture-release')
        assert not pet.physics.pose.held and pet._pressed_at is None and not pet.drag_timer.isActive()
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()


def test_opening_workspace_during_cameo_keeps_original_desktop_home(tmp_path,monkeypatch):
    from PySide6.QtCore import QRect
    from grangerpet.pet import PetWindow
    from grangerpet.config import Settings,SettingsStore
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('grangerpet.credentials.get_secret',lambda _: '')
    pet=PetWindow(Settings(size=100,cursor_reaction=False),SettingsStore(tmp_path/'settings.json'))
    pet.frame_timer.stop();pet.cursor_timer.stop();pet.show();app.processEvents()
    try:
        pet.move(400,250);home=pet.pos()
        pet.life.start_action('malfoy');pet.life.started-=2;pet._tick()
        assert pet.pos()!=home and pet.cameo.home==home
        monkeypatch.setattr(pet.panel,'desktop_window_state',lambda:{'active':True,
            'geometry':QRect(0,0,1000,700),'dock':QRect(700,150,260,250)})
        pet._sync_overlay_placement()
        assert pet._dock_home==home
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()


def test_scale_during_cameo_keeps_the_feet_baseline(tmp_path,monkeypatch):
    from dataclasses import replace
    from grangerpet.pet import PetWindow
    from grangerpet.config import Settings,SettingsStore
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr('grangerpet.credentials.get_secret',lambda _: '')
    pet=PetWindow(Settings(size=100,cursor_reaction=False),SettingsStore(tmp_path/'settings.json'))
    pet.frame_timer.stop();pet.cursor_timer.stop();pet.show();app.processEvents()
    try:
        pet.move(400,250);foot=pet.y()+pet.height()
        pet.life.start_action('malfoy');pet.life.started-=2;pet._tick()
        pet.apply_settings(replace(pet.settings,size=195));pet._tick()
        assert pet.y()+pet.height()==foot
        pet.life.finish();pet._tick()
        assert pet.y()+pet.height()==foot and not pet.cameo.isVisible()
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()
