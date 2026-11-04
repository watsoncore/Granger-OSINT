"""Native probes must select real, visible menu items, not their triggers."""
from scripts.qa_v4_investigation import Session


def test_radio_item_lookup_ignores_trigger_with_the_same_visible_text():
    session=object.__new__(Session)
    trigger={'text':'TON','label':'Network','role':None,'width':200}
    radio={'text':'TON Public network','role':'menuitemradio','width':200}
    session.dom=lambda:{'elements':[trigger,radio]}
    assert session.find('TON',role='menuitemradio')[0] is radio
    assert session.find('Network')[0] is trigger


def test_visible_portal_search_near_viewport_top_can_be_clicked():
    session=object.__new__(Session)
    search={'label':'Найти: Инструмент узла','width':220,'height':25,'x':1550,'y':20,'hit':True}
    session.dom=lambda:{'elements':[search],'width':1920,'height':1020}
    actions=[]
    session.action=lambda action,payload:actions.append((action,payload))
    session.click(search['label'])
    assert actions==[('input',{'kind':'click','at':[1660,32.5]})]
