"""Actual local19-project computations, upstream vectors and bounded failures."""
from datetime import datetime,timezone
import math,threading,time
import pytest
from grangerpet.integrations19.local_tools import execute,tiktok_timestamp,role_classify,INPUT_SCHEMAS
from grangerpet.integrations19.solar import shadow_regions,sun_position,LocalToolError

def test_documented_tiktok_reference_exact_integer_and_url_no_network(monkeypatch):
    # RyanBenson originalresearch, linked by Bellingcat upstreamREADME.
    # ID6854717870488702213, embeddedtime1595988373; sourcepagecreateTime1595988377.
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('Localoperationattemptednetwork'))
    result=tiktok_timestamp('https://www.tiktok.com/@billnye/video/6854717870488702213?lang=en')
    assert result['video_id']=='6854717870488702213'
    assert result['timestamp_unix']==1595988373
    assert result['date_utc']=='2020-07-29T02:06:13Z'
    assert result['source_url']=='https://www.tiktok.com/@billnye/video/6854717870488702213'
    assert tiktok_timestamp(result['video_id'])['timestamp_unix']==result['timestamp_unix']
    assert result['network_requests']==0 and result['warnings']

@pytest.mark.parametrize('value',['123',6854717870488702213,'https://vm.tiktok.com/SHORT/',
    'https://tiktok.com.evil.test/@billnye/video/6854717870488702213','http://www.tiktok.com/@billnye/video/6854717870488702213',
    'https://user:password@www.tiktok.com/@billnye/video/6854717870488702213','https://www.tiktok.com/@x/live/6854717870488702213',
    '18446744073709551615','0000000000000000000','6854717870488702213.0'])
def test_tiktok_strict_argument_validation(value):
    with pytest.raises(LocalToolError) as error:tiktok_timestamp(value)
    assert error.value.code=='invalid_arguments'

def test_solar_matches_actual_upstream_suncalc_test_vector():
    # Exact upstream tests/test_suncalc.py (MIT), not a mockedsolarresponse.
    position=sun_position('2013-03-05T00:00:00Z',50.5,30.5)
    assert position['altitude_radians']==pytest.approx(-.7000406838781611,abs=1e-12)
    assert position['azimuth_north_clockwise_deg']==pytest.approx((math.degrees(-2.5003175907168385)+180)%360,abs=1e-10)

SCENARIO={'datetime_utc':'2024-02-29T13:59:59Z','object_height':10,'shadow_length':5,'grid_step_deg':5,'max_cells':30}

def test_documented_shadowfinder_height_length_example_produces_actual_ambiguous_band():
    # Actual READMECLIscenario10,5,2024-02-29,13:59:59UTC.
    result=shadow_regions(SCENARIO)
    assert result['observed_sun_altitude_deg']==pytest.approx(math.degrees(math.atan(2)))
    assert result['cells_evaluated']==72*29
    assert result['matching_cells_total']>1
    assert result['regions']['type']=='FeatureCollection'
    for feature in result['regions']['features']:
        data=feature['properties'];assert abs(data['relative_residual'])<=.1
        assert data['predicted_shadow_length']>0 and data['sun_altitude_deg']>0
        assert len(feature['geometry']['coordinates'][0])==5
        assert (data['predicted_shadow_length']-5)/5==pytest.approx(data['relative_residual'])
    assert result['warnings'] and result['duration_ms']>0

def test_shadow_angle_mode_exact_known_candidate_and_night_mismatch():
    dt='2024-06-21T12:00:00Z';location={'latitude':51.5,'longitude':0}
    angle=sun_position(dt,**location)['sun_altitude_deg']
    result=shadow_regions({'datetime_utc':dt,'sun_altitude_deg':angle,'bounds':[-2,50,2,54],'grid_step_deg':1,
        'candidates':[location,{'latitude':-51.5,'longitude':180,'label':'nightside'}]})
    one,two=result['candidate_scores']
    assert one['matches_tolerance'] and one['compatibility_score']==pytest.approx(1)
    assert two['sun_altitude_deg']<0 and two['compatibility_score']==0
    assert not two['matches_tolerance'] and two['relative_residual'] is None
    assert 'not location probability' in result['score_semantics']

