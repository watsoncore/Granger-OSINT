"""Real agent protocol with controlled source/model fixtures, no live claims."""
import json

from grangerpet.agent import AgentRunner,AgentLimits
from test_agent import Client,turn,call


class Sources:
    def __init__(self):self.calls=[]
    def catalog(self):return [{'name':n,'available':True} for n in ('web_search','hn_search')]
    def schemas(self):return [{'type':'function','function':{'name':n,'parameters':{'type':'object'}}} for n in ('web_search','hn_search')]
    def execute(self,name,args,**kwargs):
        self.calls.append((name,args))
        return {'tool':name,'query':args['query'],'status':'unavailable' if name=='web_search' else 'complete',
            'results':[] if name=='web_search' else [{'id':'123','title':'Actual fixture story','type':'publication','platform':'hn_search','url':'https://news.ycombinator.com/item?id=123','description':'Public source fixture content','status':'metadata','details':{'acquisition':'official_api'}}]}


def test_agent_does_not_finish_on_first_source_failure_with_public_alternative():
    registry=Sources();client=Client([turn(call(args={'query':'fixture'})),turn(text='Источник недоступен.'),turn(text='Получены сведения другого источника.')])
    result=AgentRunner(client,registry).run('fixture',[{'role':'user','text':'Найди публичные упоминания fixture'}])
    assert [r[0] for r in registry.calls]==['web_search','hn_search']
    assert result['evidence'][0]['provenance']['tool']=='hn_search'
    assert result['investigation']['fallback_attempts']==1 and result['investigation']['status']=='completed'
    assert any(row.get('role')=='tool' and json.loads(row['content']).get('tool')=='hn_search' for row in client.requests[-1])


def test_agent_respects_explicit_source_scope_and_never_synthesizes_a_url():
    registry=Sources();client=Client([turn(call(args={'query':'fixture'})),turn(text='Ограниченный источник недоступен.')])
    result=AgentRunner(client,registry).run('fixture',[{'role':'user','text':'Используй только web_search для fixture'}])
    assert [r[0] for r in registry.calls]==['web_search'] and not result['evidence']


def test_repeating_failed_provider_moves_to_untried_source_before_pause():
    registry=Sources();client=Client([turn(call(args={'query':'fixture'},identifier='first')),turn(call(args={'query':'fixture'},identifier='second')),turn(call(args={'query':'fixture'},identifier='third')),turn(text='Получены реальные результаты.')])
    result=AgentRunner(client,registry,limits=AgentLimits(no_progress_rounds=3)).run('fixture',[{'role':'user','text':'Найди публичные упоминания fixture'}])
    assert [r[0] for r in registry.calls]==['web_search','hn_search']
    assert result['investigation']['status']=='completed' and result['evidence']
