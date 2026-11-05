from copy import deepcopy
import pytest
from grangerpet.research_canvas import new_document,add_node,apply,CanvasError


def two():
    doc=new_document();a=add_node(doc,{'type':'analyst_note','label':'A','position':{'x':0,'y':0}});b=add_node(doc,{'type':'analyst_note','label':'B','position':{'x':420,'y':220}})
    return doc,a,b


def test_analyst_relation_saves_semantics_style_and_independent_confidence():
    doc,a,b=two();doc=apply(doc,'edge',{'from_id':a,'to_id':b,'relation_type':'references','direction':'bidirectional','color':'#6789ab','stroke':'dotted','width':3,'confidence':65,'source_url':'https://example.org/source','note':'Нужно проверить'})
    edge=doc['relations'][0]
    assert edge['direction']=='bidirectional' and edge['source_urls']==['https://example.org/source']
    assert edge['attributes']['analyst_confidence']==65 and edge['verification_status']=='unverified'
    assert edge['claim_kind']=='analyst_assertion' and edge['attributes']['stroke']=='dotted'
    edge['origin']='tool'
    with pytest.raises(CanvasError,match='Источник связи'):apply(doc,'edge_edit',{'relation_id':edge['id'],'from_id':a,'to_id':b,'relation_type':'changed'})


@pytest.mark.parametrize('extra',[{'confidence':101},{'direction':'made_up'},{'source_url':'https://key:secret@example.org/'},{'evidence_ids':['foreign-evidence']},{'width':float('nan')},{'color':'red;script'}])
def test_invalid_or_cross_investigation_relation_does_not_change_document(extra):
    doc,a,b=two();before=deepcopy(doc)
    with pytest.raises(CanvasError):apply(doc,'edge',{'from_id':a,'to_id':b,**extra})
    assert doc==before


def test_group_bounds_and_move_include_collapsed_descendants():
    doc,a,b=two();doc=apply(doc,'group',{'ids':[a,b],'label':'Область'})
    group=next(n for n in doc['entities'] if n['type']=='entity_group');position=doc['view']['positions'][group['id']]
    assert doc['view']['card_sizes'][group['id']]['width']>=720
    doc=apply(doc,'view',{'view':{'collapsed':[group['id']]}})
    moved=apply(doc,'positions',{'positions':{group['id']:{'x':position['x']+50,'y':position['y']+70}}})
    assert moved['view']['positions'][a]=={'x':50,'y':70}
    assert moved['view']['positions'][b]=={'x':470,'y':290}
