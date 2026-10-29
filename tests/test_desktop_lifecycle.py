"""Local page scheduling policy; real EXE lifecycle is checked separately."""
from types import SimpleNamespace

import pytest
from PySide6.QtWebEngineCore import QWebEnginePage

from grangerpet.desktop_surface import DesktopSurface


State=QWebEnginePage.LifecycleState


class Timer:
    def __init__(self):self.active=False
    def start(self):self.active=True
    def stop(self):self.active=False
    def isActive(self):return self.active


class Page:
    def __init__(self,visible=False,recommended=State.Frozen,state=State.Active):
        self.visible,self.recommended,self.state=visible,recommended,state
        self.transitions=[]

    def isVisible(self):return self.visible
    def recommendedState(self):return self.recommended
    def lifecycleState(self):return self.state
    def setLifecycleState(self,value):self.state=value;self.transitions.append(value)


@pytest.mark.parametrize('visible,recommended,ready,expected',[
    (False,State.Frozen,True,State.Frozen),
    (False,State.Discarded,True,State.Frozen),
    (False,State.Active,True,State.Active),
    (True,State.Frozen,True,State.Active),
    (False,State.Frozen,False,State.Active),
])
def test_page_policy_freezes_only_a_ready_hidden_page_without_discard(visible,recommended,ready,expected):
    page=Page(visible,recommended)
    surface=SimpleNamespace(_closing=False,_renderer_visible=visible,trusted_page=page,_freeze_timer=Timer(),
        bridge=SimpleNamespace(ui_ready=ready))
    DesktopSurface._apply_lifecycle(surface)
    if expected==State.Frozen:
        assert page.state==State.Active
        assert surface._freeze_timer.active
        DesktopSurface._freeze_hidden_page(surface)
    assert page.state==expected
    assert State.Discarded not in page.transitions


def test_restoring_page_keeps_it_active_during_the_visibility_transition():
    page=Page(False,State.Frozen,State.Frozen)
    surface=SimpleNamespace(_closing=False,_renderer_visible=True,trusted_page=page,_freeze_timer=Timer(),
        bridge=SimpleNamespace(ui_ready=True))
    DesktopSurface._apply_lifecycle(surface)
    assert page.state==State.Active


def test_restore_cancels_freeze_grace_and_stale_timeout_cannot_freeze_visible_page():
    page=Page(False,State.Frozen)
    surface=SimpleNamespace(_closing=False,_renderer_visible=False,trusted_page=page,
        _freeze_timer=Timer(),bridge=SimpleNamespace(ui_ready=True))
    DesktopSurface._apply_lifecycle(surface)
    assert surface._freeze_timer.active
    surface._renderer_visible=True
    DesktopSurface._apply_lifecycle(surface)
    assert not surface._freeze_timer.active
    DesktopSurface._freeze_hidden_page(surface)
    assert page.state==State.Active
