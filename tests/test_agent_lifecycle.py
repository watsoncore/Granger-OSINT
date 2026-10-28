"""Investigation continuations use saved primary data, not a fresh search."""
from copy import deepcopy
import json
import threading
import time

import pytest

from grangerpet.agent import AgentLimits, AgentRunner
from grangerpet.ai import AIError
from grangerpet.usage import UsageLedger


def response(*calls, text=None, usage=True):
    return {'message': {'role': 'assistant', 'content': text, **({'tool_calls': list(calls)} if calls else {})},
            'metadata': {'usage': {'prompt_tokens': 25, 'completion_tokens': 10, 'total_tokens': 35}} if usage else {}}


def tool(identifier='call_1', query='fixture', name='web_search'):
    return {'id': identifier, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps({'query': query})}}


class Client:
    _key = 'NOT-AN-ACTUAL-SECRET'
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []
    def complete_turn(self, model, messages, **kwargs):
        self.requests.append(deepcopy(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class Registry:
    def __init__(self):
        self.calls = []
    def catalog(self):
        return [{'name': 'web_search', 'available': True}]
    def schemas(self):
        return [{'type': 'function', 'function': {'name': 'web_search', 'parameters': {'type': 'object'}}}]
    def execute(self, name, arguments, **kwargs):
        self.calls.append((name, arguments))
        return {'tool': name, 'query': arguments['query'], 'status': 'complete', 'obtained_at': '2026-10-28T00:00:00+00:00',
                'results': [{'id': arguments['query'], 'type': 'web', 'title': arguments['query'], 'platform': 'Fixture',
                    'url': 'https://example.org/' + arguments['query'], 'description': 'Наблюдение источника. ' * 40,
                    'status': 'indexed', 'sources': ['fixture']}]}


HISTORY = [{'role': 'user', 'text': 'Проверь публичные сведения и сопоставь источники.'}]


def test_default_research_continues_after_old_step_and_call_limits():
    registry = Registry()
    client = Client([response(tool('call_' + str(index), 'query_' + str(index))) for index in range(18)] + [response(text='Получены сведения.')])
    result = AgentRunner(client, registry).run('fixture', HISTORY)
    assert len(registry.calls) == 18 and result['investigation']['steps'] == 19
    assert result['investigation']['status'] == 'completed' and len(result['evidence']) == 18


def test_resume_restores_goal_context_evidence_usage_and_cache_without_repeating_network():
    first_registry = Registry()
    runner = AgentRunner(Client([response(tool())]), first_registry, limits=AgentLimits(max_steps=1))
    stopped = runner.run('fixture', HISTORY, conversation_id='conversation_1')
    saved = runner.checkpoint()
    assert stopped['partial'] and saved['record']['stop_reason'] == 'step_limit'
    registry = Registry()
    client = Client([response(tool('same_again')), response(text='Проверка завершена.')])
    resumed_runner = AgentRunner(client, registry)
    result = resumed_runner.run('fixture', [], resume_state=saved, conversation_id='conversation_1')
    assert not registry.calls and result['investigation']['id'] == stopped['investigation']['id']
    assert result['investigation']['goal'] == HISTORY[-1]['text']
    assert result['evidence'] == stopped['evidence'] and result['investigation']['usage']['total_tokens'] == 105
    assert result['investigation']['steps'] == 3 and result['investigation']['resume_count'] == 1
    assert json.loads(client.requests[-1][-1]['content'])['status'] == 'duplicate_skipped'


def test_resume_finishes_queued_calls_without_losing_completed_sibling():
    runner = AgentRunner(Client([response(tool('first', 'one'), tool('second', 'two'))]), Registry(),
                         limits=AgentLimits(max_tool_calls=1))
    first = runner.run('fixture', HISTORY)
    checkpoint = runner.checkpoint()
    assert first['investigation']['tool_calls'] == 1
    assert len(checkpoint['pending_outcomes']) == 1 and checkpoint['pending_calls'][1]['dispatched'] is False
    client, registry = Client([response(text='Готово.')]), Registry()
    result = AgentRunner(client, registry).run('fixture', [], resume_state=checkpoint)
    assert registry.calls == [('web_search', {'query': 'two'})]
    assert len(result['evidence']) == 2 and result['investigation']['tool_calls'] == 2
    assert [row['tool_call_id'] for row in client.requests[0] if row['role'] == 'tool'] == ['first', 'second']


def test_resume_cannot_reset_unchanged_explicit_budget():
    runner = AgentRunner(Client([response(tool())]), Registry(), limits=AgentLimits(max_steps=1))
    runner.run('fixture', HISTORY)
    client = Client([])
    result = AgentRunner(client, Registry(), limits=AgentLimits(max_steps=1)).run('fixture', [], resume_state=runner.checkpoint())
    assert not client.requests and result['investigation']['stop_reason'] == 'step_limit'


def test_duplicate_calls_in_same_round_execute_only_once():
    registry = Registry()
    runner = AgentRunner(Client([response(tool('one'), tool('two')), response(text='Готово.')]), registry)
    result = runner.run('fixture', HISTORY)
    assert len(registry.calls) == 1 and result['investigation']['tool_calls'] == 1


def test_repetitive_cached_loop_is_paused_with_resumable_reason():
    registry = Registry()
    client = Client([response(tool('call_' + str(index))) for index in range(8)])
    result = AgentRunner(client, registry).run('fixture', HISTORY)
    assert len(registry.calls) == 1 and result['investigation']['stop_reason'] == 'no_progress'
    assert result['investigation']['resumable'] and result['investigation']['status'] == 'paused'


def test_manual_continuation_stops_between_complete_protocol_rounds():
    runner = AgentRunner(Client([response(tool())]), Registry(), limits=AgentLimits(auto_continue=False))
    result = runner.run('fixture', HISTORY)
    assert result['investigation']['stop_reason'] == 'manual_pause'
    saved = runner.checkpoint()
    assert not saved['pending_calls'] and saved['messages'][-1]['role'] == 'tool' and saved['pending_work']


def test_compaction_keeps_all_primary_evidence_and_reconstructs_valid_protocol():
    client = Client([response(tool('call_' + str(index), 'q_' + str(index))) for index in range(36)] + [response(text='Готово.')])
    runner = AgentRunner(client, Registry(), limits=AgentLimits(max_context_chars=16000))
    result = runner.run('fixture', HISTORY)
    assert len(result['evidence']) == 36 and result['investigation']['context_compactions'] > 0
    assert runner.checkpoint()['context_memory']
    archive=runner.checkpoint()['protocol_archive']
    assert sum(bool(row.get('tool_calls'))for row in archive)==36
    assert sum(row.get('role')=='tool'for row in archive)==36
    for request in client.requests:
        assert len(request) <= 90
        pending = set()
        for row in request:
            if row['role'] == 'assistant':
                assert not pending
                pending.update(call['id'] for call in row.get('tool_calls', []))
            elif row['role'] == 'tool':
                pending.remove(row['tool_call_id'])
        assert not pending


def test_actual_usage_is_saved_per_returned_request_before_later_api_failure(tmp_path):
    ledger = UsageLedger(tmp_path / 'usage.sqlite3')
    events = []
    runner = AgentRunner(Client([response(tool()), AIError('Failure', code='network')]), Registry())
    result = runner.run('fixture', HISTORY, conversation_id='chat_1', usage_ledger=ledger, on_event=events.append)
    totals = ledger.snapshot(conversation_id='chat_1', investigation_id=result['investigation']['id'])['totals']
    assert totals['requests'] == 2 and totals['failed_requests'] == 1 and totals['total_tokens'] == 35
    assert totals['partial_usage'] and len([row for row in events if row['type'] == 'usage']) == 2


def test_absent_usage_remains_unknown_and_reservations_are_separate():
    result = AgentRunner(Client([response(text='Ответ', usage=False)]), Registry()).run('fixture', HISTORY)
    assert 'usage' not in result['metadata']
    assert result['investigation']['usage']['total_tokens'] is None
    assert result['investigation']['accounted_tokens'] is None
    assert result['investigation']['budget_reserved_tokens'] > 0


def test_individual_provider_timeout_does_not_hang_and_late_usage_is_accounted(tmp_path):
    class SlowClient(Client):
        def complete_turn(self, *args, **kwargs):
            time.sleep(.15)  # Deliberately ignores cancellation to test wrapper.
            return response(text='Late response')
    ledger = UsageLedger(tmp_path / 'usage.sqlite3')
    runner = AgentRunner(SlowClient([]), Registry(), limits=AgentLimits(per_request_timeout=.03))
    started = time.monotonic()
    with pytest.raises(AIError) as caught:
        runner.run('fixture', HISTORY, usage_ledger=ledger)
    assert caught.value.code == 'timeout' and time.monotonic() - started < .14
    time.sleep(.19)
    totals = ledger.snapshot()['totals']
    assert totals['requests'] == 1 and totals['total_tokens'] == 35


def test_checkpoint_callback_failure_stops_before_external_cost():
    client, registry = Client([]), Registry()
    def unavailable(value):
        raise OSError('disk unavailable')
    result = AgentRunner(client, registry).run('fixture', HISTORY, checkpoint_callback=unavailable)
    assert not client.requests and not registry.calls
    assert result['investigation']['stop_reason'] == 'checkpoint_error'
    assert result['investigation']['persistence_error'] == 'checkpoint_unavailable'


def test_dispatched_interruption_is_not_silently_reexecuted_on_resume():
    event = threading.Event()
    def progress(value):
        if value['type'] == 'tool_start':
            event.set()
    class InterruptedRegistry(Registry):
        def execute(self, *args, **kwargs):
            time.sleep(.15)  # Cancellation arrives before any final outcome.
            return {'tool': args[0], 'query': 'fixture', 'status': 'cancelled', 'results': []}
    runner = AgentRunner(Client([response(tool())]), InterruptedRegistry())
    runner.run('fixture', HISTORY, cancel_event=event, on_event=progress)
    saved = runner.checkpoint()
    assert saved['pending_calls'][0]['dispatched'] is True
    client, registry = Client([response(text='Требуется другая проверка.')]), Registry()
    result = AgentRunner(client, registry).run('fixture', [], resume_state=saved)
    assert not registry.calls and 'interrupted' in client.requests[0][-1]['content']
    assert not result['evidence']
