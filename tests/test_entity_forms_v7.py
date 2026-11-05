import pytest
from grangerpet.entity_forms import organization
from grangerpet.research_canvas import add_node,new_document,CanvasError


def test_company_identifier_is_jurisdiction_bound_and_not_verified_by_format():
    target=organization({'jurisdiction':'KZ','identifier_type':'bin','identifier':'123456789012'})
    assert target['registration_number']=='123456789012' and target['registration_verified'] is False
    with pytest.raises(ValueError):organization({'jurisdiction':'KZ','identifier_type':'inn','identifier':'1234567890'})
    with pytest.raises(ValueError):organization({'jurisdiction':'RU','identifier_type':'inn','identifier':'123456789012'})


def test_named_companies_remain_distinct_candidates_but_exact_registration_deduplicates():
    doc=new_document('Typed inputs')
    a=add_node(doc,{'type':'organization','label':'Aurora','company':{'jurisdiction':'GB','identifier':'Aurora'}})
    b=add_node(doc,{'type':'organization','label':'Aurora','company':{'jurisdiction':'GB','identifier':'Aurora'}})
    assert a!=b
    args={'type':'organization','label':'Registration fixture','company':{'jurisdiction':'GB','identifier_type':'company_number','identifier':'01234567'}}
    assert add_node(doc,args)==add_node(doc,args)
    assert all(node['attributes']['registration_verified'] is False for node in doc['entities'])


@pytest.mark.parametrize('kind,value',[('email','broken'),('domain','not a domain'),('infrastructure_asset','999.4.5.6'),('phone','arbitrary')])
def test_typed_entities_reject_unrelated_labels_as_identifiers(kind,value):
    with pytest.raises(CanvasError):add_node(new_document('Validation'),{'type':kind,'label':'Display name','value':value})


def test_company_route_is_corporate_and_rotates_context_without_guessing_domains():
    from grangerpet.entity_router import route_goal
    from grangerpet.chat_intent import SessionIntent
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    targets=route_goal('Исследуй компанию Microsoft Corporation в США')
    assert len(targets)==1 and targets[0].entity_type=='organization'
    assert targets[0].identifier=='Microsoft Corporation' and targets[0].platform=='US'
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    calls=registry.initial_calls('Исследуй компанию Microsoft Corporation в США')
    assert calls==[{'name':'company_research','arguments':{'query':'Microsoft Corporation','jurisdiction':'US','identifier_type':'name'}}]
    state=SessionIntent()
    a=state.decide('Исследуй компанию Aurora A','chat')['context_scope']
    b=state.decide('Исследуй компанию Aurora B','chat')['context_scope']
    assert a!=b
    assert any(target.entity_type=='domain' for target in route_goal('Проверь DNS компании example.org'))
