from test_desktop_bridge import bridge
from test_investigation_graph_bridge import wait
from grangerpet.agent_evidence import normalize_evidence


def test_gallery_is_asynchronous_scoped_and_reuses_revision_without_inference(bridge,monkeypatch):
    identifier='img_'+'a'*64
    row=normalize_evidence({'id':'scene','type':'image_analysis','title':'Fixture pixels','platform':'Local fixture','details':{
        'attachment_id':identifier,'tool':'image_understand','description':'Fixture scene'}},'image_understand',identifier)
    snapshot={'id':'e'*32,'goal':'Где сделан снимок?','status':'completed','evidence':[row],
        'checkpoint_revision':1,'executions':[],'conversation_id':bridge.host.chat_widget.conversation_id}
    bridge.host.chat_widget._last_investigation=snapshot
    calls=[]
    class Store:
        def comparison_preview(self,value,cancel):calls.append(value);return 'data:image/jpeg;base64,YQ=='
        def small_preview(self,value,cancel):return 'data:image/jpeg;base64,YQ=='
    monkeypatch.setattr('grangerpet.geoint_tools.attachment_store',lambda:Store())
    before=bridge.snapshot()['geo_views']
    assert bridge.dispatch('geoint_view_get',{'id':snapshot['id']})['state']=='loading'
    wait(lambda:bridge._geo_views[snapshot['id']]['state']=='ready')
    assert not before
    assert bridge.snapshot()['geo_views'][snapshot['id']]['scenes'][0]['evidence_id']==row['evidence_id']
    bridge.dispatch('geoint_view_get',{'id':snapshot['id']})
    assert calls==[identifier]
    assert bridge.dispatch('source_open',{'evidence_id':row['evidence_id']})['evidence_id']==row['evidence_id']
    bridge.dispatch('investigation_graph_get',{'id':snapshot['id'],'mode':'geo'})
    wait(lambda:bridge._graph_data.get('state')=='ready')
    assert bridge._graph_data['has_geoint'] and bridge._graph_data['view']['mode']=='geo'


def test_tile_job_completes_without_mutating_previous_snapshot_and_cancel_clears(bridge,monkeypatch):
    monkeypatch.setattr('grangerpet.geoint.tiles.TileStore.get',lambda self,z,x,y,**kwargs:{'key':'0/0/0','state':'ready','image':'data:image/png;base64,YQ=='})
    before=bridge.snapshot()['map_tiles']
    bridge.dispatch('geoint_tile_get',{'z':0,'x':0,'y':0})
    wait(lambda:'0/0/0'in bridge._map_tiles)
    assert not before and bridge.snapshot()['map_tiles']['0/0/0']['state']=='ready'
    bridge.dispatch('geoint_tiles_cancel',{})
    assert not bridge.snapshot()['map_tiles']
