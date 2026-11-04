"""A bounded graph projection must not hide a whole later source category."""
from copy import deepcopy

import pytest

from grangerpet.engine.blockchain_rows import normalize_dossier


ADDRESS='0x'+'12'*20
PEER='0x'+'34'*20


def report_fixture():
    return {'target_address':ADDRESS,'detected_chains':['eth'],
        'tokens':[{'chain':'eth','contract':'0x'+format(index,'040x'),'name':'Token '+str(index),
            'amount_decimal':'1'} for index in range(2200)],
        'balances':[{'chain':'eth','address':ADDRESS,'asset':'ETH','amount_decimal':'1.01'}],
        'transactions':[{'chain':'eth','tx_hash':'explicit-source-tx','event_id':'explicit-source-tx:0',
            'from_address':ADDRESS,'to_address':PEER,'asset':'ETH','amount_decimal':'0.000000000000000001'}],
        'counterparties':[{'chain':'eth','address':PEER,'tx_count':1}]}


def test_large_asset_section_cannot_starve_transaction_balance_or_counterparty():
    report=report_fixture();original=deepcopy(report)
    rows=normalize_dossier(report)
    assert len(rows)==2000 and rows[0]['type']=='blockchain_summary' and rows[1]['type']=='blockchain_analytics'
    assert any(row['type']=='token_asset' for row in rows)
    tx=next(row for row in rows if row['type']=='transaction')
    assert tx['details']['amount_decimal']=='0.000000000000000001'
    assert any(row['type']=='balance' for row in rows)
    assert any(row['type']=='blockchain_counterparty' for row in rows)
    projection=rows[0]['details']['projection']
    assert projection['truncated'] and projection['record_budget']==2000
    assert projection['available_counts']['token_asset']==2200
    assert projection['emitted_counts']['token_asset']==1995
    assert projection['omitted_counts']=={'token_asset':205}
    assert projection['transaction_observed']==projection['transaction_selected']==1
    assert projection['raw_dossier_retained_elsewhere'] is False  # only the caller can confirm durable storage
    assert set(projection['available_saved_sections'])>={'assets','transactions','balances'}
    assert 'Проекция ограничена' in rows[0]['description']
    assert report==original


def test_cached_transaction_section_selects_actual_transaction_without_asset_noise():
    rows=normalize_dossier(report_fixture(),operation='transactions')
    assert [row['type'] for row in rows]==['blockchain_summary','blockchain_analytics','transaction','blockchain_counterparty']
    assert next(row for row in rows if row['type']=='transaction')['details']['tx_hash']=='explicit-source-tx'
    assert not rows[0]['details']['projection']['truncated']


def test_explicit_transaction_limit_remains_visible_even_when_record_budget_is_large():
    report=report_fixture();report['tokens']=[]
    report['transactions']=[{**report['transactions'][0],'event_id':'event:'+str(i),'tx_hash':'tx:'+str(i)} for i in range(75)]
    rows=normalize_dossier(report,max_transactions=50)
    projection=rows[0]['details']['projection']
    assert projection['transaction_observed']==75 and projection['transaction_selected']==50
    assert projection['transaction_limit']==50 and projection['omitted_counts']['transaction']==25
    assert projection['available_counts']['transaction']==75 and projection['truncated']


def test_small_budget_is_fair_and_deterministic_across_all_requested_categories():
    report=report_fixture();first=normalize_dossier(report,max_records=6)
    assert [row['type'] for row in first]==['blockchain_summary','blockchain_analytics','balance','token_asset','transaction','blockchain_counterparty']
    assert [row['id'] for row in first]==[row['id'] for row in normalize_dossier(report,max_records=6)]
    assert len(normalize_dossier(report,max_records=1))==1


@pytest.mark.parametrize('budget',[0,-1,2001,True,1.5])
def test_record_budget_cannot_disable_transport_bound(budget):
    with pytest.raises(ValueError):normalize_dossier(report_fixture(),max_records=budget)
