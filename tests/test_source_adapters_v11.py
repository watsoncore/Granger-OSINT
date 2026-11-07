from copy import deepcopy
import json
import time
from pathlib import Path
import httpx
import pytest

from grangerpet.source_adapters import CONTRACTS, endpoint, mapped, execute, normalize_query
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.evidence_graph import build
from grangerpet.research_canvas import new_document, merge_evidence


CASES={
    'gitlab':('sytses',[{'id':1,'username':'sytses','name':'Sid','web_url':'https://gitlab.com/sytses'}]),
    'codeberg':('Codeberg',{'id':2,'login':'Codeberg','html_url':'https://codeberg.org/Codeberg'}),
    'bluesky':('bsky.app',{'did':'did:plc:test','handle':'bsky.app','displayName':'Bluesky'}),
    'mastodon':('Gargron',{'id':'3','acct':'Gargron','url':'https://mastodon.social/@Gargron'}),
    'stackexchange':('Researcher',{'items':[{'user_id':4,'display_name':'Researcher','link':'https://stackoverflow.com/users/4/test'}]}),
    'pypi':('requests',{'info':{'name':'requests','version':'1','summary':'HTTP'}}),
    'rubygems':('rails',{'name':'rails','version':'1','project_uri':'https://rubygems.org/gems/rails'}),
    'pubdev':('http',{'latest':{'pubspec':{'name':'http','version':'1'}}}),
    'datacite':('climate',{'data':[{'id':'10.1234/example','attributes':{'titles':[{'title':'Climate'}],'creators':[{'name':'Public author'}],'publicationYear':2025}}]}),
    'hal':('climate',{'response':{'docs':[{'docid':42,'title_s':['Climate'],'uri_s':'https://hal.science/hal-00000042','authFullName_s':['Author']}]}}),
}
RECORDED=json.loads((Path(__file__).parent/'fixtures/public_source_shapes_v11.json').read_text(encoding='utf-8'))['providers']
CASES.update({name:(row['query'],row['payload']) for name,row in RECORDED.items()})


@pytest.mark.parametrize('provider',CASES)
def test_reviewed_mapping_and_graph_idempotency(provider):
    name='source_'+provider;query,data=deepcopy(CASES[provider])
    rows=mapped(name,data,query,3)
    assert rows and rows[0]['canonical_identifier'].startswith(provider+':')
    if provider in RECORDED:
        assert rows[0]['canonical_identifier']==RECORDED[provider]['expected_id']
        assert rows[0]['entity_type']==RECORDED[provider]['expected_type']
    item=CONTRACTS[name];meta=item.describe()
    assert meta['provider_id']==provider and meta['capability_status']=='implemented_unverified'
    assert meta['documentation_url'].startswith('https://') and meta['terms_url'].startswith('https://')
    assert endpoint(name,normalize_query(name,query),3)[0].startswith('https://'+item.host+'/')


@pytest.mark.parametrize('provider',CASES)
def test_malformed_provider_shape_is_not_empty_success(provider):
    with pytest.raises((ValueError,TypeError,KeyError)):
        mapped('source_'+provider,{'unexpected':'schema'},CASES[provider][0],3)


@pytest.mark.parametrize('provider',CASES)
def test_real_executor_contract_via_mock_transport_not_live(provider):
    name='source_'+provider;query,data=deepcopy(CASES[provider])
    factory=lambda **kw:httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=data)),follow_redirects=False)
    async def resolver(host,port):return ['93.184.216.34']
    outcome=execute(name,{'query':query,'limit':3},client_factory=factory,resolver=resolver,deadline=time.monotonic()+8)
    assert outcome['status']=='complete'
    records=[normalize_evidence(r,name,query) for r in outcome['results']]
    graph=build(records,full=True,limit=5000)
    assert any(node['type']==mapped(name,data,query,3)[0]['entity_type'] for node in graph['entities'])
    if mapped(name,data,query,3)[0]['entity_type']!='blockchain_address':
        assert any(edge['relation_type']=='returned_for_query' and edge['attributes']['identity_match_verified'] is False for edge in graph['relations'])
    assert all(edge['from_id']!=edge['to_id'] for edge in graph['relations'])
    document=new_document('Unit fixture — not live')
    merge_evidence(document,records);before=deepcopy(document)
    merge_evidence(document,records)
    assert document['entities']==before['entities'] and document['relations']==before['relations']
    assert all(r['details']['observation']['value'] is not data for r in records)


