"""Explicit synthetic transport fixtures; no claim of external source access."""
import asyncio
import json
import threading
import time

import httpx
import pytest

from grangerpet import network_sources as network
from grangerpet.agent_tools import ToolRegistry, _SPECS
from grangerpet.config import Settings
from grangerpet.engine.adapters import default_adapters, select_adapters
from grangerpet.engine.models import SearchQuery
from grangerpet.engine.router import detect_query
from grangerpet.entity_router import route, route_goal
from grangerpet.tool_manifest import relevant_names


class Fixture:
    def __init__(self, handler): self.handler=handler; self.requests=[]
    def factory(self, **kwargs):
        async def run(request):
            self.requests.append(request)
            response=self.handler(request)
            if asyncio.iscoroutine(response): response=await response
            return response
        kwargs.pop('transport', None)
        return httpx.AsyncClient(transport=httpx.MockTransport(run), **kwargs)
    async def resolver(self, host, port): return ['1.1.1.1']
    def execute(self, tool, value, **kwargs):
        return network.execute(tool,value,client_factory=self.factory,resolver=self.resolver,**kwargs)


@pytest.mark.parametrize('text,kind,value', [
    ('Исследуй 66.249.67.41', 'infrastructure_asset', '66.249.67.41'),
    ('Проверь 2001:4860:4860::8888', 'infrastructure_asset', '2001:4860:4860::8888'),
    ('Диапазон 8.8.8.0/24', 'network_range', '8.8.8.0/24'),
    ('Маршруты AS15169', 'autonomous_system', 'AS15169'),
    ('DNS example.org', 'domain', 'example.org'),
])
def test_literal_resources_inside_user_goal_reach_specialized_tools(text,kind,value):
    targets=route_goal(text)
    assert any(t.entity_type==kind and t.identifier==value for t in targets)
    registry=ToolRegistry(Settings(),secret_getter=lambda name:'')
    calls=registry.initial_calls(text)
    assert calls and not any(c['name'] in ('web_search','wikipedia_search','hn_search') for c in calls)
    assert len(calls)<=3
    assert not {'wikipedia_search','hn_search','openlibrary_search'} & relevant_names(_SPECS,text)


@pytest.mark.parametrize('value,kind', [('66.249.67.41','ip'),('2001:4860:4860::8888','ip'),('8.8.8.0/24','network'),('AS15169','network'),('example.org','domain')])
def test_manual_search_uses_passive_adapters_instead_of_keyword_search(value,kind):
    query=SearchQuery(value).normalized()
    assert query.kind==kind
    adapters=select_adapters(query,{},default_adapters(),verify_runtime=False)
    assert adapters and not any(a.id=='public_web' for a in adapters)


@pytest.mark.parametrize('tool,value', [
    ('network_rdap','192.168.1.1'),('network_routing','127.0.0.0/8'),
    ('network_reverse_dns','::1'),('network_reputation','224.0.0.1'),
    ('network_routing','AS4294967296'),('network_rdap','66.249.67.41;cmd'),
    ('domain_dns','router.local'),('domain_rdap','example.org/path')])
def test_invalid_or_private_targets_never_make_requests(tool,value):
    fixture=Fixture(lambda r:pytest.fail('Network must not run'))
    assert fixture.execute(tool,value)['status']=='invalid_arguments'
    assert not fixture.requests


def test_authoritative_rdap_retains_registration_not_contact_secrets():
    def handle(request):
        if request.url.host=='data.iana.org':
            return httpx.Response(200,json={'services':[[['66.0.0.0/8'],['https://rdap.arin.net/registry/']]]})
        assert request.url.host=='rdap.arin.net' and request.url.path=='/registry/ip/66.249.67.41'
        return httpx.Response(200,json={'objectClassName':'ip network','name':'SYNTHETIC-NET','startAddress':'66.249.64.0',
            'endAddress':'66.249.95.255','country':'US','events':[{'eventAction':'registration','eventDate':'2000-01-01'}],
            'entities':[{'roles':['registrant'],'vcardArray':['vcard',[
                ['fn',{},'text','Fixture Organization'],['tel',{},'text','PRIVATE-FIXTURE-PHONE']]]}]})
    fixture=Fixture(handle);result=fixture.execute('network_rdap','66.249.67.41')
    assert result['status']=='complete' and len(result['results'])==1
    fields=result['results'][0]['details']
    assert fields['name']=='SYNTHETIC-NET' and fields['registry_entities'][0]['name']=='Fixture Organization'
    assert 'PRIVATE-FIXTURE-PHONE' not in json.dumps(result)
    assert len(fixture.requests)==2


