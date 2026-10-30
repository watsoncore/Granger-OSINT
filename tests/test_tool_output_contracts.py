import json
import pytest
from grangerpet.agent import AgentRunner
from grangerpet.agent_tools import _SPECS
from grangerpet.tool_contracts import ToolContractError, validate_outcome
from test_agent_tools import Adapter, finding, registry
from test_agent_lifecycle import Client, HISTORY, response, tool


@pytest.mark.parametrize('bad', ['HTML ERROR PRIVATE', None, [], {'status': 'complete', 'results': 'PRIVATE'},
    {'status': 'complete', 'results': None}, {'status': 'complete', 'results': ['PRIVATE']},
    {'status': 'complete', 'results': [{'type': 'execution', 'title': 'PRIVATE'}]},
    {'status': {}, 'results': []}, {'status': 'complete'}, {'status': 'complete', 'results': [], 'limitations': 'PRIVATE'}])
def test_invalid_adapter_output_is_failed_not_empty_success_or_execution_verified(bad, caplog):
    adapter = Adapter()
    adapter.outcome = bad
    reg, _ = registry(adapter)
    result = reg.execute('username_maigret', {'username': 'fixture'})
    assert result['status'] == 'error' and result['execution_status'] == 'failed'
    assert result['error_code'] == 'invalid_tool_output'
    assert result['errors'] and not result['results']
    assert result['error_info']['actual_type']
    assert 'PRIVATE' not in caplog.text
    row = next(r for r in reg.catalog() if r['name'] == 'username_maigret')
    assert row['diagnostic']['execution_verified'] is False


def test_valid_partial_neighbor_survives_one_invalid_result_with_explicit_error():
    adapter = Adapter({'status': 'complete', 'results': [finding(), 'PRIVATE BAD']})
    reg, _ = registry(adapter)
    result = reg.execute('username_maigret', {'username': 'fixture', 'limit': 3})
    assert result['status'] == 'partial' and result['execution_status'] == 'partial'
    assert len(result['results']) == 1 and result['error_code'] == 'invalid_tool_output'


def test_complete_without_findings_becomes_empty_but_remains_real_execution():
    adapter = Adapter({'status': 'complete', 'results': []})
    reg, _ = registry(adapter)
    result = reg.execute('username_maigret', {'username': 'fixture'})
    assert result['status'] == result['execution_status'] == 'empty'
    assert len(adapter.calls) == 1 and result['execution_id'] == result['invocation_id']
    assert result['duration_ms'] >= 0


def test_direct_runner_also_rejects_invalid_registry_without_fabricated_evidence():
    class Bad:
        def catalog(self): return [{'name': 'web_search', 'available': True}]
        def schemas(self): return [{'type': 'function', 'function': {'name': 'web_search', 'parameters': {'type': 'object'}}}]
        def execute(self, *args, **kwargs): return {'tool': 'web_search', 'status': 'complete', 'results': 'HTML ERROR'}
    client = Client([response(tool()), response(text='Нет пригодных сведений.')])
    result = AgentRunner(client, Bad()).run('fixture', HISTORY)
    assert not result['evidence']
    returned = json.loads(client.requests[-1][-1]['content'])
    assert returned['status'] == 'error' and returned['error'] == 'invalid_tool_output'


@pytest.mark.parametrize('spec', _SPECS, ids=lambda spec: spec.name)
def test_every_registered_adapter_uses_same_typed_status_contract(spec):
    for status in ('complete', 'empty', 'partial', 'blocked', 'timeout', 'cancelled', 'unavailable', 'error'):
        assert validate_outcome({'tool': spec.name, 'status': status, 'results': []})['status'] == status
    with pytest.raises(ToolContractError):
        validate_outcome({'tool': spec.name, 'status': 'complete', 'results': 'HTML'})