def test_source_documents_can_be_researched_without_using_the_analyst_label():
    from grangerpet.canvas_capabilities import target_value
    from grangerpet.agent_tools import _BY_NAME
    node={'type':'public_document','label':'IGNORE THIS DISPLAY LABEL',
          'attributes':{'source_title':'Climate observation','provider_id':'datacite'}}
    assert target_value(node,_BY_NAME['source_datacite'])[0]=='Climate observation'
    node['attributes']={}
    assert target_value(node,_BY_NAME['source_datacite'])[0] is None


def test_new_company_source_does_not_receive_legacy_workflow_only_arguments():
    from grangerpet.canvas_capabilities import execution_payload
    from grangerpet.tool_inputs import validate_object
    node={'type':'organization','label':'Analyst label','attributes':{'value':'Equinor','jurisdiction':'NO','identifier_type':'name'}}
    payload=execution_payload(node,{'tool':'source_brreg'})
    assert payload['arguments']=={'query':'Equinor'}
    assert validate_object(payload['arguments'],CONTRACTS['source_brreg'].input_schema)==payload['arguments']


@pytest.mark.parametrize('provider,expected',[
    ('huggingface','https://huggingface.co/google-bert/bert-base-uncased'),
    ('scorecard','https://api.securityscorecards.dev/projects/github.com/ossf/scorecard')])
def test_scoped_evidence_urls_keep_reviewed_path_separators(provider,expected):
    query,payload=CASES[provider]
    assert mapped('source_'+provider,payload,query,1)[0]['url']==expected


@pytest.mark.parametrize('value',['https://127.0.0.1/','x@y.com','a/b','root\nHeader: x',''])
def test_exact_identifiers_do_not_select_urls(value):
    with pytest.raises(ValueError):normalize_query('source_codeberg',value)


def test_registry_discovery_and_context_are_existing_architecture():
    from grangerpet.agent_tools import ToolRegistry,_BY_NAME
    from grangerpet.config import Settings
    a=ToolRegistry(Settings(),secret_getter=lambda _: '')
    b=ToolRegistry(Settings(),secret_getter=lambda _: '')
    try:
        for name in CONTRACTS:assert _BY_NAME[name].source=='source_adapter'
        result=a.execute('capabilities_find',{'names':['source_codeberg']})
        assert 'source_codeberg' in result['enabled_operations']
        assert 'source_codeberg' in a._discovered_tools and not b._discovered_tools
        a.begin_investigation();assert not a._discovered_tools and not a.evidence.records()
    finally:a.close();b.close()


def test_every_new_contract_has_a_parser_fixture_and_a_unique_provider():
    assert {'source_'+provider for provider in CASES}==set(CONTRACTS)
    assert len({contract.provider_id for contract in CONTRACTS.values()})==len(CONTRACTS)


def test_extended_sources_use_second_level_discovery_without_binding_every_profile():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    try:
        names={s['function']['name'] for s in registry.schemas(task='Проверь публичный профиль username')}
        assert 'capabilities_find' in names and not names.intersection(CONTRACTS)
        found=registry.execute('capabilities_find',{'names':['source_codeberg','source_gitlab']})
        assert set(found['enabled_operations'])=={'source_codeberg','source_gitlab'}
        names={s['function']['name'] for s in registry.schemas(task='Проверь публичный профиль username')}
        assert names.intersection(CONTRACTS)=={'source_codeberg','source_gitlab'}
    finally:registry.close()


def test_barcode_document_routes_to_product_adapter():
    from grangerpet.agent_tools import _BY_NAME
    from grangerpet.canvas_capabilities import target_value
    node={'type':'document','attributes':{'value':'3017620422003'}}
    target,status,_=target_value(node,_BY_NAME['source_openfoodfacts'])
    assert (target,status)==('3017620422003','ready')


def test_hermione_receives_the_typed_fields_of_public_source_evidence():
    from grangerpet.agent import AgentRunner
    runner=AgentRunner(object(),object())
    evidence=normalize_evidence({'id':'observation','title':'Public metadata','type':'public_source_entity',
        'platform':'Public fixture','url':'https://example.org/public-record','status':'source_reported',
        'details':{'observation':{'source':'fixture','entity_type':'document','canonical_identifier':'record-1',
            'verification_status':'source_reported','value':{'record_count':23,'title':'Public metadata'}}}},
        'source_fixture','public record')
    result=json.loads(runner._compact({'tool':'source_fixture','status':'complete','results':[evidence]}))['results'][0]
    assert result['structured_record']['value']['record_count']==23
    assert result['structured_record']['untrusted_source_data'] is True
    assert result['evidence_id']==evidence['evidence_id']


