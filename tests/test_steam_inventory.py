"""Synthetic inventory protocol fixtures; actual Steam checks are separate."""
import asyncio
from copy import deepcopy
import json
import threading
import time
import httpx
import pytest
from grangerpet.steam_inventory import parse_page,parse_price,collect,validate
from grangerpet.agent_tools import ToolRegistry
from grangerpet.config import Settings

BASE='76561198045277210'
ASSET={'appid':730,'contextid':'2','assetid':'100','classid':'10','instanceid':'0','amount':'1'}
DESCRIPTION={'appid':730,'classid':'10','instanceid':'0','name':'Synthetic skin','market_hash_name':'Synthetic skin (Field-Tested)',
    'marketable':1,'tradable':1,'icon_url':'safe_fixture_icon','tags':[{'category':'Type','localized_tag_name':'Pistol'},
    {'category':'Exterior','localized_tag_name':'Field-Tested'}],'descriptions':[{'value':'<b>Fixture description</b>'}]}


def page(assetid='100',more=False,cursor=None):
    return {'success':1,'assets':[{**ASSET,'assetid':assetid}],'descriptions':[deepcopy(DESCRIPTION)],
        'asset_properties':[{'appid':730,'contextid':'2','assetid':assetid,'asset_properties':[
            {'propertyid':1,'name':'Pattern Template','int_value':'89'},
            {'propertyid':2,'name':'Wear Rating','float_value':'0.309961795806884766'}]}],
        'total_inventory_count':2,'more_items':int(more),**({'last_assetid':cursor} if cursor else {})}


def run_fixture(handler,**updates):
    calls=[]
    def factory(**options):
        options.pop('transport',None)
        def request(req):calls.append(req);return handler(req)
        return httpx.AsyncClient(transport=httpx.MockTransport(request),**options)
    async def resolver(host,port):return ['1.1.1.1']
    result=asyncio.run(collect({'profile':BASE,'max_pages':3,'page_size':10,'price_limit':0,**updates},
        deadline=time.monotonic()+15,client_factory=factory,resolver=resolver))
    return result,calls


def test_asset_description_join_keeps_distinct_assets_and_observed_float_not_name_inference():
    payload=page();payload['assets'].append({**ASSET,'assetid':'101'})
    parsed=parse_page(payload,steamid=BASE,appid=730,contextid='2')['items']
    assert len(parsed)==2 and parsed[0]['name']=='Synthetic skin'
    assert parsed[0]['float_value']=='0.309961795806884766' and parsed[0]['pattern_template']=='89'
    assert parsed[1]['float_value'] is None and parsed[1]['stickers'] is None
    assert '<b>' not in parsed[0]['description']


def test_real_cursor_protocol_is_followed_until_exhaustion_and_each_asset_is_evidence():
    def handler(req):
        payload=page('101') if 'start_assetid=100' in str(req.url) else page(more=True,cursor='100')
        return httpx.Response(200,json=payload)
    result,calls=run_fixture(handler)
    assert len(calls)==2 and result['status']=='complete'
    assert result['results'][0]['details']['coverage']['all_items_observed_in_this_call']
    items=[row for row in result['results'] if row['type']=='steam_item']
    assert len(items)==2 and items[0]['id']!=items[1]['id']


def test_rate_limit_after_first_page_retains_items_with_partial_coverage():
    result,calls=run_fixture(lambda req:httpx.Response(429,json={}) if 'start_assetid=' in str(req.url) else
        httpx.Response(200,json=page(more=True,cursor='100')))
    assert len(calls)==2 and result['status']=='partial' and len(result['results'])==2
    assert result['results'][0]['details']['coverage']['stop_reason']=='steam_inventory_http_429'


def test_repeated_cursor_or_assets_stops_without_infinite_pagination():
    result,calls=run_fixture(lambda req:httpx.Response(200,json=page(more=True,cursor='100')))
    assert len(calls)==2 and result['results'][0]['details']['coverage']['stop_reason']=='no_new_assets'


def test_page_limit_exposes_observed_next_cursor_and_does_not_claim_complete():
    result,calls=run_fixture(lambda req:httpx.Response(200,json=page(more=True,cursor='100')),max_pages=1)
    coverage=result['results'][0]['details']['coverage']
    assert result['status']=='partial' and coverage['next_cursor']=='100' and coverage['stop_reason']=='page_limit'
    assert not coverage['all_items_observed_in_this_call']


