"""Steam contract fixtures, explicitly distinct from public Steam live checks."""
import asyncio
import json
import time

import httpx
import pytest

from grangerpet.steam_public import normalize,validate,collect,_xml
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings
from grangerpet.entity_router import route,route_goal
from grangerpet.engine.models import SearchQuery
from grangerpet.engine.adapters import default_adapters,select_adapters

BASE='76561197960265731'
XML=('<?xml version="1.0"?><profile><steamID64>'+BASE+'</steamID64><steamID>Тестовый профиль</steamID>'
    '<privacyState>public</privacyState><avatarFull>https://avatars.steamstatic.com/fixture.jpg</avatarFull>'
    '<memberSince>January 1, 2000</memberSince><summary>Только fixture</summary></profile>')


@pytest.mark.parametrize('value',[BASE,'STEAM_0:1:1','[U:1:3]',f'https://steamcommunity.com/profiles/{BASE}'])
def test_reviewed_steamrecon_normalizer_preserves_distinct_identifiers(value):
    identity,url=normalize(value)
    assert identity.steamid64==BASE and identity.account_id==3
    assert identity.steam2=='STEAM_0:1:1' and url.endswith(BASE)
    assert route(value).platform=='steam'
    query=SearchQuery(value).normalized();assert query.kind=='steam'
    assert {a.id for a in select_adapters(query,{},default_adapters(),verify_runtime=False)}=={'steam_profile','steam_aliases','steam_friends'}


@pytest.mark.parametrize('value',[
    'https://evil.example.org/steamcommunity.com/profiles/'+BASE,
    'https://steamcommunity.com.evil.example.org/profiles/'+BASE,
    'https://user:password@steamcommunity.com/id/fixture',
    'https://steamcommunity.com/id/fixture?sessionid=private',
    'https://steamcommunity.com/id/fixture/friends',
    '76561197960265727','STEAM_2:1:1','[U:1:4294967296]',
    'fixture;cmd','file:///profile',])
def test_spoofed_unsafe_non_public_or_out_of_range_steam_target_is_rejected(value):
    with pytest.raises(ValueError):validate('steam_profile',value)


def run_fixture(tool,value,handler):
    requests=[]
    def factory(**kwargs):
        kwargs.pop('transport',None)
        def request(req):requests.append(req);return handler(req)
        return httpx.AsyncClient(transport=httpx.MockTransport(request),**kwargs)
    async def resolver(host,port):return ['1.1.1.1']
    async def run():return await collect(tool,value,deadline=time.monotonic()+10,client_factory=factory,resolver=resolver)
    return asyncio.run(run()),requests


def test_actual_reviewed_xml_parser_extracts_cyrillic_and_source_not_private_configuration():
    result,requests=run_fixture('steam_profile','https://steamcommunity.com/id/fixture',lambda r:httpx.Response(200,text=XML,headers={'content-type':'text/xml'}))
    assert len(requests)==1 and result['status']=='complete'
    row=result['results'][0]
    assert row['details']['steamid64']==BASE and row['details']['profile']['personaname']=='Тестовый профиль'
    assert row['url']=='https://steamcommunity.com/profiles/'+BASE
    assert row['details']['requested_profile']=='https://steamcommunity.com/id/fixture'
    assert 'SteamRecon' in row['details']['source_project']


def test_private_profile_keeps_available_metadata_without_zeroing_closed_sections():
    result,_=run_fixture('steam_profile',BASE,lambda r:httpx.Response(200,text=XML.replace('public','private'),headers={'content-type':'text/xml'}))
    assert result['status']=='partial' and result['results'][0]['details']['profile']['privacy']=='private'
    assert not any(k in result['results'][0]['details'] for k in ('private_friends_count','owned_games_count'))


def test_aliases_keep_public_names_and_dates_without_identity_inference():
    result,requests=run_fixture('steam_aliases',BASE,lambda r:httpx.Response(200,json=[{'newname':'Старый ник','timechanged':'Fixture date'}]))
    assert requests[0].url.path.endswith('/ajaxaliases/')
    assert result['results'][0]['details']['aliases']==[{'name':'Старый ник','seen_at':'Fixture date'}]
    assert result['results'][0]['details']['identity_verified'] is False


def test_friend_parser_uses_actual_friend_links_not_all_profile_urls_on_a_page():
    html='<a href="https://steamcommunity.com/profiles/76561197960265733">navigation</a><div class="friend_block_v2"><a class="selectable_overlay" href="https://steamcommunity.com/profiles/76561197960265735">friend</a></div><footer><a href="https://steamcommunity.com/profiles/76561197960265737">footer</a></footer>'
    result,_=run_fixture('steam_friends',BASE,lambda r:httpx.Response(200,text=html,headers={'content-type':'text/html'}))
    assert result['results'][0]['details']['friends']==['https://steamcommunity.com/profiles/76561197960265735']


def test_xml_entities_rejected_before_parser_execution():
    with pytest.raises(ValueError):_xml(b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///secret">]><profile>&y;</profile>')


def test_registry_routes_steam_goal_and_uses_resolved_id_for_followups():
    registry=ToolRegistry(Settings(),secret_getter=lambda name:'')
    goal='Исследуй https://steamcommunity.com/id/fixture'
    calls=registry.initial_calls(goal)
    assert calls==[{'name':'steam_profile','arguments':{'profile':'https://steamcommunity.com/id/fixture'}}]
    from grangerpet.agent_evidence import normalize_evidence
    raw={'id':'fixture','type':'profile','title':'Fixture','platform':'steam','url':'https://steamcommunity.com/profiles/'+BASE,
        'details':{'steamid64':BASE,'requested_profile':'https://steamcommunity.com/id/fixture','canonical_url':'https://steamcommunity.com/profiles/'+BASE}}
    record=normalize_evidence(raw,'steam_profile','https://steamcommunity.com/id/fixture')
    registry.evidence.add({'tool':'steam_profile','status':'complete','query':goal,'results':[record]})
    assert {'name':'steam_aliases','arguments':{'profile':BASE}} in registry.continuation_calls(goal)


def test_steam_data_reaches_final_synthesis_without_cross_platform_identity_merges():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.investigation_analysis import analyze,model_context,factual_report
    from grangerpet.evidence_graph import build
    raw={'id':'fixture','type':'profile','title':'Тестовый профиль','platform':'steam','url':'https://steamcommunity.com/profiles/'+BASE,
        'details':{'steamid64':BASE,'requested_profile':'https://steamcommunity.com/id/fixture','canonical_url':'https://steamcommunity.com/profiles/'+BASE,
            'profile':{'personaname':'Тестовый профиль','privacy':'public'},'aliases':[{'name':'Старый ник'}],
            'friends':['https://steamcommunity.com/profiles/76561197960265735']}}
    record=normalize_evidence(raw,'steam_profile','https://steamcommunity.com/id/fixture')
    analysis=analyze({'goal':'Исследуй https://steamcommunity.com/id/fixture','evidence':[record]})
    assert model_context(analysis)['social_profiles'][0]['steamid64']==BASE
    assert 'Старый ник' in factual_report(analysis)
    graph=build([record],full=True,limit=5000,goal='Исследуй https://steamcommunity.com/id/fixture')
    assert any(r['relation_type']=='public_friend_link' for r in graph['relations'])
    root=next(n for n in graph['entities'] if n['attributes'].get('is_root'))
    assert root['attributes']['steamid64']==BASE
