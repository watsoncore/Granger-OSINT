from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import pytest

from grangerpet.agent_journal import InvestigationJournal
from grangerpet.agent_evidence import normalize_evidence
from grangerpet.research_canvas import CanvasStore, new_document, apply, merge_evidence, validate


def store(tmp_path):return CanvasStore(InvestigationJournal(tmp_path/'investigations'))


def finding():
    return normalize_evidence({'id':'fixture-profile','type':'profile','platform':'github','title':'octocat',
        'url':'https://github.com/octocat','status':'source_reported','details':{'login':'octocat'}},'github_profile','octocat')


def test_atomic_reopen_preserves_position_notes_and_encryption(tmp_path):
    s=store(tmp_path);doc=s.save(new_document('Русское расследование'),0)
    doc=apply(doc,'node',{'type':'infrastructure_asset','label':'66.249.67.41','position':{'x':123,'y':-51,'pinned':True}})
    identifier=doc['entities'][0]['id']
    doc=apply(doc,'annotate',{'entity_id':identifier,'annotation':{'markdown':'**Личная заметка**'}})
    saved=s.save(doc,1);reopened=store(tmp_path).load(doc['id'])
    assert reopened['view']['positions'][identifier]=={'x':123,'y':-51,'pinned':True}
    assert reopened['annotations'][identifier]['markdown']=='**Личная заметка**'
    assert reopened['revision']==2
    assert b'66.249.67.41' not in (s._folder(doc['id'])/'r0000000002.dpapi').read_bytes()
    assert s.list()[0]['title']=='Русское расследование'


def test_stale_writer_cannot_overwrite_and_original_revisions_remain(tmp_path):
    s=store(tmp_path);first=s.save(new_document(),0)
    second=s.save(apply(first,'rename',{'title':'Новое имя'}),1)
    with pytest.raises(ValueError,match='Конфликт'):store(tmp_path).save(first,1)
    assert s.load(first['id'])['title']=='Новое имя'
    assert len(list(s._folder(first['id']).glob('r*.dpapi')))==2


def test_competing_store_instances_only_one_revision_wins(tmp_path):
    s=store(tmp_path);value=s.save(new_document(),0)
    def save(label):
        try:return store(tmp_path).save(apply(value,'rename',{'title':label}),1)['revision']
        except ValueError:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,['a','b']))
    assert sorted(str(v) for v in results)==['2','conflict']


def test_corrupt_latest_recovers_previous_without_overwriting_any_bytes(tmp_path):
    s=store(tmp_path);first=s.save(new_document('До сбоя'),0);second=s.save(apply(first,'rename',{'title':'После'}),1)
    damaged=s._folder(first['id'])/'r0000000002.dpapi';damaged.write_bytes(b'corrupt ciphertext')
    restored=s.load(first['id']);assert restored['title']=='До сбоя' and restored['recovered_revision']
    next_value=s.save(restored,1);assert next_value['revision']==3
    assert damaged.read_bytes()==b'corrupt ciphertext'


def test_source_import_is_deduplicated_and_retains_annotations_and_position():
    doc=new_document();records=[finding()];merge_evidence(doc,records)
    node=next(n for n in doc['entities'] if n['type']=='public_profile');identifier=node['id']
    doc=apply(doc,'annotate',{'entity_id':identifier,'annotation':{'markdown':'Не считать личностью'}})
    doc=apply(doc,'positions',{'positions':{identifier:{'x':900,'y':200,'pinned':True}}})
    counts=(len(doc['entities']),len(doc['relations']),len(doc['evidence']))
    merge_evidence(doc,records);validate(doc)
    assert counts==(len(doc['entities']),len(doc['relations']),len(doc['evidence']))
    assert doc['annotations'][identifier]['markdown']=='Не считать личностью'
    assert doc['view']['positions'][identifier]['x']==900
    assert all(e['evidence_ids'] and e.get('provenance') for e in doc['relations'])


def test_hiding_removing_and_deleting_have_distinct_semantics():
    doc=new_document();merge_evidence(doc,[finding()]);identifier=doc['entities'][0]['id'];before=deepcopy(doc['evidence'])
    hidden=apply(doc,'hide',{'ids':[identifier]});assert identifier in hidden['view']['hidden'] and hidden['entities']==doc['entities']
    removed=apply(doc,'remove',{'ids':[identifier]});assert identifier in removed['view']['removed'] and removed['evidence']==before
    deleted=apply(doc,'delete_entity',{'ids':[identifier]});assert identifier not in {n['id'] for n in deleted['entities']} and deleted['evidence']==before


def test_explicit_refresh_retains_original_proof_and_projects_latest_observation():
    from grangerpet.agent_evidence import current_observation
    first=finding();second=deepcopy(first)
    second['details']['login']='updated-login'
    second['provenance']['obtained_at']='2026-11-05T00:00:00+00:00'
    doc=new_document();merge_evidence(doc,[first]);merge_evidence(doc,[second])
    assert len(doc['evidence'])==1
    saved=doc['evidence'][0]
    assert saved['details']==first['details']
    assert current_observation(saved)['details']['login']=='updated-login'
    assert saved['observations'][0]['details']==first['details']
    count=len(saved['observations']);merge_evidence(doc,[second])
    assert len(doc['evidence'][0]['observations'])==count
    validate(doc)


