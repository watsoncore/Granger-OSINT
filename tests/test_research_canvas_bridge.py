import time
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from test_desktop_bridge import bridge
from grangerpet.agent_evidence import normalize_evidence


def wait(bridge):
    end=time.monotonic()+12
    while bridge._research_canvas.job and time.monotonic()<end:
        QApplication.processEvents();QTest.qWait(10)
    assert not bridge._research_canvas.job
    state=bridge.snapshot()['research_canvas']
    assert not state.get('error'),state.get('error')
    return state


def action(bridge,op,**payload):
    document=bridge._research_canvas.document if bridge._research_canvas else None
    bridge.dispatch('research_canvas_'+op,{'id':document['id'] if document else '',
        'revision':document['revision'] if document else 0,**payload})
    return wait(bridge)

def test_public_media_preview_stays_outside_durable_graph_revisions(bridge):
    action(bridge,'new',title='Transient preview')
    action(bridge,'edit',operation='node',arguments={
        'type':'public_profile','value':'https://github.com/octocat','label':'Профиль'})
    controller=bridge._research_canvas
    node=controller.document['entities'][0]
    node['attributes']['media']={'id':'media_fixture','kind':'public_avatar','state':'pending'}
    controller._commit(controller.document)
    key=(controller.document['id'],node['id'],'media_fixture')
    controller.media_previews[key]={'id':'media_fixture','kind':'public_avatar','state':'ready',
                                  'thumbnail':'data:image/jpeg;base64,dGVzdA=='}
    visible=controller.render()['document']['entities'][0]['attributes']['media']
    assert visible['state']=='ready'
    assert controller.document['entities'][0]['attributes']['media']['state']=='pending'
    changed=action(bridge,'edit',operation='view',arguments={'view':{'ui':{'inspector_open':True}}})
    persisted=controller.store.load(changed['document']['id'])
    assert persisted['entities'][0]['attributes']['media']=={'id':'media_fixture','kind':'public_avatar','state':'pending'}
    assert changed['document']['entities'][0]['attributes']['media']['state']=='ready'


def test_qt_actual_canvas_editor_undo_redo_and_reopen_do_not_change_chat(bridge):
    messages=list(bridge.host.chat_widget.messages)
    created=action(bridge,'new',title='Ручной Qt-контроль');identifier=created['document']['id']
    changed=action(bridge,'edit',operation='node',arguments={'type':'infrastructure_asset','label':'66.249.67.41'})
    assert len(changed['document']['entities'])==1 and changed['can_undo']
    assert action(bridge,'undo')['document']['entities']==[]
    assert len(action(bridge,'redo')['document']['entities'])==1
    reopened=action(bridge,'open',id=identifier)
    assert reopened['document']['title']=='Ручной Qt-контроль'
    assert bridge.host.chat_widget.messages==messages


def test_canvas_image_positions_dedup_and_link_detach_preserve_original_and_evidence(bridge):
    from io import BytesIO
    from PIL import Image
    from grangerpet.canvas_media import media_node
    from grangerpet.research_canvas import merge_evidence

    action(bridge,'new',title='Media')
    controller=bridge._research_canvas
    document=controller.document
    row=normalize_evidence({'id':'media-profile','type':'profile','platform':'github',
        'url':'https://github.com/octocat','title':'octocat','status':'source_reported'},'github_profile','octocat')
    merge_evidence(document,[row])
    controller._commit(document)
    profile=next(node for node in controller.document['entities'] if node['type']=='public_profile')
    media=BytesIO()
    Image.new('RGB',(320,180),'#47617a').save(media,'PNG')
    source=media.getvalue()
    stored=bridge._images().import_bytes(source,'Фото.png')
    first=action(bridge,'attach',attachment_id=stored['id'],position={'x':320.5,'y':-25})['document']
    saved_evidence=controller.store.load(first['id'])['evidence']
    picture=next(node for node in first['entities'] if node['type']=='image')
    assert first['view']['positions'][picture['id']]=={'x':320.5,'y':-25,'pinned':True}
    assert picture['id'] in first['view']['manual_position_ids']
    assert 'thumbnail' not in picture['attributes']['media']
    action(bridge,'attach',attachment_id=stored['id'],entity_id=profile['id'])
    linked=action(bridge,'attach',attachment_id=stored['id'],entity_id=profile['id'])['document']
    owner=next(node for node in linked['entities'] if node['id']==profile['id'])
    assert [reference['id'] for reference in owner['attributes']['image_attachments']]==[stored['id']]
    scope={'canvas_id':linked['id'],'entity_id':profile['id'],'attachment_id':stored['id']}
    assert media_node(bridge,scope)[1]==stored['id']
    detached=action(bridge,'edit',operation='detach_image',arguments={'entity_id':profile['id'],'attachment_id':stored['id']})['document']
    assert controller.store.load(detached['id'])['evidence']==saved_evidence
    assert bridge._images().read_bytes(stored['id'])==source
    import pytest
    with pytest.raises(ValueError,match='не прикреплено'):
        media_node(bridge,scope)


