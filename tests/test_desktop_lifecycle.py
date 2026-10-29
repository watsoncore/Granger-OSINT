"""Only local page visibility is changed; no forced Frozen/Discarded or GPU flags."""
from types import SimpleNamespace
import pytest
from PySide6.QtWebEngineCore import QWebEnginePage
from grangerpet.desktop_surface import DesktopSurface
State=QWebEnginePage.LifecycleState
class Page:
    def __init__(self,state=State.Active):self.state=state;self.visible=None;self.transitions=[]
    def setVisible(self,value):self.visible=value
    def setLifecycleState(self,value):self.state=value;self.transitions.append(value)
@pytest.mark.parametrize('shown,minimized,surface_shown,expected',[
    (True,False,True,True),(True,True,True,False),(False,False,False,False),
    (True,False,False,False),(False,False,True,False)])
def test_hidden_page_uses_browser_background_scheduling_and_no_forced_freeze(shown,minimized,surface_shown,expected):
    page=Page();published=[]
    surface=SimpleNamespace(_closing=False,host=SimpleNamespace(isVisible=lambda:shown,isMinimized=lambda:minimized),
        isVisible=lambda:surface_shown,trusted_page=page,bridge=SimpleNamespace(set_publication_visible=published.append))
    DesktopSurface._sync_visibility(surface)
    assert page.visible==expected and published==[expected]
    assert State.Frozen not in page.transitions and State.Discarded not in page.transitions
    assert surface._renderer_visible==expected

def test_restore_reactivates_page_without_discarding_its_document():
    page=Page(State.Frozen)
    surface=SimpleNamespace(_closing=False,host=SimpleNamespace(isVisible=lambda:True,isMinimized=lambda:False),
        isVisible=lambda:True,trusted_page=page,bridge=SimpleNamespace(set_publication_visible=lambda value:None))
    DesktopSurface._sync_visibility(surface)
    assert page.visible and page.state==State.Active and page.transitions==[State.Active]

def test_shutdown_surface_ignores_late_visibility_events():
    DesktopSurface._sync_visibility(SimpleNamespace(_closing=True))
