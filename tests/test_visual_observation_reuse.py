"""Cache identity and source preservation; fixtures make no ML accuracy claim."""
from copy import deepcopy
import time

from grangerpet.agent_evidence import normalize_evidence
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings
from grangerpet.investigation import InvestigationEvidence
from grangerpet.investigation_progress import semantic_facts
from grangerpet.visual_models import pipeline
from grangerpet.visual_models.observations import signature

IMAGE = 'img_'+'a'*64


def observation(tool, **args):
    args = {'attachment_id': IMAGE, **args}
    return normalize_evidence({'id':signature(tool,args),'type':'image_analysis','title':'Fixture observation','platform':'Local fixture','status':'hypothesis',
        'details':{'status':'completed','capability':tool,'attachment_id':IMAGE,
            'local_inference_signature':signature(tool,args),'predictions':[{'lat':1,'lon':2}]}},
        'visual_geoint',IMAGE,'2026-10-30T00:00:00Z')


def test_exact_observation_reused_after_restore_without_readiness_or_worker(monkeypatch):
    row = observation('waypoint_predict', seed=7)
    reg = ToolRegistry(Settings(),attachment_ids=[IMAGE],secret_getter=lambda _: '')
    reg.restore_investigation([row],{})
    monkeypatch.setattr(reg,'_state',lambda *a: (_ for _ in ()).throw(AssertionError('New inference')))
    result = reg.execute('waypoint_predict',{'attachment_id':IMAGE,'seed':7})
    assert result['from_saved_data'] is True and result['inference_calls']==0
    assert result['results']==[row]
    store=InvestigationEvidence();store.restore([row],[])
    assert store.add(result)==[row['evidence_id']]
    assert store.records()==[row]  # Original time/tool/provenance is retained.


def test_effective_parameters_and_manifest_version_participate_in_cache_identity():
    args={'attachment_id':IMAGE}
    assert signature('geoclip_predict',args)==signature('geoclip_predict',{**args,'seed':9,'samples':64})
    assert signature('waypoint_predict',args)!=signature('waypoint_predict',{**args,'seed':9})
    assert signature('waypoint_predict',args)!=signature('waypoint_predict',{**args,'top_k':3})
    assert signature('waypoint_match',{**args,'reference_id':'img_'+'b'*64})!=signature('waypoint_match',{**args,'reference_id':'img_'+'c'*64})


def test_pipeline_reuses_completed_models_but_runs_metadata_and_preserves_stage_flags(monkeypatch):
    rows=[observation(name) for name in ('image_understand','geoclip_predict','waypoint_predict')]
    monkeypatch.setattr(pipeline.geoint_tools,'execute',lambda *a,**k:{'status':'complete','results':[]})
    monkeypatch.setattr(pipeline.visual_tools,'execute',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Model repeated')))
    monkeypatch.setattr(pipeline.scene,'execute',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Scene repeated')))
    result=pipeline.execute({'attachment_id':IMAGE,'include_ocr':False},Settings(),object(),
        deadline=time.monotonic()+5,reuse_records=rows)
    assert result['status']=='complete'
    assert all(s['from_saved_data'] for s in result['stages'] if s['tool']!='image_metadata')
    assert all(row in result['results'] for row in rows)


def test_seed_trials_are_not_independent_progress_but_other_image_or_method_is():
    first=observation('waypoint_predict');second=observation('waypoint_predict',seed=7)
    assert semantic_facts([first,second])==semantic_facts([first])
    assert len(semantic_facts([first,observation('geoclip_predict')]))==2
    other=deepcopy(second);other['details']['attachment_id']='img_'+'b'*64
    assert len(semantic_facts([first,other]))==2


def test_failed_observations_are_not_reused(monkeypatch):
    from grangerpet.visual_models.observations import cached
    row=observation('image_understand');row['details']['status']='timeout'
    assert cached('image_understand',{'attachment_id':IMAGE},[row]) is None
