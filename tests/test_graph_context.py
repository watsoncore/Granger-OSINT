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
