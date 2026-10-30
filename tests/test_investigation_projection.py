from copy import deepcopy
import hashlib
import json
import threading
import pytest
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.investigation_results import project, relevance
from grangerpet.evidence_graph import build
from grangerpet.graph_store import GraphViewStore
from grangerpet.agent_journal import InvestigationJournal
from grangerpet.investigation_workspace import InvestigationWorkspace


def evidence(kind,url,details,*,query='fixture',title='Synthetic observation',number='one'):
    return normalize_evidence({'id':number,'title':title,'type':kind,'platform':'Fixture','url':url,
        'description':'Synthetic test content','details':details,'status':'content_observed'},'fixture',query)


def test_telegram_actual_link_is_verified_but_unrelated_search_stays_background():
    url='https://t.me/s/fixture_project'
    page=evidence('community',url,{'username':'fixture_project','canonical_url':'https://t.me/fixture_project',
        'object_type_verified':True,'entity_type':'telegram_channel','reading_method':'direct_http','body_sha256':'a'*64,
        'links':[{'url':'https://github.com/public-fixture/project','content_region':'post_content',
            'extraction_method':'public_post_parser','selector':'.tgme_widget_message_text a[href]'}]})
    repo=evidence('repository','https://github.com/public-fixture/project',{'full_name':'public-fixture/project','acquisition':'official_api'},number='repo')
    noise=evidence('publication','https://news.ycombinator.com/item?id=123',{},title='An unrelated real estate article',number='noise')
    snapshot={'id':'a'*32,'status':'completed','goal':'Исследуй https://t.me/fixture_project','tool_calls':3,'evidence':[page,repo,noise],'executions':[]}
    value=project(snapshot)
    assert value['relevance'][page['evidence_id']]['level']=='direct'
    assert value['relevance'][repo['evidence_id']]['level']=='linked'
    assert value['relevance'][noise['evidence_id']]['level']=='background'
    link=next(r for r in value['relations'] if r['relation_type']=='publishes_link')
    assert link['verification_status']=='verified' and link['evidence_ids']==[page['evidence_id']]
    assert link['attributes']['identity_inference'] is False
    assert value['counts']['background']==1 and len(value['summary']['findings'])==2
    assert value['root_id'] in {n['id'] for n in value['entities']}


def test_transfer_aggregation_deduplicates_events_keeps_direction_assets_and_exact_decimal():
    first='0:'+'0'*64;second='0:'+'1'*64
    def tx(identifier,amount,asset='TON',query='fixture'):
        return evidence('transaction','https://tonviewer.com/transaction/'+identifier,
            {'chain':'ton','tx_hash':identifier,'from_address':first,'to_address':second,'amount_decimal':amount,'asset':asset},number=identifier,query=query)
    rows=[tx('hash1','1.2'),tx('hash2','0.3'),tx('hash1','1.2',query='second-acquisition'),tx('hash3',None,'OTHER')]
    graph=build(rows,limit=5000,full=True,goal=first)
    transfers=[r for r in graph['relations'] if r['relation_type']=='transfers']
    assert len(transfers)==2
    ton=next(r for r in transfers if r['aggregate']['asset']=='TON')
    assert ton['aggregate']['count']==2 and ton['aggregate']['amount']=='1.5'
    assert len(ton['aggregate']['transaction_ids'])==2
    nodes={node['id']:node for node in graph['entities']}
    assert nodes[ton['from_id']]['attributes']['address']==first
    assert nodes[ton['to_id']]['attributes']['address']==second
    unknown=next(r for r in transfers if r['aggregate']['asset']=='OTHER')
    assert unknown['aggregate']['amount'] is None and unknown['aggregate']['unknown_amount_count']==1
    assert all(node['attributes']['owner_verified'] is False for node in nodes.values() if node['type']=='blockchain_address')


