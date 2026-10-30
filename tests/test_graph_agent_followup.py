import json
from grangerpet.agent import AgentRunner,AgentLimits
from test_agent_lifecycle import Client, Registry, HISTORY, response, tool


class GraphRegistry(Registry):
    def schemas(self):
        return [{'type':'function','function':{'name':name,'parameters':{'type':'object'}}}
                for name in ('web_search','evidence_get','evidence_graph')]


def test_completed_investigation_can_be_explicitly_extended_with_same_goal_and_id():
    first=AgentRunner(Client([response(tool()),response(text='Первый итог.')]),Registry())
    result=first.run('fixture',HISTORY,conversation_id='conversation_1')
    saved=first.checkpoint()
    client=Client([response(text='Объяснение сохранённой связи.')])
    followup={'text':'Объясни выбранный узел по сохранённым доказательствам.',
        'context':{'selected_entity_ids':['ent_'+'a'*24],'entities':[{'id':'ent_'+'a'*24,'label':'Fixture'}]},'intent':'explain'}
    registry=GraphRegistry()
    result=AgentRunner(client,registry).run('fixture',[],resume_state=saved,followup=followup,conversation_id='conversation_1')
    assert result['investigation']['id']==saved['id'] and result['investigation']['goal']==HISTORY[0]['text']
    assert not registry.calls and result['investigation']['status']=='completed'
    assert 'selected_entity_ids' in client.requests[0][-1]['content']
    assert result['evidence']==saved['evidence']


def test_explanation_cannot_launch_new_network_tool_even_if_model_proposes_it():
    first=AgentRunner(Client([response(text='Первый итог.')]),Registry())
    first.run('fixture',HISTORY)
    registry=GraphRegistry()
    client=Client([response(tool('forbidden')),response(text='Новый поиск не запускался.')])
    result=AgentRunner(client,registry).run('fixture',[],resume_state=first.checkpoint(),
        followup={'text':'Объясни связь.','context':{'entities':[]},'intent':'explain'})
    assert not registry.calls
    assert json.loads(client.requests[-1][-1]['content'])['status']=='unavailable'


def test_explicit_local_explanation_after_research_budget_exhaustion_gets_bounded_real_turn():
    first=AgentRunner(Client([response(text='Сохранённый итог.')]),Registry())
    first.run('fixture',HISTORY)
    saved=first.checkpoint()
    saved['record'].update(steps=100,tool_calls=100,elapsed_seconds=100,status='limit_reached')
    saved['budget_reserved_tokens']=100000
    client=Client([response(text='Новое объяснение сохранённых оснований.')]);registry=GraphRegistry()
    runner=AgentRunner(client,registry,limits=AgentLimits(max_steps=1,max_tool_calls=1,max_tokens=8000,timeout=5))
    result=runner.run('fixture',[],resume_state=saved,
        followup={'text':'Объясни связь.','context':{'entities':[]},'intent':'explain'})
    assert result['investigation']['status']=='completed' and len(client.requests)==1
    assert result['investigation']['steps']==101 and result['investigation']['tool_calls']==100
    assert runner.checkpoint()['budget_reserved_tokens']>=100000
    assert runner.checkpoint()['protocol_archive'][:len(saved['protocol_archive'])]==saved['protocol_archive']
    assert not registry.calls
    # Ordinary resume never grants a fresh local-analysis phase.
    again=AgentRunner(Client([response(text='Should not run')]),registry,limits=AgentLimits(max_steps=1,max_tokens=8000,timeout=5))
    pending=runner.checkpoint();pending['record']['status']='paused'
    resumed=again.run('fixture',[],resume_state=pending)
    assert resumed['investigation']['status']=='completed' and not again.client.requests
    assert resumed['text']==result['text']  # Reuse the completed answer, without another paid request.
