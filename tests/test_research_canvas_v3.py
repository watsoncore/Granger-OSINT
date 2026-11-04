"""Canvas view state and canonical crypto identity round trips."""
from copy import deepcopy

import pytest

from grangerpet.agent_evidence import normalize_evidence
from grangerpet.agent_journal import InvestigationJournal
from grangerpet.crypto_targets import resolve_crypto_target
from grangerpet.engine.blockchain_rows import normalize_dossier
from grangerpet.research_canvas import (
    CanvasError, CanvasStore, add_node, apply, merge_evidence, new_document, validate,
)


EVM = '0xAbCdEf0123456789aBcDEF0123456789abCdef01'
BTC = '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'
TON = 'UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'
CHAINS = ('eth','bsc','polygon','arbitrum','optimism','avalanche')


def nodes_and_edge():
    doc = new_document('Сохранённое расследование')
    first = add_node(doc, {'type': 'person', 'label': 'Аналитик А'})
    second = add_node(doc, {'type': 'person', 'label': 'Аналитик Б'})
    doc = apply(doc, 'edge', {'from_id': first, 'to_id': second, 'relation_type': 'hypothesis'})
    return doc, first, second, doc['relations'][0]['id']


def test_ui_card_sizes_and_expansion_round_trip_in_encrypted_store(tmp_path):
    doc, first, second, edge = nodes_and_edge()
    doc = apply(doc, 'duplicate_nodes', {'ids': [first]})
    visual = next(iter(doc['view']['instances']))
    doc = apply(doc, 'view', {'view': {
        'ui': {'inspector_tab': 'actions', 'inspector_width': 440, 'inspector_open': False,
               'card_mode': 'expanded', 'graph_mode': 'transactions'},
        'card_sizes': {first: {'width': 360, 'height': 190}, visual: {'width': 210, 'height': 72}},
        'expanded': [first, visual], 'expanded_relations': [edge]}})
    store = CanvasStore(InvestigationJournal(tmp_path / 'profile'))
    saved = store.save(doc, 0)
    reopened = store.load(doc['id'])
    assert reopened['view'] == saved['view']
    assert reopened['view']['ui']['inspector_width'] == 440
    assert reopened['view']['card_sizes'][visual] == {'width': 210, 'height': 72}
    assert 'Аналитик А'.encode() not in (store._folder(doc['id']) / 'r0000000001.dpapi').read_bytes()


def test_partial_ui_and_card_size_patches_preserve_existing_view_state():
    doc, first, second, _ = nodes_and_edge()
    doc = apply(doc, 'card_size', {'id': first, 'width': 350, 'height': 200})
    doc = apply(doc, 'view', {'view': {'ui': {'inspector_width': 450, 'card_mode': 'compact'}}})
    doc = apply(doc, 'view', {'view': {'ui': {'inspector_tab': 'evidence'},
        'card_sizes': {second: {'width': 200, 'height': 120}}}})
    assert doc['view']['ui'] == {'inspector_width': 450, 'card_mode': 'compact', 'inspector_tab': 'evidence'}
    assert len(doc['view']['card_sizes']) == 2
    assert doc['view']['card_sizes'][first] == {'width': 350, 'height': 200}


@pytest.mark.parametrize('patch', [
    {'ui': {'inspector_width': 219}}, {'ui': {'inspector_width': 651}},
    {'ui': {'inspector_width': True}}, {'ui': {'inspector_width': float('inf')}},
    {'ui': {'inspector_tab': 'unknown'}}, {'ui': {'graph_mode': 'invented'}},
    {'ui': {'card_mode': 'big'}}, {'ui': {'inspector_open': 1}}, {'ui': {'other': True}},
    {'ui': []}, {'card_sizes': []}, {'expanded': [['bad']]},
    {'expanded_relations': ['rel_' + '0' * 24]}, {'viewport': {'x': 0, 'y': 0}},
    {'viewport': {'x': 0, 'y': 0, 'scale': 0}},
])
def test_invalid_ui_mutation_is_rejected_without_changing_source_document(patch):
    doc, _, _, _ = nodes_and_edge()
    original = deepcopy(doc)
    with pytest.raises(CanvasError):
        apply(doc, 'view', {'view': patch})
    assert doc == original


