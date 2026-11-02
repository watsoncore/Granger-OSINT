from grangerpet.agent_browser import PageParser
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.evidence_graph import build
from grangerpet.investigation_results import relevance


def page(details,url='https://github.com/solvnox'):
    return normalize_evidence({'id':url,'type':'web','title':'Public fixture','platform':'Fixture','url':url,
        'details':{'reading_method':'direct_http','body_sha256':'a'*64,**details}},'web_read',url)


def test_unscoped_css_like_marker_stays_in_evidence_without_a_service_claim():
    from copy import deepcopy
    from grangerpet.investigation_analysis import analyze
    address='0:'+'a'*64
    row=normalize_evidence({'id':'marker','type':'label','title':'Telegram marker: @media','platform':'TON',
        'details':{'chain':'ton','address':address,'target_address':address,'label':'Telegram marker: @media',
            'source':'tonscan_public','owner_verified':False}},'blockchain_gansar',address)
    original=deepcopy(row)
    assert relevance([row],address)[row['evidence_id']]['level']=='background'
    graph=build([row],full=True,limit=5000,goal=address)
    assert not any(n['type']=='service_claim' for n in graph['entities'])
    assert graph['technical_exclusions'][0]['evidence_id']==row['evidence_id']
    assert not analyze({'goal':address,'evidence':[row]})['assets']
    assert row==original
    actual=deepcopy(row);actual['url']='https://t.me/media'
    from grangerpet.link_relevance import unscoped_web_marker
    assert not unscoped_web_marker(actual)  # A real linked username is not rejected by its spelling.


def test_navigation_divs_and_footer_links_do_not_turn_into_author_claims():
    parser=PageParser('https://github.com/solvnox')
    parser.feed('''<div role="navigation"><a href="https://example.org/menu">Menu</a></div>
        <main><div class="markdown-body"><p>My project: <a href="https://t.me/public_fixture">Project</a></p></div>
        <div><a href="https://docs.github.com/en/site-policy/acceptable-use-policies/reporting-abuse-or-spam">Reporting abuse</a></div></main>
        <footer><a href="https://www.githubstatus.com/">Status</a></footer>
        <div><a href="https://example.net/unknown">Unclassified</a></div>''')
    data=parser.extracted();row=page(data)
    graph=build([row],full=True,limit=5000,goal=row['url'])
    claims=[edge for edge in graph['relations'] if edge['relation_type']=='publishes_link']
    assert len(claims)==1
    target=next(node for node in graph['entities'] if node['id']==claims[0]['to_id'])
    assert target['attributes']['url']=='https://t.me/public_fixture'
    assert len(data['navigation_links'])==3
    assert 'Menu' not in data['text']
    origin=claims[0]['provenance'][0]
    assert origin['source_record_id']==row['evidence_id'] and origin['source_url']==row['url']
    assert origin['extraction_method']=='inert_html_parser' and origin['observed_text_or_field']=='Project'
    assert {'subject','predicate','object','verification_status','observed_at'}<=origin.keys()
    current=next(node for node in graph['entities'] if node['id']==graph['root_id'])
    assert current['attributes']['navigation_metadata'] and current['attributes']['unclassified_links']


def test_page_hash_alone_cannot_upgrade_a_legacy_unknown_anchor():
    row=page({'links':[{'url':'https://example.org/legacy','text':'Link'}]})
    graph=build([row],full=True,limit=5000,goal=row['url'])
    assert not any(edge['relation_type']=='publishes_link' for edge in graph['relations'])
    linked=page({},'https://example.org/legacy')
    assert relevance([row,linked],row['url'])[linked['evidence_id']]['level']=='background'


def test_large_collections_keep_all_members_in_reversible_presentation_groups():
    rows=[page({},f'https://example.org/{index}') for index in range(100)]
    graph=build(rows,full=True,limit=5000,goal='https://example.org/0')
    group=next(node for node in graph['entities'] if node['type']=='entity_group')
    assert group['attributes']['member_count']==99
    assert graph['root_id'] not in group['attributes']['member_ids']
    assert all(any(node['id']==member for node in graph['entities']) for member in group['attributes']['member_ids'])
    assert all(edge['attributes']['grouping_only'] for edge in graph['relations'] if edge['relation_type']=='group_contains')


