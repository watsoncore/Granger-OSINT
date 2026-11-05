"""Stress-data construction only; these tests never launch native UI or network."""
import importlib.util
import json
from pathlib import Path

import pytest

from grangerpet.agent_evidence import normalize_evidence


SCRIPT=Path(__file__).resolve().parents[1]/'scripts/qa_canvas_stress.py'
SPEC=importlib.util.spec_from_file_location('qa_canvas_stress_v3',SCRIPT)
stress=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stress)


@pytest.mark.parametrize('count',[50,100,500,1000,5000])
def test_documented_sizes_have_mixed_media_cards_and_manual_projection(count):
    doc=stress.synthetic_document(count,'data:image/png;base64,SYNTHETIC_FIXTURE')
    assert len(doc['entities'])==count and len(doc['relations'])==count-1
    assert doc['view']['ui']['graph_mode']=='manual'
    assert doc['evidence']==[] and doc['view']['card_sizes']
    assert len({node['type'] for node in doc['entities']})==10
    assert any(node['attributes'].get('media') for node in doc['entities'])
    assert all(node['attributes']['origin']=='synthetic_fixture' for node in doc['entities'])
    assert all(node['source']==['Synthetic QA'] for node in doc['entities'])


def receipt_fixture():
    # Explicit offline fixture, never a live verification artifact.
    address='1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'
    return {'tool':'blockchain_gansar','status':'partial','query':address,
        'obtained_at':'2026-11-04T00:00:00+00:00','source_diagnostics':{'offline_unit_fixture':True},
        'results':[normalize_evidence({'id':'offline-fixture:one','title':'Offline transaction fixture',
            'type':'transaction','platform':'Offline fixture','details':{'chain':'btc','target_address':address,
                'from_address':address,'to_address':'1BoatSLRHtKNngkdXEeobR76b53LETtpyT','tx_hash':'fixture-one',
                'event_id':'fixture-one:0','amount_decimal':'1','asset':'BTC'}},'blockchain_gansar',address)]}


def test_observation_seed_preserves_exact_evidence_and_separate_provenance(tmp_path):
    payload=receipt_fixture();path=tmp_path/'offline-result-fixture.json'
    path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    doc,provenance=stress.observed_document(path)
    assert doc['evidence']==payload['results']
    assert doc['view']['ui']['graph_mode']=='wallet'
    assert provenance['data_origin']=='provided_observed_result'
    assert provenance['source_diagnostics']=={'offline_unit_fixture':True}
    assert provenance['evidence_sha256']==stress.evidence_digest(payload['results'])
    assert provenance['network_calls_by_stress_script']==0
    assert provenance['underlying_transactions']==1 and provenance['aggregate_relations']
    assert any(node['attributes'].get('is_root') for node in doc['entities'])
    assert all('synthetic_fixture'!=node['attributes'].get('origin') for node in doc['entities'])
    assert path.read_text(encoding='utf-8')==json.dumps(payload,ensure_ascii=False)


@pytest.mark.parametrize('patch',[{'mock':True},{'tool':'other'},{'status':'error'},{'results':[]}])
def test_inapplicable_observation_receipt_is_rejected(tmp_path,patch):
    path=tmp_path/'rejected.json';path.write_text(json.dumps({**receipt_fixture(),**patch}),encoding='utf-8')
    with pytest.raises(ValueError):stress.observed_document(path)


def test_invalid_stress_sizes_are_rejected():
    with pytest.raises(ValueError):stress.synthetic_document(123,'fixture')


def test_separate_maigret_workload_preserves_public_profile_evidence(tmp_path):
    rows=[normalize_evidence({'id':'offline-profile-fixture','type':'profile','platform':'GitHub',
        'url':'https://github.com/offline-fixture','title':'Offline fixture',
        'details':{'username':'offline-fixture','profile_url':'https://github.com/offline-fixture'}},'username_maigret','offline-fixture')]
    path=tmp_path/'profiles-fixture.json'
    path.write_text(json.dumps({'tool':'username_maigret','status':'partial','query':'offline-fixture','results':rows}),encoding='utf-8')
    with pytest.raises(ValueError):stress.observed_document(path)
    doc,proof=stress.observed_document(path,'username_maigret')
    assert doc['evidence']==rows and doc['view']['ui']['graph_mode']=='socmint'
    assert proof['source_tool']=='username_maigret' and proof['network_calls_by_stress_script']==0
    links=[edge for edge in doc['relations'] if edge['relation_type']=='returned_for_query']
    assert links and all(edge['attributes']['identity_verified'] is False for edge in links)