@pytest.mark.parametrize('width,height', [(159, 120), (721, 120), (200, 71),
    (200, 641), (True, 120), (200, float('nan'))])
def test_invalid_card_size_is_rejected(width, height):
    doc, first, _, _ = nodes_and_edge()
    with pytest.raises(CanvasError):
        apply(doc, 'card_size', {'id': first, 'width': width, 'height': height})


def test_entity_deletion_cleans_visual_state_and_relations_but_keeps_evidence():
    doc, first, second, edge = nodes_and_edge()
    doc = apply(doc, 'duplicate_nodes', {'ids': [first]})
    visual = next(iter(doc['view']['instances']))
    doc = apply(doc, 'view', {'view': {'card_sizes': {
        first: {'width': 200, 'height': 120}, visual: {'width': 300, 'height': 200},
        second: {'width': 220, 'height': 100}}, 'expanded': [first, visual, second],
        'expanded_relations': [edge]}})
    doc['view']['manual_positions'] = {**doc['view']['positions'], visual: {'x': 10, 'y': 20}}
    doc = apply(doc, 'annotate', {'entity_id': edge, 'annotation': {'markdown': 'Сохранить provenance'}})
    before = deepcopy(doc['evidence'])
    removed = apply(doc, 'delete_entity', {'ids': [first]})
    assert removed['evidence'] == before and removed['relations'] == []
    assert set(removed['view']['card_sizes']) == {second}
    assert set(removed['view']['manual_positions']) == {second}
    assert removed['view']['expanded'] == [second] and removed['view']['expanded_relations'] == []
    assert not removed['view']['instances'] and edge not in removed['annotations']


def test_hide_restore_keeps_sizes_and_duplicate_has_independent_size():
    doc, first, _, _ = nodes_and_edge()
    doc = apply(doc, 'card_size', {'id': first, 'width': 200, 'height': 120})
    doc = apply(doc, 'duplicate_nodes', {'ids': [first]})
    visual = next(iter(doc['view']['instances']))
    assert doc['view']['card_sizes'][visual] == doc['view']['card_sizes'][first]
    doc = apply(doc, 'card_size', {'id': visual, 'width': 400, 'height': 250})
    doc = apply(apply(doc, 'hide', {'ids': [visual]}), 'restore', {'ids': [visual]})
    assert doc['view']['card_sizes'][first] == {'width': 200, 'height': 120}
    assert doc['view']['card_sizes'][visual] == {'width': 400, 'height': 250}


@pytest.mark.parametrize('chain,address', [('ton', TON), ('btc', BTC),
    ('btc', 'BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4'),
    ('tron', 'TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj'),
    ('solana', '11111111111111111111111111111111'), *[(chain, EVM) for chain in CHAINS]])
def test_manual_wallet_and_import_share_one_network_scoped_entity(chain, address):
    doc = new_document()
    identifier = add_node(doc, {'type': 'blockchain_address', 'label': 'Мой адрес', 'value': address, 'chain': chain})
    report = {'target_address': address, 'detected_chains': [chain], 'balances': [
        {'chain': chain, 'address': address, 'asset': 'OBSERVED', 'amount_decimal': '1'}]}
    records = [normalize_evidence(row, 'blockchain_gansar', address) for row in normalize_dossier(report)]
    merge_evidence(doc, records)
    wallets = [node for node in doc['entities'] if node['type'] == 'blockchain_address']
    assert len(wallets) == 1 and wallets[0]['id'] == identifier
    assert wallets[0]['attributes']['chain'] == chain
    assert wallets[0]['attributes']['address'] == resolve_crypto_target(address, chain)['canonical_address']
    assert doc['annotations'][identifier]['label'] == 'Мой адрес'
    validate(doc)


