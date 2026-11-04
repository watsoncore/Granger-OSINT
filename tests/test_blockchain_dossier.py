from grangerpet.engine.blockchain_rows import normalize_dossier
from grangerpet.engine.blockchain_contracts import diagnostics,policy,reason
import pytest


def test_protected_dossier_merge_retains_complementary_sections_and_scoped_id(tmp_path):
    from grangerpet.blockchain_store import BlockchainStore,merge_reports
    store=BlockchainStore(tmp_path)
    first={'target_address':'wallet','detected_chains':['ton'],'balances':[{'chain':'ton','asset':'TON','amount_decimal':'0.01'}]}
    second={'target_address':'wallet','detected_chains':['ton'],'ton_assets':[{'asset_id':'item','type':'nft'}]}
    report=merge_reports(first,second,'nft');identifier=store.save(report)
    assert store.load(identifier)==report
    assert b'wallet' not in next(tmp_path.iterdir()).read_bytes()
    assert report['balances']==first['balances'] and report['ton_assets']==second['ton_assets']
    with pytest.raises(ValueError):store.load('../../private')


def test_requested_blockchain_branches_remain_independent_and_address_scoped():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    r=ToolRegistry(Settings(),secret_getter=lambda name:'')
    address='0x'+'1'*40
    calls=r.continuation_calls('Проверь '+address+' NFT, ENS, контракт и контрагентов на уровень глубже')
    assert {call['arguments']['operation'] for call in calls}=={'nft','identity','contracts','trace'}
    assert {call['arguments']['address'] for call in calls}=={address}


def test_investigation_retains_more_than_fifty_structured_rows_without_losing_asset_sections():
    from grangerpet.investigation import InvestigationEvidence
    from grangerpet.agent_evidence import normalize_evidence
    rows=normalize_dossier({'target_address':'wallet','detected_chains':['ton'],
        'transactions':[{'chain':'ton','tx_hash':str(i),'event_id':str(i)} for i in range(100)]},max_transactions=100)
    store=InvestigationEvidence()
    records=[normalize_evidence(row,'blockchain_gansar','wallet','2026-10-30T00:00:00Z',())for row in rows]
    store.add({'tool':'blockchain_gansar','query':'wallet','status':'partial','obtained_at':'2026-10-30T00:00:00Z','results':records})
    assert len(store.records())==102
    assert any(row['type']=='blockchain_analytics' for row in store.records())


def test_distinct_asset_categories_survive_large_transaction_history_with_exact_values():
    report={'target_address':'wallet','detected_chains':['ton'],
        'transactions':[{'chain':'ton','tx_hash':str(i),'event_id':'event'+str(i),'amount_decimal':'0.000000001','from_address':'a','to_address':'b','asset':'TON','source':'tonapi'}for i in range(100)],
        'balances':[{'chain':'ton','address':'wallet','asset':'TON','amount_decimal':'1234567890123456789.000000001'}],
        'tokens':[{'chain':'ton','contract':'jetton','name':'Unverified token','holding_status':'current','raw':{'image':'https://example.org/jetton.png'}}],
        'ton_assets':[{'asset_id':'item','type':'nft','owner_address':'wallet','ownership_verified':False,'image_url':'https://example.org/nft.png'}],
        'ens_profile':{'lookup_status':'unavailable'},'contract_observations':[{'blockchain':'ton','address':'wallet','source':'getter'}]}
    rows=normalize_dossier(report,max_transactions=50)
    assert len([r for r in rows if r['type']=='transaction'])==50
    assert next(r for r in rows if r['type']=='balance')['details']['amount_decimal']=='1234567890123456789.000000001'
    assert next(r for r in rows if r['type']=='nft_asset')['details']['ownership_verified'] is False
    assert any(r['type']=='token_asset' for r in rows) and any(r['type']=='contract_observation' for r in rows)
    assert not any(r['details']['identity_verified'] for r in rows)


def test_provider_count_uses_real_start_events_not_endpoint_or_health_row_count():
    report={'source_health':[{'source':'tonapi','status':'partial'},{'source':'ton_assets','status':'ok'},{'source':'tonapi','status':'timeout'}]}
    result=diagnostics(report,{'providers_started':['tonapi','tonapi'],'requests_used':6,'finished':False})
    assert result['providers_attempted']==1 and result['http_requests']==6 and len(result['health'])==3
    assert result['provider_count_complete'] is False


