"""Contracts for candidate research; fixtures never claim a real location match."""
from types import SimpleNamespace
import threading
import time

import pytest

from grangerpet.geoint.research import hypotheses, queries_for, execute
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings

IMAGE='img_'+'a'*64


def observations():
    return [{'evidence_id':'ev_'+'1'*20,'platform':'GeoCLIP','details':{'attachment_id':IMAGE,
        'predictions':[{'lat':55.75,'lon':37.62,'raw_score':7},{'lat':55.7501,'lon':37.6201,'raw_score':6},
            {'lat':48.85,'lon':2.35,'raw_score':5}]}},
        {'evidence_id':'ev_'+'2'*20,'platform':'Florence','details':{'attachment_id':IMAGE,
            'description':'A clock tower and a city street.', 'tool':'image_understand'}}]


def test_nearby_model_points_cluster_without_probability_or_false_confirmation():
    candidates=hypotheses(observations(),IMAGE)
    assert len(candidates)==2
    assert len(candidates[0]['model_observations'])==2
    assert candidates[0]['verification_status']=='model_candidate'
    assert candidates[0]['uncertainty_radius_m'] is None  # Never invent accuracy.
    assert len(hypotheses(observations(),'img_'+'b'*64))==0


def test_multilingual_queries_are_grounded_in_scene_and_candidate_not_country_guess():
    candidate=hypotheses(observations(),IMAGE)[0]
    candidate['region']='Candidate locality'
    query=queries_for(candidate,observations())
    assert {row['language'] for row in query}=={'en','ru'}
    assert 'clock tower' in query[0]['query'] and 'башня часы' in query[1]['query']


class Sources:
    def reverse(self,candidate,cancel):return {'name':'Fixture place','source_url':'https://example.org/place'}
    def landmarks(self,*args):return [{'name':'Fixture clock tower','latitude':55.75,'longitude':37.62}]
    def commons(self,*args):return []
    def wikipedia(self,*args):return []
    def panoramax(self,*args):return []


def test_no_photos_preserves_candidates_and_truthful_uncertainty():
    result=execute({'attachment_id':IMAGE},records=observations(),store=object(),sources=Sources())
    assert result['status']=='complete'
    assert all(candidate['verification_status']=='model_candidate' for candidate in result['candidates'])
    assert not any(row['type']=='reference_image' for row in result['results'])
    assert any('не найдены' in text for text in result['limitations'])


def test_alternative_regions_have_distinct_provenance_and_both_run_before_photo_work():
    class Control(Sources):
        def __init__(self):self.visits=[]
        def reverse(self,candidate,cancel):
            self.visits.append(('region',candidate['latitude']))
            return super().reverse(candidate,cancel)
        def commons(self,candidate,*args):
            self.visits.append(('photos',candidate['latitude']))
            return []
    sources=Control()
    regions=[{'latitude':43.157,'longitude':77.058,'label':'Медеу'},{'latitude':46.5,'longitude':11.8,'label':'Доломиты'}]
    result=execute({'attachment_id':IMAGE,'alternative_regions':regions},records=observations(),store=object(),sources=sources)
    assert sources.visits[:2]==[('region',43.157),('region',46.5)]
    assert len(result['candidates'])==2 and all(c['location_role']=='proposed_region' for c in result['candidates'])
    assert all(not c['source_model'] and not c['supporting_evidence'] and not c['camera_position_verified'] for c in result['candidates'])


def test_one_provider_error_does_not_discard_other_candidate_or_claim_success():
    class Failed(Sources):
        def commons(self,*args):raise RuntimeError('Never expose PRIVATE-ERROR-DETAIL')
    result=execute({'attachment_id':IMAGE},records=observations(),store=object(),sources=Failed())
    assert result['status']=='partial' and len(result['candidates'])==2
    assert any(row.get('error_code')=='RuntimeError' for row in result['stages'])
    assert 'PRIVATE-ERROR' not in str(result)


def test_research_requires_saved_candidates_and_selected_attachment():
    result=execute({'attachment_id':IMAGE},records=[],store=object(),sources=Sources())
    assert result['status']=='unavailable' and not result['results']
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    assert registry.execute('geoint_research',{'attachment_id':IMAGE})['status']=='invalid_arguments'


def test_cancellation_retains_already_emitted_candidate():
    event=threading.Event();received=[]
    def emit(row):received.append(row);event.set()
    result=execute({'attachment_id':IMAGE},records=observations(),store=object(),sources=Sources(),cancel_event=event,on_result=emit)
    assert result['status']=='cancelled' and received and result['results']


def test_agent_continuation_schedules_research_without_repeating_local_models():
    from grangerpet.agent_evidence import normalize_evidence
    registry=ToolRegistry(Settings(),attachment_ids=[IMAGE],secret_getter=lambda _: '')
    row={'id':'predict','type':'image_analysis','title':'Fixture prediction','platform':'GeoCLIP','details':observations()[0]['details']}
    registry.evidence.restore([normalize_evidence(row,'visual_geoint',IMAGE)],[])
    calls=registry.continuation_calls('Найди место съёмки фото')
    assert calls==[{'name':'geoint_research','arguments':{'attachment_id':IMAGE}}]


def test_explicit_metadata_ocr_scope_prevents_other_sources_even_if_model_requests_one():
    registry=ToolRegistry(Settings(),attachment_ids=[IMAGE],secret_getter=lambda _: '')
    schemas=registry.schemas(task='Только локальные метаданные и OCR выбранного изображения, без внешних источников.')
    names={row['function']['name'] for row in schemas}
    assert names<={'image_metadata','image_ocr','evidence_get','evidence_graph','capabilities_find'}
    blocked=registry.execute('web_search',{'query':'must not leave the computer'})
    assert blocked['error_code']=='outside_user_local_scope' and not blocked['results']
