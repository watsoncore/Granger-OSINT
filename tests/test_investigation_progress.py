from copy import deepcopy
import threading
import pytest
from grangerpet.agent import AgentLimits, AgentRunner
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.investigation_progress import normalized_arguments, semantic_facts
from grangerpet.ai import AIError
from test_agent_lifecycle import Client, Registry, HISTORY, response, tool


class Empty(Registry):
    def execute(self, name, args, **kwargs):
        self.calls.append((name, args))
        return {'tool': name, 'query': args['query'], 'status': 'empty', 'results': []}


def test_distinct_empty_queries_stop_as_no_progress_with_meaningful_report():
    registry = Empty()
    client = Client([response(tool(str(i), 'empty_' + str(i))) for i in range(12)])
    runner = AgentRunner(client, registry)
    result = runner.run('fixture', HISTORY)
    assert len(registry.calls) == 3 and len(client.requests) == 4
    assert result['investigation']['stop_reason'] == 'no_progress'
    assert 'Пригодных доказательств не получено' in result['text']
    assert result['investigation']['report_status']=='fallback'
    assert result['investigation']['final_report'] == result['text']
    assert runner.checkpoint()['record']['final_report'] == result['text']


class Denied(Empty):
    def execute(self, name, args, **kwargs):
        result = super().execute(name, args, **kwargs)
        result.update(status='blocked', error='http_403')
        return result


def test_identical_failed_call_not_automatically_retried_after_resume():
    first = AgentRunner(Client([response(tool())]), Denied(), limits=AgentLimits(max_steps=1))
    first.run('fixture', HISTORY)
    registry = Denied()
    result = AgentRunner(Client([response(tool('again')), response(text='Исчерпаны доступные направления.')]), registry).run(
        'fixture', [], resume_state=first.checkpoint())
    assert registry.calls == []
    assert result['investigation']['tool_calls'] == 1


def test_same_document_via_different_query_or_acquisition_is_not_new_progress():
    one = normalize_evidence({'id': 'page', 'title': 'Page', 'type': 'web', 'platform': 'Web', 'url': 'https://example.org/a',
        'description': 'Same observed content', 'details': {'content_text': 'actual page', 'query': 'one', 'retrieved_at': 'one'}}, 'web_search', 'one')
    two = normalize_evidence({**one, 'details': {**one['details'], 'query': 'two', 'retrieved_at': 'two', 'reading_method': 'direct_http'}}, 'web_read', 'two')
    assert semantic_facts([one]) == semantic_facts([two])
    two['details']['content_text'] = 'A new public property'
    assert semantic_facts([one]) != semantic_facts([two])


def test_real_change_or_contradiction_is_progress_but_derived_graph_is_not():
    one = normalize_evidence({'id': 'x', 'title': 'Fixture', 'type': 'observation', 'platform': 'Fixture', 'details': {'property': 1}}, 'fixture', 'x')
    changed = deepcopy(one)
    changed['verification'] = 'contradictory'
    changed['observations'] = [{'details': {'property': 2}, 'status': 'metadata', 'description': ''}]
    assert semantic_facts([one]) != semantic_facts([changed])
    derived = {**one, 'details': {'capability': 'evidence_graph', 'total_entities': 999}}
    assert semantic_facts([derived]) == set()


@pytest.mark.parametrize('reason,limits', [('step_limit', AgentLimits(max_steps=1)), ('tool_limit', AgentLimits(max_tool_calls=1))])
def test_budget_stop_ends_research_and_attempts_separate_tool_free_synthesis(reason, limits):
    client = Client([response(tool('a'), tool('b', 'next'))] if reason == 'tool_limit' else [response(tool())])
    result = AgentRunner(client, Registry(), limits=limits).run('fixture', HISTORY)
    assert len(client.requests) == 2
    assert result['investigation']['stop_reason'] == reason
    assert result['evidence'] and '**Сведения источников**' not in result['text']
    assert 'https://example.org/' in result['text'] and '## Ограничения' in result['text']
    assert result['investigation']['report_status']=='fallback'


def test_api_failure_has_source_report_without_more_model_calls():
    client = Client([response(tool()), AIError('Fixture unavailable', code='network')])
    result = AgentRunner(client, Registry()).run('fixture', HISTORY)
    assert len(client.requests) == 2
    assert 'Наблюдение источника' in result['text'] and 'Языковой анализ недоступен' in result['text']


def test_scoped_telegram_does_not_fallback_to_unrelated_github_or_hn_names():
    from test_public_fallback import Sources
    registry = Sources()
    client = Client([response(tool()), response(text='Публичная страница недоступна.')])
    result = AgentRunner(client, registry).run('fixture', [{'role': 'user', 'text': 'Исследуй https://t.me/solvnox_project'}])
    assert [name for name, _ in registry.calls] == ['web_search']
    assert not result['evidence']


def test_conservative_signatures_preserve_wallet_case_and_url_path():
    assert normalized_arguments('web_read', {'url': ' HTTPS://EXAMPLE.org/Path?b=2&a=1&utm_source=test '}) == {'url': 'https://example.org/Path?a=1&b=2'}
    assert normalized_arguments('blockchain_gansar', {'address': ' AbCd '}) == {'address': 'AbCd'}
    assert normalized_arguments('github_profile', {'username': '@OctoCat'}) == {'username': 'octocat'}