def test_manual_evm_requires_network_and_never_combines_cross_network_wallets():
    doc = new_document()
    with pytest.raises(CanvasError, match='Выберите сеть'):
        add_node(doc, {'type': 'blockchain_address', 'label': EVM})
    eth = add_node(doc, {'type': 'blockchain_address', 'label': EVM, 'chain': 'eth'})
    bsc = add_node(doc, {'type': 'blockchain_address', 'label': EVM, 'chain': 'bsc'})
    assert eth != bsc
    with pytest.raises(CanvasError):
        add_node(doc, {'type': 'blockchain_address', 'label': '50.7.89.130'})


def test_old_document_without_v3_view_fields_and_stale_manual_snapshot_stays_readable():
    doc, first, _, _ = nodes_and_edge()
    for field in ('card_sizes', 'ui', 'expanded', 'expanded_relations'):
        doc['view'].pop(field, None)
    doc['view']['manual_positions'] = {'ent_' + '0' * 24: {'x': 1, 'y': 2}}
    assert validate(doc) is doc
    changed = apply(doc, 'card_size', {'id': first, 'width': 240, 'height': 100})
    assert changed['view']['card_sizes'][first]['width'] == 240


def test_editing_analyst_edge_preserves_its_note_and_expansion_on_new_id():
    doc, first, second, edge = nodes_and_edge()
    doc = apply(doc, 'view', {'view': {'expanded_relations': [edge]}})
    doc = apply(doc, 'annotate', {'entity_id': edge, 'annotation': {'markdown': 'Гипотеза'}})
    doc = apply(doc, 'edge_edit', {'relation_id': edge, 'from_id': first, 'to_id': second,
        'relation_type': 'possibly_related'})
    changed = doc['relations'][0]['id']
    assert changed != edge and doc['view']['expanded_relations'] == [changed]
    assert doc['annotations'][changed]['markdown'] == 'Гипотеза' and edge not in doc['annotations']


@pytest.mark.parametrize('mode',['wallet','flow','counterparties','paths'])
def test_crypto_worker_layout_state_round_trip_restores_manual_positions(mode):
    doc, first, second, _ = nodes_and_edge()
    original=deepcopy(doc['view']['positions'])
    arranged=apply(doc,'layout',{'mode':mode,'positions':{
        first:{'x':0,'y':0},second:{'x':420,'y':150}}})
    assert arranged['view']['layout']==mode
    assert arranged['view']['manual_positions']==original
    restored=apply(arranged,'layout',{'mode':'manual','positions':{}})
    assert restored['view']['positions']==original


def test_incremental_crypto_import_rebuilds_aggregate_from_all_retained_observations():
    address='0x'+'12'*20
    peer='0x'+'34'*20
    doc=new_document()
    def transaction(event,amount):
        return normalize_evidence({'id':event,'type':'transaction','title':event,'platform':'Offline fixture',
            'details':{'chain':'eth','target_address':address,'from_address':address,'to_address':peer,
                'event_id':event,'tx_hash':event,'amount_decimal':amount,'asset':'ETH'}},'blockchain_gansar',address)
    first,second=transaction('first','1'),transaction('second','2')
    merge_evidence(doc,[first])
    wallet=next(node for node in doc['entities'] if node['type']=='blockchain_address')
    identifier=wallet['id']
    doc=apply(doc,'annotate',{'entity_id':identifier,'annotation':{'markdown':'Ручная заметка'}})
    doc=apply(doc,'positions',{'positions':{identifier:{'x':913,'y':417,'pinned':True}}})
    merge_evidence(doc,[second])
    edge=next(edge for edge in doc['relations'] if edge['relation_type']=='transfers')
    aggregate=edge['aggregate']
    transactions={node['id'] for node in doc['entities'] if node['type']=='transaction'}
    assert aggregate['count']==2 and aggregate['amount']=='3'
    assert set(aggregate['transaction_ids'])==transactions and len(transactions)==2
    assert set(edge['evidence_ids'])=={first['evidence_id'],second['evidence_id']}
    assert {row['evidence_id'] for row in doc['evidence']}=={first['evidence_id'],second['evidence_id']}
    assert doc['view']['positions'][identifier]=={'x':913,'y':417,'pinned':True}
    assert doc['annotations'][identifier]['markdown']=='Ручная заметка'
    validate(doc)


