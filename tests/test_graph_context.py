import json
from grangerpet.graph_context import selection_context


def test_large_aggregate_is_bounded_structured_context_with_selected_endpoints():
    nodes={str(i):{'id':str(i),'type':'blockchain_address','label':'x'*400,
        'attributes':{'address':'a'*10000,'raw_html':'private unrelated payload'},'evidence_ids':['ev_'+str(j) for j in range(5000)]} for i in range(50)}
    edges={str(i):{'id':str(i),'from_id':'0','to_id':str(i+1),'relation_type':'transfers',
        'verification_status':'source_reported','source_urls':['https://example.org/'+'a'*1000]*1000,
        'evidence_ids':['ev_'+str(j) for j in range(5000)],'aggregate':{'count':5000,'amount':'123.4','asset':'TON','transaction_ids':['x']*5000}} for i in range(49)}
    result=selection_context(nodes,edges,{'0','40'},'39')
    assert len(json.dumps(result,ensure_ascii=False))<=18000
    assert result['selected_entity_ids']==['0','40']
    assert {'0','40'}<={row['id'] for row in result['entities']}
    assert result['relations'][0]['id']=='39'
    assert result['relations'][0]['aggregate']['amount']=='123.4'
    assert 'transaction_ids' not in result['relations'][0]['aggregate']
    assert 'raw_html' not in json.dumps(result)


def test_selected_context_contains_bounded_saved_provenance_excerpts_only():
    nodes={'a':{'id':'a','type':'website','label':'a','attributes':{},'evidence_ids':['ev_1']}}
    records=[{'evidence_id':'ev_1','title':'Observed page','url':'https://example.org/',
        'details':{'content_excerpt':'actual public excerpt'*1000,'secret_unrelated_field':'not selected'},
        'provenance':{'tool':'web_read','obtained_at':'2026-10-30'}},
        {'evidence_id':'ev_other','description':'unrelated contents'}]
    result=selection_context(nodes,{}, {'a'},records=records)
    assert len(result['sources'])==1 and result['sources'][0]['tool']=='web_read'
    assert len(result['sources'][0]['excerpt'])==700
    assert 'unrelated' not in json.dumps(result)


def test_selected_steam_asset_precedes_neighbor_evidence_and_keeps_item_properties():
    nodes={'owner':{'id':'owner','type':'public_profile','label':'Owner','attributes':{},'evidence_ids':['ev_owner']},
        'item':{'id':'item','type':'inventory_item','label':'Observed skin','attributes':{'assetid':'123','steamid64':'76561198045277210',
        'float_value':'0.1234567','pattern_template':'37','price':{'amount_decimal':'0.12','currency':'USD'}},'evidence_ids':['ev_item']}}
    edges={'edge':{'id':'edge','from_id':'owner','to_id':'item','relation_type':'owns_public_item','evidence_ids':['ev_item']}}
    result=selection_context(nodes,edges,{'item'},records=[{'evidence_id':'ev_owner','description':'Owner'}, {'evidence_id':'ev_item','description':'Selected asset'}])
    assert result['sources'][0]['evidence_id']=='ev_item'
    assert result['entities'][0]['attributes']['float_value']=='0.1234567'
    assert result['entities'][0]['attributes']['price']['currency']=='USD'
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    calls=registry.focus_calls({'intent':'investigate','context':result,'text':'Исследуй выбранный предмет'})
    assert len(calls)==1 and calls[0]['name']=='evidence_get' and calls[0]['arguments']['evidence_id']=='ev_item'
