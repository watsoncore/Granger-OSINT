import time
import pytest
from grangerpet.entity_router import route, route_goal
from grangerpet.tool_manifest import relevant_names
from grangerpet.agent_tools import _SPECS
from grangerpet.telegram_public import execute
from grangerpet.chat import investigation_requested
from test_agent_tools import registry, Adapter


@pytest.mark.parametrize('value,kind,platform,tool', [
    ('https://t.me/solvnox_project', 'public_channel_or_profile', 'telegram', 'telegram_public'),
    ('https://t.me/s/telegram/20', 'public_post', 'telegram', 'telegram_public'),
    ('https://github.com/octocat/Hello-World', 'github_repository', 'github', 'github_repository'),
    ('https://github.com/octocat', 'github_profile', 'github', 'github_profile'),
    ('EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c', 'blockchain_address', 'ton', 'blockchain_gansar'),
    ('0:' + 'ab' * 32, 'blockchain_address', 'ton', 'blockchain_gansar'),
    ('48.8584,2.2945', 'geographic_coordinates', '', 'map_panoramax'),
    ('8.8.8.8', 'infrastructure_asset', 'ip', 'ip_lookup'),
    ('contact@example.org', 'email', '', 'mail_dns'),
    ('img_' + 'a' * 64, 'image', '', 'visual_geoint'),
])
def test_deterministic_target_and_existing_specialized_tool(value, kind, platform, tool):
    target = route(value)
    assert target.entity_type == kind and target.platform == platform
    assert tool in target.tools
    assert route(value).to_dict()['id'] == target.to_dict()['id']
    assert tool in relevant_names(_SPECS, value)


def test_private_telegram_or_invalid_ton_never_become_username_or_authorized_discovery():
    assert route('https://t.me/+private_invite') is None
    invalid = route('EQ' + 'A' * 46)
    assert invalid.platform == 'ton' and not invalid.tools and invalid.properties['validation_error']
    assert not route('192.168.1.1').tools


def test_telegram_scope_does_not_offer_unrelated_hn_or_books_but_observed_link_expands_github():
    task = 'Исследуй https://t.me/solvnox_project и построй граф'
    names = relevant_names(_SPECS, task)
    assert {'telegram_public', 'web_read', 'evidence_graph'} <= names
    assert not {'hn_search', 'hn_profile', 'openlibrary_search', 'github_profile'} & names
    observed = [{'url': 'https://t.me/s/solvnox_project', 'details': {'links': [{'url': 'https://github.com/observed-example/project'}]}}]
    assert 'github_repository' in relevant_names(_SPECS, task, observed)


def test_literal_goal_extraction_never_invents_similar_cross_platform_identity():
    targets = route_goal('Изучи https://t.me/solvnox_project. Адрес 0:' + 'ab' * 32)
    assert {t.platform for t in targets} == {'telegram', 'ton'}
    assert not any('watsoncore' in t.identifier for t in targets)


def test_tool_availability_question_uses_backend_agent_context():
    assert investigation_requested('Гермиона, какие GEOINT-инструменты тебе доступны?')
    assert investigation_requested('GeoCLIP и Waypoint готовы?')
    assert not investigation_requested('Привет, как ты?')
    assert not investigation_requested('Расскажи без инструментов про GeoCLIP')
    assert investigation_requested('EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c')
    assert investigation_requested('48.8584,2.2945')


class Reader:
    def __init__(self): self.urls = []
    def allow_url(self, url, **kwargs): return True
    def read(self, url, **kwargs):
        self.urls.append(url)
        return {'status': 'complete', 'results': [{'id': url, 'title': 'Public fixture', 'type': 'web', 'platform': 't.me',
            'url': url, 'description': 'Actual fixture page', 'details': {'metadata': {'og:title': 'Synthetic channel'},
                'links': [{'url': 'https://t.me/fixture_channel/12'}, {'url': 'https://github.com/public-example/project'}]}, 'status': 'content_observed'}]}


def test_public_channel_type_only_from_observed_preview_posts_without_session():
    reader = Reader()
    result = execute('fixture_channel', reader=reader)
    assert reader.urls == ['https://t.me/fixture_channel', 'https://t.me/s/fixture_channel']
    assert result['results'][0]['details']['object_type_verified'] is False
    assert result['results'][1]['details']['entity_type'] == 'telegram_channel'
    assert result['results'][1]['details']['identity_verified'] is False


