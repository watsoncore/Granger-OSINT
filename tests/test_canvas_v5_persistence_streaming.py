"""V5 layout snapshots and incremental source results use durable contracts."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from grangerpet import credentials
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.agent_journal import InvestigationJournal
from grangerpet.research_canvas import CanvasStore,add_node,apply,new_document,validate
from grangerpet.research_canvas_bridge import ResearchCanvasBridge


@pytest.fixture(autouse=True)
def private_storage(tmp_path,monkeypatch):
    profile=tmp_path/'profile'
    monkeypatch.setenv('APPDATA',str(profile))
    monkeypatch.setattr(credentials,'_STORE',credentials.CredentialsStore(
        prefix='Granger-V5-Canvas-Fixture',directory=profile/'vault',data_root=profile))


def canvas():
    value=new_document('V5 layout contract')
    first=add_node(value,{'type':'username','label':'Первый объект','value':'fixture_one'})
    second=add_node(value,{'type':'username','label':'Второй объект','value':'fixture_two'})
    return value,first,second


def viewport(doc,x,y,scale):
    return apply(doc,'view',{'view':{'viewport':{'x':x,'y':y,'scale':scale}}})


def profile(identifier='one'):
    return normalize_evidence({'id':'fixture-'+identifier,'type':'profile','platform':'Fixture',
        'title':identifier,'url':'https://example.org/'+identifier,'status':'source_reported',
        'details':{'username':identifier}},'username_maigret','fixture_one')


def controller(tmp_path,doc=None):
    class HostBridge:
        def __init__(self):
            self._raw_sources={};self.notifications=0
            self.host=SimpleNamespace(chat_widget=SimpleNamespace(_journal=InvestigationJournal(tmp_path/'journal')))
        def mark_dirty(self):self.notifications+=1
    value=ResearchCanvasBridge(HostBridge());value.document=doc or new_document()
    return value


def test_manual_wallet_manual_restores_exact_dragged_positions_and_camera():
    doc,first,second=canvas()
    manual={first:{'x':123.25,'y':-48.5,'pinned':True},second:{'x':701.5,'y':390.25}}
    doc=apply(doc,'positions',{'positions':manual});doc=viewport(doc,142.75,-91.25,.87)
    original=deepcopy(doc)
    wallet={first:{'x':0,'y':0},second:{'x':600,'y':0}}
    doc=apply(doc,'layout',{'mode':'wallet','positions':wallet})
    doc=viewport(doc,350,250,1.25)
    restored=apply(doc,'layout',{'mode':'manual','positions':{first:{'x':999,'y':999}}})
    assert restored['view']['positions']==manual
    assert restored['view']['viewport']==original['view']['viewport']
    assert restored['view']['layout_positions']['wallet']==wallet
    assert set(restored['view']['manual_position_ids'])=={first,second}
    assert original['view']['layout']=='manual'  # operations do not mutate ACK snapshots


def test_cached_automatic_layout_restores_its_camera_and_explicit_relayout_can_replace_it():
    doc,first,second=canvas()
    wallet={first:{'x':-100,'y':0},second:{'x':500,'y':90}}
    radial={first:{'x':0,'y':100},second:{'x':-600,'y':-90}}
    doc=apply(doc,'layout',{'mode':'wallet','positions':wallet});doc=viewport(doc,400,300,.75)
    doc=apply(doc,'layout',{'mode':'radial','positions':radial});doc=viewport(doc,100,50,.45)
    restored=apply(doc,'layout',{'mode':'wallet','positions':radial,'reuse_saved':True})
    assert restored['view']['positions']==wallet
    assert restored['view']['viewport']=={'x':400,'y':300,'scale':.75}
    recomputed=apply(restored,'layout',{'mode':'wallet','positions':radial,'reuse_saved':False})
    assert recomputed['view']['positions']==radial


def test_delete_entity_removes_visual_instances_and_all_layout_position_caches():
    doc,first,second=canvas()
    doc=apply(doc,'duplicate_nodes',{'ids':[first]})
    instance=next(iter(doc['view']['instances']))
    doc=apply(doc,'positions',{'positions':{first:{'x':15,'y':20},instance:{'x':50,'y':70}}})
    positions={**doc['view']['positions'],instance:doc['view']['instances'][instance]['position']}
    doc=apply(doc,'layout',{'mode':'wallet','positions':positions})
    doc=apply(doc,'layout',{'mode':'radial','positions':positions})
    deleted=apply(doc,'delete_entity',{'ids':[first]})
    assert {node['id'] for node in deleted['entities']}=={second}
    assert instance not in deleted['view']['instances']
    for field in ('positions','manual_positions'):
        assert first not in deleted['view'].get(field,{}) and instance not in deleted['view'].get(field,{})
    assert not set(deleted['view']['manual_position_ids'])&{first,instance}
    assert all(not set(snapshot)&{first,instance} for snapshot in deleted['view']['layout_positions'].values())
    assert deleted['evidence']==doc['evidence']
    validate(deleted)


def test_encrypted_reopen_keeps_new_snapshots_ui_and_legacy_documents_readable(tmp_path):
    doc,first,second=canvas();store=CanvasStore(InvestigationJournal(tmp_path/'journal'))
    # A pre-V5 schema has no new layout-cache fields and remains directly readable.
    legacy=store.save(doc,0)
    assert 'layout_positions' not in legacy['view']
    assert store.load(legacy['id'])['entities']==legacy['entities']
    value=apply(legacy,'positions',{'positions':{first:{'x':18.125,'y':-201.5}}})
    value=apply(value,'layout',{'mode':'wallet','positions':{first:{'x':0,'y':0},second:{'x':550,'y':0}}})
    value=apply(value,'view',{'view':{'ui':{'graph_mode':'socmint','username_root_id':first,'initial_layout':'hierarchical'}}})
    saved=store.save(value,legacy['revision']);reopened=CanvasStore(InvestigationJournal(tmp_path/'journal')).load(saved['id'])
    assert reopened['view']==saved['view'] and reopened['entities']==saved['entities']
    imported=validate(json.loads(json.dumps(reopened,ensure_ascii=False)))
    assert imported['view']==saved['view']
    raw=(store._folder(saved['id'])/f"r{saved['revision']:010d}.dpapi").read_bytes()
    assert b'fixture_one' not in raw and 'Первый объект'.encode('utf-8') not in raw


def test_streamed_findings_keep_token_merge_by_evidence_id_and_survive_final_error(tmp_path):
    value=controller(tmp_path);canvas_id=value.document['id'];first,second=profile(),profile('two')
    value.begin_tool('username_maigret',canvas_id,'node')
    token=value.preview['token']
    value.accept_tool({'tool':'username_maigret','status':'running','results':[first]},canvas_id,'node',streaming=True)
    assert value.preview['token']==token and value.preview['running'] is True
    value.accept_tool({'tool':'username_maigret','status':'running','results':[first,second]},canvas_id,'node',streaming=True)
    value.accept_tool({'tool':'username_maigret','status':'error','results':[],'error':'Provider timed out',
        'error_code':'source_timeout','limitations':['Partial results retained']},canvas_id,'node')
    preview=value.state['preview']
    assert preview['token']==token and preview['status']=='error' and preview['running'] is False
    assert preview['error_code']=='source_timeout' and preview['error']=='Provider timed out'
    assert {row['evidence_id'] for row in preview['results']}=={first['evidence_id'],second['evidence_id']}
    assert len(value.preview['records'])==2 and len(value.bridge._raw_sources)==2
    assert value.document['entities']==[] and value.document['evidence']==[]  # insert remains explicit


def test_new_run_replaces_old_selection_token_and_does_not_reuse_prior_findings(tmp_path):
    value=controller(tmp_path);canvas_id=value.document['id'];finding=profile()
    value.begin_tool('username_maigret',canvas_id,'node')
    value.accept_tool({'tool':'username_maigret','status':'complete','results':[finding]},canvas_id,'node')
    previous=value.preview['token']
    value.begin_tool('username_maigret',canvas_id,'node')
    assert value.preview['token']!=previous and value.preview['records']==[]
    assert value.state['preview']['results']==[] and value.preview['status']=='running'


def test_background_canvas_preview_stays_scoped_when_current_canvas_renders(tmp_path):
    value=controller(tmp_path);canvas_id=value.document['id'];other_id=new_document()['id']
    value.begin_tool('username_maigret',canvas_id,'one')
    value.accept_tool({'tool':'username_maigret','status':'partial','results':[profile()]},canvas_id,'one')
    expected=deepcopy(value.state['preview'])
    value.begin_tool('username_maigret',other_id,'two')
    value.accept_tool({'tool':'username_maigret','status':'complete','results':[profile('two')]},other_id,'two')
    assert value.state['preview']==expected
    rendered=value.render()
    assert rendered['preview']==expected
    assert rendered['preview']['canvas_id']==canvas_id
    assert value.previews[other_id]['results'][0]['evidence_id']!=expected['results'][0]['evidence_id']
