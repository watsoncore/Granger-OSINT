import time
from copy import deepcopy
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from test_desktop_bridge import bridge
from grangerpet.agent_evidence import normalize_evidence


def wait(predicate):
    end=time.monotonic()+5
    while not predicate() and time.monotonic()<end:
        QApplication.processEvents();QTest.qWait(10)
    assert predicate()


def prepare(bridge):
    row=normalize_evidence({'id':'fixture','title':'Actual fixture page','type':'web','platform':'Fixture',
        'url':'https://example.org/fixture','description':'Synthetic public contents','status':'content_observed',
        'details':{'reading_method':'direct_http','body_sha256':'a'*64,'links':[{'url':'https://github.com/public-fixture/project'}]}},
        'web_read','https://example.org/fixture')
    snapshot={'id':'e'*32,'goal':'Исследуй https://example.org/fixture','status':'completed','evidence':[row],
        'executions':[{'tool':'web_read','status':'complete','query':row['url']}],'tool_calls':1,
        'conversation_id':bridge.host.chat_widget.conversation_id}
    bridge.host.chat_widget._last_investigation=snapshot
    bridge.dispatch('investigation_graph_get',{'id':snapshot['id']})
    wait(lambda:bridge._graph_data.get('state')=='ready')
    return snapshot,row


def test_actual_bridge_prepares_graph_without_blocking_or_fabricated_sources(bridge):
    original,row=prepare(bridge)
    value=bridge.snapshot()
    graph=value['investigation_graph']
    assert graph['investigation_id']==original['id'] and graph['entities'] and graph['relations']
    assert graph['counts']['tool_calls']==1 and graph['counts']['unique_documents']==1
    assert all('details' not in source for source in graph['evidence'])
    assert bridge.dispatch('source_open',{'evidence_id':row['evidence_id']})['evidence_id']==row['evidence_id']
    assert original['evidence'][0]==row


def test_graph_selection_and_encrypted_view_are_owned_by_one_investigation(bridge):
    original,row=prepare(bridge)
    node=bridge._graph_data['entities'][0]
    assert bridge.dispatch('investigation_graph_select',{'id':original['id'],'entity_id':node['id']})['entity_id']==node['id']
    bridge.dispatch('investigation_graph_view_save',{'id':original['id'],'view':{'version':1,'mode':'graph',
        'selected_id':node['id'],'positions':{node['id']:{'x':20,'y':30,'pinned':True}},'viewport':{'x':3,'y':4,'scale':1.7}}})
    saved=bridge._workspace.views.load(original['id'])
    assert saved['selected_id']==node['id'] and saved['viewport']['scale']==1.7
    import pytest
    with pytest.raises(ValueError):bridge.dispatch('investigation_graph_select',{'id':original['id'],'entity_id':'ent_'+'0'*24})


def test_graph_analyze_passes_structured_subgraph_and_same_id_to_existing_chat(bridge,monkeypatch):
    original,row=prepare(bridge)
    chat=bridge.host.chat_widget
    monkeypatch.setattr(type(chat),'_ready',property(lambda self:True))
    calls=[]
    monkeypatch.setattr(chat,'continue_investigation',lambda identifier,**kwargs:calls.append((identifier,kwargs)))
    node=bridge._graph_data['entities'][0]
    result=bridge.dispatch('investigation_graph_analyze',{'id':original['id'],'entity_id':node['id'],'intent':'explain'})
    assert result['investigation_id']==calls[0][0]==original['id']
    context=calls[0][1]['followup']['context']
    assert context['selected_entity_ids']==[node['id']] and context['entities']
    assert len(context['entities'])<=12 and len(context['relations'])<=24
    assert bridge.route=='chat'
