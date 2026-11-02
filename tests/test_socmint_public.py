"""Explicit synthetic public-response fixtures. No live profile claims."""
import json
import time
import httpx
import pytest
from grangerpet.socmint_targets import vk,tiktok
from grangerpet.socmint_public import tiktok_observation,tiktok_public,vk_public
from grangerpet.entity_router import route
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings


@pytest.mark.parametrize('value,kind,canonical',[
    ('https://m.vk.ru/id123','profile','https://vk.com/id123'),
    ('vk.ru/club123','community','https://vk.com/club123'),
    ('https://vk.com/public123','community','https://vk.com/public123'),
    ('https://vk.com/wall-123_456','post','https://vk.com/wall-123_456'),
    ('https://vk.com/example?w=wall-123_456','post','https://vk.com/wall-123_456')])
def test_vk_variants_and_posts_route_to_public_keyless_operation(value,kind,canonical):
    target=vk(value);assert target['kind']==kind and target['canonical_url']==canonical
    routed=route(value);assert routed.canonical_url==canonical and routed.tools[0]=='vk_public'


@pytest.mark.parametrize('value',['https://vk.com@evil.example/id1','https://vk.com:444/id1',
    'https://vk.com/settings','https://m.vk.com/../../admin','https://vk.com/login'])
def test_non_profile_or_host_spoof_is_not_a_vk_public_target(value):
    with pytest.raises(ValueError):vk(value)


def test_tiktok_distinguishes_video_and_account_and_never_decodes_video_as_user_creation():
    target=tiktok('https://www.tiktok.com/@fixture/video/6718335390845095173')
    assert target['kind']=='video' and target['video_id']=='6718335390845095173'
    observed=tiktok_observation(target,{'provider_name':'TikTok','type':'video','embed_product_id':target['video_id']})
    assert observed['userId'] is None and observed['accountCreationTimestamp'] is None
    assert observed['account_creation_status']=='not_provided'
    assert tiktok('@fixture')['kind']=='profile'
    with pytest.raises(ValueError):tiktok('6718335390845095173')
    assert route(target['canonical_url']).tools[0]=='tiktok_public_profile'


def test_embed_only_exposes_observed_fields_and_rejects_mismatched_creator():
    target=tiktok('@fixture')
    payload={'provider_name':'TikTok','type':'rich','author_url':target['profile_url'],
        'author_name':'Synthetic creator','html':'<blockquote data-unique-id="fixture"></blockquote><script>throw new Error()</script>'}
    result=tiktok_observation(target,payload)
    assert result['uniqueId']=='fixture' and result['nickname']=='Synthetic creator'
    assert result['counters'] is None and result['region'] is None
    payload['author_url']='https://www.tiktok.com/@different'
    with pytest.raises(ValueError):tiktok_observation(target,payload)


@pytest.mark.parametrize('status,expected',[(200,'partial'),(403,'blocked'),(404,'unavailable'),(429,'rate_limited')])
def test_official_tiktok_endpoint_has_scoped_status_and_pinned_public_transport(status,expected):
    calls=[]
    async def handler(request):
        calls.append(request)
        return httpx.Response(status,json={'provider_name':'TikTok','type':'rich','author_name':'Synthetic fixture'},headers={'Retry-After':'120'})
    async def resolver(host,port):return ['1.1.1.1']
    def factory(**options):
        options.pop('transport',None)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler),**options)
    result=tiktok_public('@fixture',deadline=time.monotonic()+10,
        resolver=resolver,client_factory=factory)
    assert result['status']==expected and len(calls)==1
    assert calls[0].url.path=='/oembed' and 'Authorization' not in calls[0].headers
    assert bool(result['results'])==(status==200)


def test_vk_login_200_is_not_a_profile_and_access_denial_does_not_trigger_repeated_reads():
    class Reader:
        def __init__(self):self.calls=[]
        def allow_url(self,*a,**k):return True
        def read(self,url,**k):
            self.calls.append(url)
            return {'status':'complete','results':[{'title':'Вход | ВКонтакте','details':{'metadata':{'og:title':'Вход | ВКонтакте'}}}]}
    reader=Reader();result=vk_public('id123',reader=reader)
    assert result['status']=='auth_required' and not result['results'] and len(reader.calls)==1


def test_short_platform_requests_bind_public_tools_without_personal_keys():
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    for goal,tool in [('Проверь TikTok https://www.tiktok.com/@fixture','tiktok_public_profile'),('https://m.vk.ru/id123','vk_public')]:
        assert tool in {row['function']['name'] for row in registry.schemas(task=goal)}
        assert any(row['name']==tool for row in registry.initial_calls(goal))
    assert registry.execute('tiktok_public_profile',{'target':'6718335390845095173'})['status']=='invalid_arguments'
    assert registry.execute('vk_public',{'target':'https://vk.com:444/id123'})['status']=='invalid_arguments'


def test_canonical_targets_prevent_repeat_requests_through_aliases():
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    assert registry.canonical_arguments('vk_public',{'target':'https://m.vk.ru/id123'})==registry.canonical_arguments(
        'vk_public',{'target':'https://vk.com/id123'})
    assert registry.canonical_arguments('tiktok_public_profile',{'target':'@fixture'})==registry.canonical_arguments(
        'tiktok_public_profile',{'target':'https://www.tiktok.com/@fixture'})


def test_natural_platform_hint_sets_followup_target_without_guessing_platform_for_bare_name():
    from grangerpet.chat_intent import SessionIntent
    state=SessionIntent();state.decide('Проверь TikTok @fixture.','one')
    followup=state.decide('А счётчики подписчиков?','one')
    assert followup['entity_context']['target']['platform']=='tiktok'
    assert followup['entity_context']['target']['identifier']=='fixture'
    state=SessionIntent();state.decide('Проверь @fixture','one');assert state.target is None


def test_outdated_browser_stub_is_not_login_and_browser_fallback_is_attempted_only_once():
    from grangerpet.socmint_public import vk_observation
    stub={'status':'complete','results':[{'title':'ВКонтакте | ВКонтакте','description':'Ваш браузер устарел','details':{}}]}
    assert vk_observation(vk('id123'),stub)['error_code']=='vk_unsupported_browser'
    calls=[]
    result=vk_observation(vk('id123'),stub,browser_read=lambda url:calls.append(url) or stub)
    assert len(calls)==1 and result['status']=='blocked' and result['error_code']=='vk_unsupported_browser'