def test_authorized_mode_cannot_execute_legacy_adapter_without_confirmation():
    adapter = Adapter(); adapter.id = 'telegram'
    reg, _ = registry(adapter)
    denied = reg.execute('telegram_public', {'username': 'fixture_channel', 'access_mode': 'authorized'})
    assert denied['status'] == 'approval_required' and not adapter.calls
    allowed = reg.execute('telegram_public', {'username': 'fixture_channel', 'access_mode': 'authorized'}, approved=True)
    assert allowed['status'] == 'complete' and len(adapter.calls) == 1


def test_primary_route_precedes_model_broad_search_and_is_not_repeated_on_resume():
    from grangerpet.agent import AgentRunner, AgentLimits
    from test_agent_lifecycle import Client, response
    reg, _ = registry()
    reader = Reader()
    reg.web_reader = reader
    reader.begin_run = lambda: None
    reader.seed_urls_from_user = lambda text: None
    reader.checkpoint_state = lambda: {}
    reader.add_evidence = lambda records: None
    client = Client([response(text='Получены сведения публичного превью.')])
    result = AgentRunner(client, reg).run('fixture', [{'role': 'user', 'text': 'Исследуй https://t.me/fixture_channel'}])
    assert reader.urls == ['https://t.me/fixture_channel', 'https://t.me/s/fixture_channel']
    assert result['investigation']['calls'][0]['tool'] == 'telegram_public'
    assert client.requests[0][-1]['role'] == 'tool'
    assert result['investigation']['target_entities'][0]['platform'] == 'telegram'


def test_original_user_url_is_seeded_before_first_direct_page_read():
    from grangerpet.agent import AgentRunner
    from test_agent_lifecycle import Client, response
    reader = Reader()
    known = set()
    reader.begin_run = lambda: None
    reader.checkpoint_state = lambda: {}
    reader.add_evidence = lambda records: None
    reader.seed_urls_from_user = lambda text: known.add('https://example.org/Path') if 'https://example.org/Path' in text else None
    original = reader.read
    def read(url, **kwargs):
        assert url in known, 'The user URL must be authorized by backend before any page request'
        return original(url, **kwargs)
    reader.read = read
    reg, _ = registry()
    reg.web_reader = reader
    result = AgentRunner(Client([response(text='Содержимое прочитано.')]), reg).run('fixture',
        [{'role': 'user', 'text': 'Прочитай https://example.org/Path'}])
    assert len(result['evidence']) == 1 and reader.urls == ['https://example.org/Path']


def test_equivalent_platform_arguments_and_ignored_singleton_limits_share_signature():
    from grangerpet.agent import AgentRunner
    reg, _ = registry()
    runner = AgentRunner(None, reg)
    assert runner._fingerprint({'name': 'telegram_public', 'arguments': {'username': 'https://t.me/fixture_channel'}}) == runner._fingerprint(
        {'name': 'telegram_public', 'arguments': {'username': 'fixture_channel', 'access_mode': 'public', 'limit': 20}})
    assert runner._fingerprint({'name': 'github_repository', 'arguments': {'repository': 'OWNER/Repo'}}) == runner._fingerprint(
        {'name': 'github_repository', 'arguments': {'repository': 'owner/repo', 'limit': 10}})


def test_external_repository_links_survive_compact_preview_with_lots_of_navigation():
    from grangerpet.agent import AgentRunner
    reg, _ = registry()
    runner = AgentRunner(None, reg)
    runner._record = {'goal': 'Исследуй https://t.me/fixture_channel'}
    links = [{'url': 'https://t.me/fixture_channel/' + str(i), 'text': 'post'} for i in range(20)]
    links += [{'url': 'https://github.com/discovered/one'}, {'url': 'https://github.com/discovered/two'}]
    selected = runner._relevant_links(links, 'https://t.me/s/fixture_channel', 12)
    assert [r['url'] for r in selected[:2]] == ['https://github.com/discovered/one', 'https://github.com/discovered/two']
