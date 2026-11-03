from types import SimpleNamespace
import threading
import time
from grangerpet.visual_models import tools,observations,pipeline


def test_completed_computation_without_clusters_is_empty_not_geolocation(monkeypatch):
    fake=SimpleNamespace(infer=lambda *a,**k:{'status':'completed','predictions':[],'noise_frac':1.,'sample_count':8})
    monkeypatch.setattr('grangerpet.visual_models.manager.get_manager',lambda:fake)
    store=SimpleNamespace(read_bytes=lambda *a:b'fixture pixels')
    args={'attachment_id':'img_'+'a'*64,'samples':8,'seed':0}
    outcome=tools.execute('waypoint_predict',args,store=store,cancel_event=threading.Event(),deadline=time.monotonic()+5)
    assert outcome['status']=='empty' and outcome['error_code']=='no_geographic_candidates'
    record=outcome['results'][0]
    assert record['status']=='unconfirmed' and record['details']['computation_status']=='completed'
    assert record['details']['predictions']==[] and record['details']['status']=='no_candidates'
    saved=observations.cached('waypoint_predict',args,[record])
    assert saved['status']=='empty' and saved['inference_calls']==0


def test_legacy_completed_empty_checkpoint_is_not_replayed_as_complete():
    args={'attachment_id':'img_'+'b'*64,'samples':8}
    row={'status':'hypothesis','details':{'local_inference_signature':observations.signature('waypoint_predict',args),
        'status':'completed','predictions':[]}}
    outcome=observations.cached('waypoint_predict',args,[row])
    assert outcome['status']=='empty' and outcome['results'][0]['status']=='unconfirmed'
    assert row['details']['status']=='completed'  # Never rewrite saved legacy bytes.
