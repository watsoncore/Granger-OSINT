"""Binding/discovery fixtures; no source or provider success is inferred."""
from grangerpet.agent_tools import ToolRegistry,_SPECS
from grangerpet.config import Settings
from grangerpet.tool_bindings import bind,MAX_BINDINGS


def test_all_categories_stay_within_client_limit_and_literal_targets_take_priority():
    tools=[{'type':'function','function':{'name':spec.name}} for spec in _SPECS]
    selected=bind(tools,'IP 87.199.131.94',[])
    names=[row['function']['name'] for row in selected]
    assert len(names)==MAX_BINDINGS and len(set(names))==MAX_BINDINGS
    assert 'capabilities_find' in names and 'network_rdap' in names
    selected=bind(tools,'', ['wikidata_places'])
    assert selected[1]['function']['name']=='wikidata_places'


def test_discovery_enables_real_schema_without_running_source_and_survives_checkpoint():
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    registry.schemas(task='Исследуй IP 87.199.131.94')
    result=registry.execute('capabilities_find',{'names':['wikidata_places']})
    assert result['status']=='complete' and not result['results']
    assert result['capabilities'][0]['name']=='wikidata_places'
    assert result['binding_scope_changed'] and 'wikidata_places' in result['enabled_operations']
    assert 'wikidata_places' in {row['function']['name'] for row in registry.schemas(task='IP 87.199.131.94')}
    second=registry.execute('capabilities_find',{'names':['wikidata_places']})
    assert not second['binding_scope_changed']
    restored=ToolRegistry(Settings(),secret_getter=lambda _: '')
    restored.restore_investigation([],registry.checkpoint_state())
    assert restored._discovered_tools==registry._discovered_tools
    restored.begin_investigation();assert not restored._discovered_tools


def test_discovery_cannot_bypass_explicit_local_scope_or_enable_an_unknown_command():
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    registry.schemas(task='Только локальные метаданные и OCR')
    result=registry.execute('capabilities_find',{'names':['wikidata_places','shell']})
    assert result['status']=='complete' and not result['enabled_operations']
    assert not result['capabilities'][0]['allowed_in_current_scope']
    assert registry.execute('wikidata_places',{'query':'Алматы'})['status']=='unavailable'


def test_agent_refreshes_bindings_after_discovery_without_fabricating_evidence():
    from grangerpet.agent import AgentRunner
    from test_agent import turn,call
    class Client:
        last_response_metadata={}
        def __init__(self):self.n=0
        def complete_turn(self,model,messages,*,tools,**kwargs):
            self.n+=1
            assert len(tools)<=MAX_BINDINGS
            if self.n==1:return turn(call('capabilities_find',{'names':['wikidata_places']}))
            assert 'wikidata_places' in {row['function']['name'] for row in tools}
            return turn(text='Операция найдена. Сетевой запрос ещё не запускался.')
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    result=AgentRunner(Client(),registry).run('fixture',[{'role':'user','text':'Какие инструменты доступны?'}])
    assert not result['evidence'] and result['investigation']['progress']['tool_scope_advanced']