def test_error_reasons_and_depth_modes_do_not_manufacture_provider_success():
    assert reason('error','HTTP403')=='HTTP_403'
    assert reason('partial','HTTP429 Retry-After')=='HTTP_429'
    assert reason('unavailable','API key required')=='MISSING_OPTIONAL_API_KEY'
    assert reason('partial',budget_exhausted=True)=='REQUEST_BUDGET_EXHAUSTED'
    assert policy({'mode':'deep'})['transactions']>policy({'mode':'standard'})['transactions']>policy({'mode':'quick'})['transactions']
    assert policy({'mode':'deep'})['seconds']>policy({'mode':'standard'})['seconds']
    assert policy({'mode':'quick','limit':1000})['transactions']==50


def test_agent_dedup_uses_effective_ton_operation_instead_of_encoding_or_refresh():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    from grangerpet.validators.ton_address import parse_ton_address
    r=ToolRegistry(Settings(research_mode='quick'),secret_getter=lambda name:'')
    address='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'
    first=r.canonical_arguments('blockchain_gansar',{'address':address})
    repeated=r.canonical_arguments('blockchain_gansar',{'address':parse_ton_address(address)['raw'],'chain':'ton','mode':'quick','operation':'profile','scope':'wallet','limit':1000,'refresh':True})
    assert first==repeated


def test_identity_dedup_ignores_financial_options_and_explicit_goal_routes_directly():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    r=ToolRegistry(Settings(research_mode='quick'),secret_getter=lambda name:'')
    address='0x'+'1'*40
    expected=r.canonical_arguments('blockchain_gansar',{'address':address,'operation':'identity'})
    assert r.canonical_arguments('blockchain_gansar',{'address':address,'operation':'identity','chain':'eth','section':'identity','depth':1,'limit':100,'refresh':True})==expected
    calls=r.initial_calls('Проверь ENS и Web3-идентификаторы '+address+'. operation identity')
    assert calls==[{'name':'blockchain_gansar','arguments':{'address':address,'operation':'identity','chain':'eth'}}]
    assert not r.initial_calls('Проверь баланс '+address)
    assert r.initial_calls('Проверь баланс BSC '+address)[0]['arguments']['chain']=='bsc'


def test_selected_focus_calls_only_selected_address_and_never_neighbor_labels():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    registry=ToolRegistry(Settings(),secret_getter=lambda name:'')
    selected='0x'+'1'*40;neighbor='0x'+'2'*40
    context={'selected_entity_ids':['selected'],'entities':[{'id':'selected','attributes':{'address':selected}},
        {'id':'neighbor','attributes':{'address':neighbor}}]}
    calls=registry.focus_calls({'intent':'investigate','text':'Исследуй выделенного контрагента на один уровень глубже','context':context})
    assert calls==[{'name':'blockchain_gansar','arguments':{'address':selected,'operation':'trace','depth':1}}]
    cached=registry.focus_calls({'intent':'cached','text':'Покажи сохранённые активы','context':context})
    assert cached[0]['arguments']=={'address':selected,'operation':'cached','section':'assets'}


def test_latest_summary_reaches_projection_without_erasing_original_observation():
    from grangerpet.agent_evidence import normalize_evidence,current_observation
    from grangerpet.investigation import InvestigationEvidence
    from grangerpet.investigation_results import project
    target='0x'+'1'*40
    initial={'target_address':target,'detected_chains':['eth'],'transactions':[]}
    final={**initial,'balances':[{'chain':'eth','address':target,'asset':'ETH','amount_decimal':'0.00001'}]}
    store=InvestigationEvidence()
    for report in (initial,final):
        records=[normalize_evidence(row,'blockchain_gansar',target,'2026-10-30T00:00:00Z',())for row in normalize_dossier(report)]
        store.add({'tool':'blockchain_gansar','query':target,'status':'partial','results':records})
    summary=next(row for row in store.records() if row['type']=='blockchain_summary')
    assert summary['details']['counts']['balances']==0
    assert current_observation(summary)['details']['counts']['balances']==1
    view=project({'goal':target,'evidence':store.records()})
    assert view['summary']['findings'][0]['details']['counts']['balances']==1