def test_geoint_graph_binds_original_candidate_and_actual_reference_without_media_aliasing():
    attachment='img_'+'a'*64
    def row(kind,key,details,url=''):
        return normalize_evidence({'id':key,'type':kind,'title':key,'platform':'Fixture','url':url,'details':{'attachment_id':attachment,**details}},'geoint_research',attachment)
    rows=[row('image_analysis','scene',{'tool':'image_understand','description':'Fixture scene'}),
        row('geoint_candidate','candidate',{'candidate_id':'geo_a','latitude':55.7,'longitude':37.6,'region':'Fixture place','verification_status':'geographically_plausible'}),
        row('reference_image','reference',{'candidate_id':'geo_a','image_url':'https://example.org/actual.jpg','latitude':55.71,'longitude':37.61,'comparison':{'status':'complete','match_count':4}},'https://example.org/archive')]
    graph=build(rows,full=True,limit=5000,goal='Где снята выбранная фотография?')
    original=next(node for node in graph['entities'] if node['attributes'].get('original_image'))
    assert graph['root_id']==original['id'] and 'media' not in original['attributes']
    assert len([node for node in graph['entities'] if node['type']=='geographic_candidate'])==1
    assert {'has_geographic_hypothesis','reference_for_candidate','locally_compared_with'}<={edge['relation_type'] for edge in graph['relations']}
    assert all(edge['verification_status']!='verified' for edge in graph['relations'] if edge['relation_type'] in ('reference_for_candidate','locally_compared_with'))


def test_telegram_post_is_a_publication_and_never_another_profile():
    row=normalize_evidence({'id':'post','type':'post','title':'Post','platform':'Telegram','url':'https://t.me/public_fixture/123','details':{}},'telegram_public','public_fixture')
    graph=build([row],full=True,limit=5000,goal=row['url'])
    assert any(node['type']=='public_post' for node in graph['entities'])
    assert not any(node['type']=='public_profile' for node in graph['entities'])


def test_layout_migration_preserves_original_protected_positions_and_refuses_corrupt_ciphertext(tmp_path):
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.graph_store import GraphViewStore
    views=GraphViewStore(InvestigationJournal(tmp_path));identifier='a'*32
    original={'version':1,'mode':'graph','positions':{'ent_'+'b'*24:{'x':10,'y':20,'pinned':True}}}
    views.save(identifier,original);raw=views._path(identifier).read_bytes()
    views.save(identifier,{**original,'layout_algorithm':'semantic_cards','inspector_width':420})
    assert (tmp_path/(identifier+'.graph.dpapi.layout-v1-backup')).read_bytes()==raw
    assert views.load(identifier)['positions']==original['positions']
    second='c'*32
    views._path(second).write_bytes(b'broken but preserved bytes')
    import pytest
    # A corrupt DPAPI envelope fails explicitly; do not erase bytes to force migration.
    with pytest.raises(Exception):views.save(second,{**original,'layout_algorithm':'semantic_cards'})
    assert views._path(second).read_bytes()==b'broken but preserved bytes'


def test_network_topic_groups_retain_relevance_and_preserve_primary_evidence():
    from grangerpet.investigation_results import project
    address='66.249.67.41'
    row=normalize_evidence({'id':'geo','type':'ip','platform':'ipwhois','title':'GeoIP',
        'url':'https://ipwho.is/'+address,'details':{'address':address,'geoip':{'provider':'ipwhois','country_name':'United States'}}},'network_geoip',address)
    data=project({'id':'a'*32,'goal':'Исследуй IP '+address,'evidence':[row]})
    groups=[node for node in data['entities'] if node['attributes'].get('topic_group')]
    assert groups and all(node['relevance']['level']!='background' for node in groups)
    assert all(node['evidence_ids']==[row['evidence_id']] for node in groups)
    assert data['counts']['unique_evidence']==1


def test_v2_layout_preserves_previous_sidecar_bytes(tmp_path):
    from grangerpet.agent_journal import InvestigationJournal
    from grangerpet.graph_store import GraphViewStore
    views=GraphViewStore(InvestigationJournal(tmp_path));identifier='b'*32
    before={'version':1,'layout_algorithm':'semantic_cards','mode':'tree','tree_positions':{'ent_'+'a'*24:{'x':10,'y':20}}}
    views.save(identifier,before);original=views._path(identifier).read_bytes()
    views.save(identifier,{**before,'layout_algorithm':'semantic_network_v2','tree_positions':{}})
    assert views._path(identifier).with_name(identifier+'.graph.dpapi.layout-v2-backup').read_bytes()==original
