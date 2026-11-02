"""Intent fixtures, not live source claims."""
from grangerpet.chat_intent import SessionIntent
from grangerpet.chat import investigation_requested
from grangerpet.context import conversation_context


def test_short_literal_ip_uses_tools_without_research_verb():
    assert investigation_requested('а этот IP 87.199.131.94?')
    assert SessionIntent().decide('а этот IP 87.199.131.94?','one')['kind']=='research'


def test_scoped_location_and_explicit_consent_do_not_grant_other_permissions():
    state=SessionIntent();state.decide('Исследуй IP 66.249.67.41','one')
    result=state.decide('а какая локация?','one')
    assert result['kind']=='research' and result['entity_context']['target']['identifier']=='66.249.67.41'
    assert state.decide('Разрешаю','one')['kind']=='research'
    assert state.decide('Почему небо голубое?','one')['kind']=='conversation'
    assert state.decide('Да','one')['kind']=='conversation'


def test_defer_social_and_new_conversation_never_reactivate_old_goal():
    state=SessionIntent();state.decide('Исследуй IP 66.249.67.41','one')
    assert state.decide('Герми, ты здесь?','one')['kind']=='social'
    assert state.decide('Отложим','one')['kind']=='defer'
    assert state.decide('Что делаешь?','one')['kind']=='social'
    assert state.decide('а какая локация?','one')['kind']=='conversation'
    state.decide('Исследуй IP 87.199.131.94','one')
    assert state.decide('Разрешаю','two')['kind']=='conversation'
    assert state.target is None


def test_context_barrier_keeps_archive_but_drops_old_research_from_working_view():
    rows=[{'role':'user','text':'Исследуй Apple 66.249.67.41'},{'role':'model','text':'Старая ошибка Wikipedia 429'},
          {'role':'user','text':'Отложим'},{'role':'model','text':'Хорошо.'},{'role':'user','text':'Герми, ты здесь?'}]
    assert 'Wikipedia' not in str(conversation_context(rows))
    assert 'Apple' not in str(conversation_context(rows))
    state=SessionIntent();state.restore(rows,'one');assert state.target is None
    assert len(rows)==5


def test_selected_image_replaces_previous_ip_and_restores_only_in_its_conversation():
    image='img_'+'a'*64
    state=SessionIntent();state.decide('Исследуй IP 66.249.67.41','one')
    state.decide('Где это?', 'one',images=[{'id':image}])
    assert state.target['entity_type']=='image'
    assert state.decide('сравни рельеф','one')['entity_context']['target']['identifier']==image
    state.restore([{'role':'user','text':'Где это?','attachments':[{'id':image}]}],'one')
    assert state.target['identifier']==image
    assert state.decide('сравни рельеф','two')['entity_context'] is None


def test_runner_uses_scoped_target_for_seed_tools_without_rewriting_original_question():
    from grangerpet.agent import AgentRunner
    from grangerpet.ai import AIError
    from test_agent import Client,Registry,turn
    import pytest
    class ScopedRegistry(Registry):
        def initial_calls(self,goal):self.seed_goal=goal;return []
    registry=ScopedRegistry();context=SessionIntent()
    context.decide('а этот IP 87.199.131.94?','one')
    kwargs=context.decide('какая локация?','one')['entity_context']
    result=AgentRunner(Client([turn(text='Контрольный ответ, не реальная геолокация.')]),registry).run(
        'fixture',[{'role':'user','text':'какая локация?'}],conversation_id='one',entity_context=kwargs)
    assert '87.199.131.94' in registry.seed_goal
    assert result['investigation']['goal']=='какая локация?'
    assert result['investigation']['active_target']['identifier']=='87.199.131.94'
    with pytest.raises(AIError,match='другой беседе'):
        AgentRunner(Client([]),ScopedRegistry()).run('fixture',[{'role':'user','text':'какая локация?'}],
            conversation_id='two',entity_context=kwargs)


def test_attachment_working_scope_does_not_fall_back_to_old_authorizations():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    image='img_'+'a'*64
    registry=ToolRegistry(Settings(),attachment_ids=[image],secret_getter=lambda _: '')
    registry.allow_attachments([])
    assert registry.attachment_context()==[]
    state=registry.checkpoint_state()
    assert state['attachment_ids']==[image] and state['active_attachment_ids']==[]
    restored=ToolRegistry(Settings(),secret_getter=lambda _: '')
    restored.restore_investigation([],state)
    assert restored.attachment_context()==[] and image in restored._attachment_ids


def test_new_registry_run_clears_old_url_authority_but_keeps_selected_image_cache():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.config import Settings
    image='img_'+'a'*64
    old=normalize_evidence({'id':'old','type':'profile','title':'Old scope fixture','platform':'fixture',
        'url':'https://example.org/old'},'web_read','old')
    visual=normalize_evidence({'id':'visual','type':'image_analysis','title':'Image cache fixture','platform':'local',
        'details':{'attachment_id':image}},'image_understand',image)
    registry=ToolRegistry(Settings(),attachment_ids=[image],secret_getter=lambda _: '')
    registry.evidence.restore([old,visual],[]);registry.begin_investigation()
    assert registry.evidence.records()==[visual]
    registry.allow_attachments([]);registry.begin_investigation()
    assert registry.evidence.records()==[]
    assert old['url']=='https://example.org/old'  # This changes only the working projection.
