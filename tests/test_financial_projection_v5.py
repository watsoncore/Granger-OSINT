"""V5 observed transfers: provider conflict, action scope and retained proof."""
from copy import deepcopy
from grangerpet.engine.blockchain_analytics import analyze_transactions
from grangerpet.evidence_graph import build
from grangerpet.agent_evidence import normalize_evidence

TON='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'
RAW='0:8c50fdc65bbb398b475838a8037346fe9abe97d09870a296d0df46146f34dd64'
PEER='0:'+'1'*64
def tx(amount='0.000000001',**values):return {'chain':'ton','event_id':'same-event','tx_hash':'same-tx','from_address':TON,'to_address':PEER,'amount_decimal':amount,'asset':'TON','timestamp':'2026-11-05T01:00:00Z',**values}
def evidence(row,source):return normalize_evidence({'id':source,'type':'transaction','title':'Observed movement','platform':source,'url':'https://example.org/'+source,'details':row},'blockchain_gansar',TON)

def test_conflicting_amount_providers_count_once_and_keep_unknown_amount_and_both_proofs():
 records=[evidence(tx(),'provider-one'),evidence(tx('0.000000002',from_address=RAW),'provider-two')]
 before=deepcopy(records)
 graph=build(records,full=True,limit=5000)
 flow=next(edge for edge in graph['relations'] if edge['relation_type']=='transfers')
 assert flow['aggregate']['count']==1 and flow['aggregate']['amount'] is None
 assert flow['aggregate']['amount_conflict_count']==1 and flow['aggregate']['unknown_amount_count']==1
 assert set(flow['evidence_ids'])=={row['evidence_id'] for row in records}
 assert len(flow['source_urls'])==2 and records==before
 rows=[{**row['details'],'evidence_id':row['evidence_id'],'url':row['url']} for row in records]
 analytics=analyze_transactions(rows,RAW,'ton')
 assert analytics['unique_events']==1 and analytics['assets'][0]['outgoing'] is None
 assert analytics['assets'][0]['amount_conflict_events']==1
 assert len(analytics['counterparties'][0]['evidence_ids'])==2

def test_action_index_distinguishes_movements_sharing_a_hash_and_all_can_be_drilled():
 records=[evidence(tx(str(index+1),event_semantics={'action_index':index}),'provider-'+str(index)) for index in range(2)]
 graph=build(records,full=True,limit=5000)
 flow=next(edge for edge in graph['relations'] if edge['relation_type']=='transfers')
 assert flow['aggregate']['count']==2 and flow['aggregate']['amount']=='3'
 assert len(flow['aggregate']['transaction_ids'])==2
 events=[node for node in graph['entities'] if node['type']=='transaction']
 assert {event['attributes']['tx_hash'] for event in events}=={'same-tx'}
 assert all(event['attributes']['from_address']==TON and event['attributes']['to_address']==PEER for event in events)
 analytics=analyze_transactions([row['details'] for row in records],RAW,'ton')
 assert analytics['unique_events']==2 and analytics['assets'][0]['outgoing']=='3'

def test_failed_and_successful_claims_for_same_movement_do_not_become_confirmed_money():
 records=[evidence(tx(status='completed'),'one'),evidence(tx(status='failed'),'two')]
 graph=build(records,full=True,limit=5000)
 assert not any(edge['relation_type']=='transfers' for edge in graph['relations'])
 event=next(node for node in graph['entities'] if node['type']=='transaction')
 assert event['attributes']['status']=='conflicting_observations' and len(event['evidence_ids'])==2
 analytics=analyze_transactions([row['details'] for row in records],RAW,'ton')
 assert analytics['unique_events']==0 and analytics['excluded']['conflicting_status_observations']==1

def test_network_aliases_do_not_double_count_and_unknown_precision_is_not_scaled():
 rows=[tx('0.000000000000000000001',chain='ethereum',from_address='0x'+'1'*40,to_address='0x'+'2'*40,asset='ETH'),tx('0.000000000000000000001',chain='eth',from_address='0x'+'1'*40,to_address='0x'+'2'*40,asset='ETH')]
 analytics=analyze_transactions(rows,'0x'+'1'*40,'eth')
 assert analytics['unique_events']==1 and analytics['assets'][0]['outgoing']=='0.000000000000000000001'