def test_preview_requires_explicit_selected_server_evidence_and_preserves_source_open(bridge):
    created=action(bridge,'new',title='Preview');doc_id=created['document']['id']
    row=normalize_evidence({'id':'qa-profile','type':'profile','platform':'github','title':'octocat',
        'url':'https://github.com/octocat','details':{'login':'octocat'},'status':'source_reported'},'github_profile','octocat')
    controller=bridge._research_canvas
    controller.accept_tool({'tool':'github_profile','status':'partial','results':[row],'limitations':['fixture']},doc_id,'')
    assert controller.document['entities']==[]
    state=action(bridge,'insert',token=controller.preview['token'],evidence_ids=[row['evidence_id']])
    assert state['document']['entities'] and state['preview']['status']=='partial'
    first=len(controller.document['entities'])
    action(bridge,'insert',token=controller.preview['token'],evidence_ids=[row['evidence_id']])
    assert len(controller.document['entities'])==first
    assert bridge.dispatch('source_open',{'evidence_id':row['evidence_id']})['evidence_id']==row['evidence_id']


def test_canvas_tool_action_uses_existing_registry_path_and_does_not_insert_automatically(bridge,monkeypatch):
    action(bridge,'new',title='Node tool')
    action(bridge,'edit',operation='node',arguments={'type':'blockchain_address','label':'UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'})
    calls=[];monkeypatch.setattr(bridge,'_run_tool',lambda payload,canvas_target=None:calls.append((payload,canvas_target)))
    doc=bridge._research_canvas.document;node=doc['entities'][0]
    bridge.dispatch('research_canvas_tool',{'id':doc['id'],'revision':doc['revision'],'entity_id':node['id'],'tool':'blockchain_gansar','arguments':{'address':node['attributes']['address']}})
    assert calls[0][1]==(doc['id'],node['id']) and not doc['evidence']


def test_canvas_rejects_stale_project_even_with_same_canonical_node(bridge):
    import pytest
    first=action(bridge,'new',title='Первое')['document']
    action(bridge,'edit',operation='node',arguments={'type':'infrastructure_asset','label':'66.249.67.41'})
    old=bridge._research_canvas.document
    node=old['entities'][0]['id']
    action(bridge,'new',title='Второе')
    action(bridge,'edit',operation='node',arguments={'type':'infrastructure_asset','label':'66.249.67.41'})
    with pytest.raises(ValueError,match='версия'):
        bridge.dispatch('research_canvas_tool',{'id':old['id'],'revision':old['revision'],'entity_id':node,'tool':'network_rdap','query':'66.249.67.41'})


def test_import_keeps_provenance_but_does_not_trust_exported_verification(bridge,tmp_path):
    import json
    from copy import deepcopy
    from grangerpet.research_canvas import new_document,merge_evidence
    row=normalize_evidence({'id':'import-fixture','type':'profile','platform':'github','title':'octocat',
        'url':'https://github.com/octocat','details':{'login':'octocat'},'status':'source_reported'},'github_profile','octocat')
    doc=new_document('Импорт');merge_evidence(doc,[row]);original=deepcopy(doc['evidence'])
    doc['entities'][0]['verification_status']='verified'
    path=tmp_path/'import.granger.json';path.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8-sig')
    action(bridge,'list');bridge._research_canvas._import(path)
    result=bridge._research_canvas.document
    assert result['id']!=doc['id'] and result['evidence']==original
    assert all(n['verification_status']=='unverified' and n['attributes']['imported_unverified'] for n in result['entities'])


def test_explain_selected_note_is_bounded_valid_context_without_pixels_or_tools(bridge,monkeypatch):
    import json
    action(bridge,'new',title='Область ИИ')
    action(bridge,'edit',operation='node',arguments={'type':'analyst_note','label':'Гипотеза','markdown':'Нужна проверка'})
    doc=bridge._research_canvas.document;node=doc['entities'][0]
    calls=[];monkeypatch.setattr(bridge.host.chat_widget,'_submit_text',lambda text,**kwargs:calls.append((text,kwargs)))
    bridge._research_canvas.action('research_canvas_analyze',{'id':doc['id'],'revision':doc['revision'],'ids':[node['id']],'intent':'explain'})
    text,kwargs=calls[0];assert text.startswith('Не используй инструменты.') and 'base64' not in text
    assert 'selected_entity_ids' not in text
    assert kwargs['context_scope']=='canvas:'+doc['id']
    context=kwargs['evidence_context'];assert len(json.dumps(context,ensure_ascii=False))<=8500
    assert context['selected_entity_ids']==[node['id']]
    assert context['analyst_annotations'][node['id']]['claim_kind']=='analyst_assertion'


def test_saved_search_preview_publishes_only_on_gui_thread(bridge,monkeypatch):
    from PySide6.QtCore import QThread
    action(bridge,'new',title='Из поиска')
    row=normalize_evidence({'id':'search-fixture','type':'profile','platform':'github','title':'octocat',
        'url':'https://github.com/octocat','details':{'login':'octocat'},'status':'source_reported'},'github_profile','octocat')
    monkeypatch.setattr(bridge._workspace,'load',lambda *args:{'status':'partial','evidence':[row]})
    calls=[];original=bridge.mark_dirty
    def mark_dirty():
        calls.append(QThread.currentThread()==QApplication.instance().thread())
        original()
    monkeypatch.setattr(bridge,'mark_dirty',mark_dirty)
    state=action(bridge,'from_search',investigation_id='qa-saved-search')
    assert calls and all(calls)
    assert state['preview']['tool']=='saved_investigation' and len(state['preview']['results'])==1
    assert state['preview']['from_saved_data'] and state['preview']['request_counts']['http_requests']==0
    assert not state['document']['entities']