def test_timezone_offset_normalized_without_assuming_local_timezone():
    one=shadow_regions({**SCENARIO,'datetime_utc':'2024-02-29T15:59:59+02:00'})
    two=shadow_regions(SCENARIO)
    assert one['datetime_utc']==two['datetime_utc'] and one['regions']==two['regions']

@pytest.mark.parametrize('change',[{'datetime_utc':'2024-02-29T13:59:59'}, {'datetime_utc':'not-a-date'},
    {'object_height':0},{'shadow_length':-1},{'object_height':True},{'sun_altitude_deg':50},
    {'bounds':[180,-50,-180,80]},{'grid_step_deg':.1},{'tolerance_fraction':0},{'max_cells':2001},
    {'bounds':[-180,-90,180,90],'grid_step_deg':.5},{'surprise':'unreviewed'},
    {'candidates':[{'latitude':float('nan'),'longitude':0}]}])
def test_shadow_invalid_or_missing_inputs_never_invent_parameters(change):
    with pytest.raises(LocalToolError) as error:shadow_regions({**SCENARIO,**change})
    assert error.value.code=='invalid_arguments'

def test_shadow_bounded_geojson_has_explicit_truncation():
    result=shadow_regions({**SCENARIO,'max_cells':1,'tolerance_fraction':.5})
    assert result['matching_cells_total']>1 and result['matching_cells_returned']==1 and result['truncated']

@pytest.mark.parametrize('operation',[lambda **k:tiktok_timestamp('6854717870488702213',**k),
 lambda **k:shadow_regions(SCENARIO,**k),lambda **k:role_classify(['CEO'],**k)])
def test_cancel_and_deadline_do_not_execute_local_operations(operation):
    event=threading.Event();event.set()
    with pytest.raises(LocalToolError) as error:operation(cancel_event=event)
    assert error.value.code=='cancelled'
    with pytest.raises(LocalToolError) as error:operation(deadline=time.monotonic()-1)
    assert error.value.code=='timeout'


def test_shadow_cancellation_is_checked_inside_actual_grid_loop():
    class CancelAfterChecks:
        def __init__(self):self.calls=0
        def is_set(self):
            self.calls+=1
            return self.calls>=4
    event=CancelAfterChecks()
    with pytest.raises(LocalToolError) as error:
        shadow_regions({**SCENARIO,'grid_step_deg':.5},cancel_event=event)
    assert error.value.code=='cancelled' and event.calls==4

@pytest.mark.parametrize('title,level',[('Chief Executive Officer','Executive'),('Director of Finance','Director'),
 ('Senior Software Engineer','Senior'),('Junior Developer','Junior'),('Intern','Entry')])
def test_mit_local_role_classifier_upstream_examples(title,level):
    result=role_classify([title]);assert result['results'][0]['role_level']==level
    assert result['network_requests']==0 and result['warnings']

def test_role_classifier_keeps_input_and_unknown_is_heuristic_not_employment_fact():
    result=execute('role_classify',{'titles':['Непроверенный текст должности','CEO']})
    assert result['results'][0]['title']=='Непроверенный текст должности'
    assert result['results'][0]['role_level']=='Staff'
    assert result['results'][1]['input_index']==1

@pytest.mark.parametrize('args',[{}, {'titles':[]},{'titles':['x'*257]},{'titles':['CEO'],'token':'SECRET'}])
def test_role_strict_schema(args):
    with pytest.raises(LocalToolError):execute('role_classify',args)

def test_local_tool_schema_is_finite_and_unknown_commands_cannot_execute():
    assert set(INPUT_SCHEMAS)=={'tiktok_timestamp','shadow_regions','role_classify'}
    assert all(row['additionalProperties'] is False for row in INPUT_SCHEMAS.values())
    with pytest.raises(LocalToolError):execute('shell',{'command':'anything'})
