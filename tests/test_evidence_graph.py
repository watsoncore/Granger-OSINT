from grangerpet.evidence_graph import build
import threading
import pytest


def record(kind,platform,url,details,number=1):return {'evidence_id':'ev_'+str(number).zfill(20),'type':kind,'platform':platform,'url':url,'title':'alice','details':details}


def test_equal_nicknames_on_different_platforms_never_merge_owners():
    graph=build([record('profile','github','https://github.com/alice',{'login':'alice'}),record('profile','hn','https://news.ycombinator.com/user?id=alice',{'username':'alice'},2)])
    assert len([n for n in graph['entities'] if n['type']=='username'])==2
    assert len([n for n in graph['entities'] if n['type']=='public_profile'])==2
    assert not any('owner' in e['relation_type'] or 'same' in e['relation_type'] for e in graph['relations'])
    assert all(e['evidence_ids'] for e in graph['relations'])


def test_local_phone_plan_metadata_enriches_the_same_manual_number_without_locating_a_person():
    from grangerpet.research_canvas import new_document,add_node,merge_evidence
    doc=new_document('Phone reference fixture')
    identifier=add_node(doc,{'type':'phone','value':'+12025550123','label':'QA number'})
    from grangerpet.agent_evidence import normalize_evidence
    raw=record('phone_metadata','Numbering plan','',{'e164':'+12025550123','country':'US','country_code':1})
    raw.update(id='+12025550123',status='metadata')
    row=normalize_evidence(raw,
        'phone_metadata','+12025550123')
    merge_evidence(doc,[row])
    phones=[node for node in doc['entities'] if node['type']=='phone']
    assert len(phones)==1 and phones[0]['id']==identifier and phones[0]['evidence_ids']
    assert phones[0]['attributes']['numbering_metadata_only']
    assert phones[0]['attributes']['owner_verified'] is False
    assert phones[0]['attributes']['current_location_verified'] is False


def test_email_domain_observation_keeps_email_case_and_never_verifies_a_mailbox():
    graph=build([record('email_domain','mail_dns','https://dns.google/query?name=example.org&type=MX',
        {'email':'PublicName@example.org','domain':'example.org'})],full=True)
    email=next(node for node in graph['entities'] if node['type']=='email')
    assert email['attributes']['address']=='PublicName@example.org'
    assert email['attributes']['mailbox_verified'] is False
    assert any(edge['relation_type']=='uses_email_domain' for edge in graph['relations'])


def test_transactions_link_addresses_but_service_labels_never_verify_identity():
    graph=build([record('transaction','ton','https://example.org/tx',{'chain':'ton','tx_hash':'actual-hash','from_address':'address1','to_address':'address2'}),record('label','ton','https://example.org/label',{'chain':'ton','address':'address2','label':'Bybit'},2)])
    assert {e['relation_type'] for e in graph['relations']} >= {'sent_from','sent_to','source_labels_address'}
    assert all(n['attributes']['owner_verified'] is False for n in graph['entities'] if n['type']=='blockchain_address')
    assert any(e['claim_kind']=='unverified_label' and e['verification_status']=='unverified' for e in graph['relations'])


def test_visual_candidates_and_camera_gps_are_different_uncertain_relationships():
    image='img_'+'a'*64
    graph=build([record('image_analysis','local','',{'attachment_id':image,'metadata':{'gps':{'latitude':55.75,'longitude':37.6}}}),record('image_analysis','geoclip','',{'attachment_id':image,'model_version':'fixture','predictions':[{'rank':1,'latitude':35.6,'longitude':139.7,'raw_score':.9}]},2)])
    assert {e['relation_type'] for e in graph['relations']}=={'metadata_reports_coordinate','has_geographic_hypothesis'}
    assert [n for n in graph['entities'] if n['type']=='geographic_candidate'][0]['attributes']['calibrated_probability'] is False


def test_graph_is_paged_cancellable_and_neighbors_keep_evidence():
    data=[record('profile','github',f'https://github.com/u{i}',{'login':f'u{i}'},i) for i in range(10)]
    first=build(data,limit=4);assert len(first['entities'])==4 and first['next_offset']==4
    next_page=build(data,limit=4,offset=4);assert {n['id'] for n in first['entities']}.isdisjoint(n['id'] for n in next_page['entities'])
    profile=next(n for n in first['entities'] if n['type']=='public_profile')
    neighbors=build(data,center=profile['id']);assert any(e['from_id']==profile['id'] for e in neighbors['relations'])
    event=threading.Event();event.set()
    with pytest.raises(InterruptedError):build(data,cancel_event=event)
