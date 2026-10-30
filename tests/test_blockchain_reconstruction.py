from copy import deepcopy
from decimal import Decimal

from grangerpet.engine.blockchain_analytics import analyze_transactions
from grangerpet.engine.blockchain_rows import normalize_dossier
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.evidence_graph import build
from grangerpet.investigation_analysis import analyze,model_context
from test_reconstruction_analysis import TON,RAW,PEER,tx


def test_unknown_token_tickers_do_not_become_one_asset_and_ton_embedded_contracts_canonicalize():
    result=analyze_transactions([tx('one',asset='USD'),tx('two',asset='USD'),
        tx('three',asset='JETTON:'+TON),tx('four',asset='JETTON:'+RAW)],TON,'ton')
    assert len(result['assets'])==3
    jetton=next(item for item in result['assets'] if item['contract'])
    assert jetton['event_count']==2 and jetton['outgoing']=='0.2' and jetton['contract']==RAW
    assert all(item['identity_status']=='contract_unknown_not_aggregated' for item in result['assets'] if item!=jetton)


def test_unknown_directional_amount_is_not_zero_and_known_subtotal_is_explicit():
    value=analyze_transactions([tx('in', '5',from_address=PEER,to_address=RAW),tx('out',None)],TON,'ton')
    asset=value['assets'][0]
    assert asset['incoming']=='5' and asset['outgoing'] is None and asset['volumes_partial']
    assert asset['amount_coverage']['outgoing']=={'known_events':0,'unknown_events':1}
    peer=value['counterparties'][0]['volumes_by_asset']['ton|TON']
    assert peer['incoming']=='5' and peer['outgoing'] is None


def test_repeated_pattern_has_an_explicit_non_accusatory_criterion_and_measured_intervals():
    rows=[tx(str(i),'0.123456789012345678901',timestamp=f'2026-10-01T12:{i*2:02d}:00Z') for i in range(3)]
    value=analyze_transactions(rows,TON,'ton')
    assert value['assets'][0]['outgoing']=='0.370370367037037036703'
    pattern=value['repeated_patterns'][0]
    assert pattern['count']==3 and pattern['median_interval_seconds']==120
    assert 'причина' in pattern['interpretation'] and pattern['criteria'].startswith('at_least_3')
    assert value['activity_by_hour_utc']=={'2026-10-01T12:00:00+00:00':3}


def test_graph_does_not_merge_long_same_prefix_contracts_and_keeps_exact_dates_amounts_aliases():
    contract1='0:'+'2'*63+'1';contract2='0:'+'2'*63+'2'
    report={'target_address':TON,'detected_chains':['ton'],'transactions':[
        tx('one','0.12345678901234567890123456789',asset='USD',contract=contract1),
        tx('two','0.00000000000000000000000000001',asset='USD',contract=contract1,from_address=RAW),
        tx('three','9',asset='USD',contract=contract2)]}
    rows=[normalize_evidence(row,'blockchain_gansar',TON) for row in normalize_dossier(report)]
    graph=build(rows,full=True,limit=5000,goal=TON)
    flows=[edge for edge in graph['relations'] if edge['relation_type']=='transfers']
    assert len(flows)==2
    primary=next(edge for edge in flows if edge['aggregate']['count']==2)
    assert primary['aggregate']['amount']=='0.12345678901234567890123456790'
    assert primary['aggregate']['first_seen']=='2026-10-01T12:00:00+00:00'
    wallet=next(node for node in graph['entities'] if node['type']=='blockchain_address' and node['attributes']['address']==RAW)
    assert wallet['attributes']['transaction_count']==3 and wallet['attributes']['counterparty_count']==1
    assert TON in wallet['attributes']['original_addresses'] and RAW in wallet['attributes']['original_addresses']


def test_unknown_contract_holdings_and_dated_assets_survive_analysis_without_name_merge():
    report={'target_address':TON,'detected_chains':['ton'],'tokens':[{'chain':'ton','name':'Same','symbol':'USD','amount_decimal':'2','source':'one'},
        {'chain':'ton','name':'Same','symbol':'USD','amount_decimal':'3','source':'two'}]}
    rows=normalize_dossier(report)
    tokens=[row for row in rows if row['type']=='token_asset']
    assert len(tokens)==2 and tokens[0]['id']!=tokens[1]['id']
    result=analyze({'goal':TON,'evidence':[normalize_evidence(row,'blockchain_gansar',TON) for row in rows]})
    assert len(result['assets'])==2
    assert all(item['data']['asset_identity_status']=='contract_unknown_not_aggregated' for item in model_context(result)['assets'])


def test_alternate_asset_sections_do_not_erase_known_balance_or_duplicate_nft():
    rows=[{'id':'token','type':'token_asset','title':'Tether USD','details':{'contract':PEER,'amount_decimal':'0.000000','symbol':'USD₮'}},
        {'id':'alternate-token','type':'token_asset','title':'USD₮','details':{'asset_id':PEER,'amount_decimal':None}},
        {'id':'token-nft','type':'token_asset','title':'Name','details':{'contract':RAW,'symbol':'NFT'}},
        {'id':'nft','type':'nft_asset','title':'Name','details':{'asset_id':TON,'ownership_verified':False,'ownership_status':'current'}}]
    normalized=[normalize_evidence({**row,'platform':'Fixture','details':{**row['details'],'chain':'ton','target_address':TON}},'blockchain_gansar',TON) for row in rows]
    value=analyze({'goal':TON,'evidence':normalized})
    assert len(value['assets'])==2
    token=next(row for row in value['assets'] if row['kind']=='token_asset')
    assert token['data']['amount_decimal']=='0.000000' and len(token['evidence_ids'])==2
    nft=next(row for row in value['assets'] if row['kind']=='nft_asset')
    assert nft['data']['ownership_verified'] is False and len(nft['evidence_ids'])==2
    assert nft['field_sources']['ownership_status']['evidence_id']==normalized[-1]['evidence_id']