def test_prices_are_observed_usd_quotes_with_dates_and_unknown_is_not_zero():
    price=parse_price({'success':True,'lowest_price':'$1,234.56'},name='Fixture',endpoint='https://steamcommunity.com/market/priceoverview/',observed_at='2026-11-02T00:00:00Z')
    assert price['amount_decimal']=='1234.56' and price['currency']=='USD' and price['observed_at'].endswith('Z')
    assert parse_price({'success':True},name='Fixture',endpoint='',observed_at='')['amount_decimal'] is None


def test_inventory_scope_drift_is_rejected_and_inventory_url_normalizes_to_same_profile():
    payload=page();payload['assets'][0]['appid']=440
    with pytest.raises(ValueError):parse_page(payload,steamid=BASE,appid=730,contextid='2')
    assert validate({'profile':'https://steamcommunity.com/profiles/'+BASE+'/inventory/'})['profile']==BASE


def test_inventory_is_routed_and_followup_uses_observed_cursor_without_friend_dossier():
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    goal='Покажи инвентарь Steam '+BASE
    assert registry.initial_calls(goal)[0]['name']=='steam_inventory'
    raw={'tool':'steam_inventory','status':'partial','query':BASE,'results':[{'id':'inventory','title':'Fixture',
        'type':'steam_inventory','platform':'steam','url':'https://steamcommunity.com/profiles/'+BASE+'/inventory/',
        'details':{'steamid64':BASE,'appid':730,'contextid':'2','canonical_url':'https://steamcommunity.com/profiles/'+BASE,
            'coverage':{'more_items':True,'next_cursor':'100','stop_reason':'page_limit'}}}]}
    registry.evidence.add(raw)
    calls=registry.continuation_calls(goal)
    assert calls[0]['arguments']['cursor']=='100'
    assert not any(row['name']=='steam_friends' for row in calls)


def test_registry_retains_item_level_payload_beyond_default_twenty_search_results(monkeypatch):
    def execute(tool,value,**kwargs):
        return {'tool':tool,'status':'partial','query':BASE,'results':[
            {'id':'item:'+str(index),'type':'steam_item','platform':'steam','title':'Fixture '+str(index),
             'url':'https://steamcommunity.com/profiles/'+BASE+'/inventory/','details':{'assetid':str(index),'steamid64':BASE}}
            for index in range(257)]}
    monkeypatch.setattr('grangerpet.steam_public.execute',execute)
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    result=registry.execute('steam_inventory',{'profile':BASE,'price_limit':0})
    assert len(result['results'])==257 and len(registry.evidence.records())==257


def test_inventory_projection_keeps_partial_coverage_and_compacts_items_before_model():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.steam_inventory_view import inventories
    from grangerpet.investigation_analysis import analyze,model_context,factual_report
    from grangerpet.evidence_graph import build
    from grangerpet.engine.models import canonical_url
    records=[normalize_evidence({'id':'item:'+str(index),'type':'steam_item','platform':'steam','title':'Synthetic '+str(index),
        'url':f'https://steamcommunity.com/profiles/{BASE}/inventory/#730_2_{index+1}',
        'details':{'steamid64':BASE,'appid':730,'contextid':'2','assetid':str(index+1),'name':'Synthetic '+str(index),
            'amount':'1','category':'Pistol','canonical_url':'https://steamcommunity.com/profiles/'+BASE,
            'price':{'currency':'USD','amount_decimal':'0.11','observed_at':'2026-11-02T00:00:00Z'} if index==0 else None}},
        'steam_inventory',BASE) for index in range(1000)]
    records.append(normalize_evidence({'id':'inventory','type':'steam_inventory','platform':'steam','title':'Inventory fixture',
        'url':'https://steamcommunity.com/profiles/'+BASE+'/inventory/','details':{'steamid64':BASE,'appid':730,'contextid':'2',
            'coverage':{'reported_total':1100,'starts_at_cursor':None,'stop_reason':'exhausted','pages':[]}}},'steam_inventory',BASE))
    view=inventories(records)[0]
    assert len(view['items'])==1000 and view['coverage_status']=='partial' and view['valuation']['priced_assets']==1
    assert view['valuation']['observed_subtotal_decimal']=='0.11' and view['valuation']['unpriced_assets']==999
    analysis=analyze({'goal':'Инвентарь Steam '+BASE,'evidence':records})
    assert len(json.dumps(model_context(analysis),ensure_ascii=False))<15000
    assert 'не полная стоимость' in factual_report(analysis).lower()
    graph=build(records,full=True,limit=5000,goal='Инвентарь Steam '+BASE)
    assert len([node for node in graph['entities'] if node['type']=='inventory_item'])==1000
    category=next(node for node in graph['entities'] if node['attributes'].get('display_type')=='inventory_category')
    assert category['attributes']['member_count']==1000
    assert '#730_2_1' in canonical_url(records[0]['url'])


