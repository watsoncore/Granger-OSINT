"""Manifest/readiness contract tests; fixture execution is not a live smoke."""
import json
import threading
import time

import pytest

from grangerpet.agent_tools import ToolRegistry, _SPECS
from grangerpet.config import Settings
from grangerpet.tool_manifest import manifest, relevant_names, technical_state


def registry(secret_getter=None):
    return ToolRegistry(Settings(), readiness=lambda *a, **k: {'runtime_ready': True},
                        secret_getter=secret_getter or (lambda _: ''),
                        web_provider=type('NoNetwork', (), {'availability': lambda _: {'available': True, 'state': 'unverified'}})())


def test_every_installed_manifest_has_explicit_input_output_and_access_contract():
    expected = {'id','name','category','description','accepted_inputs','output_schema','access_mode',
                'auth_requirements','required_permissions','network_requirements','rate_limit_policy',
                'capabilities','source_url','documentation_url','adapter_version','execution_mode','input_schema',
                'requires_external_key','requires_user_confirmation','supports_cancellation','supports_evidence'}
    ids = set()
    for spec in _SPECS:
        item = manifest(spec).to_dict()
        assert set(item) == expected and item['id'] not in ids
        ids.add(item['id'])
        assert item['description'] and item['accepted_inputs'] == (spec.kind,)
        assert item['access_mode'] in {'OFFICIAL_API','LOCAL_CLI','OPEN_DATASET','PERMITTED_HTTP','PERMITTED_BROWSER','MANUAL_ONLY','NOT_SUPPORTED'}
        assert item['source_url'].startswith('https://') and item['documentation_url'].startswith('https://')
        assert item['output_schema']['type'] == 'object'
        assert {'invocation_id','tool_id','status','data','evidence_ids','warnings','errors'} <= set(item['output_schema']['required'])


@pytest.mark.parametrize('state,expected', [('auth_required','authentication_required'), ('missing_runtime','not_installed'),
    ('disabled','disabled'), ('blocked','temporarily_unavailable'), ('timeout','temporarily_unavailable'),
    ('rate_limited','temporarily_unavailable'), ('failed','failed')])
def test_current_unavailability_takes_priority_over_historical_success(state, expected):
    assert technical_state({'state':state,'available':False,'last_execution':{'status':'complete'}}) == expected


def test_readiness_never_equates_partial_execution_or_configuration_with_live_success():
    assert technical_state({'state':'ready','available':True}) == 'ready_local'
    assert technical_state({'state':'ready','available':True,'last_execution':{'status':'partial'}}) == 'ready_local'
    assert technical_state({'state':'ready','available':True,'last_execution':{'status':'complete'}}) == 'live_verified'
    assert technical_state({'state':'unavailable','available':False,'last_execution':{'status':'complete'}}) != 'live_verified'
    reg = registry()
    reg.catalog()  # Fill real readiness cache, no API request.
    reg._last_executions['github_repository'] = {'status':'partial','obtained_at':'fixture'}
    row = next(row for row in reg.catalog() if row['name']=='github_repository')
    assert row['readiness_status'] == 'ready_local'
    assert row['diagnostic']['execution_verified'] is False


def test_task_schemas_select_relevant_capabilities_and_hide_keys_private_options():
    reg = registry(lambda name: 'SYNTHETIC-VT-KEY' if name=='virustotal_api_key' else '')
    selected = reg.schemas(task='Проверь публичные метаданные GitHub репозитория watsoncore/Granger-OSINT')
    names = {item['function']['name'] for item in selected}
    assert 'github_repository' in names and 'hash_virustotal' not in names and 'telegram_public' not in names
    assert len(selected) < len(_SPECS)
    for item in selected:
        schema = item['function']['parameters']
        assert schema['additionalProperties'] is False
        assert all(key in schema['properties'] for key in schema['required'])
        if not schema['required']:assert item['function']['name'] in ('evidence_graph','capabilities_find')
    assert 'SYNTHETIC-VT-KEY' not in json.dumps(selected)
    assert 'source_root' not in json.dumps(selected)


def test_x_profile_and_post_tools_are_discoverable_from_natural_x_tasks():
    reg=registry()
    for task in ('Проверь профиль X jack','Прочитай пост X по URL https://x.com/jack/status/20'):
        names={s['function']['name'] for s in reg.schemas(task=task)}
        assert {'x_profile','x_post'}<=names
    assert 'x_profile' in {s['function']['name'] for s in reg.schemas(task='Проверь публичные профили по никнейму')}


def test_scoped_image_offers_visual_pipeline_without_requiring_id_in_user_text(monkeypatch):
    monkeypatch.setattr('grangerpet.visual_models.tools.readiness',lambda:{'available':True,'state':'ready_local','reason':'Fixture only'})
    reg=registry();reg.allow_attachments(['img_'+'a'*64])
    names={s['function']['name'] for s in reg.schemas(task='Посмотри, где это снято')}
    assert {'visual_geoint','geoclip_predict','waypoint_predict','image_metadata'}<=names


def test_virustotal_dispatch_reads_only_its_key_and_requires_approval(monkeypatch):
    requested, invocations = [], []
    def getter(name):
        requested.append(name)
        assert name == 'virustotal_api_key'
        return 'SYNTHETIC-VT-KEY'
    def execute(tool, value, **kwargs):
        invocations.append((tool, value, kwargs))
        return {'tool':tool,'status':'empty','results':[],'limitations':['Local transport fixture only']}
    monkeypatch.setattr('grangerpet.public_integrations.execute', execute)
    reg = registry(getter)
    args = {'sha256':'a'*64}
    denied = reg.execute('hash_virustotal', args)
    assert denied['status'] == 'approval_required' and not invocations
    result = reg.execute('hash_virustotal', args, approved=True)
    assert result['status'] == 'empty' and len(invocations) == 1
    assert invocations[0][2]['secret'] == 'SYNTHETIC-VT-KEY'
    assert requested and set(requested) == {'virustotal_api_key'}
    assert 'SYNTHETIC-VT-KEY' not in json.dumps(result)
    assert result['invocation_id'] and result['tool_id'] == 'hash_virustotal'
    assert result['started_at'] and result['finished_at'] and result['data'] == {'results':[]}


@pytest.mark.parametrize('name,args', [('github_repository', {'repository':'owner/repo','url':'https://evil.invalid'}),
    ('hash_virustotal',{'sha256':'a'*64,'api_key':'model-provided'}), ('threat_feodo',{'address':'127.0.0.1'})])
def test_schema_enforcement_rejects_host_secret_injection_before_dispatch(monkeypatch, name, args):
    monkeypatch.setattr('grangerpet.public_integrations.execute', lambda *a, **k: pytest.fail('Disallowed dispatch'))
    result = registry().execute(name, args, approved=True)
    assert result['status'] == 'invalid_arguments' and result['results'] == []


def test_cancelled_or_expired_registry_call_cannot_reach_public_adapter(monkeypatch):
    monkeypatch.setattr('grangerpet.public_integrations.execute', lambda *a, **k: pytest.fail('Disallowed dispatch'))
    reg = registry()
    cancel = threading.Event(); cancel.set()
    assert reg.execute('github_repository',{'repository':'owner/repo'},cancel_event=cancel)['status']=='cancelled'
    assert reg.execute('github_repository',{'repository':'owner/repo'},deadline=time.monotonic()-1)['status']=='timeout'