@pytest.mark.parametrize('endpoint',['http://rdap.arin.net/','https://localhost/','https://127.0.0.1/'])
def test_unusable_iana_endpoint_cannot_select_a_local_or_insecure_service(endpoint):
    fixture=Fixture(lambda r:httpx.Response(200,json={'services':[[['66.0.0.0/8'],[endpoint]]]}))
    result=fixture.execute('network_rdap','66.249.67.41')
    assert result['status']=='error' and len(fixture.requests)==1


def test_ptr_nxdomain_is_an_observation_not_safety_or_ownership_claim():
    fixture=Fixture(lambda r:httpx.Response(200,json={'Status':3}))
    result=fixture.execute('network_reverse_dns','66.249.67.41')
    assert result['status']=='complete' and result['results'][0]['details']['answers']==[]
    assert fixture.requests[0].url.params['name']=='41.67.249.66.in-addr.arpa'


@pytest.mark.parametrize('failure',[429,'timeout','malformed'])
def test_routing_failure_keeps_other_independent_observations(failure):
    def handle(request):
        name=request.url.path.split('/')[2]
        if name=='prefix-overview':
            if failure=='timeout':raise httpx.ReadTimeout('Synthetic timeout',request=request)
            if failure=='malformed':return httpx.Response(200,json='not an object')
            return httpx.Response(429,json={})
        return httpx.Response(200,json={'status':'ok','data':{'observed_resource':'8.8.8.0/24','fixture':name}})
    result=Fixture(handle).execute('network_routing','8.8.8.0/24')
    assert result['status']=='partial' and len(result['results'])==2
    assert {r['details']['dataset'] for r in result['results']}=={'routing-status','routing-history'}
    code={'timeout':'timeout','malformed':'invalid_source_response'}.get(failure,'http_429')
    assert any(d.get('error_code')==code for d in result['source_diagnostics'])


def test_dns_servfail_is_not_reported_as_an_empty_or_clean_observation():
    result=Fixture(lambda r:httpx.Response(200,json={'Status':2})).execute('network_reverse_dns','8.8.8.8')
    assert result['status']=='unavailable' and not result['results']
    assert result['error_code']=='dns_rcode_2'


@pytest.mark.parametrize('body,success', [
    ('{"cidr":"8.8.8.0/24","sblid":"FIXTURE"}\n{"timestamp":1,"copyright":"Fixture"}',True),
    ('',False),('[]',False),('{"timestamp":1}',False)])
def test_drop_validated_dataset_and_empty_body_not_clean_verdict(body,success):
    result=Fixture(lambda r:httpx.Response(200,text=body,headers={'content-type':'application/x-ndjson'})).execute('network_reputation','8.8.8.8')
    assert (result['status']=='complete') is success
    if success:assert result['results'][0]['details']['matched'] is True
    else:assert not result['results']


def test_cancellation_preserves_dns_evidence_already_observed():
    event=threading.Event()
    async def handle(request):
        if request.url.params['type']=='AAAA':return httpx.Response(200,json={'Status':0,'Answer':[{'type':28,'data':'2001:4860::8888'}]})
        event.set();await asyncio.sleep(3);return httpx.Response(200,json={})
    result=Fixture(handle).execute('domain_dns','example.org',cancel_event=event)
    assert result['status']=='cancelled' and len(result['results'])==1
    assert result['results'][0]['details']['answers'][0]['data']=='2001:4860::8888'