def test_agent_and_checkpoint_retain_all_inventory_rows_and_detail_reads_expose_float(monkeypatch):
    from grangerpet.agent import AgentRunner
    from test_agent import Client,turn
    def execute(tool,value,**kwargs):
        return {'tool':tool,'status':'partial','query':BASE,'results':[
            {'id':'item:'+str(index),'type':'steam_item','platform':'steam','title':'Fixture '+str(index),
             'url':'https://steamcommunity.com/profiles/'+BASE+'/inventory/',
             'details':{'capability':'steam_inventory','assetid':str(index+1),'steamid64':BASE,'appid':730,'contextid':'2','amount':'1','float_value':'0.25'}}
            for index in range(257)]}
    monkeypatch.setattr('grangerpet.steam_public.execute',execute)
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    registry.continuation_calls=lambda goal:[]
    runner=AgentRunner(Client([turn(text='Тестовая сводка.')]),registry)
    result=runner.run('fixture',[{'role':'user','text':'Покажи инвентарь Steam '+BASE}])
    assert len(result['evidence'])==257 and len(runner.checkpoint()['evidence'])==257
    detailed=json.loads(runner._compact({'tool':'evidence_get','status':'complete','results':[result['evidence'][0]]}))
    assert detailed['results'][0]['structured_record']['float_value']=='0.25'


def test_rate_limit_backoff_prevents_a_new_worker(monkeypatch):
    from grangerpet import steam_public
    monkeypatch.setattr(steam_public,'_COOLDOWN',{'steam_inventory':time.monotonic()+60})
    monkeypatch.setattr(steam_public,'_CACHE',{})
    monkeypatch.setattr(steam_public.subprocess,'Popen',lambda *a,**k:pytest.fail('Worker must not start during backoff'))
    assert steam_public.execute('steam_inventory',{'profile':BASE})['status']=='rate_limited'


def test_model_bindings_follow_only_observed_cursor_then_retire_exhausted_scope(monkeypatch):
    from grangerpet.agent import AgentRunner
    from test_agent import turn
    calls=[]
    def execute(tool,value,**kwargs):
        cursor=value.get('cursor');calls.append(cursor)
        return {'tool':tool,'status':'partial','query':BASE,'results':[{'id':'summary:'+str(cursor),'type':'steam_inventory',
            'platform':'steam','title':'Inventory fixture','url':'https://steamcommunity.com/profiles/'+BASE+'/inventory/',
            'details':{'steamid64':BASE,'appid':730,'contextid':'2','capability':'steam_inventory',
                'coverage':{'more_items':cursor is None,'next_cursor':'100' if cursor is None else None,
                    'observed_assets':1,'reported_total':3,'stop_reason':'page_limit' if cursor is None else 'exhausted'}}}]}
    monkeypatch.setattr('grangerpet.steam_public.execute',execute)
    class Client:
        def __init__(self):self.n=0
        def complete_turn(self,model,messages,*,tools,**kwargs):
            self.n+=1;bindings={row['function']['name']:row['function']['parameters'] for row in tools}
            if self.n==1:
                schema=bindings['steam_inventory'];assert schema['properties']['cursor']['enum']==['100']
                assert 'cursor' in schema['required']
                from test_agent import call
                return turn(call('steam_inventory',{'profile':BASE,'cursor':'100','price_limit':0}))
            assert 'steam_inventory' not in bindings
            return turn(text='Сервер исчерпал пагинацию; число предметов не согласовано.')
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '');registry.continuation_calls=lambda goal:[]
    AgentRunner(Client(),registry).run('fixture',[{'role':'user','text':'Инвентарь Steam '+BASE}])
    assert calls==[None,'100']