def test_unrelated_import_updates_aggregates_without_resurrecting_deleted_membership():
    first=finding();doc=new_document();merge_evidence(doc,[first])
    deleted=next(n['id'] for n in doc['entities'] if n['type']=='public_profile')
    doc=apply(doc,'delete_entity',{'ids':[deleted]})
    second=normalize_evidence({'id':'other-profile','type':'profile','platform':'github','title':'other',
        'url':'https://github.com/other','details':{'login':'other'},'status':'source_reported'},'github_profile','other')
    merge_evidence(doc,[second]);validate(doc)
    assert len(doc['evidence'])==2 and deleted not in {n['id'] for n in doc['entities']}


def test_manual_claim_cannot_be_promoted_to_verified_or_rewrite_source_relation():
    doc=apply(new_document(),'node',{'type':'person','label':'Утверждение аналитика'})
    doc=apply(doc,'node',{'type':'hypothesis','label':'Гипотеза'});a,b=[n['id'] for n in doc['entities']]
    with pytest.raises(ValueError,match='доказанным'):apply(doc,'edge',{'from_id':a,'to_id':b,'status':'verified'})
    doc=apply(doc,'edge',{'from_id':a,'to_id':b,'relation_type':'potentially_related','status':'inferred'})
    assert doc['relations'][0]['evidence_ids']==[] and doc['relations'][0]['origin']=='analyst'


def test_nested_groups_reject_cycles_and_broken_evidence():
    doc=apply(new_document(),'node',{'type':'entity_group','label':'A'})
    doc=apply(doc,'group',{'ids':[doc['entities'][0]['id']],'label':'B'})
    a,b=doc['entities'];b['attributes']['parent_group_id']=a['id']
    with pytest.raises(ValueError,match='групп'):validate(doc)
    doc=new_document();merge_evidence(doc,[finding()]);doc['evidence']=[]
    with pytest.raises(ValueError,match='доказательств'):validate(doc)


def test_json_export_roundtrip_keeps_common_ids_and_evidence(tmp_path):
    doc=new_document('Формат');merge_evidence(doc,[finding()]);validate(json.loads(json.dumps(doc)))
    restored=validate(json.loads(json.dumps(doc)))
    assert restored['entities']==doc['entities'] and restored['evidence']==doc['evidence']


def test_copy_creates_visual_instance_without_new_entity_or_source_fact():
    doc=new_document();merge_evidence(doc,[finding()]);original=doc['entities'][0]['id']
    nodes=deepcopy(doc['entities']);evidence=deepcopy(doc['evidence'])
    copied=apply(doc,'duplicate_nodes',{'ids':[original]})
    assert copied['entities']==nodes and copied['evidence']==evidence
    assert len(copied['view']['instances'])==1
    identifier,instance=next(iter(copied['view']['instances'].items()))
    assert instance['entity_id']==original and identifier!=original
    moved=apply(copied,'positions',{'positions':{identifier:{'x':91,'y':12,'pinned':True}}})
    assert moved['view']['instances'][identifier]['position']['x']==91
    assert moved['view']['positions'][original]==doc['view']['positions'][original]


def test_manual_layout_restores_original_positions_after_automatic_layout():
    doc=apply(new_document(),'node',{'type':'domain','label':'example.org','position':{'x':10,'y':40}})
    identifier=doc['entities'][0]['id']
    arranged=apply(doc,'layout',{'mode':'types','positions':{identifier:{'x':300,'y':200}}})
    restored=apply(arranged,'layout',{'mode':'manual','positions':{}})
    assert restored['view']['positions'][identifier]=={'x':10,'y':40}


def test_group_move_translates_collapsed_nested_and_visual_members_once():
    doc=apply(new_document(),'node',{'type':'person','label':'Member','position':{'x':10,'y':20}})
    member=doc['entities'][0]['id'];doc=apply(doc,'duplicate_nodes',{'ids':[member]});instance=next(iter(doc['view']['instances']))
    doc=apply(doc,'group',{'ids':[member,instance],'label':'Inner'});inner=doc['entities'][-1]['id']
    doc=apply(doc,'group',{'ids':[inner],'label':'Outer'});outer=doc['entities'][-1]['id'];doc['view']['collapsed']=[outer]
    before=deepcopy(doc);p=doc['view']['positions'][outer]
    moved=apply(doc,'positions',{'positions':{outer:{'x':p['x']+40,'y':p['y']-15}}})
    for identifier in (member,inner,outer):
        assert moved['view']['positions'][identifier]['x']==before['view']['positions'][identifier]['x']+40
        assert moved['view']['positions'][identifier]['y']==before['view']['positions'][identifier]['y']-15
    assert moved['view']['instances'][instance]['position']['x']==before['view']['instances'][instance]['position']['x']+40
    explicit=apply(doc,'positions',{'positions':{outer:{'x':p['x']+40,'y':p['y']-15},member:{'x':999,'y':888}}})
    assert explicit['view']['positions'][member]=={'x':999,'y':888}


def test_visual_membership_rejects_cycles_and_detaches_when_parent_deleted():
    doc=apply(new_document(),'node',{'type':'person','label':'Member'})
    member=doc['entities'][0]['id'];doc=apply(doc,'duplicate_nodes',{'ids':[member]});instance=next(iter(doc['view']['instances']))
    doc=apply(doc,'group',{'ids':[instance],'label':'Parent'});parent=doc['entities'][-1]['id']
    bad=deepcopy(doc);bad['view']['instances'][instance]['parent_group_id']=instance
    with pytest.raises(ValueError,match='групп'):validate(bad)
    removed=apply(doc,'delete_entity',{'ids':[parent]})
    assert not removed['view']['instances'][instance].get('parent_group_id')
