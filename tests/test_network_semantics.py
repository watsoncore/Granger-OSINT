"""Network role/scope/GeoIP transport fixtures, not real geolocation claims."""
import httpx
import pytest
from grangerpet.network_semantics import registration_match,registry_entity_type
from grangerpet.network_report import profiles,markdown
from grangerpet.geoip_sources import parse
from test_network_research import Fixture


def test_parent_rdap_range_is_not_relabelled_as_requested_prefix():
    fields={'startAddress':'31.0.0.0','endAddress':'31.255.255.255'}
    match=registration_match('31.1.0.0/16',fields)
    assert match['match_type']=='matched_parent' and match['returned_prefixes']==['31.0.0.0/8']
    assert match['covers_entire_requested_range'] and not match['requested_prefix_is_returned_object']


def test_legacy_maintainer_and_rir_names_are_not_organizations_and_new_cards_deduplicate_fn_org():
    from grangerpet.network_sources import _rdap_fields
    assert registry_entity_type({'name':'MNT-PS','roles':['registrant']})=='maintainer'
    assert registry_entity_type({'name':'ORG-NCC1-RIPE','roles':['registrant']})=='registry_authority'
    fields=_rdap_fields({'objectClassName':'ip network','entities':[{'handle':'MNT-PS','roles':['registrant'],
        'vcardArray':['vcard',[['fn',{},'text','MNT-PS'],['org',{},'text','Synthetic Company']]]}]})
    assert len(fields['registry_entities'])==1 and fields['registry_entities'][0]['entity_type']=='maintainer'
    fields=_rdap_fields({'objectClassName':'ip network','entities':[{'handle':'ORG-FIXTURE-RIPE','roles':['registrant'],
        'vcardArray':['vcard',[['fn',{},'text','Synthetic Company'],['kind',{},'text','org']]]}]})
    assert fields['registry_entities'][0]['entity_type']=='organization'


def test_bgp_facts_merge_source_links_while_different_values_stay_separate():
    records=[{'type':'ip','url':'https://source.example/'+str(index),'details':{'address':'66.249.67.41','prefix':prefix}}
             for index,prefix in enumerate(('66.249.64.0/19','66.249.64.0/19','66.249.0.0/16'))]
    view=profiles(records)[0];facts=[fact for fact in view['facts'] if fact['label']=='BGP-префикс']
    assert len(facts)==2 and len(facts[0]['sources'])==2
    report=markdown([view]);assert 'https://source.example/0' in report and 'https://source.example/1' in report


@pytest.mark.parametrize('source,data',[
    ('ipwhois',{'ip':'66.249.67.41','success':True,'country':'United States','city':'Synthetic city','latitude':37.4,'longitude':-122.1}),
    ('ipapi_is',{'ip':'66.249.67.41','country':'United States','city':'Synthetic city','lat':37.4,'lon':-122.1})])
def test_geoip_preserves_unknown_accuracy_and_is_not_registration_or_person_position(source,data):
    result=parse(source,'66.249.67.41',data)
    assert result['city']=='Synthetic city' and result['accuracy_radius_km'] is None
    assert result['exact_device_location_verified'] is False and result['database_updated_at'] is None


@pytest.mark.parametrize('data',['invalid',None,[],{'ip':'8.8.8.8','success':True,'country':'US'}])
def test_geoip_schema_and_target_mismatch_cannot_be_success(data):
    with pytest.raises(ValueError):parse('ipwhois','66.249.67.41',data)


def test_independent_geoip_failure_keeps_other_source_and_does_not_set_registration_country():
    def handler(request):
        if request.url.host=='api.ipapi.is':return httpx.Response(429,json={'error_code':'ERR_FREE_TIER_EXHAUSTED'},headers={'Retry-After':'3600'})
        return httpx.Response(200,json={'ip':'66.249.67.41','success':True,'country':'United States','city':'Fixture city','latitude':37.4,'longitude':-122.1})
    result=Fixture(handler).execute('network_geoip','66.249.67.41')
    assert result['status']=='partial' and len(result['results'])==1
    assert 'country' not in result['results'][0]['details']
    report=markdown(profiles(result['results']))
    assert 'GeoIP · Страна' in report and 'Страна регистрации' not in report


def test_parent_prefix_and_registry_roles_reach_semantic_graph():
    from grangerpet.agent_evidence import normalize_evidence
    from grangerpet.evidence_graph import build
    record=normalize_evidence({'id':'parent','type':'ip','platform':'rdap_registry','title':'RDAP fixture',
        'url':'https://registry.example/ip/31.1.0.0/16','details':{'address':'31.1.0.0/16','startAddress':'31.0.0.0','endAddress':'31.255.255.255',
            'registry_entities':[{'name':'MNT-PS','roles':['registrant']},{'name':'ORG-NCC1-RIPE','roles':['registrant']}] }},'network_rdap','31.1.0.0/16')
    graph=build([record],full=True,limit=5000,goal='31.1.0.0/16')
    assert any(node['label']=='31.0.0.0/8 · реестровый родитель' for node in graph['entities'])
    assert any(edge['relation_type']=='matched_parent_registration' for edge in graph['relations'])
    assert not any(node['type']=='organization' for node in graph['entities'])


def test_short_scoped_location_starts_geoip_instead_of_plain_lookup():
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.config import Settings
    registry=ToolRegistry(Settings(),secret_getter=lambda _: '')
    calls=registry.initial_calls('Какая локация? Объект текущего запроса: 87.199.131.94')
    assert calls[0]['name']=='network_geoip'
