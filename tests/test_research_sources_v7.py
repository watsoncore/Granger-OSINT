import asyncio
import json
import httpx
import pytest
from grangerpet import research_workflows as workflows


@pytest.fixture(autouse=True)
def isolated_cache():
    workflows._CACHE.clear();workflows._NEXT.clear()
    yield
    workflows._CACHE.clear();workflows._NEXT.clear()


async def public_resolver(host,port):return ['8.8.8.8']


def client_factory(payload,requests,*,status=200):
    def handler(request):
        requests.append(request)
        return httpx.Response(status,json=payload,headers={'Content-Type':'application/json','Location':'https://other.example/secret'})
    def factory(**kwargs):
        kwargs['transport']=httpx.MockTransport(handler)
        return httpx.AsyncClient(**kwargs)
    return factory


def gleif_record(lei,country):
    return {'id':lei,'attributes':{'lei':lei,'entity':{'legalName':{'name':'Fixture organization'},
        'legalAddress':{'country':country},'legalJurisdiction':country,'status':'ACTIVE'},'registration':{'status':'ISSUED'}}}


def test_company_source_preserves_candidates_and_country_without_asserting_identity():
    requests=[]
    result=workflows.execute_source('company_gleif',{'query':'Fixture organization','jurisdiction':'KZ','limit':4},
        resolver=public_resolver,client_factory=client_factory({'data':[gleif_record('A'*18+'12','KZ'),gleif_record('B'*18+'34','KZ'),gleif_record('C'*18+'56','RU')]},requests))
    assert result['status']=='complete' and len(result['results'])==2
    assert len({row['details']['canonical_identifier'] for row in result['results']})==2
    assert all(row['details']['identity_match_verified'] is False for row in result['results'])
    assert all(len(row['details']['content_sha256'])==64 and row['details']['parser_version']=='1' for row in result['results'])
    assert len(requests)==1 and requests[0].url.host=='api.gleif.org'


def test_missing_official_key_is_reported_without_a_network_request():
    requests=[]
    result=workflows.execute_source('company_companies_house',{'query':'Fixture','jurisdiction':'GB'},
        resolver=public_resolver,client_factory=client_factory({},requests))
    assert result['status']=='auth_required' and requests==[] and result['results']==[]


def test_auth_never_follows_redirects_or_appears_in_safe_result():
    requests=[];fixture_key='local-only-source-fixture'
    result=workflows.execute_source('company_companies_house',{'query':'Fixture','jurisdiction':'GB'},
        secret_getter=lambda _:fixture_key,resolver=public_resolver,client_factory=client_factory({},requests,status=302))
    assert len(requests)==1 and requests[0].url.host=='api.company-information.service.gov.uk'
    assert result['status']=='unavailable' and result['results']==[]
    assert fixture_key not in json.dumps(result)


def test_corporate_workflow_never_uses_dns_or_guessed_identifiers():
    requests=[]
    result=workflows.company_research({'query':'Fixture organization','jurisdiction':'KZ'},resolver=public_resolver,
        client_factory=client_factory({'data':[]},requests))
    assert result['status']=='empty' and result['source_attempts'][0]['source']=='company_gleif'
    assert all(request.url.host=='api.gleif.org' for request in requests)
    assert not result['results']


def test_invalid_schema_is_a_source_failure_not_a_fabricated_record():
    result=workflows.execute_source('company_gleif',{'query':'Fixture'},resolver=public_resolver,
        client_factory=client_factory({'unexpected':True},[]))
    assert result['status'] not in ('complete','empty') and result['error_code']=='source_schema_changed'


def test_opencorporates_query_credential_does_not_enter_httpx_logs(caplog):
    import logging
    with caplog.at_level(logging.INFO,logger='httpx'):
        result=workflows.execute_source('company_opencorporates',{'query':'Fixture'},secret_getter=lambda _:'private-fixture-key',
            resolver=public_resolver,client_factory=client_factory({'results':{'companies':[]}},[]))
    assert 'private-fixture-key' not in caplog.text and 'api_token' not in caplog.text
    assert result['status']=='empty'


def test_company_candidates_project_separate_registrations_without_name_merging():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.evidence_graph import build
    result=workflows.execute_source('company_gleif',{'query':'Fixture organization'},resolver=public_resolver,
        client_factory=client_factory({'data':[gleif_record('A'*18+'12','KZ'),gleif_record('B'*18+'34','KZ')]},[]))
    records=[normalize_evidence(row,'company_research','Fixture organization') for row in result['results']]
    graph=build(records,full=True,limit=5000)
    companies=[row for row in graph['entities'] if row['type']=='organization']
    assert len(companies)==2 and len({row['id'] for row in companies})==2
    assert all(row['verification_status']=='source_reported' and row['attributes']['identity_match_verified'] is False for row in companies)
    assert sum(row['type']=='company_registration' for row in graph['entities'])==2
    assert sum(row['relation_type']=='source_reports_registration' for row in graph['relations'])==2
