"""Explicit vendor counterparty claims are not pairwise financial transfers."""
from copy import deepcopy

from grangerpet.agent_evidence import normalize_evidence
from grangerpet.evidence_graph import build


BTC='1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'
PEER='bc1pnyyy2n2wgjwfsmj283uf0qhusufphtf6ymcnmed8gc0umaz8qx3sajgafh'
EVM='0x'+'12'*20
EVM_PEER='0x'+'34'*20


def observation(identifier='one',chain='btc',target=BTC,address=PEER,count=20):
    return normalize_evidence({'id':'counterparty:'+identifier,'type':'blockchain_counterparty',
        'title':address,'platform':'Gansar offline DTO fixture','url':'https://example.org/public-observation',
        'details':{'chain':chain,'address':address,'target_address':target,'tx_count':count,
            'total_in':0.0003642,'total_out':0.0,
            'amounts_by_asset':{chain+'|native|BTC':{'in':'0.00036420','out':'0'}},
            'aggregate_amount_valid':True,'first_seen':'2026-11-02T20:36:22Z',
            'last_seen':'2026-11-02T20:36:22Z','acquisition':'public_blockchain_observation'}},
        'blockchain_gansar',target)


def test_actual_utxo_counterparty_shape_is_connected_without_inventing_a_transfer():
    record=observation();original=deepcopy(record)
    graph=build([record],full=True,limit=5000,goal=BTC)
    relation=next(edge for edge in graph['relations'] if edge['relation_type']=='source_reports_counterparty')
    assert relation['direction']=='undirected'
    assert relation['attributes']['count']==20
    assert relation['attributes']['first_seen']=='2026-11-02T20:36:22+00:00'
    assert relation['attributes']['last_seen']=='2026-11-02T20:36:22+00:00'
    assert relation['attributes']['financial_transfer'] is False
    assert relation['attributes']['owner_verified'] is False and relation['attributes']['direction_unknown'] is True
    assert 'aggregate' not in relation and 'amount' not in relation['attributes']
    assert 'total_in' not in relation['attributes'] and 'total_out' not in relation['attributes']
    assert not any(edge['relation_type']=='transfers' for edge in graph['relations'])
    assert relation['evidence_ids']==[record['evidence_id']]
    assert relation['source_urls']==[record['url']]
    assert relation['provenance'][0]['source_record_id']==record['evidence_id']
    assert 'tx_count' in relation['provenance'][0]['observed_field']
    assert record==original


def test_duplicate_providers_do_not_sum_reported_counts_and_each_claim_keeps_provenance():
    first=observation();second=observation('two',count=12)
    graph=build([first,first,second],full=True,limit=5000,goal=BTC)
    relations=[edge for edge in graph['relations'] if edge['relation_type']=='source_reports_counterparty']
    assert len(relations)==1
    relation=relations[0]
    assert relation['attributes']['count']==20
    assert relation['attributes']['count_semantics']=='maximum_source_reported_count_not_summed'
    assert {row['count'] for row in relation['attributes']['source_count_claims']}=={12,20}
    assert set(relation['evidence_ids'])=={first['evidence_id'],second['evidence_id']}
    assert len(relation['provenance'])==2


def test_identical_hex_counterparty_claims_have_different_network_scopes():
    records=[observation(chain,chain,EVM,EVM_PEER) for chain in ('eth','bsc')]
    graph=build(records,full=True,limit=5000,goal=EVM)
    nodes={node['id']:node for node in graph['entities']}
    relations=[edge for edge in graph['relations'] if edge['relation_type']=='source_reports_counterparty']
    assert len(relations)==2 and len({edge['id'] for edge in relations})==2
    assert {nodes[edge['from_id']]['attributes']['chain'] for edge in relations}=={'eth','bsc'}
    assert all(nodes[edge['from_id']]['attributes']['chain']==nodes[edge['to_id']]['attributes']['chain'] for edge in relations)
    assert all(not edge.get('aggregate') and edge['attributes']['financial_transfer'] is False for edge in relations)


def test_counterparty_claim_never_links_a_wallet_to_itself_or_invents_unknown_count():
    graph=build([observation(address=BTC),observation('unknown',count=None)],full=True,limit=5000,goal=BTC)
    relations=[edge for edge in graph['relations'] if edge['relation_type']=='source_reports_counterparty']
    assert len(relations)==1 and relations[0]['attributes']['count'] is None
