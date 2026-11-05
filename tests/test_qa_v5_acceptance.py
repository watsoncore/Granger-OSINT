"""Regression tests for the native V5 acceptance driver contracts."""
import json

import pytest

from scripts.qa_v5_acceptance import V5Session,node_input_point,read_observations


def test_waits_for_rendered_toolbar_after_document_ack_before_expanding():
    session=object.__new__(V5Session)
    events=[]
    doc={'view':{'ui':{}}}
    rendered=False
    expanded=False

    def action(name,payload):
        assert name=='research_canvas_open'
        doc['id']=payload['id']
        events.append('backend-ack')

    def metrics():
        nonlocal rendered
        rendered=True
        events.append('renderer-ack')
        return {'canvas_id':doc['id'],'canvas':{'width':1200}}

    def find(label):
        found=rendered and label==('Встроить' if expanded else 'Развернуть')
        return ({'text':label} if found else None),{}

    def click(label):
        nonlocal expanded
        assert label=='Развернуть' and rendered
        expanded=True
        events.append('expand')

    session.idle=lambda:None
    session.action=action
    session.document=lambda:doc
    session.canvas=lambda:{'busy':False}
    session.metrics=metrics
    session.find=find
    session.click=click

    session.open_document('isolated-fixture')
    assert events==['backend-ack','renderer-ack','expand','renderer-ack']


def test_saved_mock_results_are_rejected_before_seeding_native_acceptance(tmp_path):
    receipt=tmp_path/'mock.json'
    receipt.write_text(json.dumps({'mock':True,'status':'complete','results':[{'id':'not-real'}]}),encoding='utf-8')
    with pytest.raises(ValueError,match='real observations'):
        read_observations(receipt,'blockchain_gansar','fixture')


def test_graph_drag_uses_exposed_card_corner_when_selected_transaction_covers_center():
    nodes=[{'id':'root','x':500,'y':300,'width':340,'height':160},
           {'id':'transaction','x':550,'y':335,'width':300,'height':140}]
    canvas={'x':300,'y':250,'width':1200,'height':680,'qaNodes':json.dumps(nodes)}
    x,y=node_input_point(canvas,'root')
    assert 630<x<700 and 470<y<575
