"""Orchestration fixtures only: these tests make no network/API calls."""
from copy import deepcopy
import json
import pytest
from grangerpet.agent import AgentRunner
from grangerpet.research_policy import personal_steps,plan_review
from grangerpet.investigation import new_investigation
from grangerpet.investigation_contracts import validate_checkpoint,InvestigationContractError
from test_agent import Registry,Client,call,turn


class PersonalRegistry(Registry):
    def catalog(self):
        return [{'name':name,'available':True,'source':name,'kind':'username'} for name in ('public_one','public_two')]
    def schemas(self):
        return [{'type':'function','function':{'name':name,'parameters':{'type':'object'}}} for name in ('public_one','public_two')]


def request(name,identifier):return call(name,{'username':'public-unit-fixture'},identifier)


def test_unapproved_multisource_plan_never_dispatches_personal_calls():
    registry=PersonalRegistry();client=Client([turn(request('public_one','a'),request('public_two','b')),turn(text='План отклонён.')])
    AgentRunner(client,registry).run('fixture',[{'role':'user','text':'Проверь публичный никнейм'}])
    assert registry.calls==[]


def test_concrete_plan_approves_only_these_calls_and_does_not_cross_investigations():
    plans=[];checkpoints=[];registry=PersonalRegistry()
    def approve(name,args):plans.append((name,deepcopy(args)));return True
    replies=[turn(request('public_one','a'),request('public_two','b')),turn(text='Готово по fixture.')]
    runner=AgentRunner(Client(replies+replies),registry)
    for _ in range(2):
        runner.run('fixture',[{'role':'user','text':'Проверь публичный никнейм'}],approval_callback=approve,
            checkpoint_callback=lambda value:checkpoints.append(deepcopy(value)))
    assert len(plans)==2 and all(name=='research_plan' for name,_ in plans)
    assert len(registry.calls)==4
    assert {row['provider'] for row in plans[0][1]['steps']}=={'public_one','public_two'}
    assert plans[0][1]['new_tool_calls']==2
    private=checkpoints[-1]
    assert len(private['source_plan_grants'])==2
    assert 'public-unit-fixture' not in json.dumps(private['source_contacts'])
    validate_checkpoint(private)


def test_second_source_on_later_step_also_requires_review():
    plans=[];registry=PersonalRegistry()
    client=Client([turn(request('public_one','a')),turn(request('public_two','b')),turn(text='Второй источник не разрешён.')])
    AgentRunner(client,registry).run('fixture',[{'role':'user','text':'Проверь публичный никнейм'}],
        approval_callback=lambda name,args:plans.append(args) or False)
    assert len(registry.calls)==1 and registry.calls[0][0]=='public_one'
    assert plans[0]['previous_sources']==['public_one']


def test_model_cannot_bypass_declined_plan_by_changing_limit_or_using_one_source():
    plans=[];registry=PersonalRegistry()
    changed=call('public_one',{'username':'public-unit-fixture','limit':1},'changed')
    client=Client([turn(request('public_one','a'),request('public_two','b')),turn(changed),turn(text='План не выполнялся.')])
    AgentRunner(client,registry).run('fixture',[{'role':'user','text':'Проверь публичный никнейм'}],
        approval_callback=lambda name,args:plans.append(args) or False)
    assert len(plans)==1 and registry.calls==[]


def test_local_metadata_does_not_require_external_source_plan():
    calls=[{'name':'phone_metadata','arguments':{'phone':'+12025550123'},'fingerprint':'a'*64}]
    assert personal_steps(calls,{'phone_metadata':{'kind':'phone','manifest':{'network_requirements':'none'}}})==[]


@pytest.mark.parametrize('field,value',[('source_plan_grants',['not-a-fingerprint']),
    ('source_plan_denied',['a'*64]*257),('source_contacts',[{'target':'a'*64,'provider':'public','api_key':'forbidden'}])])
def test_saved_plan_authority_has_a_strict_bounded_contract(field,value):
    record,state=new_investigation('Unit fixture');state['record']=record;state[field]=value
    with pytest.raises(InvestigationContractError):validate_checkpoint(state)