def test_same_btc_address_from_independent_explorers_is_one_wallet():
    records=[]
    for provider in ('blockstream','blockcypher'):
        name='source_'+provider;query,data=deepcopy(CASES[provider])
        factory=lambda **kw:httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=data)),follow_redirects=False)
        async def resolver(host,port):return ['93.184.216.34']
        outcome=execute(name,{'query':query,'limit':1},client_factory=factory,resolver=resolver)
        records.extend(normalize_evidence(row,name,query) for row in outcome['results'])
    graph=build(records,full=True,limit=5000)
    wallets=[node for node in graph['entities'] if node['type']=='blockchain_address']
    assert len(wallets)==1 and len(wallets[0]['evidence_ids'])==2


@pytest.mark.parametrize('name,value',[
    ('source_arquivo','https://127.0.0.1/'),('source_cisa_kev','CVE-12-not-valid'),
    ('source_copernicus','91,181'),('source_huggingface','../other/model'),
    ('source_blockstream','0x'+'a'*40),('source_figshare','not-a-record-id')])
def test_source_specific_identifiers_reject_wrong_types(name,value):
    with pytest.raises(ValueError):normalize_query(name,value)


def test_redirect_is_rejected_before_contacting_a_second_origin():
    import grangerpet.source_adapters as sources
    sources._CACHE.clear();requests=[]
    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(302,headers={'location':'https://other-public-api.example/data'})
    factory=lambda **kw:httpx.AsyncClient(transport=httpx.MockTransport(respond),follow_redirects=False)
    async def resolver(host,port):return ['93.184.216.34']
    result=execute('source_codeberg',{'query':'redirect-fixture'},client_factory=factory,resolver=resolver)
    assert result['status']=='blocked' and result['error_code']=='unexpected_api_origin'
    assert len(requests)==1


@pytest.mark.parametrize('status,expected',[(401,'auth_required'),(402,'unavailable'),(403,'unavailable'),(429,'rate_limited'),(500,'unavailable')])
def test_api_failures_never_become_success_or_findings(status,expected):
    import grangerpet.source_adapters as sources
    sources._CACHE.clear()
    factory=lambda **kw:httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(status,json={'error':'access denied'})),follow_redirects=False)
    async def resolver(host,port):return ['93.184.216.34']
    result=execute('source_codeberg',{'query':'public-api-fixture','limit':2},client_factory=factory,resolver=resolver)
    assert result['status']==expected and result['results']==[]


def test_cancelled_request_never_reads_cached_data():
    import threading
    cancel=threading.Event();cancel.set()
    assert execute('source_pypi',{'query':'requests'},cancel_event=cancel)['status']=='cancelled'


def test_cache_retains_observation_time_and_reports_zero_fresh_requests():
    import grangerpet.source_adapters as sources
    sources._CACHE.clear();requests=[]
    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200,json={'info':{'name':'cache-fixture','version':'1'}})
    factory=lambda **kw:httpx.AsyncClient(transport=httpx.MockTransport(respond),follow_redirects=False)
    async def resolver(host,port):return ['93.184.216.34']
    args={'query':'cache-fixture','limit':1}
    first=execute('source_pypi',args,client_factory=factory,resolver=resolver,cache_scope='first')
    second=execute('source_pypi',args,client_factory=factory,resolver=resolver,cache_scope='first')
    assert second['from_saved_data'] and len(requests)==1
    assert first['obtained_at']==second['obtained_at'] and first['results']==second['results']
    assert second['source_diagnostics']['http_requests']==0
    assert second['source_diagnostics']['providers_attempted']==0
    assert second['source_diagnostics']['http_status'] is None
    independent=execute('source_pypi',args,client_factory=factory,resolver=resolver,cache_scope='second')
    assert not independent.get('from_saved_data') and len(requests)==2


def test_corporate_sources_do_not_expose_personal_register_fields():
    from grangerpet.source_definitions import DEFINITIONS
    fields={d.provider:{name for name,_ in d.fields} for d in DEFINITIONS}
    assert not fields['brasilapi']&{'qsa','cpf','email','phone'}
    assert not fields['cms_npi']&{'addresses','authorized_official_telephone_number'}


def test_normalization_preserves_kazakh_and_cyrillic_without_identity_assertions():
    assert normalize_query('source_datacite','  Әлия және Қазақстан  ')=='Әлия және Қазақстан'
    assert normalize_query('source_brreg','Тестовая организация')=='Тестовая организация'