def test_incremental_counterparty_import_keeps_maximum_claim_and_each_source_reference():
    from test_crypto_counterparty_graph import observation
    doc=new_document()
    first,second=observation('first',count=20),observation('second',count=12)
    merge_evidence(doc,[first]);merge_evidence(doc,[second])
    edge=next(edge for edge in doc['relations'] if edge['relation_type']=='source_reports_counterparty')
    assert edge['attributes']['count']==20
    assert {claim['count'] for claim in edge['attributes']['source_count_claims']}=={12,20}
    assert set(edge['evidence_ids'])=={first['evidence_id'],second['evidence_id']}
    assert edge['direction']=='undirected' and 'aggregate' not in edge
    assert edge['attributes']['financial_transfer'] is False and 'amount' not in edge['attributes']
    validate(doc)


@pytest.mark.parametrize('change',[{'success':False},{'to_address':'0x'+'56'*20},{'asset':'USDC','token_contract':'0x'+'78'*20}])
def test_refresh_retires_obsolete_tool_flow_but_preserves_proof_notes_and_manual_links(tmp_path,change):
    address='0x'+'12'*20;peer='0x'+'34'*20
    def observation(**changed):
        return normalize_evidence({'id':'refresh-event','type':'transaction','title':'Observed transfer',
            'platform':'Offline fixture','details':{'chain':'eth','target_address':address,
                'from_address':address,'to_address':peer,'event_id':'refresh-event','tx_hash':'refresh-event',
                'amount_decimal':'1','asset':'ETH','success':True,**changed}},'blockchain_gansar',address)
    first=observation();doc=new_document();merge_evidence(doc,[first])
    flow=next(edge for edge in doc['relations'] if edge['relation_type']=='transfers')
    doc=apply(doc,'annotate',{'entity_id':flow['id'],'annotation':{'markdown':'Проверить исходный перевод'}})
    doc=apply(doc,'edge',{'from_id':flow['from_id'],'to_id':flow['to_id'],'relation_type':'analyst_hypothesis'})
    manual=next(edge for edge in doc['relations'] if edge.get('origin')=='analyst')
    doc['view']['expanded_relations']=[flow['id']]
    positions=deepcopy(doc['view']['positions'])
    second=observation(**change);assert first['evidence_id']==second['evidence_id']
    merge_evidence(doc,[second]);validate(doc)
    assert flow['id'] not in {edge['id'] for edge in doc['relations']}
    assert manual in doc['relations'] and flow['id'] not in doc['view']['expanded_relations']
    retired=doc['retired_tool_relations'][flow['id']]
    assert retired['relation']==flow and retired['annotation']=={'markdown':'Проверить исходный перевод'}
    assert flow['id'] not in doc['annotations']
    assert doc['evidence'][0]['details']==first['details']
    assert doc['evidence'][0]['observations'][-1]['details']==second['details']
    assert all(doc['view']['positions'][key]==value for key,value in positions.items())
    store=CanvasStore(InvestigationJournal(tmp_path/'journal'));saved=store.save(doc,0)
    reopened=CanvasStore(InvestigationJournal(tmp_path/'journal')).load(doc['id'])
    assert reopened['retired_tool_relations']==saved['retired_tool_relations']
    assert manual in reopened['relations']
    # A later source correction may confirm the original flow again. Restore
    # its analyst annotation without erasing the archived projection/history.
    merge_evidence(reopened,[first]);validate(reopened)
    assert any(edge['id']==flow['id'] for edge in reopened['relations'])
    assert reopened['annotations'][flow['id']]['markdown']=='Проверить исходный перевод'
