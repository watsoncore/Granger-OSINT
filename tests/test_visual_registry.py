"""Authorization and evidence fidelity, without claiming fixture ML accuracy."""
import json
import threading
import pytest
from grangerpet.agent import AgentRunner,AgentLimits
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings
from grangerpet.evidence_graph import build
from grangerpet.tool_inputs import validate_object
from grangerpet.visual_models.pipeline import INPUT_SCHEMA

IMAGE='img_'+'a'*64
OTHER='img_'+'b'*64


def registry(**kwargs):
    return ToolRegistry(Settings(),secret_getter=lambda _: '',**kwargs)


@pytest.mark.parametrize('tool,args',[
    ('geoclip_predict',{'attachment_id':IMAGE}),
    ('waypoint_predict',{'attachment_id':IMAGE}),
    ('visual_geoint',{'attachment_id':IMAGE}),
    ('waypoint_match',{'attachment_id':IMAGE,'reference_id':OTHER}),
    ('geoclip_predict',{'attachment_id':'../private.jpg'}),
    ('geoclip_predict',{'attachment_id':IMAGE,'model_path':'C:/private'}),
])
def test_opaque_attachment_ids_do_not_grant_access_to_unselected_images(monkeypatch,tool,args):
    monkeypatch.setattr('grangerpet.visual_models.tools.execute',lambda *a,**k:pytest.fail('Must reject before decrypt/worker'))
    monkeypatch.setattr('grangerpet.visual_models.pipeline.execute',lambda *a,**k:pytest.fail('Must reject before decrypt/worker'))
    assert registry().execute(tool,args)['status']=='invalid_arguments'


def test_matching_requires_both_images_to_be_scoped(monkeypatch):
    monkeypatch.setattr('grangerpet.visual_models.tools.execute',lambda *a,**k:pytest.fail('Unselected reference'))
    assert registry(attachment_ids=[IMAGE]).execute('waypoint_match',{'attachment_id':IMAGE,'reference_id':OTHER})['status']=='invalid_arguments'


def test_model_installation_is_not_a_live_execution_claim(monkeypatch):
    monkeypatch.setattr('grangerpet.visual_models.tools.readiness',lambda:{'available':False,'state':'not_installed','reason':'Fixture missing runtime'})
    reg=registry(attachment_ids=[IMAGE])
    assert reg.execute('visual_geoint',{'attachment_id':IMAGE})['status']=='not_installed'
    assert not any(s['function']['name']=='visual_geoint' for s in reg.schemas(task='фото geoint'))


def test_geometry_survives_common_evidence_bounds_as_real_numeric_geojson():
    result=registry().execute('shadow_regions',{'datetime_utc':'2024-02-29T13:59:59Z','object_height':10,'shadow_length':5,'grid_step_deg':1,'max_cells':1000})
    assert result['status']=='complete'
    details=result['results'][0]['details'];features=details['regions']['features']
    assert 0<len(features)<=60 and details['matching_cells_returned']==len(features)
    assert all(type(number) in (float,int) for f in features for ring in f['geometry']['coordinates'] for point in ring for number in point)
    assert '[ограничено]' not in json.dumps(features,ensure_ascii=False)


def test_lat_lon_worker_candidates_reach_graph_without_identity_assertions():
    record={'evidence_id':'ev_'+'1'*20,'type':'image_analysis','platform':'GeoCLIP','details':{
        'attachment_id':IMAGE,'predictions':[{'lat':55.75,'lon':37.62,'raw_score':19.1}]}}
    result=build([record]);candidate=next(n for n in result['entities'] if n['type']=='geographic_candidate')
    assert candidate['attributes']['raw_score']==19.1 and candidate['attributes']['calibrated_probability'] is False
    assert result['relations'][0]['verification_status']=='model_hypothesis'


def test_duplicate_model_methods_are_rejected_before_dispatch():
    with pytest.raises(ValueError):validate_object({'attachment_id':IMAGE,'methods':['geoclip_predict','geoclip_predict']},INPUT_SCHEMA)


def test_model_previews_are_never_sent_to_gateway_even_by_evidence_get():
    runner=AgentRunner(object(),registry(),limits=AgentLimits())
    runner._record={'goal':'где снято фото?'};runner._state={'sent_content':{}}
    record={'evidence_id':'ev_'+'1'*20,'title':'Fixture ML output','type':'image_analysis','details':{
        'tool':'geoclip','capability':'geoclip_predict','source_record':True,'preview':'data:image/jpeg;base64,PRIVATE-PIXELS',
        'predictions':[{'lat':55.75,'lon':37.62,'raw_score':19.1}],'model_version':'fixture'},'provenance':{}}
    for tool in ('visual_geoint','evidence_get'):
        compact=runner._compact({'tool':tool,'status':'complete','results':[record]})
        encoded=json.dumps(compact)
        assert 'PRIVATE-PIXELS' not in encoded and 'base64' not in encoded
        assert '55.75' in encoded and '19.1' in encoded


def test_cpu_timeout_is_longer_than_http_but_does_not_change_http_or_user_longer_timeout():
    assert ToolRegistry.timeout_for('geoclip_predict',25)==180
    assert ToolRegistry.timeout_for('visual_geoint',25)==240
    assert ToolRegistry.timeout_for('visual_geoint',300)==300
    assert ToolRegistry.timeout_for('x_post',25)==25
