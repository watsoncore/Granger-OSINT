"""Deterministic local scheduler and real action frames; no network or user files."""
import hashlib
import os
import random

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from grangerpet.animation import SpriteLibrary
from grangerpet.pet_life import ACTIONS, PetLifeController
from grangerpet.pet_actions import action_frame
from grangerpet.pet import PetWindow
from grangerpet.config import Settings, SettingsStore


@pytest.fixture(scope='module')
def app():
    value=QApplication.instance() or QApplication([])
    value.setQuitOnLastWindowClosed(False)
    return value


def controller():
    now=[100.0]
    return now,PetLifeController(clock=lambda:now[0],rng=random.Random(42))


def test_cold_start_and_recent_activity_do_not_trigger_idle_actions():
    now,life=controller()
    for seconds in (1,10,20,34):
        now[0]=100+seconds;life.update(system_idle=seconds)
        assert not life.active
    life.notify_activity();now[0]+=30;life.update(system_idle=30)
    assert not life.active


def test_local_idle_can_schedule_without_accessing_any_external_service():
    now,life=controller();now[0]=300
    life.next_due=101
    life.update(system_idle=200)
    assert life.action in ('reading','cast','leave','avada')


def test_no_fixed_repeating_interval_or_same_action_choice():
    now,life=controller();deadlines=[];actions=[]
    for _ in range(12):
        now[0]+=200;life.next_due=now[0]-1
        life.update(system_idle=200);actions.append(life.action)
        life.finish();deadlines.append(life.next_due-now[0])
    assert len(set(round(x) for x in deadlines))>3
    assert len(set(actions))>1


@pytest.mark.parametrize('name', ['reading','cast','avada','yawn','sleep'])
def test_every_nontravel_action_interrupts_for_real_user_work(name):
    now,life=controller();life.start_action(name)
    now[0]+=.5;life.notify_activity()
    assert life.action in ('settle','wake')
    now[0]+=1;life.update(available=False,system_idle=0)
    assert not life.active


def test_sleep_sequence_has_yawn_sleep_and_natural_wake():
    now,life=controller();life.start_action('yawn',duration=.5)
    now[0]+=.6;life.update(system_idle=400)
    assert life.action=='sleep'
    life.notify_activity();assert life.action=='wake'
    now[0]+=1;life.update(system_idle=0)
    assert not life.active


def test_leave_away_return_is_continuous_and_activity_does_not_restart_return():
    now,life=controller();life.start_action('leave',duration=2)
    assert life.pose().travel==0
    now[0]+=1;assert .4<life.pose().travel<.6
    life.notify_activity(immediate=True);assert life.action=='return'
    original_start=life.started
    for _ in range(5):
        now[0]+=.1;life.update(available=False,system_idle=0)
    assert not life.active
    assert life.started==original_start


def test_avada_is_rare_and_has_long_cooldown():
    now,life=controller();life.start_action('avada');stamp=life.last_avada
    life.finish();now[0]+=200;life.next_due=now[0]-1
    life.update(system_idle=400)
    assert life.action!='avada' and life.last_avada==stamp


@pytest.mark.parametrize('name',['reading','cast','avada','yawn','sleep','leave','return','wake'])
def test_actions_have_real_distinct_transparent_frames_without_asset_replacement(app,name):
    now,life=controller();library=SpriteLibrary()
    life.start_action(name,duration=3)
    values=[]
    for sample in (.2,1.1,2.4):
        now[0]=100+sample
        image=action_frame(library,life.pose())
        assert image.width()==256 and image.height()==256 and image.hasAlphaChannel()
        assert image.pixelColor(0,0).alpha()==0
        values.append(hashlib.sha256(bytes(image.constBits())).hexdigest())
    assert len(set(values))>=2


def test_invalid_action_or_duration_is_not_a_command_channel():
    _,life=controller()
    with pytest.raises(ValueError):life.start_action('powershell')
    with pytest.raises(ValueError):life.start_action('reading',duration=float('nan'))


def test_actual_pet_leave_does_not_hide_or_persist_offscreen_position(app,tmp_path,monkeypatch):
    monkeypatch.setattr('grangerpet.credentials.get_secret',lambda _: '')
    pet=PetWindow(Settings(size=100,cursor_reaction=False),SettingsStore(tmp_path/'settings.json'))
    pet.frame_timer.stop();pet.cursor_timer.stop();pet.show();app.processEvents()
    try:
        pet.move(250,200);home=pet.pos()
        pet.life.start_action('leave',now=100,duration=2)
        pet._apply_life_travel(pet.life.pose(101))
        assert pet.isVisible() and pet.pos()!=home
        pet._save_position();saved=pet.store.load()
        assert (saved.x,saved.y)==(home.x(),home.y())
        pet.life.finish(102);pet._apply_life_travel(pet.life.pose(102))
        assert pet.pos()==home
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()


def test_busy_investigation_interrupts_local_life_and_returns_home(app,tmp_path,monkeypatch):
    monkeypatch.setattr('grangerpet.credentials.get_secret',lambda _: '')
    pet=PetWindow(Settings(size=100),SettingsStore(tmp_path/'settings.json'))
    pet.frame_timer.stop();pet.cursor_timer.stop()
    try:
        pet.move(230,200);home=pet.pos()
        pet.life.start_action('leave',now=100,duration=2);pet._apply_life_travel(pet.life.pose(101))
        pet._search_state('thinking')
        assert pet.life.action=='return' and pet.animation.state=='thinking' and pet._busy
        pet.life.started-=1;pet._tick()
        assert pet.pos()==home and not pet.life.active
        for action in ('reading','sleep','cast'):
            pet.life.start_action(action);pet._tick()
            assert not pet.life.active and pet.animation.state=='thinking'
    finally:
        pet.shutdown();pet.panel.deleteLater();pet.deleteLater();app.processEvents()