def test_registry_result_reaches_existing_evidence_and_capability_contract(monkeypatch):
    fixture=Fixture(lambda r:httpx.Response(200,json={'Status':0,'Answer':[{'type':12,'data':'fixture.example.org.'}]}))
    original=network.execute
    monkeypatch.setattr(network,'execute',lambda name,value,**kw:original(name,value,client_factory=fixture.factory,resolver=fixture.resolver,**kw))
    registry=ToolRegistry(Settings(),secret_getter=lambda name:'')
    outcome=registry.execute('network_reverse_dns',{'address':'8.8.8.8'})
    assert outcome['status']=='complete' and outcome['results'][0]['evidence_id'].startswith('ev_')
    assert registry.evidence.records()[0]['details']['answers'][0]['value']=='fixture.example.org.'
    assert not registry.execute('network_reverse_dns',{'address':'8.8.8.8','secret':'NOPE'})['results']


def test_invalid_ipv4_cannot_fall_through_to_domain_or_username():
    assert route('999.249.67.41') is None
    assert not detect_query('999.249.67.41').valid


def test_network_fields_survive_synthesis_context_and_have_readable_fallback():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.investigation_analysis import analyze,model_context,factual_report
    raw={'id':'network-fixture','title':'RIPE fixture','type':'ip','platform':'ripestat',
        'url':'https://stat.ripe.net/data/network-info/data.json?resource=8.8.8.8',
        'details':{'address':'8.8.8.8','prefix':'8.8.8.0/24','asns':['15169']}}
    analysis=analyze({'goal':'Исследуй 8.8.8.8','evidence':[normalize_evidence(raw,'ip_lookup','8.8.8.8')]})
    context=model_context(analysis)
    assert context['network_profiles'][0]['resource']=='8.8.8.8'
    report=factual_report(analysis,language_unavailable=True)
    assert '8.8.8.0/24' in report and 'AS15169' in report and '[Источник](https://' in report
    assert 'ev_' not in report


def test_prefix_api_url_does_not_hide_an_exact_typed_ip_observation():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.investigation_analysis import analyze,model_context
    from grangerpet.investigation_results import relevance
    row=normalize_evidence({'id':'prefix-fixture','title':'RIPE prefix overview','type':'ip','platform':'ripestat',
        'url':'https://stat.ripe.net/data/prefix-overview/data.json?resource=8.8.8.0/24',
        'details':{'address':'8.8.8.8','dataset':'prefix-overview','data':{'asns':[{'asn':15169,'holder':'Fixture AS'}]}}},'network_routing','8.8.8.8')
    assert relevance([row],'Исследуй 8.8.8.8')[row['evidence_id']]['level']=='direct'
    context=model_context(analyze({'goal':'Исследуй 8.8.8.8','evidence':[row]}))
    assert any(f['value']=='AS15169' for f in context['network_profiles'][0]['facts'])
    from grangerpet.evidence_graph import build
    graph=build([row],full=True,limit=5000,goal='Исследуй 8.8.8.8')
    assert any(e['relation_type']=='announced_by' for e in graph['relations'])


def test_graph_uses_real_dns_and_route_relations_without_identity_inference():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.evidence_graph import build
    raw=[{'id':'dns','title':'DNS fixture','type':'domain','platform':'google_dns',
        'url':'https://dns.google/resolve?name=example.org&type=A',
        'details':{'domain':'example.org','record_type':'A','value':'8.8.8.8'}},
        {'id':'route','title':'RIPE fixture','type':'ip','platform':'ripestat',
        'url':'https://stat.ripe.net/data/network-info/data.json?resource=8.8.8.8',
        'details':{'address':'8.8.8.8','prefix':'8.8.8.0/24','asns':['15169']}}]
    records=[normalize_evidence(row,'fixture',row['details'].get('address','example.org')) for row in raw]
    graph=build(records,full=True,limit=5000,goal='Исследуй example.org и 8.8.8.8')
    relations={r['relation_type'] for r in graph['relations']}
    assert {'resolves_to','within_announced_prefix','announced_by'} <= relations
    assert not any('owner' in r or 'same_person' in r for r in relations)
    ips=[n for n in graph['entities'] if n['attributes'].get('address')=='8.8.8.8']
    assert len(ips)==1 and not ips[0]['attributes'].get('technical')
    for edge in graph['relations']:
        if edge['relation_type'] in ('resolves_to','announced_by'):assert edge['evidence_ids'] and edge['provenance']