def test_duplicate_acquisitions_are_one_resource_without_deleting_provenance():
    one=evidence('web','https://example.org/page',{},query='one')
    two=evidence('web','https://example.org/page',{},query='two')
    original=deepcopy([one,two])
    value=project({'id':'b'*32,'goal':'https://example.org/page','evidence':[one,two],'tool_calls':2,'executions':[]})
    assert value['counts']['raw_records']==2 and value['counts']['unique_evidence']==1
    assert value['counts']['unique_documents']==1 and value['counts']['tool_calls']==2
    assert value['evidence'][0]['related_evidence_ids']==[one['evidence_id'],two['evidence_id']]
    assert [one,two]==original


def test_nested_old_truncation_marker_cannot_crash_graph_or_become_gps():
    row=evidence('image_analysis','',{'attachment_id':'img_'+'a'*64,'metadata':{},'image':{}},number='image')
    row['details'].update(metadata='[ограничено]',image='[ограничено]',predictions=['[ограничено]'])
    graph=build([row],limit=5000,full=True,goal='img_'+'a'*64)
    assert any(n['type']=='image' for n in graph['entities'])
    assert not any(n['type'] in ('coordinate','geographic_candidate') for n in graph['entities'])


def test_graph_has_stable_relation_ids_and_bounded_full_projection():
    rows=[evidence('profile','https://example.org/u'+str(i),{'username':'u'+str(i)},number=str(i)) for i in range(1000)]
    value=build(rows,limit=5000,full=True,goal='https://example.org/u0')
    assert len(value['entities'])>=1000 and len(value['relations'])>=1000
    assert len(value['entities'])<=5000 and len(value['relations'])<=20000
    assert len({r['id']for r in value['relations']})==len(value['relations'])
    assert all(r['from_id'] in {n['id']for n in value['entities']} and r['to_id'] in {n['id']for n in value['entities']} for r in value['relations'])
    stopped=threading.Event();stopped.set()
    with pytest.raises(InterruptedError):project({'evidence':rows},cancel_event=stopped)


def test_encrypted_view_positions_selection_and_active_id_survive_restart(tmp_path):
    identifier='c'*32
    store=GraphViewStore(InvestigationJournal(tmp_path))
    view={'version':1,'mode':'graph','positions':{'ent_'+'a'*24:{'x':15,'y':-4,'pinned':True}},
        'viewport':{'x':3,'y':4,'scale':1.5},'selected_id':'ent_'+'a'*24,'query':'Личная строка фильтра'}
    store.save(identifier,view);store.select(identifier)
    assert 'Личная строка фильтра'.encode() not in (tmp_path/(identifier+'.graph.dpapi')).read_bytes()
    reopened=GraphViewStore(InvestigationJournal(tmp_path))
    assert reopened.load(identifier)==view and reopened.active()==identifier


def test_unknown_view_format_is_backed_up_as_identical_ciphertext_before_replacement(tmp_path):
    from grangerpet.credentials import CredentialsStore
    identifier='d'*32;store=GraphViewStore(InvestigationJournal(tmp_path))
    original=CredentialsStore._protect(b'{"version":99,"private":"old"}')
    path=tmp_path/(identifier+'.graph.dpapi');path.write_bytes(original)
    store.save(identifier,{'version':1,'mode':'graph'})
    backup=path.with_name(path.name+'.recovery-backup')
    assert backup.read_bytes()==original
    assert json.loads(CredentialsStore._protect(backup.read_bytes(),decrypt=True))['version']==99
    assert store.load(identifier)['version']==1


def test_manual_search_uses_same_protected_checkpoint_and_resume_cache(tmp_path):
    from test_agent_tools import registry
    reg,_=registry();row=evidence('web','https://example.org/',{})
    outcome={'tool':'web_search','query':'fixture','status':'complete','results':[row]}
    workspace=InvestigationWorkspace(InvestigationJournal(tmp_path))
    result=workspace.manual_result('fixture',outcome,{'query':'fixture'},reg,'f'*32)
    saved=workspace.journal.load_checkpoint(result['id'])
    assert saved['record']['goal'] and saved['record']['mode']=='manual'
    assert saved['evidence'] and saved['call_cache'] and saved['record']['status']=='paused'
    restored=InvestigationWorkspace(InvestigationJournal(tmp_path))
    assert restored.active_id==result['id'] and restored.manual['evidence']==result['evidence']
